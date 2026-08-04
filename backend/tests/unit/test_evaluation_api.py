import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.db_models import Artifact, Base, PageCheckpoint, ParseJob
from app.models.enums import ArtifactType, JobStatus, PageStatus
from app.models.schemas import ParseSettings
from app.routers import evaluation_runs
from app.services.parsing.contracts import BoundingBox, PageLayout, Region


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, path: str, data: bytes) -> str:
        self.values[path] = data
        return path

    def read(self, path: str) -> bytes:
        return self.values[path]

    def delete_tree(self, path: str) -> None:
        return None


@pytest.mark.asyncio
async def test_completed_job_can_be_evaluated_against_grounded_labels(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = MemoryStore()
    layout = PageLayout(
        page_number=1,
        width=1,
        height=1,
        regions=[
            Region(
                id="body",
                type="text",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.5),
                content="Hello",
            )
        ],
    )
    store.write("layout.json", layout.model_dump_json().encode())
    store.write("document.md", b"Hello\n")
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job1",
                original_filename="sample.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings=ParseSettings().model_dump(mode="json"),
                pages=[
                    PageCheckpoint(
                        page_number=1, status=PageStatus.COMPLETED, layout_path="layout.json"
                    )
                ],
                artifacts=[
                    Artifact(
                        job_id="job1",
                        type=ArtifactType.CLEAN_MARKDOWN,
                        relative_path="document.md",
                        mime_type="text/markdown",
                        size=6,
                        sha256="b" * 64,
                    )
                ],
            )
        )
        await session.commit()

    async def db_override() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app = FastAPI()
    app.include_router(evaluation_runs.router)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[evaluation_runs.get_object_store] = lambda: store
    monkeypatch.setattr(evaluation_runs, "async_session", sessions)
    gold = {
        "schema_version": "paperplane-ground-truth/v1",
        "document_id": "sample",
        "source_sha256": "a" * 64,
        "markdown": "Hello\n",
        "pages": [
            {
                "page": 1,
                "regions": [
                    {
                        "id": "body",
                        "type": "text",
                        "order": 0,
                        "bbox": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.5},
                        "text": "Hello",
                    }
                ],
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/evaluation-runs/from-job/job1",
            files={"gold": ("gold.json", json.dumps(gold), "application/json")},
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["metrics"]["macro_score"] == 1.0
    assert payload["cases"][0]["status"] == "completed"
    await engine.dispose()
