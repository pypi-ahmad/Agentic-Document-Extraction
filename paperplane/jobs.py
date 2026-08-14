"""Durable local job metadata and private artifact storage."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Job:
    id: str
    filename: str
    engine: str
    page_start: int
    page_end: int | None
    status: JobStatus
    created_at: str
    updated_at: str
    checkpoint_page: int | None
    result_json: str | None
    error: str | None


class JobStore:
    """SQLite metadata plus filesystem artifacts, both scoped to one local app root."""

    def __init__(self, database: Path, artifacts: Path, *, ttl_days: int = 7) -> None:
        self.database = Path(database)
        self.artifacts = Path(artifacts)
        self.ttl_days = ttl_days
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    page_start INTEGER NOT NULL,
                    page_end INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    checkpoint_page INTEGER,
                    result_json TEXT,
                    error TEXT
                )
                """
            )

    @staticmethod
    def _job(row: sqlite3.Row | None) -> Job | None:
        return Job(**dict(row)) if row is not None else None

    def create_job(self, *, filename: str, engine: str, page_range: tuple[int, int | None]) -> Job:
        job_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (
                    job_id,
                    filename,
                    engine,
                    page_range[0],
                    page_range[1],
                    "pending",
                    timestamp,
                    timestamp,
                ),
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._connect() as connection:
            return self._job(
                connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            )

    def list_jobs(self) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [job for row in rows if (job := self._job(row)) is not None]

    def _status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, error = ?, result_json = COALESCE(?, result_json) WHERE id = ?",
                (status, _now(), error, json.dumps(result) if result is not None else None, job_id),
            )

    def mark_running(self, job_id: str) -> None:
        self._status(job_id, "running")

    def complete_job(self, job_id: str, *, result: dict[str, Any]) -> None:
        self._status(job_id, "completed", result=result)

    def fail_job(self, job_id: str, error: str) -> None:
        self._status(job_id, "failed", error=error)

    def cancel_job(self, job_id: str) -> None:
        self._status(job_id, "cancelled")

    def save_checkpoint(self, job_id: str, *, page: int, payload: dict[str, Any]) -> Path:
        directory = self.artifacts / job_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "checkpoint.json"
        temporary = directory / "checkpoint.tmp"
        temporary.write_text(json.dumps({"page": page, "payload": payload}), encoding="utf-8")
        temporary.replace(path)
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET checkpoint_page = ?, updated_at = ? WHERE id = ?",
                (page, _now(), job_id),
            )
        return path

    def save_artifact(self, job_id: str, name: str, data: bytes) -> Path:
        safe_name = Path(name).name
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("Artifact name must be a file name")
        directory = self.artifacts / job_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / safe_name
        temporary = directory / f"{safe_name}.tmp"
        temporary.write_bytes(data)
        temporary.replace(path)
        return path

    def resume_checkpoint(self, job_id: str) -> tuple[int, dict[str, Any]] | None:
        path = self.artifacts / job_id / "checkpoint.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["page"]), dict(data["payload"])

    def delete_job(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        directory = self.artifacts / job_id
        if directory.exists():
            shutil.rmtree(directory)

    def clear_all(self) -> None:
        for job in self.list_jobs():
            self.delete_job(job.id)

    def purge_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self.ttl_days)
        expired = [
            job for job in self.list_jobs() if datetime.fromisoformat(job.updated_at) < cutoff
        ]
        for job in expired:
            self.delete_job(job.id)
        return len(expired)


class DurableJobService:
    """Future-HTTP-wrappable async lifecycle around the durable store."""

    def __init__(self, store: JobStore) -> None:
        self.store = store

    def recoverable_jobs(self) -> list[Job]:
        return [job for job in self.store.list_jobs() if job.status in {"pending", "running"}]

    async def run(
        self,
        job_id: str,
        worker: Callable[[tuple[int, dict[str, Any]] | None], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise ValueError("Unknown job")
        if job.status == "cancelled":
            raise ValueError("Cancelled job cannot run")
        self.store.mark_running(job_id)
        try:
            result = await worker(self.store.resume_checkpoint(job_id))
        except Exception as exc:
            self.store.fail_job(job_id, str(exc))
            raise
        self.store.complete_job(job_id, result=result)
        return result


__all__ = ["DurableJobService", "Job", "JobStore"]
