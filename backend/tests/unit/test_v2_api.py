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


async def test_v2_pdf_artifact_preview_and_download_are_scoped_to_job(api) -> None:
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
                        id="annotated",
                        type="annotated_pdf",
                        relative_path="jobs-v2/job/annotated.pdf",
                        mime_type="application/pdf",
                        size=3,
                        sha256="b" * 64,
                    )
                ],
            )
        )
        await session.commit()
    store.write("jobs-v2/job/annotated.pdf", b"pdf")

    detail = await client.get("/api/v2/jobs/job")
    download = await client.get("/api/v2/jobs/job/artifacts/annotated")
    preview = await client.get("/api/v2/jobs/job/artifacts/annotated?disposition=inline")
    missing = await client.get("/api/v2/jobs/other/artifacts/annotated")

    artifact = detail.json()["artifacts"][0]
    assert artifact["download_url"] == "/api/v2/jobs/job/artifacts/annotated"
    assert artifact["preview_url"] == ("/api/v2/jobs/job/artifacts/annotated?disposition=inline")
    assert download.status_code == 200 and download.content == b"pdf"
    assert download.headers["content-disposition"] == 'attachment; filename="annotated.pdf"'
    assert preview.headers["content-disposition"] == 'inline; filename="annotated.pdf"'
    assert missing.status_code == 404


async def test_v2_source_preview_is_authenticated_and_inline(api) -> None:
    client, sessions, store, _ = api
    source = _pdf()
    async with sessions() as session:
        session.add(
            ParseJob(
                id="source-job",
                original_filename="scan.pdf",
                source_path="jobs-v2/source-job/source.pdf",
                source_mime="application/pdf",
                source_size=len(source),
                source_sha256="a" * 64,
                page_count=1,
                status="completed",
                settings={"mode": "balanced", "segment_documents": True},
            )
        )
        await session.commit()
    store.write("jobs-v2/source-job/source.pdf", source)

    job = await client.get("/api/v2/jobs/source-job")
    preview = await client.get("/api/v2/jobs/source-job/source")

    assert job.json()["source_preview_url"] == "/api/v2/jobs/source-job/source"
    assert preview.status_code == 200 and preview.content == source
    assert preview.headers["content-disposition"] == 'inline; filename="scan.pdf"'


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
        "schema_version": "paperplane-document/v3",
        "source": {
            "filename": "scan.pdf",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "page_count": 1,
        },
        "status": "completed",
        "quality_summary": {"verified_items": 1},
        "pages": [
            {
                "number": 1,
                "dimensions": {"width": 200, "height": 300, "unit": "pdf_points"},
                "verification_status": "verified",
                "markdown": "Hello",
                "items": [
                    {
                        "id": "p0001-c0001",
                        "order": 1,
                        "type": "text",
                        "text": "Hello",
                        "markdown_span": {"start": 0, "end": 5},
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
                        "verification": {
                            "status": "verified",
                            "model": "gpt-5.6-terra",
                            "pass": "page_reconciliation",
                        },
                    }
                ],
            }
        ],
        "processing": {"mode": "audit"},
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
                        type="json",
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
