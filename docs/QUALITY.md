# Quality

This document is the v0.4.0 reference for the quality eval
layer: the golden set, the metrics, the per-field isotonic
confidence calibration, the LLM-as-judge (G-Eval) pass, and
the prompt + schema versioning.

## What's in v0.4.0

The v0.4.0 quality stack is:

- A **golden set** of CORD receipts (Commit 1) for reproducible
  evaluation.
- A **metrics module** (Commit 1) with the standard
  2025-2026 metric set for document extraction.
- A **per-field isotonic calibrator** (Commit 2) that maps
  the LLM's raw confidence to a calibrated probability.
- A **self-refine reflection loop** (Commit 3) that re-invokes
  the LLM with explicit validation feedback when the first
  pass fails.
- A **G-Eval LLM-as-judge** (Commit 6) that scores a sampled
  fraction of completed extractions on four criteria.
- A **versioned prompt** system (Commit 7) that lets you
  A/B-test prompt changes with a one-line `git diff`.

## The metrics

Implemented in `backend/app/services/eval/metrics.py`:

- **`field_f1`** — micro-averaged F1 across all (field, sample)
  pairs. The standard for CORD / FUNSD.
- **`schema_conformance_rate`** — fraction of predictions that
  validate against the schema with all required fields.
- **`anls`** — Average Normalized Levenshtein Similarity
  (Biten et al. 2019) for free-text Q&A.
- **`ece`** — Expected Calibration Error. Lower is better; 0.05
  is the production target.
- **`brier`** — Mean squared error between predicted prob and
  outcome. Lower is better.
- **`auroc`** — area under the ROC curve for the auto-accept
  vs. needs-review routing. Higher is better.
- **`coverage_at_target_accuracy`** — the production-realistic
  selective-prediction metric. Returns `(max_coverage,
  threshold)` such that accepting only predictions above the
  threshold achieves at least the target accuracy. Higher
  coverage is better at the same target.
- **`reliability_diagram_text` / `render_reliability_diagram`**
  — text or PNG reliability diagrams for log output and the
  eval report.
- **`build_report` / `EvalReport`** — the aggregate
  per-pass report. `EvalReport.to_dict()` produces the JSON
  shape that the eval runner writes to `eval/runs/`.

## Per-field calibration

LLM self-reported confidence is not well-calibrated out of the
box. The calibrator (`backend/app/services/eval/calibration.py`)
fits an isotonic regression per field on the golden set, then
applies the mapping to live predictions.

- **Algorithm**: PAVA (Pool-Adjacent-Violators). O(n), monotone
  non-decreasing, weighted. Same algorithm as
  `sklearn.isotonic.IsotonicRegression`, stdlib-only.
- **Storage**: JSON artifact (not pickle) at the path set in
  `Settings.confidence_calibration_path` (default
  `./calibration.json`). Git-diffable, safe to commit, schema-
  versioned for forward migration.
- **Fit**: `just eval-fit-calibrator` reads `eval/runs/`, fits
  the calibrator, writes the artifact.
- **Apply**: at extraction time, the calibrator is loaded once
  and applied per-field to the LLM's confidence map. Fields
  with no per-field map fall back to the global default.

## Reflection loop

When validation fails, the `reflect` node (graph Commit 3)
re-invokes the LLM with a reflection prompt that includes
the previous output, the validation errors, and the attempt
number. Up to `Settings.max_reflection_attempts` times
(default 2; set to 0 to disable).

Empirically one reflection pass improves field F1 by 4-9
points on receipts and invoices (Self-Refine, Madaan et al.
2023).

## G-Eval judge

A sampled fraction of completed extractions is scored by a
small local Ollama model (default `qwen3.5:4b`) on four
criteria:

- **correctness** — extracted values match ground truth.
- **completeness** — all required fields are present.
- **schema_conformance** — the JSON is well-formed and matches
  the schema.
- **fluency** — text values are natural and well-formatted.

Each criterion is scored 1-5 with a one-sentence reason; the
overall score is the unweighted mean. Results are persisted
to the new `extraction_judgments` table; below-threshold
judgments (default < 3.5) are flagged in the audit log.

Configuration (in `Settings`):

- `judge_enabled: bool = True` — set False to skip entirely.
- `judge_sample_rate: float = 0.05` — fraction of completed
  extractions to judge.
- `judge_ollama_model: str = "qwen3.5:4b"`.
- `judge_ollama_base_url: str = ""` — falls back to
  `Settings.ollama_base_url`.
- `judge_ollama_timeout_seconds: float = 60.0`.
- `judge_min_overall_score: float = 3.5` — below this is
  flagged.

## Prompt + schema versioning

Prompts live in `prompts/<version>/<name>.md` as Markdown with
YAML front-matter. The front-matter carries prompt metadata
(name, version, description, model_floor); the Markdown body
is the prompt template.

- **Loader**: `backend/app/services/llm/prompts_loader.py`.
  `load_prompt(name, version)` returns a `Prompt` object;
  `.render(**kwargs)` formats the body.
- **Schema versioning**: every `Extraction` row records the
  `prompt_version` (e.g. `v1`) and `schema_version` that
  produced it. New columns added by Alembic migration
  `0003_prompt_schema_version`.
- **A/B testing**: bump the prompt version (e.g. v1 → v2),
  run `just eval`, then `just eval-diff` to compare the new
  prompt's metrics against the previous run.
- **Front-matter strictness**: missing `---` delimiter raises
  `ValueError`. The example block uses `{{` / `}}` for
  literal braces (the `.format()` placeholder syntax).

## How to use the eval pipeline

1. Fetch the golden set: `just fetch-golden-set`. Writes
   `eval/golden_set/v1/manifest.json` and the receipts.
2. Run the eval: `just eval`. Writes a JSON report to
   `eval/runs/<timestamp>.json` and a PNG reliability diagram.
3. Fit a calibrator: `just eval-fit-calibrator`. Writes
   `./calibration.json`.
4. Compare runs: `just eval-diff`. Prints a markdown table of
   metric deltas; exits 1 on regression.

## Recommended targets

- **field_f1**: 0.85+ (CORD single-page receipts).
- **ece**: 0.05 or below (post-calibration).
- **auroc**: 0.90+ (good separation between correct and
  incorrect).
- **coverage_at_target_accuracy_0.95**: 0.90+ (auto-accept 90%
  of fields at 95% accuracy).
