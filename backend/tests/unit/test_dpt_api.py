from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.routers.dpt_api import _extraction_dependency
from app.services.agentic.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    NormalizedBox,
    assemble_parse_response,
)
from app.services.agentic.extraction import (
    AgenticSchemaExtractor,
    ExtractionCandidate,
    ExtractionRequest,
    SourceEvidence,
)


class FakeParser:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def parse(self, *, data: bytes, filename: str, model: str):
        self.calls.append({"data": data, "filename": filename, "model": model})
        return assemble_parse_response(
            document_id="document",
            job_id="request",
            model=model,
            pages=[
                AgenticPageInput(
                    page_number=1,
                    blocks=[
                        AgenticBlockInput(
                            type="text",
                            markdown="Invoice total: 42",
                            box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        )
                    ],
                )
            ],
        )


@pytest.mark.asyncio
async def test_parse_is_stateless_and_returns_result_immediately(monkeypatch) -> None:
    parser = FakeParser()
    app.state.agentic_parser = parser
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/parse",
            files={"file": ("invoice.pdf", b"document bytes", "application/pdf")},
            data={"model": "paperplane-ade-fast-latest"},
        )

    assert response.status_code == 200
    assert response.json()["metadata"]["model"] == "paperplane-ade-fast-latest"
    assert "Invoice total: 42" in response.json()["markdown"]
    assert parser.calls == [
        {
            "data": b"document bytes",
            "filename": "invoice.pdf",
            "model": "paperplane-ade-fast-latest",
        }
    ]


@pytest.mark.asyncio
async def test_parse_requires_openai_configuration(monkeypatch) -> None:
    app.state.agentic_parser = FakeParser()
    monkeypatch.setattr(settings, "openai_api_key", "")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/parse",
            files={"file": ("invoice.pdf", b"document bytes", "application/pdf")},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "openai_not_configured"


@pytest.mark.asyncio
async def test_persistence_routes_are_removed() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v2/parse" in paths
    assert "/v2/extract" in paths
    assert "/v2/parse/jobs" not in paths
    assert "/v2/extract/jobs" not in paths
    assert "/api/extraction-schemas" not in paths
    assert "/api/review-cases" not in paths


@pytest.mark.asyncio
async def test_extract_returns_grounded_schema_result() -> None:
    async def terra(request: ExtractionRequest) -> ExtractionCandidate:
        assert request.markdown == "Invoice total: 42"
        return ExtractionCandidate(
            value={"total": 42},
            evidence={"/total": [SourceEvidence(text="42")]},
        )

    app.dependency_overrides[_extraction_dependency] = lambda: AgenticSchemaExtractor(terra)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v2/extract",
                json={
                    "markdown": "Invoice total: 42",
                    "json_schema": {
                        "type": "object",
                        "properties": {"total": {"type": "number"}},
                        "required": ["total"],
                        "additionalProperties": False,
                    },
                },
            )
    finally:
        app.dependency_overrides.pop(_extraction_dependency, None)

    assert response.status_code == 200
    assert response.json()["extraction"] == {"total": 42}
    assert response.json()["extraction_metadata"]["total"]["ranges"] == [
        {"start": 15, "end": 17}
    ]
