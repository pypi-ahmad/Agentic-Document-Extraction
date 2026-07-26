"""Create idempotent, auditable human-review cases from quality diagnostics."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import ReviewCase
from app.services.parsing.agentic_contracts import PageDiagnostics


async def sync_page_review_cases(
    session: AsyncSession,
    job_id: str,
    diagnostics: PageDiagnostics,
    policy: dict | None,
) -> None:
    for decision in diagnostics.region_decisions:
        if decision.final_status == "pass":
            await _supersede(session, job_id, decision.observation.region_id)
            continue
        selected = decision.attempts[decision.selected_attempt_index]
        original = {
            "observation": decision.observation.model_dump(mode="json"),
            "plan": decision.plan.model_dump(mode="json"),
            "selected_attempt": selected.model_dump(mode="json"),
            "visual_verification": (
                decision.visual_verification.model_dump(mode="json")
                if decision.visual_verification
                else None
            ),
        }
        failure_codes = sorted({*decision.observation.risk_flags, *selected.warnings})
        if not failure_codes:
            failure_codes = [selected.reason or decision.final_status.value]
        fingerprint = hashlib.sha256(
            json.dumps(
                [job_id, "region", decision.observation.region_id, original, policy],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        exists = await session.scalar(
            select(ReviewCase.id).where(ReviewCase.fingerprint == fingerprint)
        )
        if exists:
            continue
        await _supersede(session, job_id, decision.observation.region_id)
        session.add(
            ReviewCase(
                id=uuid.uuid4().hex,
                job_id=job_id,
                item_kind="region",
                item_key=decision.observation.region_id,
                page_number=diagnostics.page_number,
                severity=decision.final_status.value,
                failure_codes=failure_codes,
                original=original,
                current=original,
                provenance={
                    "diagnostics_fingerprint": diagnostics.fingerprint,
                    "policy": policy,
                    "repair_count": diagnostics.repair_count,
                },
                fingerprint=fingerprint,
            )
        )


async def sync_grounded_review_case(
    session: AsyncSession,
    *,
    job_id: str,
    item_kind: str,
    item_key: str,
    original: dict,
    failure_codes: list[str],
    policy: dict | None,
    page_number: int | None = None,
) -> None:
    fingerprint = hashlib.sha256(
        json.dumps(
            [job_id, item_kind, item_key, original, failure_codes, policy],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if await session.scalar(select(ReviewCase.id).where(ReviewCase.fingerprint == fingerprint)):
        return
    await _supersede(session, job_id, item_key)
    session.add(
        ReviewCase(
            id=uuid.uuid4().hex,
            job_id=job_id,
            item_kind=item_kind,
            item_key=item_key,
            page_number=page_number,
            severity="fail",
            failure_codes=failure_codes,
            original=original,
            current=original,
            provenance={"policy": policy},
            fingerprint=fingerprint,
        )
    )


async def _supersede(session: AsyncSession, job_id: str, item_key: str) -> None:
    open_cases = list(
        await session.scalars(
            select(ReviewCase).where(
                ReviewCase.job_id == job_id,
                ReviewCase.item_key == item_key,
                ReviewCase.status == "open",
            )
        )
    )
    for case in open_cases:
        case.status = "superseded"
        case.resolved_at = dt.datetime.now(dt.UTC)
