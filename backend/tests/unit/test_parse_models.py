import pytest
from pydantic import ValidationError

from app.models.db_models import (
    Artifact,
    Base,
    EvaluationCase,
    EvaluationRun,
    PageCheckpoint,
    ParseBatch,
    ParseJob,
    ReprocessRun,
)
from app.models.enums import ArtifactType, JobStatus, PageStatus
from app.models.schemas import ParseSettings


def test_reset_schema_contains_only_parse_domain_tables() -> None:
    assert set(Base.metadata.tables) == {
        "parse_jobs",
        "parse_batches",
        "page_checkpoints",
        "artifacts",
        "subdocuments",
        "evaluation_runs",
        "evaluation_cases",
        "extraction_schemas",
        "review_cases",
        "review_decisions",
        "curated_documents",
        "curated_exports",
        "reprocess_runs",
    }


def test_job_statuses_cover_recovery_and_partial_completion() -> None:
    assert JobStatus.PAUSED == "paused"
    assert JobStatus.CANCELLED == "cancelled"
    assert JobStatus.COMPLETED_WITH_WARNINGS == "completed_with_warnings"


def test_page_and_artifact_enums_are_stable() -> None:
    assert PageStatus.FAILED == "failed"
    assert ArtifactType.CLEAN_MARKDOWN == "clean_markdown"
    assert ArtifactType.LLM_MARKDOWN == "llm_markdown"
    assert ArtifactType.BUNDLE == "bundle"
    assert ArtifactType.DIAGNOSTICS == "diagnostics"
    assert ArtifactType.SCHEMA_EXTRACTION == "schema_extraction"
    assert ArtifactType.SCHEMA_TABLE == "schema_table"


def test_page_checkpoint_exposes_agentic_persistence_columns() -> None:
    columns = PageCheckpoint.__table__.columns
    assert {
        "stage",
        "observation_path",
        "plan_path",
        "diagnostics_path",
        "state_path",
        "fingerprint",
        "quality_status",
        "quality_score",
        "repair_count",
    } <= set(columns.keys())


def test_models_expose_expected_relationships() -> None:
    assert ParseJob.pages.property.mapper.class_ is PageCheckpoint
    assert ParseJob.artifacts.property.mapper.class_ is Artifact
    assert ParseJob.batch.property.mapper.class_ is ParseBatch
    assert ParseJob.reprocess_runs.property.mapper.class_ is ReprocessRun
    assert EvaluationRun.cases.property.mapper.class_ is EvaluationCase


def test_sensitive_schema_extraction_requires_explicit_cloud_consent() -> None:
    with pytest.raises(ValidationError, match="allow_sensitive_cloud"):
        ParseSettings(
            document_profile="healthcare_form",
            processing_mode="hybrid",
            review_provider="openai",
            review_model="review-model",
            extraction_schema_id="schema-one",
            extraction_provider="openai",
            extraction_model="extract-model",
        )
