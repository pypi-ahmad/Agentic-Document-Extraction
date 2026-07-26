"""Authenticated single-page PaddleOCR-VL worker service."""

from __future__ import annotations

import asyncio
import os
import secrets
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from PIL import Image

MAX_IMAGE_BYTES = 32 * 1024 * 1024


def _default_pipeline_factory(**kwargs: Any) -> Any:
    from paddleocr import PaddleOCRVL

    return PaddleOCRVL(**kwargs)


def _default_table_pipeline_factory(**kwargs: Any) -> Any:
    from paddleocr import TableRecognitionPipelineV2

    return TableRecognitionPipelineV2(**kwargs)


def _result_json(result: Any) -> dict[str, Any]:
    value = result.json
    if callable(value):
        value = value()
    if not isinstance(value, dict):
        raise TypeError("Paddle result JSON is not an object")
    nested = value.get("res")
    return nested if isinstance(nested, dict) else value


def _parse_one_page(
    pipeline: Any,
    image_path: Path,
    page_number: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    prediction = next(iter(pipeline.predict(input=str(image_path))))
    restructured = list(
        pipeline.restructure_pages(
            [prediction],
            merge_tables=True,
            relevel_titles=True,
            concatenate_pages=False,
        )
    )
    if len(restructured) != 1:
        raise RuntimeError("PaddleOCR-VL returned an unexpected page count")
    page = _result_json(restructured[0])
    page["page_number"] = page_number
    page["width"] = width
    page["height"] = height
    blocks = page.get("parsing_res_list")
    if not isinstance(blocks, list):
        page["parsing_res_list"] = []
    return page


def _refine_tables(
    image_path: Path,
    page: dict[str, Any],
    table_pipeline: Any | None,
    table_pipeline_factory: Callable[..., Any],
    temp_dir: Path | None,
) -> Any | None:
    blocks = page.get("parsing_res_list", [])
    tables = [
        block
        for block in blocks
        if isinstance(block, dict) and "table" in str(block.get("block_label", "")).casefold()
    ]
    if not tables:
        return table_pipeline
    if table_pipeline is None:
        table_pipeline = table_pipeline_factory(use_layout_detection=False)
    with Image.open(image_path) as image:
        for block in tables:
            box = block.get("block_bbox")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                block.setdefault("warnings", []).append("table_bbox_missing")
                continue
            left, top, right, bottom = (int(float(value)) for value in box)
            crop = image.crop((left, top, right, bottom)).convert("RGB")
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, dir=temp_dir
            ) as temporary:
                crop_path = Path(temporary.name)
            try:
                crop_path.chmod(0o600)
                crop.save(crop_path)
                result = next(iter(table_pipeline.predict(input=str(crop_path))))
                values = _result_json(result).get("table_res_list")
                if isinstance(values, list) and values:
                    detail = values[0]
                    block["table_refinement"] = {
                        "pred_html": detail.get("pred_html", ""),
                        "cell_box_list": detail.get("cell_box_list", []),
                        "table_ocr_pred": detail.get("table_ocr_pred", {}),
                        "crop_offset": [left, top],
                    }
                else:
                    block.setdefault("warnings", []).append("table_refinement_empty")
            except Exception as exc:
                block.setdefault("warnings", []).append(
                    f"table_refinement_failed:{type(exc).__name__}"
                )
            finally:
                crop_path.unlink(missing_ok=True)
    return table_pipeline


def create_app(
    *,
    environ: Mapping[str, str] | None = None,
    pipeline_factory: Callable[..., Any] | None = None,
    table_pipeline_factory: Callable[..., Any] | None = None,
    temp_dir: Path | None = None,
    **_: object,
) -> FastAPI:
    environment = os.environ if environ is None else environ
    token = environment.get("ADE_WORKER_TOKEN", "")
    if not token:
        raise RuntimeError("ADE_WORKER_TOKEN is required")
    profile = environment.get("ADE_WORKER_PROFILE", "")
    if profile not in {"fast", "accurate"}:
        raise RuntimeError("ADE_WORKER_PROFILE must be 'fast' or 'accurate'")
    factory = pipeline_factory or _default_pipeline_factory
    refinement_factory = table_pipeline_factory or _default_table_pipeline_factory
    optional_modules = profile == "accurate"

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.pipeline = factory(
            pipeline_version="v1.6",
            device="gpu:0",
            enable_hpi=True,
            use_tensorrt=True,
            precision="fp16",
            use_queues=True,
            use_layout_detection=True,
            use_doc_orientation_classify=optional_modules,
            use_doc_unwarping=optional_modules,
            use_chart_recognition=optional_modules,
            use_seal_recognition=optional_modules,
            use_ocr_for_image_block=optional_modules,
        )
        application.state.table_pipeline = None
        application.state.request_lock = asyncio.Lock()
        yield

    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    async def authenticate(
        worker_token: str | None = Header(default=None, alias="X-ADE-Worker-Token"),
    ) -> None:
        if worker_token is None or not secrets.compare_digest(worker_token, token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @application.get("/health", dependencies=[Depends(authenticate)])
    async def health() -> dict[str, str]:
        return {
            "schema_version": "1",
            "state": "ready",
            "profile": profile,
            "model": "PaddleOCR-VL-1.6",
            "pipeline": "v1.6",
        }

    @application.post("/v1/parse-page", dependencies=[Depends(authenticate)])
    async def parse_page(
        request: Request,
        job_id: Annotated[str, Query(pattern=r"^[a-f0-9]{8,64}$")],
        page_number: Annotated[int, Query(ge=1)],
    ) -> dict[str, Any]:
        del job_id
        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type not in {"image/png", "image/jpeg"}:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be image/png or image/jpeg",
            )
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_IMAGE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Image exceeds 32 MiB",
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length",
                )
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Image exceeds 32 MiB",
                )
            payload.extend(chunk)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image payload is required",
            )
        suffix = ".png" if media_type == "image/png" else ".jpg"
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=suffix, delete=False, dir=temp_dir
        ) as temporary:
            temporary.write(payload)
            image_path = Path(temporary.name)
        try:
            image_path.chmod(0o600)
            with Image.open(image_path) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("Unsupported image format")
                width, height = image.size
                image.verify()
        except Exception:
            image_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payload is not a valid PNG or JPEG image",
            )

        try:
            started = time.perf_counter()
            async with application.state.request_lock:
                inference_started = time.perf_counter()
                page = await asyncio.to_thread(
                    _parse_one_page,
                    application.state.pipeline,
                    image_path,
                    page_number,
                    width,
                    height,
                )
                inference_ms = (time.perf_counter() - inference_started) * 1000
                refinement_ms = 0.0
                if profile == "accurate":
                    refinement_started = time.perf_counter()
                    application.state.table_pipeline = await asyncio.to_thread(
                        _refine_tables,
                        image_path,
                        page,
                        application.state.table_pipeline,
                        refinement_factory,
                        temp_dir,
                    )
                    refinement_ms = (time.perf_counter() - refinement_started) * 1000
            total_ms = (time.perf_counter() - started) * 1000
            return {
                "schema_version": "1",
                "pipeline_version": "v1.6",
                "page": page,
                "timings_ms": {
                    "inference": inference_ms,
                    "table_refinement": refinement_ms,
                    "total": total_ms,
                },
            }
        finally:
            image_path.unlink(missing_ok=True)

    return application


app = create_app()
