"""OpenAI LLM provider."""

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


class OpenAIProvider(BaseLLMProvider):
    api_key_env_var = "OPENAI_API_KEY"
    extraction_dependency_name = "langchain-openai"
    model_listing_dependency_name = "openai"
    default_model_id = "gpt-4o-mini"

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

    def get_api_key(self) -> str:
        return settings.openai_api_key

    def is_extraction_client_available(self) -> bool:
        try:
            import langchain_openai  # noqa: F401

            return True
        except Exception:
            return False

    def is_model_listing_client_available(self) -> bool:
        try:
            import openai  # noqa: F401

            return True
        except Exception:
            return False

    async def _list_models_dynamic(self) -> list[LLMModel]:
        from openai import APIStatusError, AsyncOpenAI, AuthenticationError, PermissionDeniedError

        client = AsyncOpenAI(api_key=self.get_api_key())
        preferred_models: list[LLMModel] = []
        fallback_models: list[LLMModel] = []

        try:
            async for model in client.models.list():
                model_id = getattr(model, "id", "")
                if not model_id:
                    continue
                candidate = LLMModel(
                    id=model_id,
                    name=model_id,
                    provider=self.provider_id,
                    is_default=model_id == self.default_model_id,
                )
                fallback_models.append(candidate)
                if model_id.startswith(("gpt-", "o1", "o3", "o4")):
                    preferred_models.append(candidate)
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise LLMProviderError(
                self.provider_id,
                "OpenAI API key is invalid or does not have model-listing access.",
                code="invalid_api_key",
            ) from exc
        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", 0) or 0
            raise LLMProviderError(
                self.provider_id,
                f"OpenAI model listing failed with status {status_code or 'unknown'}.",
                code="provider_api_error",
                retryable=status_code in {429} or status_code >= 500,
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "OpenAI model listing failed.",
                code="provider_api_error",
                retryable=True,
            ) from exc

        return preferred_models or fallback_models

    async def extract(
        self,
        text: str,
        schema_fields: list[dict],
        model_id: str = "auto",
    ) -> ExtractionResult:
        if not self.is_configured():
            raise LLMProviderError(
                self.provider_id,
                "OpenAI API key is not configured.",
                code="missing_api_key",
            )

        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "langchain-openai is unavailable in the current environment.",
                code="client_not_installed",
            ) from exc

        resolved_model = self.resolve_model_id(model_id)
        prompt = build_extraction_prompt(text, schema_fields)

        try:
            llm = ChatOpenAI(
                model=resolved_model,
                api_key=self.get_api_key(),
                temperature=0,
            )
            response = await llm.ainvoke(prompt)
            raw = response.content if isinstance(response.content, str) else str(response.content)
            data = parse_llm_json(raw)
            data, confidence = extract_confidence(data)
            data = coerce_to_schema(data, schema_fields)
            usage = {}
            if response.response_metadata:
                token_usage = response.response_metadata.get("token_usage", {})
                if token_usage:
                    usage = dict(token_usage)
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
