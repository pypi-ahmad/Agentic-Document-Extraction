import asyncio
import importlib.util
import io
import os
import stat
import sys
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image, PngImagePlugin

SERVICE_PATH = Path(__file__).resolve().parents[3] / "deploy" / "paddleocr-vl" / "service.py"


def _load_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADE_WORKER_TOKEN", "test-worker-token")
    monkeypatch.setenv("ADE_WORKER_PROFILE", "fast")
    spec = importlib.util.spec_from_file_location("paddleocr_hpi_service", SERVICE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@asynccontextmanager
async def _client(app: Any, *, raise_app_exceptions: bool = True) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        async with AsyncClient(transport=transport, base_url="http://worker") as client:
            yield client


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3, 2), "white").save(output, format="PNG")
    return output.getvalue()


def _jpeg_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3, 2), "white").save(output, format="JPEG")
    return output.getvalue()


class _Result:
    def __init__(self, value: dict[str, Any]) -> None:
        self.json = {"res": value}


class _Pipeline:
    def __init__(self, page: dict[str, Any] | None = None) -> None:
        self.page = page or {
            "parsing_res_list": [
                {
                    "block_id": 1,
                    "block_order": 1,
                    "block_label": "text",
                    "block_bbox": [0, 0, 3, 2],
                    "block_content": "hello",
                }
            ]
        }
        self.inputs: list[tuple[Path, bytes, int]] = []

    def predict(self, *, input: str):
        path = Path(input)
        self.inputs.append((path, path.read_bytes(), stat.S_IMODE(path.stat().st_mode)))
        return [_Result(self.page)]

    def restructure_pages(self, results: list[Any], **_: Any):
        return results


class _TablePipeline:
    def __init__(self) -> None:
        self.inputs: list[Path] = []

    def predict(self, *, input: str):
        self.inputs.append(Path(input))
        return [
            _Result(
                {
                    "table_res_list": [
                        {
                            "pred_html": "<table><tr><td>A</td></tr></table>",
                            "cell_box_list": [[0, 0, 1, 1]],
                            "table_ocr_pred": {"rec_texts": ["A"]},
                        }
                    ]
                }
            )
        ]


class _SerialProbePipeline(_Pipeline):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0
        self.guard = threading.Lock()

    def predict(self, *, input: str):
        with self.guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.1)
            return super().predict(input=input)
        finally:
            with self.guard:
                self.active -= 1


class _FailingPipeline(_Pipeline):
    def predict(self, *, input: str):
        path = Path(input)
        assert path.exists()
        raise RuntimeError("inference failed")


def test_worker_configuration_requires_token_and_valid_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _load_service(monkeypatch)

    with pytest.raises(RuntimeError, match="ADE_WORKER_TOKEN"):
        service.create_app(environ={"ADE_WORKER_PROFILE": "fast"})
    with pytest.raises(RuntimeError, match="ADE_WORKER_PROFILE"):
        service.create_app(environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "turbo"})


