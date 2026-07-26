"""Document-scoped official PaddleOCR-VL Docker runner."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.logging_setup import get_logger
from app.services.parsing.contracts import Region
from app.services.parsing.paddleocr_vl import (
    PaddleOCRVLError,
    PaddleOCRVLResponseError,
    PaddleOCRVLUnavailable,
    _regions,
)

logger = get_logger("app.parsing.paddleocr_docker")

ProgressCallback = Callable[[int, str], Awaitable[None]]
MAX_EVENT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 128 * 1024 * 1024
_SAFE_JOB_ID = re.compile(r"^[a-f0-9]{8,64}$")


class PaddleRuntimeStatus(BaseModel):
    available: bool
    docker_available: bool = False
    gpu_available: bool = False
    image_present: bool = False
    cache_ready: bool = False
    image: str
    error: str | None = None
    pull_command: str | None = None


class _ProgressEvent(BaseModel):
    event: str
    page_number: int | None = Field(default=None, ge=1)
    message: str | None = Field(default=None, max_length=500)


class PaddleOCRVLDockerRunner:
    model_name = "PaddleOCR-VL-1.6"
    pipeline_version = "v1.6"

    def __init__(
        self,
        *,
        image: str,
        cache_dir: str | Path,
        timeout_seconds: float,
        worker_script: str | Path | None = None,
    ) -> None:
        self.image = image
        self.cache_dir = Path(cache_dir).resolve()
        self.timeout_seconds = timeout_seconds
        repo_root = Path(__file__).resolve().parents[4]
        self.worker_script = Path(
            worker_script or repo_root / "deploy" / "paddleocr-vl" / "worker.py"
        ).resolve()
        self._active: dict[str, tuple[str, asyncio.subprocess.Process]] = {}
        self._progress_callbacks: dict[str, ProgressCallback] = {}
        self._lock = asyncio.Lock()

    @property
    def pull_command(self) -> str:
        return f"docker pull {self.image}"

    async def status(self) -> PaddleRuntimeStatus:
        docker_ok = await self._command_ok("docker", "info", "--format", "{{json .ServerVersion}}")
        if not docker_ok:
            return PaddleRuntimeStatus(
                available=False,
                image=self.image,
                error="Docker Desktop is unavailable",
                pull_command=self.pull_command,
            )
        gpu_ok, image_ok = await asyncio.gather(
            self._command_ok(
                "docker",
                "info",
                "--format",
                "{{json .Runtimes.nvidia}}",
                require_non_null=True,
            ),
            self._command_ok("docker", "image", "inspect", self.image),
        )
        try:
            await asyncio.to_thread(self.cache_dir.mkdir, parents=True, exist_ok=True)
            cache_ok = self.cache_dir.is_dir() and os.access(self.cache_dir, os.W_OK)
        except OSError:
            cache_ok = False
        error = None
        if not gpu_ok:
            error = "Docker NVIDIA runtime is unavailable"
        elif not image_ok:
            error = f"PaddleOCR-VL image is not installed. Run: {self.pull_command}"
        elif not cache_ok:
            error = "PaddleOCR-VL model cache is not writable"
        elif not self.worker_script.is_file():
            error = "PaddleOCR-VL worker script is missing"
        return PaddleRuntimeStatus(
            available=not error,
            docker_available=True,
            gpu_available=gpu_ok,
            image_present=image_ok,
            cache_ready=cache_ok,
            image=self.image,
            error=error,
            pull_command=None if image_ok else self.pull_command,
        )

    async def available(self) -> bool:
        return (await self.status()).available

    async def segment_document(
        self,
        *,
        job_id: str,
        image_paths: list[Path],
        page_numbers: list[int],
        work_dir: Path,
        progress: ProgressCallback | None = None,
    ) -> dict[int, list[Region]]:
        if not _SAFE_JOB_ID.fullmatch(job_id):
            raise ValueError("job_id is not safe for a Docker resource name")
        if len(image_paths) != len(page_numbers) or not image_paths:
            raise ValueError("PaddleOCR-VL requires matching page images and numbers")
        work_dir = work_dir.resolve()
        pages_dir = (work_dir / "pages").resolve()
        output_dir = (work_dir / "paddleocr-vl").resolve()
        _require_child(pages_dir, work_dir)
        _require_child(output_dir, work_dir)
        for image_path in image_paths:
            _require_child(image_path.resolve(), pages_dir)
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        manifest = {
            "schema_version": "1",
            "pipeline_version": self.pipeline_version,
            "pages": [
                {"page_number": number, "path": f"/work/input/{path.name}"}
                for number, path in zip(page_numbers, image_paths, strict=True)
            ],
            "output_path": "/work/output/result.json",
        }
        manifest_path = output_dir / "manifest.json"
        await asyncio.to_thread(
            manifest_path.write_text,
            json.dumps(manifest, separators=(",", ":")),
            "utf-8",
        )
        status = await self.status()
        if not status.available:
            raise PaddleOCRVLUnavailable(status.error or "PaddleOCR-VL Docker runtime unavailable")

        container_name = f"ade-paddle-{job_id}"
        command = self._docker_command(
            job_id=job_id,
            container_name=container_name,
            pages_dir=pages_dir,
            output_dir=output_dir,
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with self._lock:
            self._active[job_id] = (container_name, process)
        stderr_task = asyncio.create_task(_read_tail(process.stderr, 1024 * 1024))
        selected_progress = progress or self._progress_callbacks.get(job_id)
        try:
            await asyncio.wait_for(
                self._consume_progress(process, selected_progress), timeout=self.timeout_seconds
            )
            stderr = await stderr_task
            return_code = await process.wait()
        except TimeoutError:
            await self.cancel(job_id)
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            raise PaddleOCRVLUnavailable("PaddleOCR-VL document worker timed out") from None
        except asyncio.CancelledError:
            await self.cancel(job_id)
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            raise
        except PaddleOCRVLError:
            await self.cancel(job_id)
            await stderr_task
            raise
        finally:
            async with self._lock:
                self._active.pop(job_id, None)
        if return_code:
            detail = stderr.decode("utf-8", errors="replace").strip()[-1000:]
            logger.warning(
                "paddleocr_vl.container_failed",
                job_id=job_id,
                return_code=return_code,
                error=detail,
            )
            raise PaddleOCRVLUnavailable(
                f"PaddleOCR-VL worker exited with code {return_code}"
            )
        result_path = output_dir / "result.json"
        return await asyncio.to_thread(_load_regions, result_path, page_numbers)

    def set_progress_callback(
        self, job_id: str, callback: ProgressCallback | None
    ) -> None:
        if callback is None:
            self._progress_callbacks.pop(job_id, None)
        else:
            self._progress_callbacks[job_id] = callback

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            active = self._active.get(job_id)
        if active is None:
            return False
        container_name, process = active
        if not await self._container_has_job_label(container_name, job_id):
            logger.error("paddleocr_vl.cancel_label_mismatch", job_id=job_id)
            return False
        await _run_quiet("docker", "stop", "--time", "10", container_name, timeout=20)
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
        return True

    async def shutdown(self) -> None:
        async with self._lock:
            job_ids = list(self._active)
        await asyncio.gather(*(self.cancel(job_id) for job_id in job_ids))

    def _docker_command(
        self,
        *,
        job_id: str,
        container_name: str,
        pages_dir: Path,
        output_dir: Path,
    ) -> list[str]:
        for path in (pages_dir, output_dir, self.cache_dir, self.worker_script):
            if "," in str(path):
                raise ValueError("Docker bind paths cannot contain commas")
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--label",
            f"ai.paperplane.job={job_id}",
            "--label",
            "ai.paperplane.role=paddleocr-vl",
            "--gpus",
            "device=0",
            "--shm-size",
            "8g",
            "--pids-limit",
            "512",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--mount",
            f"type=bind,source={pages_dir},target=/work/input,readonly",
            "--mount",
            f"type=bind,source={output_dir},target=/work/output",
            "--mount",
            f"type=bind,source={self.cache_dir},target=/home/paddleocr/.paddlex",
            "--mount",
            f"type=bind,source={self.worker_script},target=/opt/ade/worker.py,readonly",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            self.image,
            "python",
            "/opt/ade/worker.py",
            "--manifest",
            "/work/output/manifest.json",
        ]

    async def _consume_progress(
        self,
        process: asyncio.subprocess.Process,
        progress: ProgressCallback | None,
    ) -> None:
        if process.stdout is None:
            return
        while line := await process.stdout.readline():
            if len(line) > MAX_EVENT_BYTES:
                raise PaddleOCRVLResponseError("PaddleOCR-VL progress event is too large")
            try:
                event = _ProgressEvent.model_validate_json(line)
            except ValidationError as exc:
                raise PaddleOCRVLResponseError("Invalid PaddleOCR-VL progress event") from exc
            if event.event == "error":
                raise PaddleOCRVLUnavailable(event.message or "PaddleOCR-VL worker failed")
            if progress is not None and event.page_number is not None:
                await progress(event.page_number, event.event)

    async def _container_has_job_label(self, container_name: str, job_id: str) -> bool:
        output = await _run_quiet(
            "docker",
            "inspect",
            "--format",
            "{{ index .Config.Labels \"ai.paperplane.job\" }}",
            container_name,
            timeout=5,
        )
        return output.strip() == job_id

    @staticmethod
    async def _command_ok(*command: str, require_non_null: bool = False) -> bool:
        try:
            output = await _run_quiet(*command, timeout=8)
        except (OSError, TimeoutError):
            return False
        normalized = output.strip().casefold()
        return bool(normalized) and (
            not require_non_null or normalized not in {"null", '""', "<no value>"}
        )


def _require_child(path: Path, parent: Path) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ValueError(f"Path escapes job work directory: {path}") from exc


def _load_regions(result_path: Path, expected_pages: list[int]) -> dict[int, list[Region]]:
    if not result_path.is_file():
        raise PaddleOCRVLResponseError("PaddleOCR-VL result file is missing")
    if result_path.stat().st_size > MAX_RESULT_BYTES:
        raise PaddleOCRVLResponseError("PaddleOCR-VL result file is too large")
    try:
        body = json.loads(result_path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaddleOCRVLResponseError("PaddleOCR-VL result file is invalid") from exc
    pages = body.get("pages") if isinstance(body, dict) else None
    if not isinstance(pages, list):
        raise PaddleOCRVLResponseError("PaddleOCR-VL result is missing pages")
    normalized: dict[int, list[Region]] = {}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("page_number"), int):
            raise PaddleOCRVLResponseError("PaddleOCR-VL page result is invalid")
        number = page["page_number"]
        width, height = page.get("width"), page.get("height")
        blocks = page.get("parsing_res_list")
        if not isinstance(width, int | float) or not isinstance(height, int | float):
            raise PaddleOCRVLResponseError("PaddleOCR-VL page dimensions are invalid")
        if not isinstance(blocks, list):
            raise PaddleOCRVLResponseError("PaddleOCR-VL page is missing parsing_res_list")
        normalized[number] = _regions(blocks, int(width), int(height))
    if sorted(normalized) != sorted(expected_pages):
        raise PaddleOCRVLResponseError("PaddleOCR-VL did not return every requested page")
    return normalized


async def _read_tail(stream: asyncio.StreamReader | None, limit: int) -> bytes:
    if stream is None:
        return b""
    tail = bytearray()
    while chunk := await stream.read(64 * 1024):
        tail.extend(chunk)
        if len(tail) > limit:
            del tail[:-limit]
    return bytes(tail)


async def _run_quiet(*command: str, timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        return ""
    return stdout.decode("utf-8", errors="replace")
