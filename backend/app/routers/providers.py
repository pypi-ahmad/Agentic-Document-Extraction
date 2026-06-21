"""Provider listing endpoints — OCR providers, LLM providers, models, and app config."""

from fastapi import APIRouter, HTTPException, Response

from app.cache import config_cache, parsers_cache
from app.config import settings
from app.constants import CACHE_MAX_AGE_CONFIG_S, CACHE_MAX_AGE_PRESETS_S
from app.models.enums import LLMProviderID, ModelSelectionMode, ParserEngine
from app.models.schemas import (
    AppConfigResponse,
    LLMModelListResponse,
    LLMProviderInfo,
    ModelInfo,
    OCREngineFlags,
    ParserOptionInfo,
    ProviderAvailabilityStatus,
    ProviderErrorState,
    ProviderInfo,
)
from app.services.llm.base import LLMModelCatalog, LLMProviderStatus
from app.services.llm.registry import (
    list_llm_provider_statuses,
    list_models_for_provider,
)
from app.services.ocr.registry import list_ocr_provider_statuses
from app.utils.file_handler import SUPPORTED_FILE_TYPES
from app.utils.http import apply_cache
from app.utils.http import apply_no_store as _apply_no_store_headers

router = APIRouter(prefix="/api/providers", tags=["Providers"])


def _serialize_parser_option(status) -> ParserOptionInfo:
    return ParserOptionInfo(
        id=status.provider_id,
        name=status.display_name,
        enabled=status.enabled,
        available=status.available,
    )


def _serialize_legacy_ocr_provider(status) -> ProviderInfo:
    return ProviderInfo(
        id=status.provider_id,
        name=status.display_name,
        available=status.enabled and status.available,
    )


@router.get("/ocr", response_model=list[ProviderInfo], deprecated=True)
async def get_ocr_providers(response: Response) -> list[ProviderInfo]:
    """Legacy alias for /parsers kept for backward compatibility.

    Internal parsers (for example the built-in PyMuPDF PDF reader) stay
    excluded here exactly as they do on /parsers, but the response shape
    intentionally preserves the older simpler ``available`` readiness flag.
    """
    _apply_no_store_headers(response)
    return [
        _serialize_legacy_ocr_provider(status)
        for status in list_ocr_provider_statuses(include_internal=False)
    ]


@router.get("/parsers", response_model=list[ParserOptionInfo])
async def get_parser_options(response: Response) -> list[ParserOptionInfo]:
    """List user-facing parser/OCR options with availability.

    Internal parsers (e.g. PyMuPDF) are **not** included.  They are
    implementation details of Auto routing, not user-selectable engines.
    The frontend should render every item in this list as a choosable
    option (greyed-out when ``enabled=False`` or ``available=False``).
    """
    _apply_no_store_headers(response)
    payload = await parsers_cache.get_or_set(
        "parsers",
        _load_parsers,
        ttl_seconds=CACHE_MAX_AGE_PRESETS_S,
    )
    return payload  # type: ignore[return-value]


async def _load_parsers() -> list[ParserOptionInfo]:
    return [
        _serialize_parser_option(status)
        for status in list_ocr_provider_statuses(include_internal=False)
    ]


def _serialize_llm_provider(status: LLMProviderStatus) -> LLMProviderInfo:
    return LLMProviderInfo(
        id=status.provider_id,
        name=status.display_name,
        available=status.available,
        availability=ProviderAvailabilityStatus(
            state=status.availability.state,
            configured=status.availability.configured,
            available=status.availability.available,
            can_extract=status.availability.can_extract,
            can_list_models=status.availability.can_list_models,
            auto_eligible=status.availability.auto_eligible,
        ),
        error=(
            ProviderErrorState(
                code=status.error.code,
                message=status.error.message,
                retryable=status.error.retryable,
            )
            if status.error
            else None
        ),
        is_default=status.is_default,
    )


def _serialize_llm_models(catalog: LLMModelCatalog) -> LLMModelListResponse:
    return LLMModelListResponse(
        provider_id=catalog.provider_id,
        provider_name=catalog.display_name,
        available=catalog.available,
        source=catalog.source,
        availability=ProviderAvailabilityStatus(
            state=catalog.availability.state,
            configured=catalog.availability.configured,
            available=catalog.availability.available,
            can_extract=catalog.availability.can_extract,
            can_list_models=catalog.availability.can_list_models,
            auto_eligible=catalog.availability.auto_eligible,
        ),
        models=[
            ModelInfo(
                id=model.id,
                name=model.name,
                provider=model.provider,
                is_default=model.is_default,
            )
            for model in catalog.models
        ],
        error=(
            ProviderErrorState(
                code=catalog.error.code,
                message=catalog.error.message,
                retryable=catalog.error.retryable,
            )
            if catalog.error
            else None
        ),
        resolved_provider_id=catalog.resolved_provider_id,
    )


@router.get("/llm", response_model=list[LLMProviderInfo])
async def get_llm_providers(response: Response) -> list[LLMProviderInfo]:
    """List implemented LLM providers with their current availability state."""
    _apply_no_store_headers(response)
    return [_serialize_llm_provider(status) for status in list_llm_provider_statuses()]


@router.get("/llm/{provider_id}/models", response_model=LLMModelListResponse)
async def get_llm_models(provider_id: str, response: Response) -> LLMModelListResponse:
    """Return a provider's model catalog or its current placeholder/error state."""
    _apply_no_store_headers(response)
    try:
        catalog = await list_models_for_provider(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="LLM provider not found") from exc

    return _serialize_llm_models(catalog)


# ── App config (no secrets) ─────────────────────────────────────────


@router.get("/config", response_model=AppConfigResponse)
async def get_app_config(response: Response) -> AppConfigResponse:
    """Return non-secret application configuration for UI consumption.

    Cached for CACHE_MAX_AGE_CONFIG_S so the SPA does not hammer it on
    every render. The cache is per-process; multi-replica deployments
    should swap it for a Redis-backed implementation.
    """
    apply_cache(response, CACHE_MAX_AGE_CONFIG_S)
    payload = await config_cache.get_or_set(
        "app_config",
        _load_app_config,
        ttl_seconds=CACHE_MAX_AGE_CONFIG_S,
    )
    return payload  # type: ignore[return-value]


async def _load_app_config() -> AppConfigResponse:
    return AppConfigResponse(
        parser_engines=[e.value for e in ParserEngine],
        llm_providers=[p.value for p in LLMProviderID],
        default_llm_provider=settings.default_llm_provider,
        model_selection_modes=[mode.value for mode in ModelSelectionMode],
        ocr_engine_flags=OCREngineFlags(
            paddleocr=settings.enable_paddleocr,
            glm_ocr=settings.enable_glm_ocr,
        ),
        max_upload_size_mb=settings.max_upload_size_mb,
        supported_file_types=list(SUPPORTED_FILE_TYPES),
        confidence_threshold=settings.confidence_threshold,
    )
