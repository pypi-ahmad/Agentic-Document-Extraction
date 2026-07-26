"""Authenticated source, page, hierarchy, and quality inspection endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_db
from app.routers.parse_jobs import _error, _job_or_404, get_object_store
from app.services.parsing.inspection import (
    document_tree,
    page_inspection,
    quality_report,
    render_source_page,
)
from app.services.parsing.storage import ObjectStore

router = APIRouter(
    prefix="/api/parse-jobs",
    tags=["document-inspection"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{job_id}/source")
async def source_document(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    disposition: Literal["attachment", "inline"] = Query(default="inline"),
) -> Response:
    job = await _job_or_404(db, job_id)
    return Response(
        content=store.read(job.source_path),
        media_type=job.source_mime,
        headers={
            "Content-Disposition": f'{disposition}; filename="{Path(job.original_filename).name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{job_id}/pages/{page_number}/image")
async def source_page_image(
    job_id: str,
    page_number: int,
    dpi: Annotated[int, Query()] = 200,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> Response:
    job = await _job_or_404(db, job_id)
    if page_number < 1 or page_number > job.page_count:
        raise _error("page_not_found", "Page is outside the source document", 404)
    if dpi not in {150, 200, 300}:
        raise _error("invalid_dpi", "DPI must be 150, 200, or 300")
    try:
        image = render_source_page(job, page_number, dpi, store)
    except (KeyError, OSError, ValueError, RuntimeError):
        raise _error("page_render_failed", "Source page could not be rendered", 422) from None
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/{job_id}/pages/{page_number}/inspection")
async def inspect_page(
    job_id: str,
    page_number: int,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    job = await _job_or_404(db, job_id)
    try:
        return page_inspection(job, page_number, store)
    except (KeyError, OSError, ValueError):
        raise _error("inspection_not_found", "Page inspection is not available yet", 404) from None


@router.get("/{job_id}/document-tree")
async def inspect_document_tree(
    job_id: str,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    job = await _job_or_404(db, job_id)
    items = document_tree(job, store, q)
    return {"items": items[:limit], "total": len(items)}


@router.get("/{job_id}/quality-report")
async def inspect_quality_report(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    return quality_report(await _job_or_404(db, job_id), store)
