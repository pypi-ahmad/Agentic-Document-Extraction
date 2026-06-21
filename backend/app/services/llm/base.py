"""Abstract base classes and typed result/status objects for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.enums import ModelCatalogSource, ProviderAvailabilityState


@dataclass(frozen=True)
class LLMModel:
    """A model offered by a provider."""

    id: str
    name: str
    provider: str
    is_default: bool = False


@dataclass(frozen=True)
class ProviderErrorInfo:
    """Structured provider error information suitable for API responses."""

    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ProviderAvailability:
    """Provider availability flags used by the router and frontend."""

    state: ProviderAvailabilityState
    configured: bool
    available: bool
    can_extract: bool
    can_list_models: bool
    auto_eligible: bool


@dataclass(frozen=True)
class LLMProviderStatus:
    """Resolved status for a provider."""

    provider_id: str
    display_name: str
    availability: ProviderAvailability
    error: ProviderErrorInfo | None = None
    is_default: bool = False

    @property
    def available(self) -> bool:
        return self.availability.available


@dataclass(frozen=True)
class LLMModelCatalog:
    """Structured model catalog response returned by a provider adapter."""

    provider_id: str
    display_name: str
    availability: ProviderAvailability
    source: ModelCatalogSource
    models: list[LLMModel] = field(default_factory=list)
    error: ProviderErrorInfo | None = None
    resolved_provider_id: str | None = None

    @property
    def available(self) -> bool:
        return self.availability.available


@dataclass(frozen=True)
class ExtractionResult:
    """Result from an LLM extraction call."""

    data: dict
    raw_response: str
    model_used: str
    provider: str
    usage: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Interface every LLM provider must implement."""

    api_key_env_var: str = ""
    extraction_dependency_name: str | None = None
    model_listing_dependency_name: str | None = None
    default_model_id: str = "auto"

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g. 'openai')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    def get_api_key(self) -> str:
        """Return the provider API key value (never expose it downstream)."""

    def is_configured(self) -> bool:
        """Check whether the API key / credentials are set."""

        return bool(self.get_api_key())

    @abstractmethod
    def is_extraction_client_available(self) -> bool:
        """Return whether the extraction integration dependency is installed."""

    def supports_dynamic_model_listing(self) -> bool:
        """Whether the provider adapter supports dynamic model listing."""

        return True

    def is_model_listing_client_available(self) -> bool:
        """Return whether the model-listing SDK dependency is installed."""

        return True

    def resolve_model_id(self, model_id: str) -> str:
        """Resolve the effective model id for extraction."""

        return model_id if model_id != "auto" else self.default_model_id

    def get_status(self) -> LLMProviderStatus:
        """Return the provider status used by the registry and API layer."""

        if not self.is_configured():
            error = ProviderErrorInfo(
                code="missing_api_key",
                message=f"{self.display_name} API key is not configured.",
            )
            return LLMProviderStatus(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=ProviderAvailability(
                    state=ProviderAvailabilityState.MISSING_API_KEY,
                    configured=False,
                    available=False,
                    can_extract=False,
                    can_list_models=False,
                    auto_eligible=False,
                ),
                error=error,
            )

        can_extract = self.is_extraction_client_available()
        can_list_models = (
            self.supports_dynamic_model_listing() and self.is_model_listing_client_available()
        )
        if not can_extract:
            dependency_name = self.extraction_dependency_name or "provider client"
            error = ProviderErrorInfo(
                code="client_not_installed",
                message=f"{dependency_name} is not installed.",
            )
            return LLMProviderStatus(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=ProviderAvailability(
                    state=ProviderAvailabilityState.CLIENT_NOT_INSTALLED,
                    configured=True,
                    available=False,
                    can_extract=False,
                    can_list_models=can_list_models,
                    auto_eligible=False,
                ),
                error=error,
            )

        return LLMProviderStatus(
            provider_id=self.provider_id,
            display_name=self.display_name,
            availability=ProviderAvailability(
                state=ProviderAvailabilityState.READY,
                configured=True,
                available=True,
                can_extract=True,
                can_list_models=can_list_models,
                auto_eligible=True,
            ),
        )

    async def list_models(self) -> LLMModelCatalog:
        """Return the models available from this provider.

        The default implementation handles missing credentials, missing
        listing SDKs, and structured placeholder/error states. Concrete
        providers only need to implement ``_list_models_dynamic``.
        """

        status = self.get_status()
        if not status.availability.configured:
            return LLMModelCatalog(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=status.availability,
                source=ModelCatalogSource.PLACEHOLDER,
                error=status.error,
            )

        if not self.supports_dynamic_model_listing():
            error = ProviderErrorInfo(
                code="model_listing_not_supported",
                message="Dynamic model listing is not supported for this provider integration.",
            )
            return LLMModelCatalog(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=ProviderAvailability(
                    state=ProviderAvailabilityState.LISTING_UNSUPPORTED,
                    configured=True,
                    available=status.availability.available,
                    can_extract=status.availability.can_extract,
                    can_list_models=False,
                    auto_eligible=status.availability.auto_eligible,
                ),
                source=ModelCatalogSource.PLACEHOLDER,
                error=error,
            )

        if not self.is_model_listing_client_available():
            dependency_name = self.model_listing_dependency_name or "provider SDK"
            error = ProviderErrorInfo(
                code="client_not_installed",
                message=f"{dependency_name} is not installed.",
            )
            return LLMModelCatalog(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=ProviderAvailability(
                    state=ProviderAvailabilityState.CLIENT_NOT_INSTALLED,
                    configured=True,
                    available=status.availability.available,
                    can_extract=status.availability.can_extract,
                    can_list_models=False,
                    auto_eligible=status.availability.auto_eligible,
                ),
                source=ModelCatalogSource.PLACEHOLDER,
                error=error,
            )

        try:
            models = await self._list_models_dynamic()
        except LLMProviderError as exc:
            error = exc.to_error_state()
            return LLMModelCatalog(
                provider_id=self.provider_id,
                display_name=self.display_name,
                availability=self._availability_from_model_listing_error(
                    status.availability,
                    error,
                ),
                source=ModelCatalogSource.PLACEHOLDER,
                error=error,
            )

        return LLMModelCatalog(
            provider_id=self.provider_id,
            display_name=self.display_name,
            availability=status.availability,
            source=ModelCatalogSource.DYNAMIC,
            models=self._dedupe_and_sort_models(models),
        )

    def _availability_from_model_listing_error(
        self,
        current: ProviderAvailability,
        error: ProviderErrorInfo,
    ) -> ProviderAvailability:
        if error.code == "invalid_api_key":
            return ProviderAvailability(
                state=ProviderAvailabilityState.INVALID_API_KEY,
                configured=True,
                available=False,
                can_extract=False,
                can_list_models=False,
                auto_eligible=False,
            )

        return ProviderAvailability(
            state=ProviderAvailabilityState.ERROR,
            configured=current.configured,
            available=current.available,
            can_extract=current.can_extract,
            can_list_models=False,
            auto_eligible=current.auto_eligible,
        )

    def _dedupe_and_sort_models(self, models: list[LLMModel]) -> list[LLMModel]:
        unique: dict[str, LLMModel] = {}
        for model in models:
            unique[model.id] = model
        return sorted(
            unique.values(),
            key=lambda model: (not model.is_default, model.name.lower(), model.id.lower()),
        )

    @abstractmethod
    async def _list_models_dynamic(self) -> list[LLMModel]:
        """Fetch the dynamic model list from the provider SDK/API."""

    @abstractmethod
    async def extract(
        self,
        text: str,
        schema_fields: list[dict],
        model_id: str = "auto",
    ) -> ExtractionResult:
        """Run structured extraction.

        Args:
            text: OCR-extracted text from the document.
            schema_fields: List of field definitions (name, description, type, required).
            model_id: Specific model to use, or 'auto' for provider default.

        Returns:
            ExtractionResult with extracted data.
        """


