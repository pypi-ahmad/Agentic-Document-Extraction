"""FastAPI application with lifespan."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session, init_db, close_db
from app.models.schemas import AppInfoResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    # Startup
    await init_db()
    settings.upload_path  # ensure upload dir exists
    settings.artifacts_path  # ensure artifacts dir exists
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
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


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
