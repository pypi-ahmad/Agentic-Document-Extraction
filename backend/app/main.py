"""FastAPI application for local layout-aware document parsing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import close_db, init_db
from app.logging_setup import configure_logging, get_logger
from app.routers.curation import router as curation_router
from app.routers.evaluation_runs import router as evaluation_runs_router
from app.routers.extraction_schemas import router as extraction_schemas_router
from app.routers.inspection import router as inspection_router
from app.routers.ollama_models import router as ollama_models_router
from app.routers.parse_batches import router as parse_batches_router
from app.routers.parse_jobs import router as parse_jobs_router
from app.routers.reprocessing import router as reprocessing_router
from app.routers.review_cases import router as review_cases_router
from app.routers.runtime_capabilities import router as runtime_capabilities_router
from app.security_middleware import SecurityHeadersMiddleware
from app.services.jobs import get_job_queue
from app.services.parsing.model_catalog import OllamaCatalogUnavailable
from app.services.parsing.runtime import ParserRuntime
from app.telemetry import setup_telemetry, shutdown_telemetry
from app.utils.network import validate_ollama_base_url

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    setup_telemetry()
    validate_ollama_base_url(settings.ollama_base_url)
    await init_db()
    _ = settings.upload_path
    _ = settings.artifacts_path
    runtime = ParserRuntime(
        checkpoint_path=settings.langgraph_checkpoint_path,
        ollama_base_url=settings.ollama_base_url,
        paddleocr_vl_image=settings.paddleocr_vl_image,
        paddleocr_vl_cache_dir=settings.paddleocr_vl_cache_dir,
        timeout_seconds=max(
            settings.glm_ocr_timeout_seconds,
            settings.ollama_review_timeout_seconds,
            settings.paddleocr_vl_timeout_seconds,
        ),
    )
    async with runtime:
        app.state.parser_runtime = runtime
        queue = get_job_queue()
        await queue.start(runtime)
        await queue.recover()
        logger.info("startup.complete", product="local-document-markdown")
        try:
            yield
        finally:
            await queue.shutdown(settings.job_shutdown_grace_seconds)
            await close_db()
            shutdown_telemetry()


app = FastAPI(
    title="Local Document Markdown",
    description="Vision-first, layout-aware Markdown parsing with local models.",
    version="1.0.0",
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
app.include_router(parse_jobs_router)
app.include_router(inspection_router)
app.include_router(parse_batches_router)
app.include_router(reprocessing_router)
app.include_router(review_cases_router)
app.include_router(evaluation_runs_router)
app.include_router(curation_router)
app.include_router(extraction_schemas_router)
app.include_router(ollama_models_router)
app.include_router(runtime_capabilities_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness(request: Request) -> Response:
    runtime = getattr(request.app.state, "parser_runtime", None)
    paddleocr_vl_ready = await runtime.paddleocr_vl.available() if runtime else False
    try:
        models = await runtime.model_catalog.list_models(refresh=True) if runtime else []
        compatible = [model for model in models if model.compatible]
        ollama_ready, error = bool(compatible), None
    except OllamaCatalogUnavailable as exc:
        models, compatible, ollama_ready, error = [], [], False, str(exc)
    ready = paddleocr_vl_ready
    payload = {
        "status": "ready" if ready else "degraded",
        "checks": {
            "storage": {"ok": settings.upload_path.is_dir() and settings.artifacts_path.is_dir()},
            "paddleocr_vl": {
                "ok": paddleocr_vl_ready,
                "model": "PaddleOCR-VL-1.6",
            },
            "ollama": {
                "ok": ollama_ready,
                "installed_models": len(models),
                "compatible_models": len(compatible),
                "error": error,
            },
        },
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.get("/info")
async def info() -> dict:
    return {
        "app_name": "Local Document Markdown",
        "version": app.version,
        "pipeline": [
            "ingest_and_render",
            "paddleocr_vl_page_parsing",
            "layout_stitching",
            "self_reflection",
            "targeted_repair",
            "finalize",
        ],
        "supported_file_types": ["pdf", "png", "jpg", "jpeg", "tif", "tiff"],
        "max_upload_size_mb": settings.max_upload_size_mb,
        "max_document_pages": settings.max_document_pages,
        "dynamic_ollama_models": True,
        "primary_parser": "PaddleOCR-VL-1.6",
        "local_only": False,
    }
