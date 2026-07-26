"""PostgreSQL-compatible page task leasing with SQLite development support."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.db_models import PageCheckpoint, ParseJob, V2PageTask
from app.models.enums import JobStatus, PageStatus


class V2TaskLeases:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def enqueue_job(self, job_id: str, *, page_count: int) -> None:
        async with self.sessions() as session:
            existing = set(
                await session.scalars(
                    select(V2PageTask.page_number).where(V2PageTask.job_id == job_id)
                )
            )
            session.add_all(
                V2PageTask(job_id=job_id, page_number=page)
                for page in range(1, page_count + 1)
                if page not in existing
            )
            await session.commit()

    async def claim(self, owner: str, *, lease_seconds: int) -> V2PageTask | None:
        now = dt.datetime.now(dt.UTC)
        async with self.sessions() as session:
            statement = (
                select(V2PageTask)
                .where(
                    or_(
                        V2PageTask.status == "queued",
                        and_(
                            V2PageTask.status == "leased",
                            V2PageTask.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(V2PageTask.created_at, V2PageTask.page_number)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            task = await session.scalar(statement)
            if task is None:
                return None
            task.status = "leased"
            task.lease_owner = owner
            task.lease_expires_at = now + dt.timedelta(seconds=lease_seconds)
            task.attempts += 1
            await session.commit()
            await session.refresh(task)
            return task

    async def complete(self, task_id: str, owner: str, *, result_path: str) -> None:
        async with self.sessions() as session:
            task = await session.get(V2PageTask, task_id)
            if task is None or task.status != "leased" or task.lease_owner != owner:
                raise RuntimeError("task lease is not owned by this worker")
            task.status = "completed"
            task.result_path = result_path
            task.lease_owner = None
            task.lease_expires_at = None
            task.error_message = None
            await session.commit()

    async def fail(
        self,
        task_id: str,
        owner: str,
        *,
        error_message: str,
        max_attempts: int = 3,
    ) -> None:
        async with self.sessions() as session:
            task = await session.get(V2PageTask, task_id)
            if task is None or task.status != "leased" or task.lease_owner != owner:
                raise RuntimeError("task lease is not owned by this worker")
            task.lease_owner = None
            task.lease_expires_at = None
            task.error_message = error_message
            if task.attempts < max_attempts:
                task.status = "queued"
                await session.commit()
                return
            task.status = "failed"
            job = await session.get(ParseJob, task.job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.failed_pages = max(job.failed_pages, 1)
                job.error_code = "page_task_failed"
                job.error_message = f"Page {task.page_number} failed after {task.attempts} attempts"
            checkpoint = await session.scalar(
                select(PageCheckpoint).where(
                    PageCheckpoint.job_id == task.job_id,
                    PageCheckpoint.page_number == task.page_number,
                )
            )
            if checkpoint is not None:
                checkpoint.status = PageStatus.FAILED
                checkpoint.error_message = error_message
            await session.commit()
