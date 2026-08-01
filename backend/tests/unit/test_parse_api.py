from collections.abc import AsyncIterator

import fitz
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.models.db_models import (
    Artifact,
    Base,
    ExtractionSchema,
    PageCheckpoint,
    ParseJob,
    SubDocument,
)
from app.models.enums import ArtifactType, JobStatus
from app.routers.inspection import router as inspection_router
from app.routers.parse_jobs import get_job_queue, get_model_catalog, get_object_store, router
from app.services.parsing.model_catalog import OllamaModel

SENSITIVE_DIAGNOSTIC_VALUES = (
    "observation-content-attacker",
    "native-text-attacker",
    "page-rationale-attacker",
    "region-rationale-attacker",
    "attempt-output-attacker",
)


def _sensitive_diagnostics_payload() -> dict:
    score = {
        "extraction_accuracy": 0.9,
        "structural_fidelity": 0.8,
        "completeness": 0.7,
        "markdown_consistency": 1.0,
        "overall": 0.85,
        "reasons": ["safe-score-reason"],
    }
    plan = {
        "region_id": "p1-r1",
        "strategy": "specialist",
        "expert": "table",
        "difficulty": 0.8,
        "rationale": "region-rationale-attacker",
        "risk_flags": ["complex_structure"],
        "prompt_variant": "structure_repair",
    }
    return {
        "schema_version": "1",
        "planning_mode": "page_centric",
        "stage": "completed",
        "page_number": 1,
        "plan": {
            "page_number": 1,
            "source": "model",
            "regions": [plan],
            "rationale": "page-rationale-attacker",
            "warnings": ["safe-plan-warning"],
        },
        "region_decisions": [
            {
                "observation": {
                    "region_id": "p1-r1",
                    "region_type": "table",
                    "bbox": {"left": 0.1, "top": 0.2, "right": 0.8, "bottom": 0.9},
                    "content": "observation-content-attacker",
                    "native_text": "native-text-attacker",
                    "native_healthy": False,
                    "confidence": 0.75,
                    "risk_flags": ["low_contrast"],
                },
                "plan": plan,
                "attempts": [
                    {
                        "attempt": 1,
                        "strategy": "specialist",
                        "expert": "table",
                        "prompt_id": "table-expert",
                        "prompt_version": "1",
                        "prompt_variant": "structure_repair",
                        "output": "attempt-output-attacker",
                        "score": score,
                        "verdict": "pass",
                        "reason": "safe-verdict-reason",
                        "repair_hint": "safe-repair-hint",
                        "warnings": ["safe-warning"],
                        "latency_ms": 12.5,
                        "eval_count": 20,
                        "prompt_eval_count": 10,
                    }
                ],
                "selected_attempt_index": 0,
                "final_status": "pass",
            }
        ],
        "quality_score": score,
        "quality_status": "pass",
        "repair_count": 1,
        "warnings": ["safe-page-warning"],
        "fingerprint": "safe-fingerprint",
    }


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.delete_error: Exception | None = None

    def write(self, relative_path: str, data: bytes) -> str:
        self.values[relative_path] = data
        return relative_path

    def read(self, relative_path: str) -> bytes:
        return self.values[relative_path]

    def delete_tree(self, relative_path: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        for key in list(self.values):
            if key.startswith(relative_path.rstrip("/") + "/"):
                del self.values[key]


class CapturingQueue:
    def __init__(self, in_flight: int = 0) -> None:
        self.submitted: list[str] = []
        self.in_flight = in_flight

    async def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)


class CompatibleCatalog:
    async def require_compatible(self, name: str) -> OllamaModel:
        return OllamaModel(
            name=name,
            digest=f"digest-{name}",
            capabilities=["completion", "vision"],
            compatible=True,
        )


def _pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    value = document.tobytes()
    document.close()
    return value


