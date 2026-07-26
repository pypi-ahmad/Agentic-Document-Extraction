from app.services.parsing.agentic_contracts import (
    AttemptRecord,
    PageDiagnostics,
    PagePlan,
    PlanningMode,
    ProcessingStage,
    QualityScore,
    QualityStatus,
    RegionDecision,
    RegionObservation,
    RegionPlan,
    VerificationMethod,
    VisualVerification,
)
from app.services.parsing.contracts import BoundingBox
from app.services.parsing.public_diagnostics import to_public_diagnostics

SECRETS = {
    "observation-content-attacker",
    "native-text-attacker",
    "page-rationale-attacker",
    "region-rationale-attacker",
    "attempt-output-attacker",
}


def sensitive_diagnostics() -> PageDiagnostics:
    score = QualityScore(
        extraction_accuracy=0.9,
        structural_fidelity=0.8,
        completeness=0.7,
        markdown_consistency=1.0,
        overall=0.85,
        reasons=["safe-score-reason"],
    )
    observation = RegionObservation(
        region_id="p1-r1",
        region_type="table",
        bbox=BoundingBox(left=0.1, top=0.2, right=0.8, bottom=0.9),
        content="observation-content-attacker",
        native_text="native-text-attacker",
        native_healthy=False,
        confidence=0.75,
        risk_flags=["low_contrast"],
    )
    plan = RegionPlan(
        region_id="p1-r1",
        strategy="specialist",
        expert="table",
        difficulty=0.8,
        rationale="region-rationale-attacker",
        risk_flags=["complex_structure"],
        prompt_variant="structure_repair",
    )
    attempt = AttemptRecord(
        attempt=1,
        strategy="specialist",
        expert="table",
        prompt_id="table-expert",
        prompt_version="1",
        prompt_variant="structure_repair",
        output="attempt-output-attacker",
        score=score,
        verdict="pass",
        reason="safe-verdict-reason",
        repair_hint="safe-repair-hint",
        warnings=["safe-warning"],
        latency_ms=12.5,
        eval_count=20,
        prompt_eval_count=10,
    )
    return PageDiagnostics(
        planning_mode=PlanningMode.PAGE_CENTRIC,
        stage=ProcessingStage.COMPLETED,
        page_number=1,
        plan=PagePlan(
            page_number=1,
            source="model",
            regions=[plan],
            rationale="page-rationale-attacker",
            warnings=["safe-plan-warning"],
        ),
        region_decisions=[
            RegionDecision(
                observation=observation,
                plan=plan,
                attempts=[attempt],
                selected_attempt_index=0,
                final_status=QualityStatus.PASS,
                visual_verification=VisualVerification(
                    region_id="p1-r1",
                    bbox=observation.bbox,
                    status=QualityStatus.PASS,
                    methods=[
                        VerificationMethod.LOCAL_COORDINATE,
                        VerificationMethod.CLOUD_VISUAL,
                    ],
                    reasons=["safe-coordinate-reason"],
                ),
            )
        ],
        quality_score=score,
        quality_status=QualityStatus.PASS,
        repair_count=1,
        warnings=["safe-page-warning"],
        fingerprint="safe-fingerprint",
    )


def test_public_diagnostics_is_an_explicit_allowlist() -> None:
    public = to_public_diagnostics(sensitive_diagnostics())
    encoded = public.model_dump_json()
    payload = public.model_dump(mode="json")

    assert not any(secret in encoded for secret in SECRETS)
    assert public.region_decisions[0].observation.region_type == "table"
    assert public.region_decisions[0].plan.strategy == "specialist"
    assert public.region_decisions[0].attempts[0].prompt_id == "table-expert"
    assert public.region_decisions[0].attempts[0].score.overall == 0.85
    assert public.region_decisions[0].attempts[0].reason == "safe-verdict-reason"
    assert public.region_decisions[0].visual_verification is not None
    assert public.region_decisions[0].visual_verification.status == "pass"
    assert public.plan is not None and public.plan.warnings == ["safe-plan-warning"]
    assert set(payload["region_decisions"][0]["observation"]) == {
        "region_id",
        "region_type",
        "bbox",
        "native_healthy",
        "confidence",
        "risk_flags",
    }
    assert set(payload["region_decisions"][0]["plan"]) == {
        "region_id",
        "strategy",
        "expert",
        "difficulty",
        "risk_flags",
        "prompt_variant",
    }
    assert set(payload["region_decisions"][0]["visual_verification"]) == {
        "region_id",
        "bbox",
        "status",
        "methods",
        "reasons",
    }
    assert set(payload["region_decisions"][0]["attempts"][0]) == {
        "attempt",
        "strategy",
        "expert",
        "prompt_id",
        "prompt_version",
        "prompt_variant",
        "source",
        "model",
        "score",
        "verdict",
        "reason",
        "repair_hint",
        "warnings",
        "latency_ms",
        "eval_count",
        "prompt_eval_count",
    }


def test_public_schema_never_defines_sensitive_fields() -> None:
    schema = to_public_diagnostics(sensitive_diagnostics()).model_json_schema()
    encoded = str(schema)

    assert "content" not in encoded
    assert "native_text" not in encoded
    assert "rationale" not in encoded
    assert "output" not in encoded
