"""Single source of truth for parser, provider, and model-selection enums.

These string enums are used across config, API schemas, DB columns, and the
LangGraph pipeline.  The *values* are the wire-format / DB-stored strings and
must stay stable.  Frontend TypeScript mirrors live in
``frontend/src/lib/api.ts`` (search for "ParserEngine").
"""

from enum import StrEnum

# ── OCR / parser engine ──────────────────────────────────────────────


class ParserEngine(StrEnum):
    """Local OCR/parser choices exposed in the UI dropdown."""

    AUTO = "auto"
    PADDLEOCR = "paddleocr"
    GLMOCR = "glmocr"
    DOCLING = "docling"


# ── LLM provider ────────────────────────────────────────────────────


class LLMProviderID(StrEnum):
    """LLM provider choices exposed in the UI dropdown."""

    AUTO = "auto"
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


# ── Model selection mode ─────────────────────────────────────────────


class ModelSelectionMode(StrEnum):
    """How the model is chosen for an extraction job."""

    AUTO = "auto"
    EXPLICIT_MODEL_ID = "explicit_model_id"


# ── Provider/model loading state ────────────────────────────────────


class ProviderAvailabilityState(StrEnum):
    """Provider availability states exposed via the API."""

    READY = "ready"
    MISSING_API_KEY = "missing_api_key"
    CLIENT_NOT_INSTALLED = "client_not_installed"
    INVALID_API_KEY = "invalid_api_key"
    LISTING_UNSUPPORTED = "listing_unsupported"
    ERROR = "error"


class ModelCatalogSource(StrEnum):
    """Where a provider model catalog came from."""

    DYNAMIC = "dynamic"
    PLACEHOLDER = "placeholder"


# ── Extraction job status ────────────────────────────────────────────


class ExtractionStatus(StrEnum):
    """Lifecycle states for an extraction job."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    OCR_COMPLETE = "ocr_complete"
    EXTRACTED = "extracted"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


# ── Extraction field types ───────────────────────────────────────────


class FieldType(StrEnum):
    """Data types for extraction schema fields."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"
    OBJECT = "object"


# ── Review decision ─────────────────────────────────────────────────


class ReviewDecision(StrEnum):
    """Human reviewer's decision on an extraction that needs review."""

    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewVerdict(StrEnum):
    """Persisted extraction review/validation verdicts exposed via the API."""

    VALID = "valid"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
