import uuid
from pathlib import Path

import pytest

from app.services.parsing.runtime import ParserRuntime


@pytest.mark.asyncio
async def test_parser_runtime_reuses_graph_and_closes_http_client() -> None:
    checkpoint = Path("backend/tests/_test_uploads") / f"runtime-{uuid.uuid4().hex}.sqlite"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    runtime = ParserRuntime(
        checkpoint_path=str(checkpoint),
        ollama_base_url="http://localhost:11434",
        timeout_seconds=1,
    )

    try:
        async with runtime:
            graph = runtime.graph
            assert runtime.graph is graph
            assert runtime.client.is_closed is False

        assert runtime.client.is_closed is True
    finally:
        checkpoint.unlink(missing_ok=True)
