from collections.abc import AsyncIterator

import fitz
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.db_models import Artifact, Base, ExtractionSchema, ParseJob
from app.routers.v2_jobs import get_v2_queue, get_v2_store, router


class _MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, path: str, data: bytes) -> str:
        self.values[path] = data
        return path

    def read(self, path: str) -> bytes:
        return self.values[path]

    def delete_tree(self, path: str) -> None:
        for key in list(self.values):
            if key.startswith(path.rstrip("/") + "/"):
                del self.values[key]


class _Queue:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    async def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)


def _pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    result = document.tobytes()
    document.close()
    return result


@pytest.fixture
async def api(
    monkeypatch,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker, _MemoryStore, _Queue]]:
    monkeypatch.setattr("app.routers.v2_jobs.app_settings.openai_api_key", "sk-test")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _MemoryStore()
    queue = _Queue()
    app = FastAPI()
    app.include_router(router)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_v2_store] = lambda: store
    app.dependency_overrides[get_v2_queue] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, sessions, store, queue
    await engine.dispose()


async def test_create_v2_job_queues_openai_only_processing(api) -> None:
    client, sessions, store, queue = api

    response = await client.post(
        "/api/v2/jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"mode":"balanced","segment_documents":true}'},
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["settings"] == {
        "mode": "balanced",
        "segment_documents": True,
        "extraction_schema_id": None,
    }
    assert payload["models"] == {"draft": "gpt-5.6-luna", "verification": "gpt-5.6-terra"}
    assert payload["status"] == "queued"
    assert queue.submitted == [payload["id"]]
    assert f"jobs-v2/{payload['id']}/source.pdf" in store.values
    async with sessions() as session:
        job = await session.get(ParseJob, payload["id"])
        assert job is not None and job.model_name == "gpt-5.6-luna"


async def test_v2_job_rejects_missing_openai_configuration(api, monkeypatch) -> None:
    client, _, _, queue = api
    monkeypatch.setattr("app.routers.v2_jobs.app_settings.openai_api_key", "")

    response = await client.post(
        "/api/v2/jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"mode":"economy"}'},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "openai_not_configured"
    assert queue.submitted == []


async def test_v2_history_and_cancel_use_clean_contract(api) -> None:
    client, _, _, _ = api
    created = await client.post(
        "/api/v2/jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"mode":"audit"}'},
    )
    job_id = created.json()["id"]

    history = await client.get("/api/v2/jobs")
    cancelled = await client.post(f"/api/v2/jobs/{job_id}/cancel")

    assert [item["id"] for item in history.json()["items"]] == [job_id]
    assert cancelled.json()["status"] == "cancelled"


async def test_v2_artifact_download_is_scoped_to_job(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs-v2/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="completed",
                settings={"mode": "balanced", "segment_documents": True},
                artifacts=[
                    Artifact(
                        id="document",
                        type="document_json",
                        relative_path="jobs-v2/job/document.json",
                        mime_type="application/json",
                        size=2,
                        sha256="b" * 64,
                    )
                ],
            )
        )
        await session.commit()
    store.write("jobs-v2/job/document.json", b"{}")

    response = await client.get("/api/v2/jobs/job/artifacts/document")
    missing = await client.get("/api/v2/jobs/other/artifacts/document")

    assert response.status_code == 200 and response.content == b"{}"
    assert response.headers["content-disposition"] == 'attachment; filename="document.json"'
    assert missing.status_code == 404


async def test_v2_job_snapshots_schema_for_terra_extraction(api) -> None:
    client, sessions, _, _ = api
    schema_json = {
        "type": "object",
        "properties": {"invoice_number": {"type": "string"}},
        "required": ["invoice_number"],
        "additionalProperties": False,
    }
    async with sessions() as session:
        session.add(
            ExtractionSchema(
                id="invoice-schema",
                name="Invoice",
                name_key="invoice",
                version=1,
                schema_json=schema_json,
                schema_sha256="e" * 64,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v2/jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"mode":"audit","extraction_schema_id":"invoice-schema"}'},
    )

    assert response.status_code == 202, response.text
    async with sessions() as session:
        job = await session.get(ParseJob, response.json()["id"])
        assert job is not None
        assert job.extraction_schema_snapshot["json_schema"] == schema_json
        assert job.extraction_model_name == "gpt-5.6-terra"


async def test_v2_completed_job_can_be_evaluated_against_grounded_labels(api) -> None:
    client, sessions, store, _ = api
    predicted = {
        "schema_version": "paperplane-document/v2",
        "source_filename": "scan.pdf",
        "source_sha256": "a" * 64,
        "page_count": 1,
        "markdown": '<a id="p0001-c0001"></a>\n\nHello',
        "chunks": [
            {
                "id": "p0001-c0001",
                "page": 1,
                "order": 1,
                "type": "text",
                "text": "Hello",
                "markdown": "Hello",
                "grounding": [
                    {
                        "page": 1,
                        "box": {"left": 0.1, "top": 0.1, "right": 0.5, "bottom": 0.2},
                        "method": "vision_refined",
                        "source_box": [10, 10, 50, 20],
                        "source_unit": "image_pixels",
                        "evidence_artifact_id": "crop",
                    }
                ],
                "verification_status": "verified",
                "source_model": "gpt-5.6-terra",
                "source_pass": "crop_verification",
            }
        ],
    }
    encoded = __import__("json").dumps(predicted).encode()
    async with sessions() as session:
        session.add(
            ParseJob(
                id="eval-job",
                original_filename="scan.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="completed",
                settings={"mode": "audit", "segment_documents": True},
                artifacts=[
                    Artifact(
                        id="doc",
                        type="document_json",
                        relative_path="jobs-v2/eval-job/document.json",
                        mime_type="application/json",
                        size=len(encoded),
                        sha256="b" * 64,
                    )
                ],
            )
        )
        await session.commit()
    store.write("jobs-v2/eval-job/document.json", encoded)

    response = await client.post(
        "/api/v2/jobs/eval-job/evaluate",
        files={"labels": ("labels.json", encoded, "application/json")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["macro_score"] == 1.0
