from app.services.parsing.contracts import BoundingBox, PageLayout, RecognitionCandidate, Region
from app.services.parsing.diagnostics import build_page_diagnostics


def test_build_page_diagnostics_populates_quality_and_attempts() -> None:
    page = PageLayout(
        page_number=1,
        width=1,
        height=1,
        regions=[
            Region(
                id="p0001-r0001",
                type="table",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.8),
                content="| A | B |",
                source="docling",
            )
        ],
    )
    review = {
        "score": {
            "extraction_accuracy": 0.9,
            "structural_fidelity": 0.8,
            "completeness": 0.9,
            "markdown_consistency": 0.8,
            "overall": 0.85,
            "reasons": ["minor alignment issue"],
        },
        "regions": [
            {
                "region_id": "p0001-r0001",
                "verdict": "warn",
                "reason": "minor alignment issue",
                "repair_hint": "check column two",
                "risk_flags": ["alignment"],
            }
        ],
        "quality_status": "warn",
        "latency_ms": 14,
        "eval_count": 8,
        "prompt_eval_count": 12,
    }

    diagnostics = build_page_diagnostics(page, review, repair_count=1, warnings=[])

    assert diagnostics.quality_status == "warn"
    assert diagnostics.quality_score is not None
    assert diagnostics.region_decisions[0].plan.expert == "table"
    assert diagnostics.region_decisions[0].attempts[0].eval_count == 8
    assert diagnostics.region_decisions[0].attempts[0].repair_hint == "check column two"
    assert len(diagnostics.fingerprint) == 64


def test_build_page_diagnostics_has_deterministic_fallback_without_review() -> None:
    page = PageLayout(
        page_number=2,
        width=1,
        height=1,
        regions=[
            Region(
                id="p0002-r0001",
                type="text",
                bbox=BoundingBox(left=0, top=0, right=1, bottom=1),
                content="Readable text",
                source="native",
            )
        ],
    )

    diagnostics = build_page_diagnostics(page, None, repair_count=0, warnings=[])

    assert diagnostics.quality_status == "pass"
    assert diagnostics.region_decisions[0].plan.strategy == "native"
    assert diagnostics.quality_score is not None


def test_build_page_diagnostics_records_blinded_candidate_as_second_local_attempt() -> None:
    page = PageLayout(
        page_number=1,
        width=1,
        height=1,
        regions=[
            Region(
                id="p0001-r0001",
                type="text",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                content="second local read",
                source="glm_ocr",
                recognition_candidates=[
                    RecognitionCandidate(source="paddleocr_vl", content="paddle"),
                    RecognitionCandidate(
                        source="glm_ocr", content="first local read", model="glm-ocr"
                    ),
                    RecognitionCandidate(
                        source="glm_ocr",
                        content="second local read",
                        model="glm-ocr",
                        selected=True,
                    ),
                ],
            )
        ],
    )

    diagnostics = build_page_diagnostics(page, None, repair_count=1, warnings=[])
    decision = diagnostics.region_decisions[0]

    assert len(decision.attempts) == 3
    assert decision.selected_attempt_index == 2
    assert decision.attempts[2].prompt_variant == "blind_retry"
