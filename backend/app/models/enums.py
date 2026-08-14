"""Stable string enums used by document-processing contracts."""

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    INSPECTING = "inspecting"
    PROCESSING = "processing"
    ASSEMBLING = "assembling"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class PageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(StrEnum):
    SOURCE_DOCUMENT = "source_document"
    CLEAN_MARKDOWN = "clean_markdown"
    LLM_MARKDOWN = "llm_markdown"
    GROUNDED_MARKDOWN = "grounded_markdown"
    CONTEXT_JSON = "context_json"
    GROUNDING_PDF = "grounding_pdf"
    SEARCHABLE_PDF = "searchable_pdf"
    FIGURE = "figure"
    BUNDLE = "bundle"
    WARNINGS = "warnings"
    SETTINGS = "settings"
    DIAGNOSTICS = "diagnostics"
    DOMAIN_EXTRACTION = "domain_extraction"
    STRUCTURED_BLOCKS = "structured_blocks"
    SUBDOCUMENT_MANIFEST = "subdocument_manifest"
    SCHEMA_EXTRACTION = "schema_extraction"
    SCHEMA_TABLE = "schema_table"
