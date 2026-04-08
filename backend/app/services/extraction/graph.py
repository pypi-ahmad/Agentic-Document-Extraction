"""LangGraph-powered document extraction pipeline.

Graph
-----
::

    START ──► parse ──► extract ──► validate ──► finalize ──► END
                    │            │
                    └─(fail)─►END└─(fail)─►END

The ``extract`` node retries retryable LLM errors (rate limits,
transient server errors) up to ``_MAX_LLM_RETRIES`` times with
exponential backoff.

State is a ``TypedDict`` with last-write-wins reducer fields so each node
returns only the keys it changes.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

# Maximum retry attempts for transient LLM errors (rate limits, 5xx).
_MAX_LLM_RETRIES = 2
# Base delay (seconds) for exponential backoff between retries.
_RETRY_BASE_DELAY = 1.0


# ── Reducer ──────────────────────────────────────────────────────────


def _replace(old: Any, new: Any) -> Any:  # noqa: ARG001
    """Last-write-wins reducer — new value replaces old."""
    return new


# ── Graph state ──────────────────────────────────────────────────────


class PipelineState(TypedDict, total=False):
    """Typed state flowing through the extraction graph.

    *Input fields* (set by the caller before ``ainvoke``):

    - ``file_path``, ``schema_fields``, ``ocr_provider_id``,
      ``llm_provider_id``, ``llm_model_id``
    - ``extraction_id``, ``document_id``, ``schema_id`` (traceability)

    *Pipeline-populated fields* (set by nodes):

    - ``ocr_text``, ``ocr_provider_used``
    - ``extracted_data``, ``llm_provider_used``, ``llm_model_used``
    - ``validation_errors``
    - ``status``, ``error``, ``completed_at``

    Status values are drawn from ``ExtractionStatus`` enum strings.
    """

    # ── inputs ───────────────────────────────────────────────────────
    file_path: Annotated[str, _replace]
    schema_fields: Annotated[list[dict], _replace]
    ocr_provider_id: Annotated[str, _replace]
    llm_provider_id: Annotated[str, _replace]
    llm_model_id: Annotated[str, _replace]
    extraction_id: Annotated[str, _replace]
    document_id: Annotated[str, _replace]
    schema_id: Annotated[str, _replace]

    # ── parse (OCR) ──────────────────────────────────────────────────
    ocr_text: Annotated[str, _replace]
    ocr_provider_used: Annotated[str, _replace]

    # ── extract (LLM) ───────────────────────────────────────────────
    extracted_data: Annotated[dict[str, Any], _replace]
    llm_provider_used: Annotated[str, _replace]
    llm_model_used: Annotated[str, _replace]
    confidence: Annotated[dict[str, float], _replace]
    extract_attempts: Annotated[int, _replace]

    # ── validate ─────────────────────────────────────────────────────
    validation_errors: Annotated[list[str], _replace]
    validation_results: Annotated[list[dict], _replace]
    review_verdict: Annotated[str, _replace]  # "valid" | "needs_review"

    # ── global ───────────────────────────────────────────────────────
    status: Annotated[str, _replace]
    error: Annotated[str, _replace]
    completed_at: Annotated[str, _replace]


# ── Node functions ───────────────────────────────────────────────────


async def parse_node(state: PipelineState) -> dict:
    """Validate input file and parse it with the selected OCR engine."""
    from app.services.ocr.base import OCRProviderError
    from app.services.ocr.registry import get_ocr_provider

    file_path = Path(state["file_path"])
    if not file_path.exists():
        return {"status": "failed", "error": f"File not found: {file_path.name}"}

    try:
        provider = get_ocr_provider(
            state.get("ocr_provider_id", "auto"), file_path=file_path,
        )
        result = await provider.extract_text(file_path)
        return {
            "ocr_text": result.text,
            "ocr_provider_used": result.provider,
            "status": "ocr_complete",
        }
    except OCRProviderError as exc:
        return {"status": "failed", "error": str(exc)}


async def extract_node(state: PipelineState) -> dict:
    """Extract structured data using the selected LLM provider.

    Retries retryable errors (rate limits, transient 5xx) up to
    ``_MAX_LLM_RETRIES`` times with exponential backoff.  Non-retryable
    errors (bad API key, malformed output) fail immediately.
    """
    from app.services.llm.base import LLMProviderError
    from app.services.llm.registry import get_llm_provider

    attempts = 0
    last_error: Exception | None = None

    for attempt in range(_MAX_LLM_RETRIES + 1):
        attempts = attempt + 1
        try:
            provider = get_llm_provider(state.get("llm_provider_id", "auto"))
            result = await provider.extract(
                text=state.get("ocr_text", ""),
                schema_fields=state.get("schema_fields", []),
                model_id=state.get("llm_model_id", "auto"),
            )
            # Guard: provider must return a dict
            if not isinstance(result.data, dict):
                raise ValueError(
                    f"Provider returned {type(result.data).__name__} instead of dict"
                )
            return {
                "extracted_data": result.data,
                "llm_provider_used": result.provider,
                "llm_model_used": result.model_used,
                "confidence": result.confidence,
                "extract_attempts": attempts,
                "status": "extracted",
            }
        except LLMProviderError as exc:
            last_error = exc
            if exc.retryable and attempt < _MAX_LLM_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Retryable LLM error (attempt %d/%d): %s — retrying in %.1fs",
                    attempts, _MAX_LLM_RETRIES + 1, exc, delay,
                )
                await asyncio.sleep(delay)
                continue
            # Non-retryable or exhausted retries
            break
        except ValueError as exc:
            last_error = exc
            break
        except Exception as exc:
            # Catch-all for unexpected errors (ImportError, RuntimeError, etc.)
            logger.exception("Unexpected error during extraction (attempt %d)", attempts)
            last_error = exc
            break

    return {
        "status": "failed",
        "error": str(last_error),
        "extract_attempts": attempts,
    }


async def validate_node(state: PipelineState) -> dict:
    """Validate extracted data using the validation engine.

    Passes per-field confidence scores to the validator so that
    low-confidence fields are routed to review even when the structure
    is correct.
    """
    from app.services.extraction.validation import (
        compute_review_verdict,
        validate_extraction,
    )

    extracted = state.get("extracted_data", {})
    schema_fields = state.get("schema_fields", [])
    confidence = state.get("confidence", {})

    validations = validate_extraction(extracted, schema_fields, confidence=confidence or None)
    verdict = compute_review_verdict(validations)

    # Legacy compat: plain-string error list for existing UI/persistence
    errors = [v.message for v in validations if not v.valid]

    return {
        "validation_errors": errors,
        "validation_results": [v.model_dump() for v in validations],
        "review_verdict": verdict,
    }


async def finalize_node(state: PipelineState) -> dict:
    """Stamp terminal status and completion time based on review verdict."""
    verdict = state.get("review_verdict", "valid")
    status = "needs_review" if verdict == "needs_review" else "completed"
    return {
        "status": status,
        "completed_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }


# ── Edge routing ─────────────────────────────────────────────────────


def _after_parse(state: PipelineState) -> str:
    """Skip downstream nodes when parsing fails."""
    return "extract" if state.get("status") != "failed" else "end"


def _after_extract(state: PipelineState) -> str:
    """Skip validation when extraction fails."""
    return "validate" if state.get("status") != "failed" else "end"


# ── Graph construction ───────────────────────────────────────────────


def build_extraction_graph() -> Any:
    """Build and compile the extraction pipeline graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges(
        "parse", _after_parse, {"extract": "extract", "end": END},
    )
    graph.add_conditional_edges(
        "extract", _after_extract, {"validate": "validate", "end": END},
    )
    graph.add_edge("validate", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# ── Module-level compiled graph (stateless, reusable) ────────────────
extraction_graph = build_extraction_graph()


async def run_extraction(
    file_path: str,
    schema_fields: list[dict],
    ocr_provider: str = "auto",
    llm_provider: str = "auto",
    llm_model: str = "auto",
    *,
    extraction_id: str = "",
    document_id: str = "",
    schema_id: str = "",
) -> PipelineState:
    """Execute the full extraction pipeline.

    Parameters
    ----------
    file_path:
        Path to the uploaded document file.
    schema_fields:
        List of field definitions (name, description, field_type, required).
    ocr_provider / llm_provider / llm_model:
        Provider and model selections; ``"auto"`` uses the configured defaults.
    extraction_id / document_id / schema_id:
        Optional identifiers attached to state for traceability.

    Returns
    -------
    PipelineState
        Final state dict with all extraction results.
    """
    initial_state: PipelineState = {
        "file_path": file_path,
        "schema_fields": schema_fields,
        "ocr_provider_id": ocr_provider,
        "llm_provider_id": llm_provider,
        "llm_model_id": llm_model,
        "extraction_id": extraction_id,
        "document_id": document_id,
        "schema_id": schema_id,
        "status": "pending",
        "error": "",
    }

    return await extraction_graph.ainvoke(initial_state)

