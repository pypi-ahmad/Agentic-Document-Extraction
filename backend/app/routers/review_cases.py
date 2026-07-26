"""Human review queue and immutable correction decisions."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.database import get_db
from app.models.db_models import ReviewCase, ReviewDecision

router = APIRouter(
    prefix="/api/review-cases",
    tags=["review-cases"],
    dependencies=[Depends(require_api_key)],
)


class ReviewDecisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    action: Literal["accept", "correct", "dismiss"]
    corrected: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=4000)
    reviewer: str = Field(default="local_user", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_correction(self):
        if self.action == "correct" and self.corrected is None:
            raise ValueError("corrected is required when action=correct")
        return self


class ReviewCaseResponse(BaseModel):
    id: str
    job_id: str
    item_kind: str
    item_key: str
    page_number: int | None
    severity: str
    status: str
    failure_codes: list[str]
    original: dict[str, Any]
    current: dict[str, Any]
    provenance: dict[str, Any]
    revision: int
    created_at: str | None
    resolved_at: str | None
    decisions: list[dict[str, Any]] = Field(default_factory=list)


def _serialize(case: ReviewCase) -> ReviewCaseResponse:
    return ReviewCaseResponse(
        id=case.id,
        job_id=case.job_id,
        item_kind=case.item_kind,
        item_key=case.item_key,
        page_number=case.page_number,
        severity=case.severity,
        status=case.status,
        failure_codes=case.failure_codes or [],
        original=case.original,
        current=case.current,
        provenance=case.provenance or {},
        revision=case.revision,
        created_at=case.created_at.isoformat() if case.created_at else None,
        resolved_at=case.resolved_at.isoformat() if case.resolved_at else None,
        decisions=[
            {
                "revision": item.revision,
                "action": item.action,
                "corrected": item.corrected,
                "note": item.note,
                "reviewer": item.reviewer,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in case.decisions
        ],
    )


async def _case(db: AsyncSession, case_id: str) -> ReviewCase:
    case = (
        await db.execute(
            select(ReviewCase)
            .where(ReviewCase.id == case_id)
            .options(selectinload(ReviewCase.decisions))
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(
            404, detail={"code": "review_case_not_found", "message": "Review case was not found"}
        )
    return case


@router.get("")
async def list_review_cases(
    status: str | None = Query(default="open"),
    job_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    filters = []
    if status:
        filters.append(ReviewCase.status == status)
    if job_id:
        filters.append(ReviewCase.job_id == job_id)
    query = select(ReviewCase).where(*filters).options(selectinload(ReviewCase.decisions))
    items = list(await db.scalars(query.order_by(ReviewCase.created_at.desc()).limit(limit)))
    total = int(await db.scalar(select(func.count(ReviewCase.id)).where(*filters)) or 0)
    return {"items": [_serialize(item) for item in items], "total": total}


@router.get("/{case_id}", response_model=ReviewCaseResponse)
async def get_review_case(case_id: str, db: AsyncSession = Depends(get_db)):
    return _serialize(await _case(db, case_id))


@router.post("/{case_id}/decisions", response_model=ReviewCaseResponse)
async def decide_review_case(
    case_id: str, body: ReviewDecisionRequest, db: AsyncSession = Depends(get_db)
):
    case = await _case(db, case_id)
    if case.status != "open":
        raise HTTPException(
            409, detail={"code": "review_case_closed", "message": "Review case is already closed"}
        )
    if case.revision != body.expected_revision:
        raise HTTPException(
            409,
            detail={"code": "stale_revision", "message": "Review case changed; refresh and retry"},
        )
    case.revision += 1
    case.current = body.corrected if body.action == "correct" else case.original
    case.status = {"accept": "accepted", "correct": "corrected", "dismiss": "dismissed"}[
        body.action
    ]
    case.resolved_at = dt.datetime.now(dt.UTC)
    case.decisions.append(
        ReviewDecision(
            id=uuid.uuid4().hex,
            revision=case.revision,
            action=body.action,
            corrected=body.corrected,
            note=body.note,
            reviewer=body.reviewer,
        )
    )
    await db.commit()
    return _serialize(await _case(db, case_id))