@pytest.fixture
async def api() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], MemoryStore, CapturingQueue]
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    store = MemoryStore()
    queue = CapturingQueue()
    app = FastAPI()
    app.include_router(router)
    app.include_router(inspection_router)

    async def database() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_model_catalog] = CompatibleCatalog

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, sessions, store, queue
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_job_validates_and_queues_document(api) -> None:
    client, sessions, store, queue = api

    response = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={
            "settings": '{"ocr_model":"vision:one","review_model":"vision:two","layout_device":"cpu","bundle":false}'
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["page_count"] == 1
    assert queue.submitted == [payload["id"]]
    assert f"jobs/{payload['id']}/source.pdf" in store.values
    async with sessions() as session:
        job = await session.get(ParseJob, payload["id"])
        assert job is not None and len(job.pages) == 1


@pytest.mark.asyncio
async def test_create_job_snapshots_selected_extraction_schema(api) -> None:
    client, sessions, _, _ = api
    schema_json = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"invoice_number": {"type": "string"}},
        "additionalProperties": False,
    }
    async with sessions() as session:
        schema = ExtractionSchema(
            id="schema-one",
            name="Invoice",
            name_key="invoice",
            version=3,
            schema_json=schema_json,
            schema_sha256="c" * 64,
        )
        session.add(schema)
        await session.commit()

    response = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={
            "settings": (
                '{"ocr_model":"vision:one","layout_device":"cpu","bundle":false,'
                '"extraction_schema_id":"schema-one","extraction_provider":"ollama",'
                '"extraction_model":"qwen3.5:9b"}'
            )
        },
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["extraction_schema"] == {
        "id": "schema-one",
        "name": "Invoice",
        "version": 3,
        "schema_sha256": "c" * 64,
    }
    assert payload["extraction_model_name"] == "qwen3.5:9b"
    async with sessions() as session:
        job = await session.get(ParseJob, payload["id"])
        assert job is not None
        assert job.extraction_schema_snapshot["json_schema"] == schema_json
        assert job.extraction_model_digest == "digest-qwen3.5:9b"


@pytest.mark.asyncio
async def test_create_job_rejects_missing_extraction_schema(api) -> None:
    client, _, _, queue = api

    response = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={
            "settings": (
                '{"ocr_model":"vision:one","layout_device":"cpu",'
                '"extraction_schema_id":"missing","extraction_provider":"ollama",'
                '"extraction_model":"qwen3.5:9b"}'
            )
        },
    )

    assert response.status_code == 422
    assert queue.submitted == []


@pytest.mark.asyncio
async def test_create_job_accepts_legacy_layout_device_setting(api) -> None:
    client, _, store, queue = api

    response = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={
            "settings": '{"ocr_model":"vision:one","review_model":"vision:two","layout_device":"cuda"}'
        },
    )

    assert response.status_code == 202
    assert store.values
    assert len(queue.submitted) == 1


@pytest.mark.asyncio
async def test_create_job_rejects_when_queue_is_full(api, monkeypatch) -> None:
    client, _, _, queue = api
    monkeypatch.setattr("app.config.settings.job_queue_max_depth", 1)
    queue.in_flight = 1

    response = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"ocr_model":"vision:one","review_model":"vision:two"}'},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "queue_full"


