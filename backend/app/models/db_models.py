"""SQLAlchemy ORM models."""

import datetime
import uuid

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
