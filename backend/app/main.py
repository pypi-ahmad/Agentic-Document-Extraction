"""FastAPI application with lifespan."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db, init_db, close_db
from app.models.schemas import AppInfoResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    import logging

    logger = logging.getLogger(__name__)

    # Startup
    await init_db()
    settings.upload_path  # ensure upload dir exists
    settings.artifacts_path  # ensure artifacts dir exists

    # Load built-in business rules so they run during validation
    import app.services.extraction.business_rules  # noqa: F401

    # Startup diagnostics — warn early about missing provider keys
    _log_provider_readiness(logger)

    await _recover_orphaned_jobs()
    yield
    # Shutdown
    await close_db()


async def _recover_orphaned_jobs() -> None:
    """Mark jobs stuck in non-terminal states as failed on startup.

    If the server crashed while a job was running, those rows are
    permanently stuck at ``queued`` / ``processing`` / ``ocr_complete``
    / ``extracted``.  This sweep resets them to ``failed`` so users see
    a clear error and can retry.
    """
    import logging

    from sqlalchemy import update

    from app.models.db_models import Extraction, ExtractionStep

    logger = logging.getLogger(__name__)
    stuck_statuses = ("queued", "processing", "ocr_complete", "extracted")

    async with async_session() as db:
        stmt = (
            update(Extraction)
            .where(Extraction.status.in_(stuck_statuses))
            .values(
                status="failed",
                error="Server restarted while this job was running. Please retry.",
            )
        )
        result = await db.execute(stmt)

        # Also mark any "running" steps left over from a crash as failed
        step_stmt = (
            update(ExtractionStep)
            .where(ExtractionStep.status == "running")
            .values(status="failed", error="Server restarted during this step.")
        )
        step_result = await db.execute(step_stmt)

        await db.commit()
        if result.rowcount:
            logger.warning(
                "Recovered %d orphaned extraction job(s) stuck in %s",
                result.rowcount, stuck_statuses,
            )
        if step_result.rowcount:
            logger.warning(
                "Recovered %d orphaned step(s) stuck in running state",
                step_result.rowcount,
            )


def _log_provider_readiness(logger) -> None:  # type: ignore[type-arg]
    """Log a startup summary of provider availability."""
    from app.services.llm.registry import list_llm_provider_statuses
    from app.services.ocr.registry import list_ocr_provider_statuses

    llm_statuses = list_llm_provider_statuses()
    ocr_statuses = list_ocr_provider_statuses()

    llm_ready = [s for s in llm_statuses if s.available]
    ocr_ready = [s for s in ocr_statuses if s.available and s.enabled]

    if llm_ready:
        logger.info("LLM providers ready: %s", ", ".join(s.id for s in llm_ready))
    else:
        logger.warning(
            "No LLM provider API keys configured. "
            "Set OPENAI_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY in .env"
        )

    if ocr_ready:
        logger.info("OCR providers ready: %s", ", ".join(s.id for s in ocr_ready))
    else:
        logger.info("No optional OCR providers enabled (built-in parsers still available)")


app = FastAPI(
    title="Agentic Document Extraction",
    description="Intelligent document extraction using OCR + LLMs",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.routers import documents, schemas, extractions, providers  # noqa: E402

app.include_router(documents.router)
app.include_router(schemas.router)
app.include_router(extractions.router)
app.include_router(providers.router)


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Liveness probe with lightweight system stats."""
    import os

    from sqlalchemy import func as sa_func, select, text

    from app.models.db_models import Document, Extraction

    stats: dict = {"status": "ok"}

    try:
        # Quick connectivity test + row counts
        doc_count = (await db.execute(select(sa_func.count(Document.id)))).scalar() or 0
        ext_count = (await db.execute(select(sa_func.count(Extraction.id)))).scalar() or 0
        failed_count = (
            await db.execute(
                select(sa_func.count(Extraction.id)).where(Extraction.status == "failed")
            )
        ).scalar() or 0
        # SQLite DB file size
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

    # Disk usage for upload + artifacts dirs
    def _dir_size_mb(path: str) -> float:
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
        except OSError:
            pass
        return round(total / (1024 * 1024), 2)

    stats["disk"] = {
        "uploads_mb": _dir_size_mb(settings.upload_dir),
        "artifacts_mb": _dir_size_mb(settings.artifacts_dir),
    }

    return stats


@app.get("/info")
async def app_info() -> AppInfoResponse:
    """Runtime capabilities and version metadata."""
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
    from app.services.ocr.registry import list_ocr_provider_statuses
    from app.services.llm.registry import list_llm_provider_statuses

    ocr_ready = sum(1 for s in list_ocr_provider_statuses() if s.available and s.enabled)
    llm_ready = sum(1 for s in list_llm_provider_statuses() if s.available)

    return AppInfoResponse(
        app_name="Agentic Document Extraction",
        version=app.version,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        langgraph_version=langgraph_version,
        pipeline_nodes=["parse", "extract", "validate", "finalize"],
        ocr_providers_available=ocr_ready,
        llm_providers_available=llm_ready,
        supported_file_types=list(SUPPORTED_FILE_TYPES),
        max_upload_size_mb=settings.max_upload_size_mb,
    )
