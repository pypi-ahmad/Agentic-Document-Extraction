"""FastAPI application with lifespan."""

import datetime as _dt
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, close_db, get_db, init_db
from app.logging_setup import configure_logging, get_logger
from app.metrics import metrics
from app.middleware import RequestContextMiddleware
from app.models.schemas import AppInfoResponse
from app.utils.datetime import ensure_utc as _normalize_utc
from app.utils.http import apply_no_store as _apply_no_store_headers

_logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    configure_logging()
    _logger.info("startup.begin", version=app.version)

    # Startup
    await init_db()
    _ = settings.upload_path  # ensure upload dir exists
    _ = settings.artifacts_path  # ensure artifacts dir exists

    # Load built-in business rules so they run during validation
    import app.services.extraction.business_rules

    # Startup diagnostics — warn early about missing provider keys
    _log_provider_readiness(_logger)

    await _recover_orphaned_jobs()
    _logger.info("startup.complete")
    yield
    # Shutdown
    await close_db()
    _logger.info("shutdown.complete")


async def _recover_orphaned_jobs() -> None:
    """Mark jobs stuck in non-terminal states as failed on startup.

    If the server crashed while a job was running, those rows are
    permanently stuck at ``queued`` / ``processing`` / ``ocr_complete``
    / ``extracted``.  This sweep resets them to ``failed`` so users see
    a clear error and can retry.
    """
    from sqlalchemy import select, update

    from app.models.db_models import Extraction, ExtractionStep
    from app.routers.extractions import _backfill_missing_terminal_steps

    logger = logging.getLogger(__name__)
    stuck_statuses = ("queued", "processing", "ocr_complete", "extracted")
    recovery_error = "Server restarted while this job was running. Please retry."
    recovered_at = _dt.datetime.now(_dt.UTC)

    async with async_session() as db:
        orphaned_ids = list(
            (
                await db.execute(select(Extraction.id).where(Extraction.status.in_(stuck_statuses)))
            ).scalars()
        )

        stmt = (
            update(Extraction)
            .where(Extraction.status.in_(stuck_statuses))
            .values(
                status="failed",
                error=recovery_error,
                completed_at=recovered_at,
                error_category="unknown",
            )
        )
        result = await db.execute(stmt)

        # Also finalize any "running" steps left over from a crash.
        running_steps = await db.execute(
            select(ExtractionStep).where(ExtractionStep.status == "running")
        )
        recovered_steps = 0
        for step in running_steps.scalars():
            step.status = "failed"
            step.error = "Server restarted during this step."
            if not step.completed_at:
                step.completed_at = recovered_at
            if step.started_at and step.duration_ms is None:
                step.duration_ms = max(
                    int(
                        (
                            _normalize_utc(step.completed_at) - _normalize_utc(step.started_at)
                        ).total_seconds()
                        * 1000
                    ),
                    0,
                )
            recovered_steps += 1

        for extraction_id in orphaned_ids:
            await _backfill_missing_terminal_steps(db, extraction_id)

        await db.commit()
        if result.rowcount:
            logger.warning(
                "Recovered %d orphaned extraction job(s) stuck in %s",
                result.rowcount,
                stuck_statuses,
            )
        if recovered_steps:
            logger.warning(
                "Recovered %d orphaned step(s) stuck in running state",
                recovered_steps,
            )


def _log_provider_readiness(logger: logging.Logger) -> None:
    """Log a startup summary of provider availability."""
    from app.services.llm.registry import list_llm_provider_statuses
    from app.services.ocr.registry import list_ocr_provider_statuses

    llm_statuses = list_llm_provider_statuses()
    ocr_statuses = list_ocr_provider_statuses()

    llm_ready = [s for s in llm_statuses if s.available]
    ocr_ready = [s for s in ocr_statuses if s.available and s.enabled]

    if llm_ready:
        logger.info(
            "LLM providers ready: %s",
            ", ".join(s.provider_id for s in llm_ready),
        )
    else:
        logger.warning(
            "No LLM provider API keys configured. "
            "Set OPENAI_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY in .env"
        )

    if ocr_ready:
        logger.info(
            "OCR providers ready: %s",
            ", ".join(s.provider_id for s in ocr_ready),
        )
    else:
        logger.info("No optional OCR providers enabled (built-in parsers still available)")