@pytest.mark.asyncio
async def test_health_requires_exact_token_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _load_service(monkeypatch)
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "correct-secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: object(),
    )

    async with _client(app) as client:
        missing = await client.get("/health")
        wrong = await client.get("/health", headers={"X-ADE-Worker-Token": "wrong-secret"})
        valid = await client.get("/health", headers={"X-ADE-Worker-Token": "correct-secret"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert "wrong-secret" not in wrong.text
    assert valid.status_code == 200
    assert valid.json() == {
        "schema_version": "1",
        "state": "ready",
        "profile": "fast",
        "model": "PaddleOCR-VL-1.6",
        "pipeline": "v1.6",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "optional_modules"),
    [("fast", False), ("accurate", True)],
)
async def test_pipeline_is_built_once_with_profile_flags(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    optional_modules: bool,
) -> None:
    service = _load_service(monkeypatch)
    calls: list[dict[str, Any]] = []

    def pipeline_factory(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": profile},
        pipeline_factory=pipeline_factory,
    )
    async with _client(app) as client:
        for _ in range(2):
            response = await client.get("/health", headers={"X-ADE-Worker-Token": "secret"})
            assert response.status_code == 200

    assert calls == [
        {
            "pipeline_version": "v1.6",
            "device": "gpu:0",
            "enable_hpi": True,
            "use_tensorrt": True,
            "precision": "fp16",
            "use_queues": True,
            "use_layout_detection": True,
            "use_doc_orientation_classify": optional_modules,
            "use_doc_unwarping": optional_modules,
            "use_chart_recognition": optional_modules,
            "use_seal_recognition": optional_modules,
            "use_ocr_for_image_block": optional_modules,
        }
    ]


@pytest.mark.asyncio
async def test_parse_page_authenticates_and_validates_request_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _load_service(monkeypatch)
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: object(),
    )
    headers = {"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"}

    async with _client(app) as client:
        unauthorized = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=b"image",
            headers={"Content-Type": "image/png"},
        )
        bad_job = await client.post(
            "/v1/parse-page?job_id=NOT-HEX&page_number=1",
            content=b"image",
            headers=headers,
        )
        bad_page = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=0",
            content=b"image",
            headers=headers,
        )
        empty = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=b"",
            headers=headers,
        )
        too_large = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=b"x" * (32 * 1024 * 1024 + 1),
            headers=headers,
        )
        wrong_media_type = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=b"image",
            headers={
                "X-ADE-Worker-Token": "secret",
                "Content-Type": "application/octet-stream",
            },
        )
        invalid_image = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=b"not-an-image",
            headers=headers,
        )

    assert unauthorized.status_code == 401
    assert bad_job.status_code == 422
    assert bad_page.status_code == 422
    assert empty.status_code == 400
    assert too_large.status_code == 413
    assert wrong_media_type.status_code == 415
    assert invalid_image.status_code == 400


@pytest.mark.asyncio
async def test_parse_page_returns_normalizable_page_and_timings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    pipeline = _Pipeline()
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: pipeline,
        temp_dir=tmp_path,
    )
    image = _png_bytes()

    async with _client(app) as client:
        response = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=7",
            content=image,
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1"
    assert body["pipeline_version"] == "v1.6"
    assert body["page"] == {
        "page_number": 7,
        "width": 3,
        "height": 2,
        "parsing_res_list": pipeline.page["parsing_res_list"],
    }
    assert set(body["timings_ms"]) == {"inference", "table_refinement", "total"}
    assert all(
        isinstance(value, (int, float)) and value >= 0 for value in body["timings_ms"].values()
    )
    assert pipeline.inputs[0][1] == image
    if os.name != "nt":
        assert pipeline.inputs[0][2] & 0o077 == 0


@pytest.mark.asyncio
async def test_parse_page_accepts_jpeg_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: _Pipeline(),
        temp_dir=tmp_path,
    )

    async with _client(app) as client:
        response = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=_jpeg_bytes(),
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/jpeg"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_accurate_profile_refines_tables_while_fast_profile_skips_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    table_page = {
        "parsing_res_list": [
            {
                "block_id": 4,
                "block_label": "table",
                "block_bbox": [0, 0, 3, 2],
                "block_content": "| A |",
            }
        ]
    }
    table_pipeline = _TablePipeline()
    table_factory_calls: list[dict[str, Any]] = []

    def table_factory(**kwargs: Any) -> _TablePipeline:
        table_factory_calls.append(kwargs)
        return table_pipeline

    accurate_app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "accurate"},
        pipeline_factory=lambda **_: _Pipeline(table_page),
        table_pipeline_factory=table_factory,
        temp_dir=tmp_path,
    )
    async with _client(accurate_app) as client:
        accurate = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=_png_bytes(),
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"},
        )

    fast_page = {
        "parsing_res_list": [
            {
                "block_id": 4,
                "block_label": "table",
                "block_bbox": [0, 0, 3, 2],
                "block_content": "| A |",
            }
        ]
    }
    fast_app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: _Pipeline(fast_page),
        table_pipeline_factory=table_factory,
        temp_dir=tmp_path,
    )
    async with _client(fast_app) as client:
        fast = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=_png_bytes(),
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"},
        )

    assert accurate.status_code == 200
    assert accurate.json()["page"]["parsing_res_list"][0]["table_refinement"] == {
        "pred_html": "<table><tr><td>A</td></tr></table>",
        "cell_box_list": [[0, 0, 1, 1]],
        "table_ocr_pred": {"rec_texts": ["A"]},
        "crop_offset": [0, 0],
    }
    assert table_factory_calls == [{"use_layout_detection": False}]
    assert len(table_pipeline.inputs) == 1
    assert "table_refinement" not in fast.json()["page"]["parsing_res_list"][0]


