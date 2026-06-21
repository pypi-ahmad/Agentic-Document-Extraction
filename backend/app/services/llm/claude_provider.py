"""Anthropic Claude LLM provider."""

from app.config import settings
from app.services.llm.base import (
    BaseLLMProvider,
    ExtractionResult,
    LLMModel,
    LLMProviderError,
    build_safe_runtime_provider_error,
)
from app.services.llm.output_parser import coerce_to_schema, extract_confidence, parse_llm_json
from app.services.llm.prompts import build_extraction_prompt


class ClaudeProvider(BaseLLMProvider):
    api_key_env_var = "ANTHROPIC_API_KEY"
    extraction_dependency_name = "langchain-anthropic"
    model_listing_dependency_name = "anthropic"
    default_model_id = "claude-3-5-haiku-20241022"

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def display_name(self) -> str:
        return "Anthropic Claude"

    def get_api_key(self) -> str:
        return settings.anthropic_api_key

    def is_extraction_client_available(self) -> bool:
        try:
            import langchain_anthropic  # noqa: F401

            return True
        except Exception:
            return False

    def is_model_listing_client_available(self) -> bool:
        try:
            import anthropic  # noqa: F401

            return True
        except Exception:
            return False

    async def _list_models_dynamic(self) -> list[LLMModel]:
        from anthropic import (
            APIStatusError,
            AsyncAnthropic,
            AuthenticationError,
            PermissionDeniedError,
        )

        client = AsyncAnthropic(api_key=self.get_api_key())
        models: list[LLMModel] = []

        try:
            async for model in client.models.list(limit=100):
                model_id = getattr(model, "id", "")
                if not model_id:
                    continue
                models.append(
                    LLMModel(
                        id=model_id,
                        name=getattr(model, "display_name", None) or model_id,
                        provider=self.provider_id,
                        is_default=model_id == self.default_model_id,
                    )
                )
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise LLMProviderError(
                self.provider_id,
                "Anthropic API key is invalid or does not have model-listing access.",
                code="invalid_api_key",
            ) from exc
        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", 0) or 0
            raise LLMProviderError(
                self.provider_id,
                f"Claude model listing failed with status {status_code or 'unknown'}.",
                code="provider_api_error",
                retryable=status_code in {429} or status_code >= 500,
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "Claude model listing failed.",
                code="provider_api_error",
                retryable=True,
            ) from exc

        return models

    async def extract(
        self,
        text: str,
        schema_fields: list[dict],
        model_id: str = "auto",
    ) -> ExtractionResult:
        if not self.is_configured():
            raise LLMProviderError(
                self.provider_id,
                "Anthropic API key is not configured.",
                code="missing_api_key",
            )

        try:
            from langchain_anthropic import ChatAnthropic
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "langchain-anthropic is unavailable in the current environment.",
                code="client_not_installed",
            ) from exc

        resolved_model = self.resolve_model_id(model_id)
        prompt = build_extraction_prompt(text, schema_fields)

        try:
            llm = ChatAnthropic(
                model_name=resolved_model,
                anthropic_api_key=self.get_api_key(),
                temperature=0,
            )
            response = await llm.ainvoke(prompt)
            raw = response.content if isinstance(response.content, str) else str(response.content)
            data = parse_llm_json(raw)
            data, confidence = extract_confidence(data)
            data = coerce_to_schema(data, schema_fields)
            usage = {}
            if response.response_metadata:
                u = response.response_metadata.get("usage", {})
                if u:
                    usage = dict(u)
            return ExtractionResult(
                data=data,
                raw_response=raw,
                model_used=resolved_model,
                provider=self.provider_id,
                usage=usage,
                confidence=confidence,
            )
        except ValueError as exc:
            raise LLMProviderError(
                self.provider_id,
                f"Model returned unparseable output: {exc}",
                code="invalid_json",
            ) from exc
        except Exception as exc:
            raise build_safe_runtime_provider_error(
                self.provider_id,
                self.display_name,
                exc,
            ) from exc
