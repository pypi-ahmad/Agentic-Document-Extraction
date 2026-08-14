"""Short-lived runtime composition for one local parse operation."""

from __future__ import annotations

from functools import lru_cache

import httpx

from paperplane.agnes_document import AgnesDocumentAdapter
from paperplane.contracts import ParseResponse
from paperplane.docling_parser import DoclingDocumentParser, create_docling_converter
from paperplane.openai_document import OpenAIDocumentAdapter
from paperplane.parser import MODEL_MODES, AgenticDocumentParser
from paperplane.pipeline import V2PageProcessor

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180.0
SUPPORTED_AI_PROVIDERS = {"openai", "agnes"}


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
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    provider: str = "openai",
) -> ParseResponse:
    """Parse one document without retaining a client, upload, or result."""
    if model not in MODEL_MODES:
        raise ValueError(f"Unsupported processing model: {model}")
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {provider}")
    async with httpx.AsyncClient(timeout=DEFAULT_OPENAI_TIMEOUT_SECONDS) as client:
        adapter = (
            AgnesDocumentAdapter(client, api_key=api_key)
            if provider == "agnes"
            else OpenAIDocumentAdapter(client, api_key=api_key, base_url=base_url)
        )
        parser = AgenticDocumentParser(
            V2PageProcessor(adapter),
            get_docling_parser(),
            vision_enabled=bool(api_key.strip()),
            vision_key_name="AGNES_API_KEY" if provider == "agnes" else "OPENAI_API_KEY",
            vision_parser="agnes_vision" if provider == "agnes" else "openai_vision",
        )
        return await parser.parse(data=data, filename=filename, model=model)


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "SUPPORTED_AI_PROVIDERS",
    "get_docling_parser",
    "parse_document",
]
