"""Short-lived runtime composition for one local parse operation."""

from __future__ import annotations

from functools import lru_cache

import httpx

from paperplane.contracts import ParseResponse
from paperplane.docling_parser import DoclingDocumentParser, create_docling_converter
from paperplane.openai_document import OpenAIDocumentAdapter
from paperplane.parser import MODEL_MODES, AgenticDocumentParser
from paperplane.pipeline import V2PageProcessor

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
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
    base_url: str = DEFAULT_OPENAI_BASE_URL,
) -> ParseResponse:
    """Parse one document without retaining a client, upload, or result."""
    if model not in MODEL_MODES:
        raise ValueError(f"Unsupported processing model: {model}")
    async with httpx.AsyncClient(timeout=DEFAULT_OPENAI_TIMEOUT_SECONDS) as client:
        parser = AgenticDocumentParser(
            V2PageProcessor(
                OpenAIDocumentAdapter(
                    client,
                    api_key=api_key,
                    base_url=base_url,
                )
            ),
            get_docling_parser(),
            vision_enabled=bool(api_key.strip()),
        )
        return await parser.parse(data=data, filename=filename, model=model)


__all__ = ["DEFAULT_OPENAI_BASE_URL", "get_docling_parser", "parse_document"]
