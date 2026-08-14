"""FastAPI application for stateless grounded document extraction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.logging_setup import configure_logging, get_logger
from app.routers.dpt_api import router as dpt_api_router
from app.security_middleware import SecurityHeadersMiddleware
from app.services.agentic.parsing import AgenticDocumentParser
from app.services.parsing.openai_document import OpenAIDocumentAdapter
from app.services.parsing.v2_pipeline import V2PageProcessor
from app.telemetry import setup_telemetry, shutdown_telemetry

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    setup_telemetry()
    http = httpx.AsyncClient(timeout=settings.openai_timeout_seconds)
    app.state.agentic_parser = AgenticDocumentParser(
        V2PageProcessor(
            OpenAIDocumentAdapter(
                http,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        )
    )
    logger.info(
        "startup.complete",
        product="paperplane-openai",
        draft_model="gpt-5.6-luna",
        verification_model="gpt-5.6-terra",
    )
    try:
        yield
    finally:
        await http.aclose()
        shutdown_telemetry()


app = FastAPI(
    title="Paperplane OpenAI Document Pipeline",
    description="Stateless grounded Luna/Terra document extraction.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(dpt_api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness() -> Response:
    ready = bool(settings.openai_api_key)
    payload = {
        "status": "ready" if ready else "degraded",
        "checks": {
            "openai": {
                "ok": ready,
                "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
            }
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
            "document_assembly",
        ],
        "supported_file_types": ["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
        "max_upload_size_mb": settings.max_upload_size_mb,
        "max_document_pages": settings.max_document_pages,
        "models": {
            "draft": "gpt-5.6-luna",
            "verification": "gpt-5.6-terra",
        },
        "persistence": "none",
    }