@pytest.mark.asyncio
async def test_history_detail_and_cancel_transition(api) -> None:
    client, _, _, _ = api
    created = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"ocr_model":"vision:one","review_model":"vision:two"}'},
    )
    job_id = created.json()["id"]

    history = await client.get("/api/parse-jobs")
    detail = await client.get(f"/api/parse-jobs/{job_id}")
    cancelled = await client.post(f"/api/parse-jobs/{job_id}/cancel")

    assert history.json()["total"] == 1
    assert detail.json()["original_filename"] == "scan.pdf"
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_active_job_requests_cooperative_stop(api) -> None:
    client, sessions, _, _ = api
    created = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"ocr_model":"vision:one","review_model":"vision:two"}'},
    )
    job_id = created.json()["id"]
    async with sessions() as session:
        job = await session.get(ParseJob, job_id)
        assert job is not None
        job.status = JobStatus.PROCESSING
        await session.commit()

    response = await client.post(f"/api/parse-jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelling"
    async with sessions() as session:
        job = await session.get(ParseJob, job_id)
        assert job is not None and job.cancel_requested is True


@pytest.mark.asyncio
async def test_cancel_terminal_job_is_rejected(api) -> None:
    client, sessions, _, _ = api
    created = await client.post(
        "/api/parse-jobs",
        files={"file": ("scan.pdf", _pdf(), "application/pdf")},
        data={"settings": '{"ocr_model":"vision:one","review_model":"vision:two"}'},
    )
    job_id = created.json()["id"]
    async with sessions() as session:
        job = await session.get(ParseJob, job_id)
        assert job is not None
        job.status = JobStatus.COMPLETED
        await session.commit()

    response = await client.post(f"/api/parse-jobs/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_state"


@pytest.mark.asyncio
async def test_artifact_download_uses_attachment_headers(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        job = ParseJob(
            id="job",
            original_filename="scan.pdf",
            source_path="jobs/job/source.pdf",
            source_mime="application/pdf",
            source_size=1,
            source_sha256="a" * 64,
            page_count=1,
            status=JobStatus.COMPLETED,
            settings={},
        )
        job.artifacts.append(
            Artifact(
                id="artifact",
                type=ArtifactType.CLEAN_MARKDOWN,
                relative_path="jobs/job/document.md",
                mime_type="text/markdown",
                size=5,
                sha256="b" * 64,
            )
        )
        session.add(job)
        await session.commit()
    store.write("jobs/job/document.md", b"hello")

    response = await client.get("/api/parse-jobs/job/artifacts/clean_markdown")

    assert response.status_code == 200
    assert response.content == b"hello"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_artifact_contract_exposes_filename_and_inline_preview(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        job = ParseJob(
            id="job",
            original_filename="scan.pdf",
            source_path="jobs/job/source.pdf",
            source_mime="application/pdf",
            source_size=1,
            source_sha256="a" * 64,
            page_count=1,
            status=JobStatus.COMPLETED,
            settings={},
        )
        job.artifacts.append(
            Artifact(
                id="artifact",
                type=ArtifactType.GROUNDING_PDF,
                relative_path="jobs/job/artifacts/run/annotated.pdf",
                mime_type="application/pdf",
                size=5,
                sha256="b" * 64,
            )
        )
        session.add(job)
        await session.commit()
    store.write("jobs/job/artifacts/run/annotated.pdf", b"hello")

    detail = await client.get("/api/parse-jobs/job")
    preview = await client.get("/api/parse-jobs/job/artifacts/grounding_pdf?disposition=inline")

    artifact = detail.json()["artifacts"][0]
    assert artifact["filename"] == "annotated.pdf"
    assert artifact["preview_url"].endswith("disposition=inline")
    assert artifact["sha256"] == "b" * 64
    assert preview.headers["content-disposition"] == 'inline; filename="annotated.pdf"'


@pytest.mark.asyncio
async def test_subdocument_api_exposes_classification_and_scoped_artifacts(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        job = ParseJob(
            id="job",
            original_filename="mixed.pdf",
            source_path="jobs/job/source.pdf",
            source_mime="application/pdf",
            source_size=1,
            source_sha256="a" * 64,
            page_count=2,
            status=JobStatus.COMPLETED,
            settings={},
            segmentation_status="completed",
        )
        subdocument = SubDocument(
            id="subdoc",
            ordinal=1,
            start_page=1,
            end_page=2,
            profile="invoice",
            confidence=0.9,
            identifiers=[{"kind": "invoice_number", "normalized_value": "INV-1"}],
            boundary_confidence=1,
            boundary_reasons=["start_of_file"],
            complete=True,
            missing_pages=[],
            warnings=[],
        )
        subdocument.artifacts.append(
            Artifact(
                id="subartifact",
                job_id="job",
                type=ArtifactType.CLEAN_MARKDOWN,
                relative_path="jobs/job/subdocuments/subdoc/document.md",
                mime_type="text/markdown",
                size=5,
                sha256="b" * 64,
            )
        )
        job.subdocuments.append(subdocument)
        session.add(job)
        await session.commit()
    store.write("jobs/job/subdocuments/subdoc/document.md", b"hello")

    response = await client.get("/api/parse-jobs/job/sub-documents")
    download = await client.get("/api/parse-jobs/job/sub-documents/subdoc/artifacts/subartifact")

    assert response.status_code == 200
    assert response.json()["items"][0]["profile"] == "invoice"
    assert response.json()["items"][0]["artifacts"][0]["id"] == "subartifact"
    assert download.content == b"hello"


@pytest.mark.asyncio
async def test_zip_artifact_is_download_only(api) -> None:
    client, sessions, _, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                artifacts=[
                    Artifact(
                        id="bundle",
                        type=ArtifactType.BUNDLE,
                        relative_path="jobs/job/artifacts/run/document-bundle.zip",
                        mime_type="application/zip",
                        size=5,
                        sha256="b" * 64,
                    )
                ],
            )
        )
        await session.commit()

    detail = await client.get("/api/parse-jobs/job")

    assert detail.json()["artifacts"][0]["preview_url"] is None


@pytest.mark.asyncio
async def test_artifacts_are_ordered_for_primary_output_discovery(api) -> None:
    client, sessions, _, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                artifacts=[
                    Artifact(
                        id="bundle",
                        type=ArtifactType.BUNDLE,
                        relative_path="jobs/job/document-bundle.zip",
                        mime_type="application/zip",
                        size=1,
                        sha256="b" * 64,
                    ),
                    Artifact(
                        id="markdown",
                        type=ArtifactType.CLEAN_MARKDOWN,
                        relative_path="jobs/job/document.md",
                        mime_type="text/markdown",
                        size=1,
                        sha256="c" * 64,
                    ),
                    Artifact(
                        id="annotated",
                        type=ArtifactType.GROUNDING_PDF,
                        relative_path="jobs/job/annotated.pdf",
                        mime_type="application/pdf",
                        size=1,
                        sha256="d" * 64,
                    ),
                ],
            )
        )
        await session.commit()

    detail = await client.get("/api/parse-jobs/job")

    assert [item["type"] for item in detail.json()["artifacts"]] == [
        "grounding_pdf",
        "clean_markdown",
        "bundle",
    ]


@pytest.mark.asyncio
async def test_page_diagnostics_is_scoped_to_its_job(api) -> None:
    client, sessions, store, _ = api
    payload = {
        "planning_mode": "page_centric",
        "stage": "completed",
        "page_number": 1,
        "quality_status": "warn",
        "repair_count": 0,
        "warnings": [],
        "fingerprint": "abc",
    }
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        diagnostics_path="jobs/job/checkpoints/p0001/diagnostics.json",
                    )
                ],
            )
        )
        await session.commit()
    store.write(
        "jobs/job/checkpoints/p0001/diagnostics.json", __import__("json").dumps(payload).encode()
    )

    response = await client.get("/api/parse-jobs/job/pages/1/diagnostics")
    missing = await client.get("/api/parse-jobs/other/pages/1/diagnostics")

    assert response.status_code == 200 and response.json()["quality_status"] == "warn"
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_page_diagnostics_endpoint_redacts_internal_content_and_schema(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        diagnostics_path="jobs/job/checkpoints/p0001/diagnostics.json",
                    )
                ],
            )
        )
        await session.commit()
    store.write(
        "jobs/job/checkpoints/p0001/diagnostics.json",
        __import__("json").dumps(_sensitive_diagnostics_payload()).encode(),
    )

    response = await client.get("/api/parse-jobs/job/pages/1/diagnostics")
    schema = (await client.get("/openapi.json")).json()["components"]["schemas"]

    assert response.status_code == 200
    assert not any(value.encode() in response.content for value in SENSITIVE_DIAGNOSTIC_VALUES)
    body = response.json()
    assert body["region_decisions"][0]["attempts"][0]["prompt_id"] == "table-expert"
    assert body["region_decisions"][0]["attempts"][0]["reason"] == "safe-verdict-reason"
    assert set(schema["PublicRegionObservation"]["properties"]).isdisjoint(
        {"content", "native_text"}
    )
    assert "rationale" not in schema["PublicRegionPlan"]["properties"]
    assert "rationale" not in schema["PublicPagePlan"]["properties"]
    assert "output" not in schema["PublicAttemptRecord"]["properties"]