class LLMProviderError(Exception):
    """Raised when an LLM provider encounters an error."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        code: str = "provider_error",
        retryable: bool = False,
    ) -> None:
        self.provider = provider
        self.message = message
        self.code = code
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")

    def to_error_state(self) -> ProviderErrorInfo:
        return ProviderErrorInfo(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
        )


def _is_auth_error(exc: Exception) -> bool:
    """Best-effort detection of authentication/authorization failures."""
    msg = str(exc).lower()
    if any(
        token in msg
        for token in (
            "api key",
            "authentication",
            "authorization",
            "unauthorized",
            "forbidden",
            "permission denied",
            "invalid key",
            "invalid_api_key",
            "401",
            "403",
        )
    ):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_auth_error(cause)
    return False


def _is_retryable_error(exc: Exception) -> bool:
    """Heuristic: detect retryable API errors from SDK exceptions.

    Inspects the exception message (and cause chain) for known transient
    patterns such as rate limits, server errors, and timeouts.  Used by
    provider ``extract()`` catch-all handlers so the graph retry loop
    actually activates for real transient failures.
    """
    msg = str(exc).lower()
    if any(k in msg for k in ("rate limit", "rate_limit", "429", "quota")):
        return True
    if any(
        k in msg for k in ("server error", "503", "502", "500", "service unavailable", "overloaded")
    ):
        return True
    if any(k in msg for k in ("timeout", "timed out", "deadline")):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_retryable_error(cause)
    return False


def build_safe_runtime_provider_error(
    provider_id: str,
    display_name: str,
    exc: Exception,
) -> LLMProviderError:
    """Convert a raw provider/runtime exception into a safe API-facing error."""
    if _is_auth_error(exc):
        return LLMProviderError(
            provider_id,
            f"{display_name} authentication failed.",
            code="invalid_api_key",
        )
    if _is_retryable_error(exc):
        return LLMProviderError(
            provider_id,
            f"{display_name} request failed temporarily. Please retry.",
            retryable=True,
        )
    return LLMProviderError(
        provider_id,
        f"{display_name} request failed.",
    )
