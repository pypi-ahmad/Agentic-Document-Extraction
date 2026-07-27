from collections.abc import AsyncIterator

import fitz
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.db_models import Artifact, Base, ParseJob
from app.services.agentic.contracts import AgenticPageInput, assemble_parse_response
from app.services.agentic.extraction import AgenticSchemaExtractor, ExtractionCandidate


class RecordingQueue:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    async def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)


class CompletingQueue(RecordingQueue):
    def __init__(self, sessions, artifacts_dir) -> None:
        super().__init__()
        self.sessions = sessions
        self.artifacts_dir = artifacts_dir

    async def submit(self, job_id: str) -> None:
        await super().submit(job_id)
        result = (
            assemble_parse_response(
                document_id=job_id,
                job_id=job_id,
                model="paperplane-ade-latest",
                pages=[AgenticPageInput(page_number=1)],
            )
            .model_dump_json()
            .encode()
        )
        relative_path = f"jobs-v2/{job_id}/document.json"
        target = self.artifacts_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result)
        async with self.sessions() as session:
            job = await session.get(ParseJob, job_id)
            assert job is not None
            job.status = "completed"
            job.completed_pages = 1
            session.add(
                Artifact(
                    job_id=job_id,
                    type="json",
                    relative_path=relative_path,
                    mime_type="application/json",
                    size=len(result),
                    sha256="b" * 64,
                )
            )
            await session.commit()


def _pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    value = document.tobytes()
    document.close()
    return value


def test_public_parse_and_extract_paths_are_mounted_without_api_prefix() -> None:
    paths = app.openapi()["paths"]

    assert "/v2/parse" in paths
    assert "/v2/parse/jobs" in paths
    assert "/v2/extract" in paths
    assert "/v2/extract/jobs" in paths
    assert "/api/v2/jobs" not in paths


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer local-secret"},
        {"X-API-Key": "local-secret"},
    ],
)
async def test_auth_accepts_bearer_and_legacy_api_key(monkeypatch, headers) -> None:
    monkeypatch.setattr("app.auth.settings.api_key", "local-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v2/parse/jobs", headers=headers)

    assert response.status_code != 401


async def test_auth_rejects_missing_credentials_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.auth.settings.api_key", "local-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v2/parse/jobs")

    assert response.status_code == 401


async def test_parse_job_uses_model_alias_and_hides_legacy_history(monkeypatch, tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="legacy",
                original_filename="old.pdf",
                source_path="old.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                settings={"mode": "balanced"},
            )
        )
        await session.commit()

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    queue = RecordingQueue()
    monkeypatch.setattr("app.config.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("app.config.settings.artifacts_dir", str(tmp_path))
    monkeypatch.setattr("app.routers.dpt_api.get_v2_job_queue", lambda: queue, raising=False)
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/v2/parse/jobs",
                files={"file": ("scan.pdf", _pdf(), "application/pdf")},
                data={"model": "paperplane-ade-latest"},
            )
            history = await client.get("/v2/parse/jobs?page=1&page_size=1")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        await engine.dispose()

    assert created.status_code == 202, created.text
    payload = created.json()
    assert payload["model"] == "paperplane-ade-latest"
    assert payload["settings"] == {"model": "paperplane-ade-latest"}
    assert payload["models"] == {"parser": "gpt-5.6-luna", "critic": "gpt-5.6-terra"}
    assert queue.submitted == [payload["id"]]
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert [item["id"] for item in history.json()["items"]] == [payload["id"]]


async def test_parse_job_rejects_unknown_model_before_queueing(monkeypatch) -> None:
    queue = RecordingQueue()
    monkeypatch.setattr("app.config.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("app.routers.dpt_api.get_v2_job_queue", lambda: queue, raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/parse/jobs",
            files={"file": ("scan.pdf", _pdf(), "application/pdf")},
            data={"model": "gpt-5.6-luna"},
        )

    assert response.status_code == 422
    assert queue.submitted == []


async def test_synchronous_parse_returns_completed_grounded_result(monkeypatch, tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    queue = CompletingQueue(sessions, tmp_path)
    monkeypatch.setattr("app.config.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("app.config.settings.artifacts_dir", str(tmp_path))
    monkeypatch.setattr("app.routers.dpt_api.get_v2_job_queue", lambda: queue)
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v2/parse",
                files={"file": ("scan.pdf", _pdf(), "application/pdf")},
                data={"model": "paperplane-ade-latest"},
            )
            job_response = await client.get(f"/v2/parse/jobs/{queue.submitted[0]}")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        await engine.dispose()

    assert response.status_code == 200, response.text
    assert response.json()["metadata"]["job_id"] == queue.submitted[0]
    assert response.json()["structure"]["type"] == "document"
    assert job_response.json()["result"]["metadata"]["job_id"] == queue.submitted[0]


async def test_non_strict_extract_returns_partial_grounded_candidate(monkeypatch) -> None:
    async def terra(_request):  # type: ignore[no-untyped-def]
        return ExtractionCandidate(value={"count": "two"})

    monkeypatch.setattr(
        "app.routers.dpt_api.get_agentic_extractor",
        lambda: AgenticSchemaExtractor(terra),
        raising=False,
    )
    request = {
        "markdown": "Count: two",
        "json_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        },
        "strict": False,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v2/extract", json=request)

    assert response.status_code == 206, response.text
    assert response.json()["extraction"] == {"count": "two"}
    assert response.json()["extraction_metadata"]["count"] == {
        "value": "two",
        "ranges": [{"start": 7, "end": 10}],
    }
    assert response.json()["schema_violation_error"]


async def test_strict_extract_maps_schema_violation_to_422(monkeypatch) -> None:
    async def terra(_request):  # type: ignore[no-untyped-def]
        return ExtractionCandidate(value={"count": "two"})

    monkeypatch.setattr(
        "app.routers.dpt_api.get_agentic_extractor",
        lambda: AgenticSchemaExtractor(terra),
        raising=False,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/extract",
            json={
                "markdown": "Count: two",
                "json_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "schema_violation"


async def test_async_extract_job_persists_real_completion(monkeypatch, tmp_path) -> None:
    async def terra(_request):  # type: ignore[no-untyped-def]
        return ExtractionCandidate(value={"customer": "Ada"})

    monkeypatch.setattr("app.config.settings.artifacts_dir", str(tmp_path))
    monkeypatch.setattr(
        "app.routers.dpt_api.get_agentic_extractor",
        lambda: AgenticSchemaExtractor(terra),
        raising=False,
    )
    request = {
        "markdown": "Customer: Ada",
        "json_schema": {
            "type": "object",
            "properties": {"customer": {"type": "string"}},
            "required": ["customer"],
            "additionalProperties": False,
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/v2/extract/jobs", json=request)
        job = await client.get(f"/v2/extract/jobs/{created.json()['id']}")

    assert created.status_code == 202, created.text
    assert created.json()["status"] == "queued"
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["result"]["extraction"] == {"customer": "Ada"}
