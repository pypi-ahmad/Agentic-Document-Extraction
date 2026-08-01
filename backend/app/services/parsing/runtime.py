"""Application-scoped resources for local parsing jobs."""

from __future__ import annotations

from contextlib import AsyncExitStack
from types import TracebackType

import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import settings
from app.services.extraction.graph import build_parser_graph
from app.services.parsing.engines import build_default_parser
from app.services.parsing.glmocr_layout_engine import GlmOcrLayoutEngine
from app.services.parsing.model_catalog import OllamaModelCatalog
from app.services.parsing.review import OllamaReviewer, ProviderReviewer
from app.services.parsing.vision_providers import VisionProviderRegistry


class ParserRuntime:
    """Own expensive engines and async resources for one FastAPI lifespan."""

    def __init__(
        self,
        *,
        checkpoint_path: str,
        ollama_base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.ollama_base_url = ollama_base_url
        self.timeout_seconds = timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._client: httpx.AsyncClient | None = None
        self._graph = None
        self._parser = None
        self._model_catalog: OllamaModelCatalog | None = None
        self._provider_registry: VisionProviderRegistry | None = None

    @property
    def model_catalog(self) -> OllamaModelCatalog:
        if self._model_catalog is None:
            raise RuntimeError("Parser runtime has not started")
        return self._model_catalog

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Parser runtime has not started")
        return self._client

    @property
    def provider_registry(self) -> VisionProviderRegistry:
        if self._provider_registry is None:
            raise RuntimeError("Parser runtime has not started")
        return self._provider_registry

    @property
    def graph(self):
        if self._graph is None:
            raise RuntimeError("Parser runtime has not started")
        return self._graph

    @property
    def parser(self):
        if self._parser is None:
            raise RuntimeError("Parser runtime has not started")
        return self._parser

    def reviewer(self, provider: str, model: str):
        if provider == "ollama":
            return OllamaReviewer(self.client, model)
        return ProviderReviewer(self.provider_registry, provider, model)

    async def __aenter__(self) -> ParserRuntime:
        if self._stack is not None:
            return self
        stack = AsyncExitStack()
        self._stack = stack
        self._client = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url=self.ollama_base_url.rstrip("/"), timeout=self.timeout_seconds
            )
        )
        cloud_client = await stack.enter_async_context(
            httpx.AsyncClient(timeout=self.timeout_seconds)
        )
        saver = await stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(self.checkpoint_path)
        )
        await saver.setup()
        self._model_catalog = OllamaModelCatalog(self._client)
        self._provider_registry = VisionProviderRegistry(
            cloud_client,
            self._model_catalog,
            settings,
        )
        layout_engine = GlmOcrLayoutEngine(cloud_client, settings.glmocr_server_url)
        parser = build_default_parser(self._provider_registry, layout_engine)
        self._parser = parser
        self._graph = build_parser_graph(
            parser,
            saver,
            lambda provider, model: (
                OllamaReviewer(self._client, model)
                if provider == "ollama"
                else ProviderReviewer(self._provider_registry, provider, model)
            ),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._graph = None
        self._parser = None
        self._model_catalog = None
        self._provider_registry = None