@pytest.mark.asyncio
async def test_page_diagnostics_rejects_checkpoint_path_from_another_job(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        diagnostics_path="jobs/other/checkpoints/p0001/diagnostics.json",
                    )
                ],
            )
        )
        await session.commit()
    store.write("jobs/other/checkpoints/p0001/diagnostics.json", b"{}")

    response = await client.get("/api/parse-jobs/job/pages/1/diagnostics")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_page_diagnostics_rejects_prefixed_traversal_path(api) -> None:
    client, sessions, store, _ = api
    malicious = "jobs/job/checkpoints/p0001/diagnostics.json/../../p0002/diagnostics.json"
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                pages=[PageCheckpoint(page_number=1, diagnostics_path=malicious)],
            )
        )
        await session.commit()
    store.write(malicious, b"{}")

    response = await client.get("/api/parse-jobs/job/pages/1/diagnostics")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_page_diagnostics_returns_safe_404_for_corrupt_payload(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        diagnostics_path="jobs/job/checkpoints/p0001/diagnostics.json",
                    )
                ],
            )
        )
        await session.commit()
    store.write("jobs/job/checkpoints/p0001/diagnostics.json", b'{"quality_status":"oops"}')

    response = await client.get("/api/parse-jobs/job/pages/1/diagnostics")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "diagnostics_not_found"


