from collections.abc import AsyncIterator

import fitz
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.db_models import Base, PageCheckpoint, ParseJob, ReprocessRun
from app.models.enums import JobStatus
from app.routers.parse_jobs import get_job_queue, get_object_store
from app.routers.reprocessing import router
from app.services.parsing.storage import FileStore


class Queue:
    in_flight = 0

    def __init__(self) -> None:
        self.ids: list[str] = []

    async def submit(self, job_id: str) -> None:
        self.ids.append(job_id)


def pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    value = document.tobytes()
    document.close()
    return value


def layout() -> bytes:
    return b"""{
      "page_number": 1, "width": 200, "height": 300,
      "coordinate_unit": "pdf_points",
      "regions": [{
        "id": "p0001-r0001", "type": "text",
        "bbox": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
        "content": "old", "source": "cloud_vlm", "order": 0, "confidence": 0.7
      }]
    }"""


@pytest.fixture
async def reprocess_api(
    tmp_path,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], FileStore, Queue]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store, queue = FileStore(tmp_path), Queue()
    app = FastAPI()
    app.state.parser_runtime = object()
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
async def test_region_reprocess_is_queued_with_durable_parameters_and_backups(
    reprocess_api,
) -> None:
    client, sessions, store, queue = reprocess_api
    source_path = "jobs/job/source.pdf"
    layout_path = "jobs/job/checkpoints/p0001/layout.json"
    diagnostics_path = "jobs/job/checkpoints/p0001/diagnostics.json"
    store.write(source_path, pdf())
    store.write(layout_path, layout())
    store.write(diagnostics_path, b"{}")
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path=source_path,
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={"ocr_model": "glm-ocr", "dpi": 200},
                completed_pages=1,
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        status="completed",
                        layout_path=layout_path,
                        diagnostics_path=diagnostics_path,
                        fingerprint="before",
                    )
                ],
            )
        )
        await session.commit()

    response = await client.post(
        "/api/parse-jobs/job/reprocess",
        json={
            "target_kind": "region",
            "page_number": 1,
            "region_id": "p0001-r0001",
            "dpi": 300,
            "crop_padding": 0.2,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["crop_padding"] == 0.2
    assert queue.ids == ["job"]
    assert any(path.name == "before-layout.json" for path in store.root.rglob("*.json"))
    run_id = response.json()["id"]
    detail = await client.get(f"/api/parse-jobs/job/reprocess-runs/{run_id}")
    assert detail.json()["previous_fingerprint"] == "before"
    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None and job.status == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_page_reprocess_marks_only_target_page_pending(reprocess_api) -> None:
    client, sessions, store, _ = reprocess_api
    source_path = "jobs/job/source.pdf"
    layout_path = "jobs/job/checkpoints/p0001/layout.json"
    store.write(source_path, pdf())
    store.write(layout_path, layout())
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path=source_path,
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={"ocr_model": "glm-ocr", "dpi": 200},
                completed_pages=1,
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        status="completed",
                        layout_path=layout_path,
                        fingerprint="before",
                    )
                ],
            )
        )
        await session.commit()
    response = await client.post(
        "/api/parse-jobs/job/reprocess",
        json={"target_kind": "page", "page_number": 1, "dpi": 300},
    )
    assert response.status_code == 202
    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.pages[0].status == "pending"
        assert job.settings["dpi"] == 300


def test_reprocess_run_model_is_linked_to_job() -> None:
    assert ParseJob.reprocess_runs.property.mapper.class_ is ReprocessRun
