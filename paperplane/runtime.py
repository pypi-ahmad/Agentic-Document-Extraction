"""Short-lived runtime composition for one local parse operation."""

from __future__ import annotations

from functools import lru_cache

import httpx

from paperplane.agnes_document import AgnesDocumentAdapter
from paperplane.anthropic_document import AnthropicDocumentAdapter
from paperplane.contracts import ParseResponse
from paperplane.docling_parser import DoclingDocumentParser, create_docling_converter
from paperplane.gemini_document import GeminiDocumentAdapter
from paperplane.model_catalog import DEFAULT_DOCUMENT_MODEL, get_document_model
from paperplane.openai_document import OpenAIDocumentAdapter
from paperplane.parser import MODEL_MODES, AgenticDocumentParser
from paperplane.pipeline import StructuredAdapter, V2PageProcessor

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
DEFAULT_XAI_BASE_URL = "https://api.x.ai"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180.0


@lru_cache(maxsize=1)
def get_docling_parser() -> DoclingDocumentParser:
    """Reuse Docling's heavyweight converter and loaded models across Streamlit reruns."""

    return DoclingDocumentParser(create_docling_converter())


async def parse_document(
    *,
    data: bytes,
    filename: str,
    model: str,
    api_key: str,
    ai_model: str = DEFAULT_DOCUMENT_MODEL,
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL,
) -> ParseResponse:
    """Parse one document without retaining a client, upload, or result."""
    if model not in MODEL_MODES:
        raise ValueError(f"Unsupported processing model: {model}")
    model_spec = get_document_model(ai_model)
    async with httpx.AsyncClient(timeout=DEFAULT_OPENAI_TIMEOUT_SECONDS) as client:
        adapter: StructuredAdapter
        if model_spec.provider == "agnes":
            adapter = AgnesDocumentAdapter(client, api_key=api_key)
        elif model_spec.provider == "anthropic":
            adapter = AnthropicDocumentAdapter(client, api_key=api_key)
        elif model_spec.provider == "google":
            adapter = GeminiDocumentAdapter(client, api_key=api_key)
        elif model_spec.provider == "xai":
            adapter = OpenAIDocumentAdapter(
                client,
                api_key=api_key,
                base_url=DEFAULT_XAI_BASE_URL,
                provider_name="xAI",
                explicit_prompt_cache=False,
                image_detail=False,
                minimum_reasoning_effort="low",
            )
        else:
            adapter = OpenAIDocumentAdapter(
                client,
                api_key=api_key,
                base_url=openai_base_url,
            )
        parser = AgenticDocumentParser(
            V2PageProcessor(adapter, model=model_spec.model_id),
            get_docling_parser(),
            vision_enabled=bool(api_key.strip()),
            vision_key_name=model_spec.api_key_env,
            vision_parser=f"{model_spec.provider}_vision",
        )
        return await parser.parse(data=data, filename=filename, model=model)


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_XAI_BASE_URL",
    "get_docling_parser",
    "parse_document",
]
