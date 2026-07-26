"""Approve corrected documents and export versioned evaluation datasets."""

from __future__ import annotations

import hashlib
import json
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings
from app.database import get_db
from app.models.db_models import CuratedDocument, CuratedExport, ParseJob
from app.models.enums import ArtifactType, JobStatus
from app.services.parsing.contracts import PageLayout
from app.services.parsing.storage import FileStore, ObjectStore

router = APIRouter(
    prefix="/api/curation", tags=["curation"], dependencies=[Depends(require_api_key)]
)


def get_store() -> ObjectStore:
    return FileStore(settings.artifacts_path)


class ApproveRequest(BaseModel):
    reviewer: str = Field(default="local_user", min_length=1, max_length=100)


class ExportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    document_ids: list[str] = Field(min_length=1, max_length=100)


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


@router.post("/documents/{job_id}/approve")
async def approve_document(
    job_id: str,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_store),
) -> dict[str, Any]:
    job = (
        await db.execute(
            select(ParseJob)
            .where(ParseJob.id == job_id)
            .options(
                selectinload(ParseJob.pages),
                selectinload(ParseJob.artifacts),
                selectinload(ParseJob.subdocuments),
                selectinload(ParseJob.review_cases),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise _error("job_not_found", "Parse job was not found", 404)
    if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}:
        raise _error("job_not_complete", "Only completed jobs can be curated", 409)
    if any(case.status == "open" for case in job.review_cases):
        raise _error("open_review_cases", "Resolve every open review case first", 409)
    corrections = {
        case.item_key: case.current for case in job.review_cases if case.status == "corrected"
    }
    pages = []
    for checkpoint in job.pages:
        if not checkpoint.layout_path:
            continue
        page = PageLayout.model_validate_json(store.read(checkpoint.layout_path))
        regions = []
        for order, region in enumerate(page.regions):
            corrected = corrections.get(region.id or "", {}).get("observation", {})
            value = region.model_copy(
                update={
                    key: corrected[key]
                    for key in ("content", "type", "bbox", "heading_level", "parent_id")
                    if key in corrected
                }
            )
            regions.append(
                {
                    "id": value.id or f"p{page.page_number}-r{order}",
                    "type": value.type,
                    "order": order,
                    "bbox": value.bbox.model_dump(mode="json"),
                    "text": value.content,
                    "heading_level": value.heading_level,
                    "parent_id": value.parent_id,
                    "table_cells": [cell.model_dump(mode="json") for cell in value.table_cells],
                }
            )
        pages.append({"page": page.page_number, "regions": regions})
    markdown_artifact = next(
        (item for item in job.artifacts if item.type == ArtifactType.CLEAN_MARKDOWN), None
    )
    markdown = store.read(markdown_artifact.relative_path).decode() if markdown_artifact else ""
    schema_artifact = next(
        (item for item in job.artifacts if item.type == ArtifactType.SCHEMA_EXTRACTION), None
    )
    schema_extractions = []
    if schema_artifact:
        schema_extractions = [json.loads(store.read(schema_artifact.relative_path))]
    label = {
        "schema_version": "paperplane-ground-truth/v3",
        "document_id": job.id,
        "source_sha256": job.source_sha256,
        "markdown": markdown,
        "pages": pages,
        "subdocuments": [
            {
                "start_page": item.start_page,
                "end_page": item.end_page,
                "profile": item.profile,
                "identifiers": {
                    value["kind"]: value["normalized_value"] for value in item.identifiers or []
                },
            }
            for item in job.subdocuments
        ],
        "schema_extractions": schema_extractions,
        "curation": {"reviewer": body.reviewer, "quality_policy": job.quality_policy_snapshot},
    }
    data = json.dumps(label, ensure_ascii=False, indent=2).encode()
    current = await db.scalar(select(CuratedDocument).where(CuratedDocument.job_id == job_id))
    revision = (current.revision + 1) if current else 1
    path = f"curation/documents/{job_id}/v{revision}.json"
    store.write(path, data)
    if current:
        current.revision, current.label_path = revision, path
        current.label_sha256 = hashlib.sha256(data).hexdigest()
        document = current
    else:
        document = CuratedDocument(
            id=uuid.uuid4().hex,
            job_id=job_id,
            revision=revision,
            status="approved",
            label_path=path,
            label_sha256=hashlib.sha256(data).hexdigest(),
        )
        db.add(document)
    await db.commit()
    return {
        "id": document.id,
        "job_id": job_id,
        "revision": revision,
        "label_sha256": document.label_sha256,
    }


@router.post("/exports")
async def create_export(
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_store),
) -> dict[str, Any]:
    documents = list(
        await db.scalars(
            select(CuratedDocument).where(
                CuratedDocument.id.in_(body.document_ids), CuratedDocument.status == "approved"
            )
        )
    )
    if len(documents) != len(set(body.document_ids)):
        raise _error("curated_document_missing", "Every selected document must be approved", 422)
    version = (
        int(
            await db.scalar(
                select(func.max(CuratedExport.version)).where(CuratedExport.name == body.name)
            )
            or 0
        )
        + 1
    )
    manifest = {
        "schema_version": "paperplane-eval-dataset/v2",
        "name": body.name,
        "version": version,
        "cases": [],
    }
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as bundle:
        for document in documents:
            job = await db.get(ParseJob, document.job_id)
            if job is None:
                raise _error("source_missing", "A curated source document was deleted", 409)
            suffix = Path(job.original_filename).suffix.lower()
            source_name, label_name = f"sources/{job.id}{suffix}", f"labels/{job.id}.json"
            bundle.writestr(source_name, store.read(job.source_path))
            bundle.writestr(label_name, store.read(document.label_path))
            manifest["cases"].append({"id": job.id, "source": source_name, "labels": label_name})
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    data = output.getvalue()
    export_id = uuid.uuid4().hex
    path = f"curation/exports/{export_id}.zip"
    store.write(path, data)
    record = CuratedExport(
        id=export_id,
        name=body.name,
        version=version,
        document_ids=body.document_ids,
        archive_path=path,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    db.add(record)
    await db.commit()
    return {
        "id": record.id,
        "name": body.name,
        "version": version,
        "sha256": record.sha256,
        "download_url": f"/api/curation/exports/{record.id}/download",
    }


@router.get("/exports")
async def list_exports(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    items = list(await db.scalars(select(CuratedExport).order_by(CuratedExport.created_at.desc())))
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "version": item.version,
                "sha256": item.sha256,
                "download_url": f"/api/curation/exports/{item.id}/download",
            }
            for item in items
        ]
    }


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: str, db: AsyncSession = Depends(get_db), store: ObjectStore = Depends(get_store)
) -> Response:
    item = await db.get(CuratedExport, export_id)
    if item is None:
        raise _error("export_not_found", "Curated export was not found", 404)
    return Response(
        store.read(item.archive_path),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{item.name}-v{item.version}.zip"'},
    )