app = FastAPI(
    title="Agentic Document Extraction",
    description=(
        "Document extraction using the built-in PyMuPDF PDF text reader, "
        "optional PaddleOCR image OCR, and LLM providers."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# CORS (must be registered before user middleware so it can short-circuit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request id, context binding, access log
app.add_middleware(RequestContextMiddleware)

# Register routers
from app.routers import documents, extractions, providers, schemas  # noqa: E402

app.include_router(documents.router)
app.include_router(schemas.router)
app.include_router(extractions.router)
app.include_router(providers.router)


@app.get("/health")
async def health_check(
    response: Response,
    detail: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Liveness probe.  Pass ``?detail=true`` for DB/disk stats."""
    _apply_no_store_headers(response)
    stats: dict = {"status": "ok"}

    if not detail:
        # Lightweight liveness: single cheap query to prove DB is reachable.
        try:
            from sqlalchemy import text

            await db.execute(text("SELECT 1"))
        except Exception:
            stats["status"] = "degraded"
        return stats

    # ── Detailed stats (opt-in) ──────────────────────────────────────
    import os

    from sqlalchemy import func as sa_func
    from sqlalchemy import select, text

    from app.models.db_models import Document, Extraction

    try:
        doc_count = (await db.execute(select(sa_func.count(Document.id)))).scalar() or 0
        ext_count = (await db.execute(select(sa_func.count(Extraction.id)))).scalar() or 0
        failed_count = (
            await db.execute(
                select(sa_func.count(Extraction.id)).where(Extraction.status == "failed")
            )
        ).scalar() or 0
        db_size_row = await db.execute(text("PRAGMA page_count"))
        page_count = db_size_row.scalar() or 0
        page_size_row = await db.execute(text("PRAGMA page_size"))
        page_size = page_size_row.scalar() or 4096
        stats["db"] = {
            "documents": doc_count,
            "extractions": ext_count,
            "failed": failed_count,
            "size_mb": round((page_count * page_size) / (1024 * 1024), 2),
        }
    except Exception:
        stats["status"] = "degraded"
        stats["db"] = {"error": "unreachable"}

    def _dir_size_mb(path: str) -> float:
        import contextlib

        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    with contextlib.suppress(OSError):
                        total += os.path.getsize(os.path.join(dirpath, f))
        except OSError:
            pass
        return round(total / (1024 * 1024), 2)

    stats["disk"] = {
        "uploads_mb": _dir_size_mb(settings.upload_dir),
        "artifacts_mb": _dir_size_mb(settings.artifacts_dir),
    }

    return stats


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Prometheus scrape endpoint.

    Always available (even with no auth) so the test suite and local
    observability tooling can hit it. In a real deployment, restrict
    access at the reverse-proxy layer.
    """
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)


@app.get("/info")
async def app_info(response: Response) -> AppInfoResponse:
    """Runtime capabilities and version metadata.

    ``supported_file_types`` reports accepted upload extensions, not a
    guarantee that every type has an OCR engine ready at runtime.
    """
    _apply_no_store_headers(response)
    import sys

    from app.utils.file_handler import SUPPORTED_FILE_TYPES

    # LangGraph version (best-effort)
    langgraph_version: str | None = None
    try:
        from importlib.metadata import version as pkg_version

        langgraph_version = pkg_version("langgraph")
    except Exception:
        pass

    # Count available providers at call-time
    from app.services.llm.registry import list_llm_provider_statuses
    from app.services.ocr.registry import list_ocr_provider_statuses

    # /info reports both total runtime capability and the user-facing subset.
    ocr_statuses = list_ocr_provider_statuses(include_internal=True)
    ocr_ready = sum(1 for s in ocr_statuses if s.available and s.enabled)
    user_selectable_ready = sum(
        1 for s in ocr_statuses if s.user_selectable and s.available and s.enabled
    )
    internal_ready = sum(
        1 for s in ocr_statuses if not s.user_selectable and s.available and s.enabled
    )
    llm_ready = sum(1 for s in list_llm_provider_statuses() if s.available)

    return AppInfoResponse(
        app_name="Agentic Document Extraction",
        version=app.version,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        langgraph_version=langgraph_version,
        pipeline_nodes=["parse", "extract", "validate", "finalize"],
        ocr_providers_available=ocr_ready,
        user_selectable_parsers_available=user_selectable_ready,
        internal_parsers_available=internal_ready,
        llm_providers_available=llm_ready,
        supported_file_types=list(SUPPORTED_FILE_TYPES),
        max_upload_size_mb=settings.max_upload_size_mb,
        confidence_threshold=settings.confidence_threshold,
    )
