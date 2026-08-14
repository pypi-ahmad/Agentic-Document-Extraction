"""Shared test fixtures."""

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TESTING"] = "1"

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
