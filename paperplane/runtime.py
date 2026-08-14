"""Short-lived runtime composition for local, bounded batch parsing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import httpx

from paperplane.agnes_document import AgnesDocumentAdapter
from paperplane.anthropic_document import AnthropicDocumentAdapter
from paperplane.contracts import ParseResponse, ProcessingStrategy
from paperplane.docling_parser import DoclingDocumentParser, create_docling_converter
from paperplane.gemini_document import GeminiDocumentAdapter
from paperplane.ingest import DocumentInputError
from paperplane.model_catalog import DEFAULT_DOCUMENT_MODEL, get_document_model
from paperplane.ollama_document import (
    DEFAULT_OLLAMA_BASE_URL,
    ChainedStructuredAdapter,
    OllamaDocumentAdapter,
)
from paperplane.openai_document import OpenAIDocumentAdapter, OpenAIRequestError
from paperplane.parser import MODEL_MODES, AgenticDocumentParser
from paperplane.pipeline import StructuredAdapter, V2PageProcessor

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
DEFAULT_XAI_BASE_URL = "https://api.x.ai"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180.0
MAX_BATCH_FILES = 20
MAX_BATCH_BYTES = 1024 * 1024 * 1024
MAX_BATCH_CONCURRENCY = 6


@lru_cache(maxsize=2)
def get_docling_parser(device: str = "auto") -> DoclingDocumentParser:
    """Reuse Docling's heavyweight converter and loaded models across Streamlit reruns."""

    fallback = None
    if device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                fallback = create_docling_converter("cpu")
        except ImportError:
            pass
    return DoclingDocumentParser(create_docling_converter(device), fallback)


@dataclass(frozen=True)
class BatchParseRequest:
    file_id: str
    data: bytes
    filename: str
    model: str
    api_key: str
    ai_model: str = DEFAULT_DOCUMENT_MODEL
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    strategy: ProcessingStrategy = "docling"
    page_start: int = 1
    page_end: int | None = None
    ollama_model: str = "glm-ocr:latest"
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL


@dataclass(frozen=True)
class BatchParseOutcome:
    file_id: str
    filename: str
    result: ParseResponse | None = None
    error: str | None = None


async def parse_document(
    *,
    data: bytes,
    filename: str,
    model: str,
    api_key: str,
    ai_model: str = DEFAULT_DOCUMENT_MODEL,
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL,
    strategy: ProcessingStrategy = "ai",
    page_start: int = 1,
    page_end: int | None = None,
    ollama_model: str = "glm-ocr:latest",
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> ParseResponse:
    """Parse one document without retaining a client, upload, or result."""
    if model not in MODEL_MODES:
        raise ValueError(f"Unsupported processing model: {model}")

    def cloud_adapter(client: httpx.AsyncClient, provider: str) -> StructuredAdapter:
        if provider == "agnes":
            return AgnesDocumentAdapter(client, api_key=api_key)
        if provider == "anthropic":
            return AnthropicDocumentAdapter(client, api_key=api_key)
        if provider == "google":
            return GeminiDocumentAdapter(client, api_key=api_key)
        if provider == "xai":
            return OpenAIDocumentAdapter(
                client,
                api_key=api_key,
                base_url=DEFAULT_XAI_BASE_URL,
                provider_name="xAI",
                explicit_prompt_cache=False,
                image_detail=False,
                minimum_reasoning_effort="low",
            )
        return OpenAIDocumentAdapter(client, api_key=api_key, base_url=openai_base_url)

    async with httpx.AsyncClient(timeout=DEFAULT_OPENAI_TIMEOUT_SECONDS) as client:
        adapter: StructuredAdapter
        if strategy == "ollama":
            adapter = OllamaDocumentAdapter(client, base_url=ollama_base_url)
            adapter_model = ollama_model
            key_name = "Ollama"
            parser_name = "ollama_vision"
        elif strategy == "ollama_ai":
            model_spec = get_document_model(ai_model)
            adapter = ChainedStructuredAdapter(
                OllamaDocumentAdapter(client, base_url=ollama_base_url),
                cloud_adapter(client, model_spec.provider),
                cloud_model=model_spec.model_id,
            )
            adapter_model = ollama_model
            key_name = model_spec.api_key_env
            parser_name = "ollama_vision"
        else:
            model_spec = get_document_model(ai_model)
            adapter_model = model_spec.model_id
            key_name = model_spec.api_key_env
            parser_name = f"{model_spec.provider}_vision"
            adapter = cloud_adapter(client, model_spec.provider)
        parser = AgenticDocumentParser(
            V2PageProcessor(adapter, model=adapter_model),
            get_docling_parser() if strategy in {"docling", "docling_ai"} else None,
            vision_enabled=(True if strategy == "ollama" else bool(api_key.strip())),
            vision_key_name=key_name,
            vision_parser=parser_name,
        )
        return await parser.parse(
            data=data,
            filename=filename,
            model=model,
            strategy=strategy,
            page_start=page_start,
            page_end=page_end,
        )


async def parse_documents(
    requests: list[BatchParseRequest],
    *,
    max_concurrency: int = MAX_BATCH_CONCURRENCY,
) -> list[BatchParseOutcome]:
    """Process an in-memory batch concurrently while isolating file failures."""

    if not requests:
        return []
    if len(requests) > MAX_BATCH_FILES:
        raise ValueError(f"A batch can contain at most {MAX_BATCH_FILES} files")
    if sum(len(request.data) for request in requests) > MAX_BATCH_BYTES:
        raise ValueError("Combined upload size exceeds 1 GiB")
    concurrency = max(1, min(max_concurrency, MAX_BATCH_CONCURRENCY))
    semaphore = asyncio.Semaphore(concurrency)

    async def run(request: BatchParseRequest) -> BatchParseOutcome:
        async with semaphore:
            try:
                result = await parse_document(
                    data=request.data,
                    filename=request.filename,
                    model=request.model,
                    api_key=request.api_key,
                    ai_model=request.ai_model,
                    openai_base_url=request.openai_base_url,
                    strategy=request.strategy,
                    page_start=request.page_start,
                    page_end=request.page_end,
                    ollama_model=request.ollama_model,
                    ollama_base_url=request.ollama_base_url,
                )
                return BatchParseOutcome(
                    file_id=request.file_id,
                    filename=request.filename,
                    result=result,
                )
            except (DocumentInputError, OpenAIRequestError, ValueError) as exc:
                return BatchParseOutcome(
                    file_id=request.file_id,
                    filename=request.filename,
                    error=str(exc),
                )
            except Exception:
                return BatchParseOutcome(
                    file_id=request.file_id,
                    filename=request.filename,
                    error="Parsing failed unexpectedly. Check the local logs.",
                )

    return list(await asyncio.gather(*(run(request) for request in requests)))


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_XAI_BASE_URL",
    "MAX_BATCH_BYTES",
    "MAX_BATCH_CONCURRENCY",
    "MAX_BATCH_FILES",
    "BatchParseOutcome",
    "BatchParseRequest",
    "get_docling_parser",
    "parse_document",
    "parse_documents",
]
