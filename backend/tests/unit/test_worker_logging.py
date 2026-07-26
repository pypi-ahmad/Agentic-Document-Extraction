from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.parsing import worker
from app.services.parsing.paddleocr_vl import PaddleOCRVLUnavailable


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, *_):
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        return None


class _Sessions:
    def __call__(self):
        return _Session()


@pytest.mark.asyncio
async def test_run_parse_job_logs_original_exception(monkeypatch):
    failure = RuntimeError("layout dependency missing")

    async def fail(*_):
        raise failure

    logger = Mock()
    terminalize = AsyncMock()
    sessions = _Sessions()
    monkeypatch.setattr(worker, "_execute", fail)
    monkeypatch.setattr(worker, "_terminalize", terminalize)
    monkeypatch.setattr(worker, "logger", logger)

    await worker.run_parse_job("job-id", sessions, Mock(), SimpleNamespace())

    logger.exception.assert_called_once_with(
        "parse_job.failed",
        job_id="job-id",
        exception_type="RuntimeError",
        exc_info=True,
    )
    terminalize.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_parse_job_reports_unavailable_paddleocr_vl(monkeypatch):
    failure = PaddleOCRVLUnavailable("PaddleOCR-VL service is unavailable")

    async def fail(*_):
        raise failure

    logger = Mock()
    terminalize = AsyncMock()
    sessions = _Sessions()
    monkeypatch.setattr(worker, "_execute", fail)
    monkeypatch.setattr(worker, "_terminalize", terminalize)
    monkeypatch.setattr(worker, "logger", logger)

    await worker.run_parse_job("job-id", sessions, Mock(), SimpleNamespace())

    logger.warning.assert_called_once_with(
        "parse_job.paddleocr_vl_unavailable",
        job_id="job-id",
    )
    terminalize.assert_awaited_once_with(
        sessions,
        "job-id",
        worker.JobStatus.FAILED,
        "paddleocr_vl_unavailable",
        "PaddleOCR-VL service is unavailable",
    )