@pytest.mark.asyncio
async def test_parse_page_serializes_gpu_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    pipeline = _SerialProbePipeline()
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: pipeline,
        temp_dir=tmp_path,
    )
    headers = {"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"}

    async with _client(app) as client:
        first, second = await asyncio.gather(
            client.post(
                "/v1/parse-page?job_id=deadbeef&page_number=1",
                content=_png_bytes(),
                headers=headers,
            ),
            client.post(
                "/v1/parse-page?job_id=deadbeef&page_number=2",
                content=_png_bytes(),
                headers=headers,
            ),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert pipeline.max_active == 1


@pytest.mark.asyncio
async def test_parse_page_cleans_temporary_files_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    image = _png_bytes()
    headers = {"X-ADE-Worker-Token": "top-secret", "Content-Type": "image/png"}
    success_app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "top-secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: _Pipeline(),
        temp_dir=tmp_path,
    )
    async with _client(success_app) as client:
        success = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=image,
            headers=headers,
        )

    assert success.status_code == 200
    assert list(tmp_path.iterdir()) == []

    failure_app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "top-secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: _FailingPipeline(),
        temp_dir=tmp_path,
    )
    async with _client(failure_app, raise_app_exceptions=False) as client:
        failure = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=image,
            headers=headers,
        )

    assert failure.status_code == 500
    assert "top-secret" not in failure.text
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_parse_page_cleans_table_crop_when_crop_save_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    image = _png_bytes()
    page = {
        "parsing_res_list": [
            {
                "block_id": 4,
                "block_label": "table",
                "block_bbox": [0, 0, 3, 2],
                "block_content": "| A |",
            }
        ]
    }

    def fail_save(*_: Any, **__: Any) -> None:
        raise RuntimeError("crop save failed")

    monkeypatch.setattr(service.Image.Image, "save", fail_save)
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "accurate"},
        pipeline_factory=lambda **_: _Pipeline(page),
        table_pipeline_factory=lambda **_: _TablePipeline(),
        temp_dir=tmp_path,
    )
    async with _client(app, raise_app_exceptions=False) as client:
        response = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=image,
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"},
        )

    assert response.status_code == 200
    assert response.json()["page"]["parsing_res_list"][0]["warnings"] == [
        "table_refinement_failed:RuntimeError"
    ]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_parse_page_rejects_pillow_validation_error_and_cleans_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = _load_service(monkeypatch)
    image = _png_bytes()

    def fail_verify(*_: Any, **__: Any) -> None:
        raise RuntimeError("decoder failed")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "verify", fail_verify)
    app = service.create_app(
        environ={"ADE_WORKER_TOKEN": "secret", "ADE_WORKER_PROFILE": "fast"},
        pipeline_factory=lambda **_: _Pipeline(),
        temp_dir=tmp_path,
    )
    async with _client(app, raise_app_exceptions=False) as client:
        response = await client.post(
            "/v1/parse-page?job_id=deadbeef&page_number=1",
            content=image,
            headers={"X-ADE-Worker-Token": "secret", "Content-Type": "image/png"},
        )

    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == []
