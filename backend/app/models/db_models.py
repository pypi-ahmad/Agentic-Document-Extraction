"""SQLAlchemy ORM models."""

import datetime
import uuid
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    extractions: Mapped[list["Extraction"]] = relationship(back_populates="document")


class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    extractions: Mapped[list["Extraction"]] = relationship(back_populates="schema")


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), nullable=False)
    schema_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extraction_schemas.id"), nullable=False
    )
    ocr_provider: Mapped[str] = mapped_column(String(50), default="auto")
    llm_provider: Mapped[str] = mapped_column(String(50), default="auto")
    llm_model: Mapped[str] = mapped_column(String(100), default="auto")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    validation_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    review_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_provider_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_provider_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extract_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """Which prompt version produced this extraction (e.g. ``v1``).
    NULL for extractions produced before the v0.4.0 prompt-versioning
    migration ran; treated as ``v1`` for re-runs."""
    schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """Which ExtractionSchema version produced this extraction (e.g.
    ``1``). NULL for pre-v0.4.0 extractions; treated as ``1`` for
    re-runs."""
    error_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped["Document"] = relationship(back_populates="extractions")
    schema: Mapped["ExtractionSchema"] = relationship(back_populates="extractions")
    steps: Mapped[list["ExtractionStep"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExtractionStep.id",
    )
    reviews: Mapped[list["ExtractionReview"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExtractionReview.id",
    )
    judgments: Mapped[list["ExtractionJudgment"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExtractionJudgment.id",
    )


class ExtractionStep(Base):
    """Individual pipeline step recorded during extraction execution."""

    __tablename__ = "extraction_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction: Mapped["Extraction"] = relationship(back_populates="steps")


class ExtractionReview(Base):
    """Persisted human review decision for an extraction job."""

    __tablename__ = "extraction_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    corrected_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    extraction: Mapped["Extraction"] = relationship(back_populates="reviews")


class ExtractionJudgment(Base):
    """LLM-as-judge (G-Eval) score for one extraction.

    Written by ``app.services.eval.judge.GEvalJudge`` for a sample of
    completed extractions (controlled by ``Settings.judge_sample_rate``).
    Used to surface quality regressions that the deterministic metrics
    miss (e.g. plausible-but-wrong values).
    """

    __tablename__ = "extraction_judgments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    judge_model: Mapped[str] = mapped_column(String(100), nullable=False)
    judge_version: Mapped[str] = mapped_column(String(20), nullable=False, default="geval-1")
    scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    """Per-criterion scores: {criterion: {score: 1-5, reason: str}}"""
    overall_score: Mapped[float] = mapped_column(nullable=False)
    """Mean of the per-criterion scores, in [1, 5]."""
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Chain-of-thought reasoning from the judge model (truncated to 4 KB)."""
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    extraction: Mapped["Extraction"] = relationship(back_populates="judgments")


class ExtractionAuditLog(Base):
    """Append-only audit trail for extraction lifecycle events.

    One row per meaningful state transition. Used for compliance, ops
    debugging, and "what happened to job X" investigation. The
    application writes through app.services.audit.record_audit_event
    and never updates or deletes rows.
    """

    __tablename__ = "extraction_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractionEvidence(Base):
    """Per-field evidence for a v0.5.0 evidence-grounded extraction.

    One row per field. ``text_span`` is the verbatim document text
    that backs the value; ``bbox_json`` is ``[x0, y0, x1, y1]`` in
    normalized 0..1 page coordinates. ``evidence_score`` is the
    LLM's self-assessed confidence in the evidence (NOT in the
    value's correctness).
    """

    __tablename__ = "extraction_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bbox_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    text_span: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_region_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractionEntity(Base):
    """A canonical entity linked across pages (v0.5.0 cross-page resolver).

    ``mentions`` is a list of ``{"page": int, "bbox": [..],
    "text_span": str, "region_id": str}``. ``canonical_form`` is the
    chosen normalised form of the entity name.
    """

    __tablename__ = "extraction_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, default="generic")
    canonical_form: Mapped[str] = mapped_column(String(255), nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractionVerifierRun(Base):
    """One verifier run for an extraction (v0.5.0 Phase 3).

    The verifier scores each field's evidence; ``disputed_fields``
    lists the field names where the verifier disagreed with the
    extraction and the conflict resolver flagged the field for
    human review.
    """

    __tablename__ = "extraction_verifier_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verifier_model: Mapped[str] = mapped_column(String(100), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(20), nullable=False, default="verifier-1")
    field_verdicts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    """Per-field verdicts: {field: {"verdict": "agree"|"disagree"|"unsure", "reason": str}}"""
    disputed_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    overall_agreement: Mapped[float] = mapped_column(nullable=False, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
