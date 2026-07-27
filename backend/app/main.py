"""FastAPI application for the OpenAI-only grounded document pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import close_db, init_db
from app.logging_setup import configure_logging, get_logger
from app.routers.dpt_api import router as dpt_api_router
from app.routers.extraction_schemas import router as extraction_schemas_router
from app.routers.review_cases import router as review_cases_router
from app.security_middleware import SecurityHeadersMiddleware
from app.services.v2_jobs import get_v2_job_queue
from app.telemetry import setup_telemetry, shutdown_telemetry

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    setup_telemetry()
    await init_db()
    _ = settings.upload_path
    _ = settings.artifacts_path
    queue = get_v2_job_queue()
    await queue.start()
    await queue.recover()
    logger.info(
        "startup.complete",
        product="paperplane-openai",
        draft_model="gpt-5.6-luna",
        verification_model="gpt-5.6-terra",
    )
    try:
        yield
    finally:
        await queue.shutdown()
        await close_db()
        shutdown_telemetry()


app = FastAPI(
    title="Paperplane OpenAI Document Pipeline",
    description="Grounded Luna/Terra document extraction with auditable evidence.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(dpt_api_router)
app.include_router(extraction_schemas_router)
app.include_router(review_cases_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness() -> Response:
    storage_ready = settings.artifacts_path.is_dir()
    openai_ready = bool(settings.openai_api_key)
    ready = storage_ready and openai_ready
    payload = {
        "status": "ready" if ready else "degraded",
        "checks": {
            "storage": {"ok": storage_ready},
            "openai": {
                "ok": openai_ready,
                "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
            },
        },
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.get("/info")
async def info() -> dict:
    return {
        "app_name": "Paperplane OpenAI Document Pipeline",
        "version": app.version,
        "pipeline": [
            "ingest_and_render",
            "luna_page_draft",
            "deterministic_grounding",
            "terra_crop_verification",
            "document_split_and_assembly",
        ],
        "supported_file_types": ["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
        "max_upload_size_mb": settings.max_upload_size_mb,
        "max_document_pages": settings.max_document_pages,
        "models": {
            "draft": "gpt-5.6-luna",
            "verification": "gpt-5.6-terra",
        },
        "local_ai": False,
    }
