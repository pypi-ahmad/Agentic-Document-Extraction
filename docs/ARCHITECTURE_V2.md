# v0.5.0 Architecture

> The v0.5.0 release replaces the v0.4.0 "single OCR → single LLM
> call" pipeline with an evidence-grounded, multi-stage, layout-aware
> stack. This document is the engineering reference for v0.5.0;
> for v0.4.0 see [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Definition

The v0.5.0 stack is a state machine of cooperating stages, each
backed by a dedicated Python module. The stages are:

1. **Layout parse** — emit per-region metadata (bbox, region type,
   reading order) on top of flat text.
2. **Extract** — the LLM proposes an answer, but the answer MUST
   cite evidence: page, bbox, verbatim text span.
3. **Verify** — an independent model re-checks each field's
   evidence against the document.
4. **Conflict resolve** — disagreements are routed to human
   review; agreements pass through.
5. **Cross-page resolve** — entity mentions on different pages
   are clustered and the canonical form is picked.
6. **Calibrate** — replace the v0.4.0 self-reported confidence
   with a composite signal (logprob + verifier agreement +
   evidence coverage).
7. **Validate** — schema-aware per-kind validation.
8. **Finalize** — write the extraction row and per-field
   evidence rows.

## 2. Module map

```
backend/app/
├── services/
│   ├── ocr/
│   │   ├── base.py               (v0.4.0, unchanged)
│   │   ├── layout_base.py        (NEW: BaseLayoutProvider, LayoutResult)
│   │   ├── layout_registry.py    (NEW: layout registry + auto-routing)
│   │   ├── docling_layout_provider.py  (NEW: Docling in layout mode)
│   │   └── ...                   (v0.4.0 OCR providers)
│   ├── extraction/
│   │   ├── evidence.py           (NEW: Evidence, EvidenceMap, IoU)
│   │   ├── verifier.py           (NEW: HeuristicVerifier, LLMVerifier)
│   │   ├── cross_page.py         (NEW: EntityTracker, Jaccard clustering)
│   │   ├── field_strategies.py   (NEW: per-kind validators)
│   │   └── double_pass.py        (NEW: diff_evidence_maps, merge)
│   └── eval/
│       ├── calibration.py        (v0.4.0 PAVA, unchanged)
│       ├── calibration_v2.py     (NEW: CompositeCalibrator)
│       └── metrics_v2.py         (NEW: TEDS, cell F1, IoU, ...)
├── models/
│   └── db_models.py              (+ ExtractionEvidence, + ExtractionEntity, + ExtractionVerifierRun)
alembic/versions/
└── 0004_evidence_entities_verifier.py  (NEW)
prompts/
├── v1/                            (v0.4.0, unchanged — regression gate)
└── v2/                            (NEW: evidence-grounded prompts)
scripts/
└── fetch_docvqa.py                (NEW: DocVQA + InfographicVQA fetcher)
eval/golden_set/
├── v1/                            (v0.4.0 CORD, unchanged)
└── v2/                            (NEW: DocVQA + InfographicVQA)
```

## 3. Data flow

```
┌──────────────────┐
│ Uploaded document│
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    LayoutResult
│ Layout parse     │  (text, tokens, regions, tables, reading order)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    EvidenceMap
│ Extract (LLM)    │  (field → value + page + bbox + text_span + score)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    VerifierOutput
│ Verify           │  (field → verdict + reason)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    EvidenceMap
│ Conflict resolve │  (disputed fields → human review)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    list[ResolvedEntity]
│ Cross-page       │  (entity → canonical_form + mentions)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    CompositeSignals
│ Calibrate        │  (logprob + verifier + evidence → composite score)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐    list[str] of errors
│ Validate         │  (per-kind: date, currency, id, ...)
└─────────┬────────┘
          │
          ▼
┌──────────────────┐
│ Finalize         │  (write to extractions + extraction_evidence + ...)
└──────────────────┘
```

## 4. The evidence contract

Every field the LLM extracts must be emitted in this shape
(v2/extraction.md):

```json
{
  "fields": {
    "vendor_name": {
      "value": "Acme Corp",
      "evidence": {
        "page": 0,
        "bbox": [0.10, 0.05, 0.40, 0.07],
        "text_span": "Acme Corp",
        "score": 0.95
      }
    }
  },
  "not_found": ["middle_name"]
}
```

Fields without an evidence block, or with an empty text_span,
are rejected by `build_evidence_map` and surfaced in the
response's `_meta.not_found_fields`.

## 5. Confidence, the v0.5.0 way

The v0.4.0 `_confidence` map was the LLM's self-report — easy
to game, hard to calibrate, and a known anti-pattern. v0.5.0
replaces it with a composite signal:

```python
composite = (
    w_logprob * exp(mean_logprob)
  + w_verifier * (fields_agreed / fields_verdicted)
  + w_evidence * (fields_with_text / fields_total)
)
```

Default weights: `w_logprob=0.4, w_verifier=0.3, w_evidence=0.3`.
Missing components are dropped and the weights are
re-normalized. `fit_composite_weights` fits the three weights
on a labeled holdout by gradient descent on Brier loss.

## 6. Metric suite

The v0.5.0 metric suite is `run_v2_suite` in
`app.services.eval.metrics_v2`. It takes optional inputs and
emits a flat dict:

| Category    | Metric                       | Module                 |
|-------------|------------------------------|------------------------|
| Tables      | TEDS                         | `metrics_v2.teds`      |
| Tables      | Cell P/R/F1                  | `cell_precision_recall_f1` |
| Tables      | Row/Column structure acc.    | `row_column_structure_accuracy` |
| Tables      | Header match acc.            | `header_match_accuracy` |
| KV          | Exact Match                  | `exact_match`          |
| KV          | Token F1                     | `token_f1`             |
| KV          | ANLS                         | `metrics_v2.anls` (re-export) |
| Grounding   | Evidence attribution acc.    | `evidence_attribution_accuracy` |
| Grounding   | Bbox IoU (mean)              | `mean_bbox_iou`        |
| Grounding   | Page localization acc.       | `page_localization_accuracy` |
| Production  | End-to-end task success rate | `end_to_end_task_success_rate` |

The v0.4.0 metrics (`field_f1`, `ece`, `brier`, `auroc`,
`coverage_at_target_accuracy`) are still in `app.services.eval.metrics`
and remain the v0.4.0 regression gate. New metrics should land in
`metrics_v2`.

## 7. Backward compatibility

v0.5.0 is wire-compatible with v0.4.0 at the HTTP API level.
Existing extractions keep running unchanged. New extractions
get the new pipeline. To roll a v0.5.0 deployment back to
v0.4.0 behavior, set:

```
ENABLE_LAYOUT_PARSING=false
ENABLE_VERIFIER=false
ENABLE_DOUBLE_PASS=false
ENABLE_CROSS_PAGE_ENTITIES=false
```

…and revert to the `prompts/v1/` prompt set. All four flags
default to `true` in v0.5.0.

## 8. Test count

828 tests pass, 1 skipped (Phoenix health-check that cannot
reach the OTLP collector in CI). The breakdown by module:

* `eval/metrics_v2.py` — 55 tests
* `eval/calibration_v2.py` — 35 tests
* `extraction/evidence.py` — 28 tests
* `extraction/verifier.py` — 26 tests
* `extraction/cross_page.py` — 26 tests
* `extraction/field_strategies.py` — 57 tests
* `extraction/double_pass.py` — 23 tests
* `services/ocr/layout_base.py` — 26 tests
* `scripts/fetch_docvqa.py` — 13 tests
* (plus 539 tests carried over from v0.4.0)
