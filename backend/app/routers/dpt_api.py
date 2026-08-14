"""Stateless document Parse and Extract API."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import require_api_key
from app.config import settings
from app.rate_limit import require_rate_limit
from app.services.agentic.contracts import ExtractionResponse, ParseMetadata, ParseResponse
from app.services.agentic.extraction import (
    AgenticSchemaExtractor,
    ExtractionServiceError,
    InvalidExtractionSchemaError,
    StrictSchemaViolationError,
)
from app.services.agentic.parsing import AgenticDocumentParser
from app.services.parsing.ingest import DocumentInputError
from app.services.parsing.openai_document import OpenAIRequestError

ModelAlias = Literal[
    "paperplane-ade-fast-latest",
    "paperplane-ade-latest",
    "paperplane-ade-audit-latest",
]

INVOICE_V1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string"},
        "supplier_name": {"type": "string"},
        "currency": {"type": "string"},
        "subtotal": {"type": "number"},
        "tax": {"type": "number"},
        "total": {"type": "number"},
    },
    "required": [
        "invoice_number",
        "invoice_date",
        "supplier_name",
        "currency",
        "subtotal",
        "tax",
        "total",
    ],
    "additionalProperties": False,
}

router = APIRouter(
    prefix="/v2",
    tags=["agentic-v2"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


class ExtractRequest(BaseModel):
    markdown: str
    json_schema: dict[str, Any]
    strict: bool = False
    model: ModelAlias = "paperplane-ade-latest"


@router.get("/contracts/presets/invoice-v1")
async def get_invoice_contract() -> dict[str, Any]:
    return {
        "id": "invoice-v1",
        "description": "Grounded invoice header and total fields; absent values remain unresolved.",
        "json_schema": INVOICE_V1_SCHEMA,
    }


def _error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def get_agentic_extractor() -> AgenticSchemaExtractor:
    """Deployment seam for a configured Terra extraction caller."""

    raise _error(
        "extraction_service_unavailable",
        "A Terra extraction provider has not been configured",
        503,
    )


def _extraction_dependency() -> AgenticSchemaExtractor:
    return get_agentic_extractor()


def _parser_dependency(request: Request) -> AgenticDocumentParser:
    return request.app.state.agentic_parser


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise _error("too_large", "Document exceeds the upload limit", 413)
        chunks.append(chunk)
    return b"".join(chunks), Path(file.filename or "document").name


@router.post("/parse", response_model=ParseResponse)
async def parse_document(
    file: Annotated[UploadFile, File()],
    model: Annotated[ModelAlias, Form()] = "paperplane-ade-latest",
    parser: AgenticDocumentParser = Depends(_parser_dependency),
) -> ParseResponse:
    if not settings.openai_api_key:
        raise _error("openai_not_configured", "OPENAI_API_KEY is required for parsing", 503)
    data, filename = await _read_upload(file)
    try:
        return await parser.parse(data=data, filename=filename, model=model)
    except DocumentInputError as exc:
        raise _error(exc.code, str(exc)) from exc
    except OpenAIRequestError as exc:
        raise _error("openai_request_failed", str(exc), 502) from exc


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    request: ExtractRequest,
    extractor: AgenticSchemaExtractor = Depends(_extraction_dependency),
) -> Response:
    try:
        result = await extractor.extract(
            markdown=request.markdown,
            schema=request.json_schema,
            strict=request.strict,
        )
    except StrictSchemaViolationError as exc:
        raise _error("schema_violation", str(exc), 422) from exc
    except InvalidExtractionSchemaError as exc:
        raise _error("invalid_schema", str(exc), 422) from exc
    except ExtractionServiceError as exc:
        raise _error("invalid_extraction", str(exc), exc.status_code) from exc

    response = ExtractionResponse(
        extraction=result.extraction,
        extraction_metadata=result.extraction_metadata,
        markdown=request.markdown,
        metadata=ParseMetadata(
            job_id=uuid.uuid4().hex,
            model=request.model,
            page_count=max(1, request.markdown.count("<!-- page_number=")),
            output_characters=len(request.markdown),
            service_tier="local",
            total_credits=0,
        ),
        warnings=result.warnings,
        schema_violation_error=result.schema_violation_error,
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=206 if result.schema_violation_error else 200,
    )


__all__ = ["ModelAlias", "router"]
