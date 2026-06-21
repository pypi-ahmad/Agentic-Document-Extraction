"""LLM provider subsystem — registry, adapters, and shared types."""

from app.services.llm.base import (
    BaseLLMProvider,
    ExtractionResult,
    LLMModel,
    LLMModelCatalog,
    LLMProviderError,
    LLMProviderStatus,
    ProviderAvailability,
    ProviderErrorInfo,
)
from app.services.llm.registry import (
    get_llm_provider,
    list_llm_provider_statuses,
    list_llm_providers,
    list_models_for_provider,
    register_provider,
)

__all__ = [
    "BaseLLMProvider",
    "ExtractionResult",
    "LLMModel",
    "LLMModelCatalog",
    "LLMProviderError",
    "LLMProviderStatus",
    "ProviderAvailability",
    "ProviderErrorInfo",
    "get_llm_provider",
    "list_llm_provider_statuses",
    "list_llm_providers",
    "list_models_for_provider",
    "register_provider",
]