@pytest.mark.asyncio
async def test_inspection_endpoints_expose_job_scoped_source_layout_and_quality(api) -> None:
    client, sessions, store, _ = api
    layout_path = "jobs/job/checkpoints/p0001/layout.json"
    diagnostics_path = "jobs/job/checkpoints/p0001/diagnostics.json"
    layout = {
        "page_number": 1,
        "width": 200,
        "height": 300,
        "coordinate_unit": "pdf_points",
        "regions": [
            {
                "id": "p1-r1",
                "type": "text",
                "bbox": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
                "content": "Invoice number 42",
                "source": "cloud_vlm",
                "order": 0,
                "confidence": 0.82,
                "recognition_candidates": [
                    {
                        "source": "cloud_vlm",
                        "content": "Invoice number 47",
                        "model": "repair-model-1",
                    },
                    {
                        "source": "cloud_vlm",
                        "content": "Invoice number 42",
                        "model": "repair-model-2",
                        "selected": True,
                    },
                ],
            }
        ],
    }
    diagnostics = _sensitive_diagnostics_payload()
    diagnostics["region_decisions"][0]["observation"]["content"] = "Invoice number 42"
    diagnostics["region_decisions"][0]["attempts"][0]["output"] = "Invoice number 42"
    diagnostics["region_decisions"][0]["attempts"][0]["source"] = "cloud_vlm"
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="invoice.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={"ocr_model": "glm-ocr", "bundle": False},
                completed_pages=1,
                pages=[
                    PageCheckpoint(
                        page_number=1,
                        status="completed",
                        layout_path=layout_path,
                        diagnostics_path=diagnostics_path,
                    )
                ],
            )
        )
        await session.commit()
    import json

    source = _pdf()
    store.write("jobs/job/source.pdf", source)
    store.write(layout_path, json.dumps(layout).encode())
    store.write(diagnostics_path, json.dumps(diagnostics).encode())

    source_response = await client.get("/api/parse-jobs/job/source")
    image_response = await client.get("/api/parse-jobs/job/pages/1/image?dpi=150")
    inspection = await client.get("/api/parse-jobs/job/pages/1/inspection")
    tree = await client.get("/api/parse-jobs/job/document-tree?q=invoice")
    quality = await client.get("/api/parse-jobs/job/quality-report")

    assert source_response.content == source
    assert source_response.headers["content-disposition"].startswith("inline")
    assert image_response.headers["content-type"] == "image/png"
    assert inspection.json()["regions"][0]["candidates"][0]["output"] == "Invoice number 42"
    assert tree.json()["items"][0]["id"] == "p1-r1"
    assert quality.json()["ocr_coverage"]["ratio"] == 1.0
    assert quality.json()["disagreements"][0]["region_id"] == "p1-r1"


@pytest.mark.asyncio
async def test_delete_keeps_database_row_when_storage_delete_fails(api) -> None:
    client, sessions, store, _ = api
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=JobStatus.COMPLETED,
                settings={},
            )
        )
        await session.commit()
    store.delete_error = RuntimeError("secret filesystem detail")

    response = await client.delete("/api/parse-jobs/job")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "storage_delete_failed",
        "message": "Job files could not be deleted",
    }
    assert "secret filesystem detail" not in response.text
    async with sessions() as session:
        assert await session.get(ParseJob, "job") is not None
