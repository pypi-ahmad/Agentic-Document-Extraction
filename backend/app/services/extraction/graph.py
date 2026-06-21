"""LangGraph-powered document extraction pipeline.

Graph
-----
::

    START ──► parse ──► extract ──► validate ──► reflect ──► await_review ──► finalize ──► END
                    │                                       │                │
                    │            ┌────(valid)───────────────┘                │
                    │            │                                            │
                    │            └─(needs_review, attempts < max)─► re-extract
                    │                                                     │
                    │                                       ┌─(valid)──────┘
                    │                                       │
                    │                                       └─(needs_review)─► interrupt()
                    │                                                              │
                    └─(fail)─►END                                                  └─(resume)─► finalize

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

The ``await_review`` node calls LangGraph's ``interrupt()`` to pause
the graph when validation still fails after reflection is exhausted.
The pipeline is then resumable: the review endpoint calls
``graph.ainvoke(Command(resume=...))`` to continue. This requires a
checkpointer; pass one to :func:`build_extraction_graph` (or use
:func:`build_extraction_graph_with_sqlite` for the production default).

State is a ``TypedDict`` with last-write-wins reducer fields so each node
returns only the keys it changes.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

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

    # ── await_review (interrupts for human review) ──────────────────
    review_decision: Annotated[str, _replace]  # "approved" | "corrected" | "rejected"
    review_corrections: Annotated[dict[str, Any], _replace]
    review_notes: Annotated[str, _replace]

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


async def await_review_node(state: PipelineState) -> dict:
    """Pause for human review when validation still fails after reflection.

    On a valid verdict this is a no-op and the graph proceeds to
    finalize. On ``needs_review`` it calls LangGraph's ``interrupt()``
    with a payload describing the extraction's state; the graph
    pauses, the state is checkpointed, and the caller (the review
    endpoint) resumes it with ``graph.ainvoke(Command(resume=...))``.

    The resumed value is a dict of the form::

        {
            "decision": "approved" | "corrected" | "rejected",
            "corrected_fields": {...},
            "notes": "...",
        }

    The node merges the corrections into ``extracted_data``, sets the
    review verdict, and clears the validation errors so the finalize
    node can stamp a terminal status.

    When the graph is compiled without a checkpointer, ``interrupt()``
    is unavailable and the node falls through to finalize with
    ``needs_review`` (the existing direct-DB-update review endpoint
    handles the decision in that case). This keeps the legacy
    in-process flow working for tests and for setups that have not yet
    migrated to a persisted checkpointer.
    """
    verdict = state.get("review_verdict")
    if verdict == "valid":
        return {}

    # If the graph was compiled without a checkpointer, skip the
    # interrupt and let the existing direct-review path take over.
    if not _graph_has_checkpointer():
        return {}

    payload = {
        "extraction_id": state.get("extraction_id"),
        "validation_errors": list(state.get("validation_errors") or []),
        "validation_results": list(state.get("validation_results") or []),
        "extracted_data": state.get("extracted_data", {}),
        "confidence": state.get("confidence", {}),
        "reflection_attempts": state.get("reflection_attempts", 0) or 0,
    }

    # Pause here. The graph's checkpointer persists the state; the
    # review endpoint will resume with Command(resume=...).
    decision_payload = interrupt(payload)

    if not isinstance(decision_payload, dict):
        logger.warning("await_review_node: bad resume payload, falling back to needs_review")
        return {"review_decision": "rejected", "review_notes": "Bad resume payload"}

    decision = decision_payload.get("decision", "rejected")
    corrections = decision_payload.get("corrected_fields", {}) or {}
    notes = decision_payload.get("notes", "")

    if decision == "approved":
        return {
            "review_decision": "approved",
            "review_corrections": {},
            "review_notes": notes,
            "validation_errors": [],
            "review_verdict": "valid",
        }
    if decision == "corrected":
        current = dict(state.get("extracted_data") or {})
        current.update(corrections)
        return {
            "extracted_data": current,
            "review_decision": "corrected",
            "review_corrections": corrections,
            "review_notes": notes,
            "validation_errors": [],
            "review_verdict": "valid",
        }
    if decision == "rejected":
        return {
            "review_decision": "rejected",
            "review_corrections": {},
            "review_notes": notes,
            "review_verdict": "valid",
        }
    logger.warning("await_review_node: unknown decision %r, falling back to needs_review", decision)
    return {"review_decision": "rejected", "review_notes": f"Unknown decision: {decision}"}


# Module-level flag, toggled by ``build_extraction_graph`` so that
# ``await_review_node`` knows whether ``interrupt()`` is supported.
_graph_checkpointer_enabled: bool = False


def _graph_has_checkpointer() -> bool:
    return _graph_checkpointer_enabled


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
        return "await_review"
    if attempts >= max_reflection_attempts or max_reflection_attempts <= 0:
        return "await_review"
    return "validate"


def _after_await_review(state: PipelineState) -> str:
    """Decide based on the post-resume verdict."""
    if state.get("review_verdict") == "valid":
        return "finalize"
    return "finalize"  # Always finalize; await_review has done its job.


# ── Graph construction ───────────────────────────────────────────────


def build_extraction_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the extraction pipeline graph.

    Parameters
    ----------
    checkpointer:
        Optional LangGraph checkpointer (e.g.
        ``langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`` or
        ``langgraph.checkpoint.memory.InMemorySaver``). When supplied,
        the graph is compiled with checkpointing enabled and the
        ``await_review_node`` can pause and resume via
        ``Command(resume=...)``. When ``None`` (default), the graph
        still works but ``await_review_node`` will fall through to
        finalize with ``needs_review`` for backward compatibility
        with the in-process / no-checkpoint flow.
    """
    global _graph_checkpointer_enabled
    _graph_checkpointer_enabled = checkpointer is not None

    graph = StateGraph(PipelineState)

    graph.add_node("parse", parse_node)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("await_review", await_review_node)
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
        {"validate": "validate", "await_review": "await_review"},
    )
    graph.add_conditional_edges(
        "await_review",
        _after_await_review,
        {"finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


async def build_extraction_graph_with_sqlite(db_path: str) -> Any:
    """Production factory: compile the graph with a SQLite checkpointer.

    The checkpointer is opened once at app startup and shared across
    all graph invocations. The returned compiled graph is the
    long-lived singleton; resumes look it up by ``thread_id``
    (== ``extraction_id``) and pull the latest checkpoint.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    saver = AsyncSqliteSaver.from_conn_string(db_path)
    await saver.setup()
    return build_extraction_graph(checkpointer=saver)


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
