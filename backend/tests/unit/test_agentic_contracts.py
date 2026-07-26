import pytest
from pydantic import ValidationError

from app.services.parsing.agentic_contracts import (
    AttemptRecord,
    DocumentContext,
    ExpertKind,
    PageDiagnostics,
    PageObservation,
    PagePlan,
    PlanningMode,
    ProcessingStage,
    ProcessingStrategy,
    QualityScore,
    QualityStatus,
    RegionDecision,
    RegionObservation,
    RegionPlan,
)
from app.services.parsing.contracts import BoundingBox


def _score() -> QualityScore:
    return QualityScore(
        extraction_accuracy=0.9,
        structural_fidelity=0.8,
        completeness=0.85,
        markdown_consistency=0.95,
        overall=0.875,
        reasons=["structure preserved"],
    )


def _observation() -> RegionObservation:
    return RegionObservation(
        region_id="p0001-r0001",
        region_type="table",
        bbox=BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.8),
        content="| A | B |",
        native_text="A B",
        native_healthy=False,
        confidence=0.8,
        risk_flags=["dense_table"],
    )


def _plan() -> RegionPlan:
    return RegionPlan(
        region_id="p0001-r0001",
        strategy=ProcessingStrategy.SPECIALIST,
        expert=ExpertKind.TABLE,
        difficulty=0.7,
        rationale="Dense table requires specialist extraction",
        risk_flags=["dense_table"],
    )


def test_agentic_enum_values_are_stable() -> None:
    assert PlanningMode.PAGE_CENTRIC == "page_centric"
    assert ProcessingStrategy.FALLBACK == "fallback"
    assert ExpertKind.CHART == "chart"
    assert QualityStatus.WARN == "warn"
    assert ProcessingStage.REPAIRING == "repairing"


def test_quality_score_rejects_out_of_range_dimension() -> None:
    with pytest.raises(ValidationError):
        QualityScore.model_validate({**_score().model_dump(), "overall": 1.1})


def test_quality_score_rejects_overall_that_is_not_dimension_mean() -> None:
    with pytest.raises(ValidationError, match="arithmetic mean"):
        QualityScore.model_validate({**_score().model_dump(), "overall": 0.5})


def test_document_context_has_isolated_collection_defaults() -> None:
    first = DocumentContext(page_count=2)
    second = DocumentContext(page_count=2)
    first.headings.append("Introduction")

    assert first.completed_pages == 0
    assert second.headings == []
    assert first.region_type_counts == {}
    assert first.repeated_marginalia == []


def test_document_context_rejects_more_completed_pages_than_total() -> None:
    with pytest.raises(ValidationError, match="completed_pages"):
        DocumentContext(page_count=2, completed_pages=3)


def test_document_context_rejects_negative_region_count() -> None:
    with pytest.raises(ValidationError):
        DocumentContext(page_count=2, region_type_counts={"table": -1})


def test_region_plan_defaults_to_primary_prompt_variant() -> None:
    assert _plan().prompt_variant == "primary"


def test_page_plan_rejects_duplicate_region_ids() -> None:
    with pytest.raises(ValidationError, match="region IDs"):
        PagePlan(
            page_number=1,
            source="model",
            regions=[_plan(), _plan()],
            rationale="duplicates are ambiguous",
        )


def test_page_observation_validates_dimensions_and_unique_region_ids() -> None:
    page = PageObservation(
        page_number=1,
        width=612,
        height=792,
        native_healthy=True,
        regions=[_observation()],
    )
    assert page.warnings == []

    with pytest.raises(ValidationError, match="region IDs"):
        PageObservation(
            page_number=1,
            width=612,
            height=792,
            native_healthy=True,
            regions=[_observation(), _observation()],
        )


