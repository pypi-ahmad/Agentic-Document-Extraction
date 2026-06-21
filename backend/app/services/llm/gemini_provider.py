"""Google Gemini LLM provider."""

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


class GeminiProvider(BaseLLMProvider):
    api_key_env_var = "GEMINI_API_KEY"
    extraction_dependency_name = "langchain-google-genai"
    model_listing_dependency_name = "google-genai"
    default_model_id = "gemini-2.0-flash"

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini"

    def get_api_key(self) -> str:
        return settings.gemini_api_key

    def is_extraction_client_available(self) -> bool:
        try:
            import langchain_google_genai  # noqa: F401

            return True
        except Exception:
            return False

    def is_model_listing_client_available(self) -> bool:
        try:
            import google.genai  # noqa: F401

            return True
        except Exception:
            return False

    async def _list_models_dynamic(self) -> list[LLMModel]:
        from google import genai
        from google.genai import errors as genai_errors

        client = genai.Client(api_key=self.get_api_key())
        preferred_models: list[LLMModel] = []
        fallback_models: list[LLMModel] = []

        try:
            pager = await client.aio.models.list()
            async for model in pager:
                raw_name = getattr(model, "name", "") or ""
                model_id = raw_name.split("/")[-1] if raw_name else ""
                if not model_id:
                    continue

                display_name = getattr(model, "display_name", None) or model_id
                candidate = LLMModel(
                    id=model_id,
                    name=display_name,
                    provider=self.provider_id,
                    is_default=model_id == self.default_model_id,
                )
                fallback_models.append(candidate)

                supported_actions = {
                    str(action) for action in (getattr(model, "supported_actions", None) or [])
                }
                if supported_actions and "generateContent" not in supported_actions:
                    continue
                preferred_models.append(candidate)
        except genai_errors.ClientError as exc:
            code = getattr(exc, "code", 0) or 0
            if code in {401, 403}:
                raise LLMProviderError(
                    self.provider_id,
                    "Gemini API key is invalid or does not have model-listing access.",
                    code="invalid_api_key",
                ) from exc
            raise LLMProviderError(
                self.provider_id,
                "Gemini model listing failed.",
                code="provider_api_error",
            ) from exc
        except genai_errors.ServerError as exc:
            raise LLMProviderError(
                self.provider_id,
                "Gemini model listing failed due to a provider server error.",
                code="provider_api_error",
                retryable=True,
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "Gemini model listing failed.",
                code="provider_api_error",
                retryable=True,
            ) from exc
        finally:
            close_client = getattr(client.aio, "aclose", None)
            if callable(close_client):
                await close_client()

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
                "Gemini API key is not configured.",
                code="missing_api_key",
            )

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except Exception as exc:
            raise LLMProviderError(
                self.provider_id,
                "langchain-google-genai is unavailable in the current environment.",
                code="client_not_installed",
            ) from exc

        resolved_model = self.resolve_model_id(model_id)
        prompt = build_extraction_prompt(text, schema_fields)

        try:
            llm = ChatGoogleGenerativeAI(
                model=resolved_model,
                google_api_key=self.get_api_key(),
                temperature=0,
            )
            response = await llm.ainvoke(prompt)
            raw = response.content if isinstance(response.content, str) else str(response.content)
            data = parse_llm_json(raw)
            data, confidence = extract_confidence(data)
            data = coerce_to_schema(data, schema_fields)
            return ExtractionResult(
                data=data,
                raw_response=raw,
                model_used=resolved_model,
                provider=self.provider_id,
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
