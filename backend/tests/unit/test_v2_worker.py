import hashlib
import json
from io import BytesIO

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.models.db_models import Artifact, Base, PageCheckpoint, ParseJob
from app.services.parsing.contracts import BoundingBox
from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.v2_contracts import (
    ExtractionField,
    GroundedChunk,
    Grounding,
    GroundingMethod,
    VerificationStatus,
)
from app.services.parsing.v2_pipeline import PageResult
from app.services.parsing.v2_schema_extraction import ExtractionOutcome
from app.services.v2_tasks import V2TaskLeases
from app.services.v2_worker import V2PageTaskRunner


class _Store:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, path: str, data: bytes) -> str:
        self.values[path] = data
        return path

    def read(self, path: str) -> bytes:
        return self.values[path]

    def delete_tree(self, path: str) -> None:
        raise NotImplementedError


class _Processor:
    async def process_page(self, **kwargs) -> PageResult:
        page = kwargs["page"]
        chunk = GroundedChunk(
            id=f"p{page.page_number:04d}-c0001",
            page=page.page_number,
            order=1,
            type="text",
            text="Invoice Number INV-42",
            markdown="Invoice Number INV-42",
            grounding=[
                Grounding(
                    page=page.page_number,
                    box=BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2),
                    method=GroundingMethod.VISION_REFINED,
                    source_box=(10, 10, 80, 20),
                    source_unit="image_pixels",
                    evidence_artifact_id="page-evidence",
                )
            ],
            verification_status=VerificationStatus.VERIFIED,
            source_model="gpt-5.6-terra",
            source_pass="crop_verification",
        )
        return PageResult(
            page_number=page.page_number,
            chunks=[chunk],
            markdown=f'<a id="{chunk.id}"></a>\n\n{chunk.markdown}',
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=50,
        )


class _Extractor:
    async def extract(self, **kwargs) -> ExtractionOutcome:
        return ExtractionOutcome(
            fields={
                "invoice_number": ExtractionField(
                    value="INV-42",
                    status="grounded",
                    citations=["p0001-c0001"],
                )
            },
            structured_data={"invoice_number": "INV-42"},
            usage=OpenAIUsage(input_tokens=20, output_tokens=5),
        )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


async def test_runner_persists_page_and_assembles_auditable_artifacts() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    source = _png()
    store.write("jobs-v2/job/source.png", source)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=len(source),
                source_sha256=hashlib.sha256(source).hexdigest(),
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
                extraction_schema_snapshot={
                    "json_schema": {
                        "type": "object",
                        "properties": {"invoice_number": {"type": "string"}},
                        "required": ["invoice_number"],
                        "additionalProperties": False,
                    }
                },
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker-1", lease_seconds=30)
    assert task is not None

    runner = V2PageTaskRunner(sessions, store, _Processor(), leases, extractor=_Extractor())
    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.scalar(
            select(ParseJob)
            .where(ParseJob.id == "job")
            .options(selectinload(ParseJob.artifacts), selectinload(ParseJob.pages))
        )
        assert job is not None
        assert job.status == "completed"
        assert job.completed_pages == 1
        assert job.quality_policy_snapshot["usage"]["input_tokens"] == 120
        assert job.pages[0].layout_path == "jobs-v2/job/pages/p0001.json"
        assert {artifact.type for artifact in job.artifacts} >= {
            "document_json",
            "clean_markdown",
            "usage",
            "annotated_pdf",
        }
    document = json.loads(store.values["jobs-v2/job/document.json"])
    assert document["chunks"][0]["grounding"][0]["method"] == "vision_refined"
    assert document["splits"][0]["identifier"] == "INV-42"
    assert document["usage"]["cached_input_tokens"] == 50
    assert document["extraction"]["invoice_number"]["value"] == "INV-42"
    assert document["usage"]["input_tokens"] == 120
    assert any(isinstance(item, Artifact) for item in job.artifacts)
    await engine.dispose()
