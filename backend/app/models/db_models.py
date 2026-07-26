"""SQLAlchemy models for durable document parse jobs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.enums import ArtifactType, JobStatus, PageStatus


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ParseBatch(Base):
    __tablename__ = "parse_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    bundle_path: Mapped[str | None] = mapped_column(String(1024))
    bundle_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list[ParseJob]] = relationship(
        back_populates="batch",
        order_by="ParseJob.batch_ordinal",
        lazy="selectin",
    )


class ParseJob(Base):
    __tablename__ = "parse_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    batch_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("parse_batches.id", ondelete="SET NULL"), index=True
    )
    batch_ordinal: Mapped[int | None] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    source_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=JobStatus.QUEUED, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality_policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_page: Mapped[int | None] = mapped_column(Integer)
    completed_pages: Mapped[int] = mapped_column(Integer, default=0)
    failed_pages: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(120))
    model_digest: Mapped[str | None] = mapped_column(String(128))
    review_model_name: Mapped[str | None] = mapped_column(String(120))
    review_model_digest: Mapped[str | None] = mapped_column(String(128))
    extraction_schema_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("extraction_schemas.id", ondelete="SET NULL"), index=True
    )
    extraction_schema_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extraction_model_name: Mapped[str | None] = mapped_column(String(120))
    extraction_model_digest: Mapped[str | None] = mapped_column(String(128))
    detected_profile: Mapped[str | None] = mapped_column(String(40))
    profile_confidence: Mapped[float | None] = mapped_column(Float)
    segmentation_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pages: Mapped[list[PageCheckpoint]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="PageCheckpoint.page_number",
        lazy="selectin",
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Artifact.created_at",
        lazy="selectin",
    )
    subdocuments: Mapped[list[SubDocument]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="SubDocument.ordinal",
        lazy="selectin",
    )
    review_cases: Mapped[list[ReviewCase]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    reprocess_runs: Mapped[list[ReprocessRun]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ReprocessRun.created_at",
        lazy="selectin",
    )
    batch: Mapped[ParseBatch | None] = relationship(back_populates="jobs")


class PageCheckpoint(Base):
    __tablename__ = "page_checkpoints"
    __table_args__ = (UniqueConstraint("job_id", "page_number", name="uq_job_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=PageStatus.PENDING, index=True)
    routing: Mapped[str | None] = mapped_column(String(40))
    layout_path: Mapped[str | None] = mapped_column(String(1024))
    layout_sha256: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(30))
    observation_path: Mapped[str | None] = mapped_column(String(1024))
    plan_path: Mapped[str | None] = mapped_column(String(1024))
    diagnostics_path: Mapped[str | None] = mapped_column(String(1024))
    state_path: Mapped[str | None] = mapped_column(String(1024))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    quality_status: Mapped[str | None] = mapped_column(String(20))
    quality_score: Mapped[float | None] = mapped_column(Float)
    repair_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[ParseJob] = relationship(back_populates="pages")


class V2PageTask(Base):
    """Durable, lease-based unit of page processing for stateless V2 workers."""

    __tablename__ = "v2_page_tasks"
    __table_args__ = (UniqueConstraint("job_id", "page_number", name="uq_v2_job_page_task"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120), index=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    result_path: Mapped[str | None] = mapped_column(String(1024))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReprocessRun(Base):
    __tablename__ = "reprocess_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    region_id: Mapped[str | None] = mapped_column(String(40))
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_padding: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    previous_fingerprint: Mapped[str | None] = mapped_column(String(64))
    result_fingerprint: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[ParseJob] = relationship(back_populates="reprocess_runs")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("job_id", "type", "region_id", name="uq_job_artifact"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subdocument_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("subdocuments.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40), default=ArtifactType.CLEAN_MARKDOWN)
    region_id: Mapped[str | None] = mapped_column(String(40))
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[ParseJob] = relationship(back_populates="artifacts")
    subdocument: Mapped[SubDocument | None] = relationship(back_populates="artifacts")


class SubDocument(Base):
    __tablename__ = "subdocuments"
    __table_args__ = (UniqueConstraint("job_id", "ordinal", name="uq_job_subdocument_ordinal"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    identifiers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    boundary_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    boundary_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    complete: Mapped[bool] = mapped_column(Boolean, default=True)
    missing_pages: Mapped[list[int]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[ParseJob] = relationship(back_populates="subdocuments")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="subdocument", cascade="all, delete-orphan", lazy="selectin"
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report_path: Mapped[str | None] = mapped_column(String(1024))
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    cases: Mapped[list[EvaluationCase]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EvaluationCase.created_at"
    )


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("run_id", "external_id", name="uq_evaluation_case_external"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    parse_job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    gold_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    report_path: Mapped[str | None] = mapped_column(String(1024))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[EvaluationRun] = relationship(back_populates="cases")
    parse_job: Mapped[ParseJob] = relationship()


class ReviewCase(Base):
    __tablename__ = "review_cases"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_review_case_fingerprint"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    failure_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    original: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    current: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="ReviewDecision.revision"
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (UniqueConstraint("case_id", "revision", name="uq_review_decision_revision"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("review_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    corrected: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False, default="local_user")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    case: Mapped[ReviewCase] = relationship(back_populates="decisions")


class CuratedDocument(Base):
    __tablename__ = "curated_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    label_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    label_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CuratedExport(Base):
    __tablename__ = "curated_exports"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_curated_export_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    archive_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
