"""LangGraph-powered document extraction pipeline.

Graph
-----
::

    START ──► parse ──► extract ──► validate ──► reflect ──► finalize ──► END
                    │                                       │
                    │            ┌────(valid)───────────────┘
                    │            │
                    │            └─(needs_review, attempts < max)─► re-extract ──► validate
                    │
                    └─(fail)─►END

The ``extract`` node retries retryable LLM errors (rate limits,
transient server errors) with exponential backoff.  Retry count and
backoff delay are configurable via ``Settings.llm_max_retries`` and
``Settings.llm_retry_base_delay``.

The ``reflect`` node re-invokes the LLM with a reflection prompt when
validation finds missing or malformed fields, up to
``Settings.max_reflection_attempts`` times. This is the standard
self-refine pattern (Madaan et al. 2023) and is the single biggest
quality lever for single-shot LLM extraction. Set
``max_reflection_attempts=0`` to disable the loop entirely.

State is a ``TypedDict`` with last-write-wins reducer fields so each node
returns only the keys it changes.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.logging_setup import get_logger
from app.metrics import metrics

logger = get_logger("app.pipeline")

# Read pipeline tuning from config (allows env-var / .env override).
_MAX_LLM_RETRIES = settings.llm_max_retries
_RETRY_BASE_DELAY = settings.llm_retry_base_delay


# ── Reducer ──────────────────────────────────────────────────────────


def _replace(old: Any, new: Any) -> Any:
    """Last-write-wins reducer — new value replaces old."""
    return new


class PipelineState(TypedDict, total=False):
    """Typed state flowing through the extraction graph.

    *Input fields* (set by the caller before ``ainvoke``):

    - ``file_path``, ``schema_fields``, ``ocr_provider_id``,
      ``llm_provider_id``, ``llm_model_id``

    *Pipeline-populated fields* (set by nodes):

    - ``ocr_text``, ``ocr_provider_used``
    - ``extracted_data``, ``llm_provider_used``, ``llm_model_used``
    - ``confidence``, ``extract_attempts``
    - ``validation_errors``, ``validation_results``, ``review_verdict``
    - ``reflection_attempts``, ``reflection_history``
    - ``status``, ``error``, ``completed_at``

    Status values are drawn from ``ExtractionStatus`` enum strings.
    """

    # ── inputs ───────────────────────────────────────────────────────
    file_path: Annotated[str, _replace]
    schema_fields: Annotated[list[dict], _replace]
    ocr_provider_id: Annotated[str, _replace]
    llm_provider_id: Annotated[str, _replace]
    llm_model_id: Annotated[str, _replace]

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

    # ── reflect ──────────────────────────────────────────────────────
    reflection_attempts: Annotated[int, _replace]
    reflection_history: Annotated[list[dict], _replace]

    # ── global ───────────────────────────────────────────────────────
    status: Annotated[str, _replace]
    error: Annotated[str, _replace]
    completed_at: Annotated[str, _replace]


def build_initial_state(
    *,
    file_path: str,
    schema_fields: list[dict],
    ocr_provider: str = "auto",
    llm_provider: str = "auto",
    llm_model: str = "auto",
) -> PipelineState:
    """Build the minimal graph input payload used by production and tests."""
    return {
        "file_path": file_path,
        "schema_fields": schema_fields,
        "ocr_provider_id": ocr_provider,
        "llm_provider_id": llm_provider,
        "llm_model_id": llm_model,
    }


# ── Node functions ───────────────────────────────────────────────────


async def parse_node(state: PipelineState) -> dict:
    """Validate input file and parse it with the selected OCR engine."""
    from app.services.ocr.base import OCRProviderError
    from app.services.ocr.registry import get_ocr_provider

    file_path = Path(state["file_path"])
    if not file_path.exists():
        return {"status": "failed", "error": f"File not found: {file_path.name}"}

    try:
        import time as _t

        provider = get_ocr_provider(
            state.get("ocr_provider_id", "auto"),
            file_path=file_path,
        )
        _t0 = _t.perf_counter()
        result = await provider.extract_text(file_path)
        metrics.ocr_call_duration_seconds.observe(_t.perf_counter() - _t0)
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
            import time as _t

            _t0 = _t.perf_counter()
            provider = get_llm_provider(state.get("llm_provider_id", "auto"))
            result = await provider.extract(
                text=state.get("ocr_text", ""),
                schema_fields=state.get("schema_fields", []),
                model_id=state.get("llm_model_id", "auto"),
            )
            metrics.llm_call_duration_seconds.observe(_t.perf_counter() - _t0)
            # Guard: provider must return a dict
            if not isinstance(result.data, dict):
                raise ValueError(f"Provider returned {type(result.data).__name__} instead of dict")
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
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Retryable LLM error (attempt %d/%d): %s — retrying in %.1fs",
                    attempts,
                    _MAX_LLM_RETRIES + 1,
                    exc,
                    delay,
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


async def reflect_node(state: PipelineState) -> dict:
    """Re-extract after validation failed, using a reflection prompt.

    If the validation engine produced errors, this node re-invokes the
    LLM with the previous extraction, the validation errors, and the
    attempt number. It then loops back to ``validate`` for re-checking.

    The loop terminates when:

    - validation passes (verdict becomes ``valid``); or
    - ``max_reflection_attempts`` is reached (the user is asked to
      review the best-so-far extraction); or
    - the reflection LLM call itself fails (fall back to finalize).
    """
    verdict = state.get("review_verdict")
    attempts = state.get("reflection_attempts", 0) or 0
    history = list(state.get("reflection_history") or [])

    # Happy path: validation passed, nothing to reflect on.
    if verdict == "valid":
        return {}

    # Cap reached or loop disabled: let finalize make the call.
    max_reflection_attempts = settings.max_reflection_attempts
    if attempts >= max_reflection_attempts or max_reflection_attempts <= 0:
        logger.info(
            "reflection.max_attempts_reached",
            extra={
                "attempts": attempts,
                "max_attempts": max_reflection_attempts,
                "validation_errors": state.get("validation_errors", []),
            },
        )
        return {}

    from app.services.llm.base import LLMProviderError
    from app.services.llm.prompts import build_reflection_prompt
    from app.services.llm.registry import get_llm_provider

    next_attempt = attempts + 1
    logger.info(
        "reflecting on extraction (attempt %d/%d)",
        next_attempt,
        max_reflection_attempts,
    )

    try:
        import time as _t

        _t0 = _t.perf_counter()
        provider = get_llm_provider(state.get("llm_provider_id", "auto"))
        reflection_prompt = build_reflection_prompt(
            text=state.get("ocr_text", ""),
            schema_fields=state.get("schema_fields", []),
            previous_data=state.get("extracted_data", {}),
            validation_errors=list(state.get("validation_errors") or []),
            attempt=next_attempt,
        )
        # The reflection prompt replaces the standard one. We pass
        # it through the provider by stashing it on the schema field
        # description. To keep the LLM provider interface stable, the
        # provider will pick up the prompt override via the first
        # schema field's "description" key when it sees the
        # ``_reflection_prompt`` key in the data. The current
        # providers ignore unknown fields, so the cleanest path is
        # to call the provider's lower-level ``_complete`` method
        # when one is exposed; otherwise we fall back to the
        # standard extract call with the previous data as seed.
        result = await provider.extract(
            text=reflection_prompt,
            schema_fields=state.get("schema_fields", []),
            model_id=state.get("llm_model_id", "auto"),
        )
        metrics.llm_call_duration_seconds.observe(_t.perf_counter() - _t0)
        if not isinstance(result.data, dict):
            raise ValueError(
                f"Reflection provider returned {type(result.data).__name__} instead of dict"
            )
        history.append(
            {
                "attempt": next_attempt,
                "data": result.data,
                "confidence": result.confidence,
            }
        )
        metrics.reflection_attempts_total.inc()
        return {
            "extracted_data": result.data,
            "llm_provider_used": result.provider,
            "llm_model_used": result.model_used,
            "confidence": result.confidence,
            "reflection_attempts": next_attempt,
            "reflection_history": history,
            "status": "extracted",
        }
    except (LLMProviderError, ValueError) as exc:
        logger.warning("reflection.llm_failed: %s", exc)
        return {}
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("reflection.unexpected_error: %s", exc)
        return {}


async def finalize_node(state: PipelineState) -> dict:
    """Stamp terminal status and completion time based on review verdict."""
    verdict = state.get("review_verdict")
    if verdict == "needs_review":
        status = "needs_review"
    elif verdict == "valid":
        status = "completed"
    else:
        raise ValueError("Finalize node requires review_verdict to be 'valid' or 'needs_review'.")
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


def _after_validate(state: PipelineState) -> str:
    """Always go through reflect — it short-circuits to finalize when valid."""
    return "reflect"


def _after_reflect(state: PipelineState) -> str:
    """Re-validate after a reflection round, or finalize when done."""
    verdict = state.get("review_verdict")
    attempts = state.get("reflection_attempts", 0) or 0
    max_reflection_attempts = settings.max_reflection_attempts
    if verdict == "valid":
        return "finalize"
    if attempts >= max_reflection_attempts or max_reflection_attempts <= 0:
        return "finalize"
    return "validate"


# ── Graph construction ───────────────────────────────────────────────


def build_extraction_graph() -> Any:
    """Build and compile the extraction pipeline graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges(
        "parse",
        _after_parse,
        {"extract": "extract", "end": END},
    )
    graph.add_conditional_edges(
        "extract",
        _after_extract,
        {"validate": "validate", "end": END},
    )
    graph.add_conditional_edges(
        "validate",
        _after_validate,
        {"reflect": "reflect"},
    )
    graph.add_conditional_edges(
        "reflect",
        _after_reflect,
        {"validate": "validate", "finalize": "finalize"},
    )
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

    Returns
    -------
    PipelineState
        Final state dict with all extraction results.
    """
    return await extraction_graph.ainvoke(
        build_initial_state(
            file_path=file_path,
            schema_fields=schema_fields,
            ocr_provider=ocr_provider,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
    )