def test_page_diagnostics_composes_agentic_contracts() -> None:
    plan = PagePlan(
        page_number=1,
        source="model",
        regions=[_plan()],
        rationale="Route difficult regions",
        warnings=[],
    )
    attempt = AttemptRecord(
        attempt=1,
        strategy=ProcessingStrategy.SPECIALIST,
        expert=ExpertKind.TABLE,
        prompt_version="v1",
        prompt_variant="primary",
        output="| A | B |",
        score=_score(),
        verdict=QualityStatus.PASS,
        reason="Meets threshold",
        latency_ms=125.5,
        eval_count=24,
        prompt_eval_count=40,
    )
    decision = RegionDecision(
        observation=_observation(),
        plan=_plan(),
        attempts=[attempt],
        selected_attempt_index=0,
        final_status=QualityStatus.PASS,
    )

    diagnostics = PageDiagnostics(
        planning_mode=PlanningMode.PAGE_CENTRIC,
        stage=ProcessingStage.COMPLETED,
        page_number=1,
        plan=plan,
        region_decisions=[decision],
        quality_score=_score(),
        quality_status=QualityStatus.PASS,
        fingerprint="sha256:abc",
    )

    assert diagnostics.schema_version == "1"
    assert diagnostics.repair_count == 0
    assert diagnostics.warnings == []
    assert diagnostics.region_decisions[0].attempts[0].eval_count == 24


def test_region_decision_rejects_mismatched_region_ids() -> None:
    plan = _plan().model_copy(update={"region_id": "p0001-r0002"})

    with pytest.raises(ValidationError, match="region_id"):
        RegionDecision(
            observation=_observation(),
            plan=plan,
            attempts=[_attempt()],
            selected_attempt_index=0,
            final_status=QualityStatus.PASS,
        )


def test_region_decision_requires_an_attempt() -> None:
    with pytest.raises(ValidationError, match="attempt"):
        RegionDecision(
            observation=_observation(),
            plan=_plan(),
            attempts=[],
            selected_attempt_index=0,
            final_status=QualityStatus.FAIL,
        )


def test_region_decision_rejects_selected_attempt_index_out_of_range() -> None:
    with pytest.raises(ValidationError, match="selected_attempt_index"):
        RegionDecision(
            observation=_observation(),
            plan=_plan(),
            attempts=[_attempt()],
            selected_attempt_index=1,
            final_status=QualityStatus.PASS,
        )


def test_region_decision_rejects_duplicate_attempt_numbers() -> None:
    with pytest.raises(ValidationError, match="attempt"):
        RegionDecision(
            observation=_observation(),
            plan=_plan(),
            attempts=[_attempt(), _attempt()],
            selected_attempt_index=0,
            final_status=QualityStatus.PASS,
        )


def test_region_decision_rejects_final_status_not_matching_selected_attempt() -> None:
    with pytest.raises(ValidationError, match="final_status"):
        RegionDecision(
            observation=_observation(),
            plan=_plan(),
            attempts=[_attempt()],
            selected_attempt_index=0,
            final_status=QualityStatus.FAIL,
        )


def test_page_diagnostics_rejects_plan_for_different_page() -> None:
    plan = PagePlan(
        page_number=2,
        source="deterministic",
        regions=[_plan()],
        rationale="Deterministic plan",
    )

    with pytest.raises(ValidationError, match="page_number"):
        PageDiagnostics(
            planning_mode=PlanningMode.PAGE_CENTRIC,
            stage=ProcessingStage.PLANNING,
            page_number=1,
            plan=plan,
            quality_status=QualityStatus.WARN,
            fingerprint="sha256:abc",
        )


def _attempt() -> AttemptRecord:
    return AttemptRecord(
        attempt=1,
        strategy=ProcessingStrategy.SPECIALIST,
        expert=ExpertKind.TABLE,
        prompt_version="v1",
        prompt_variant="primary",
        output="| A | B |",
        score=_score(),
        verdict=QualityStatus.PASS,
        reason="Meets threshold",
        latency_ms=125.5,
    )
