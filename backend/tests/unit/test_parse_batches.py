import io
import json
from collections.abc import AsyncIterator
from zipfile import ZipFile

import fitz
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.db_models import Artifact, Base, ParseBatch, ParseJob
from app.models.enums import ArtifactType, JobStatus
from app.routers.parse_batches import router
from app.routers.parse_jobs import get_job_queue, get_object_store


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, relative_path: str, data: bytes) -> str:
        self.values[relative_path] = data
        return relative_path

    def read(self, relative_path: str) -> bytes:
        return self.values[relative_path]

    def delete_tree(self, relative_path: str) -> None:
        for key in list(self.values):
            if key.startswith(relative_path.rstrip("/") + "/"):
                del self.values[key]


class Queue:
    in_flight = 0

    def __init__(self) -> None:
        self.ids: list[str] = []

    async def submit(self, job_id: str) -> None:
        self.ids.append(job_id)


def pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 40), text)
    value = document.tobytes()
    document.close()
    return value


@pytest.fixture
async def batch_api() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryStore, Queue]
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store, queue = MemoryStore(), Queue()
    app = FastAPI()
    app.include_router(router)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_job_queue] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, sessions, store, queue
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_upload_persists_jobs_and_exports_completed_bundles(batch_api) -> None:
    client, sessions, store, queue = batch_api
    response = await client.post(
        "/api/parse-batches",
        files=[
            ("files", ("one.pdf", pdf("one"), "application/pdf")),
            ("files", ("two.pdf", pdf("two"), "application/pdf")),
        ],
        data={"settings": json.dumps({"bundle": True})},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["total_jobs"] == 2
    assert len(queue.ids) == 2

    async with sessions() as session:
        batch = (
            await session.execute(
                select(ParseBatch)
                .where(ParseBatch.id == payload["id"])
                .options(selectinload(ParseBatch.jobs).selectinload(ParseJob.artifacts))
            )
        ).scalar_one()
        first, second = batch.jobs
        first.status = JobStatus.COMPLETED
        second.status = JobStatus.FAILED
        second.error_code = "ocr_failed"
        bundle_path = f"jobs/{first.id}/artifacts/run/document-bundle.zip"
        bundle_data = b"document archive"
        store.write(bundle_path, bundle_data)
        first.artifacts.append(
            Artifact(
                job_id=first.id,
                type=ArtifactType.BUNDLE,
                relative_path=bundle_path,
                mime_type="application/zip",
                size=len(bundle_data),
                sha256="a" * 64,
            )
        )
        await session.commit()

    detail = await client.get(f"/api/parse-batches/{payload['id']}")
    archive_response = await client.get(f"/api/parse-batches/{payload['id']}/bundle")
    assert detail.json()["status"] == "completed_with_warnings"
    assert detail.json()["bundle_ready"] is True
    assert archive_response.status_code == 200
    with ZipFile(io.BytesIO(archive_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["documents"]) == 2
        assert manifest["documents"][1]["error_code"] == "ocr_failed"
        assert any(name.endswith("document-bundle.zip") for name in archive.namelist())


@pytest.mark.asyncio
async def test_batch_upload_rejects_invalid_member_before_persisting(batch_api) -> None:
    client, sessions, store, queue = batch_api
    response = await client.post(
        "/api/parse-batches",
        files=[
            ("files", ("good.pdf", pdf("good"), "application/pdf")),
            ("files", ("bad.exe", b"not a document", "application/octet-stream")),
        ],
        data={"settings": "{}"},
    )
    assert response.status_code == 422
    async with sessions() as session:
        assert list(await session.scalars(select(ParseBatch))) == []
    assert store.values == {}
    assert queue.ids == []
