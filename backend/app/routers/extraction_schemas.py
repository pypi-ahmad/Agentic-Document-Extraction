"""Reusable extraction schema CRUD and validation endpoints."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import ExtractionSchema
from app.models.schemas import (
    ExtractionSchemaListResponse,
    ExtractionSchemaResponse,
    ExtractionSchemaValidateRequest,
    ExtractionSchemaValidationResponse,
    ExtractionSchemaWrite,
)
from app.services.parsing.extraction_schemas import schema_sha256, validate_extraction_schema

router = APIRouter(prefix="/api/extraction-schemas", tags=["Extraction Schemas"])


def _name(value: str) -> str:
    return " ".join(value.split())


def _serialize(item: ExtractionSchema) -> ExtractionSchemaResponse:
    return ExtractionSchemaResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        version=item.version,
        json_schema=item.schema_json,
        schema_sha256=item.schema_sha256,
        created_at=item.created_at.isoformat() if item.created_at else None,
        updated_at=item.updated_at.isoformat() if item.updated_at else None,
    )


def _validated(schema: dict) -> tuple[dict, str]:
    result = validate_extraction_schema(schema)
    if not result.valid or result.normalized_schema is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_extraction_schema", "errors": result.model_dump()["errors"]},
        )
    return result.normalized_schema, schema_sha256(result.normalized_schema)


@router.post("/validate", response_model=ExtractionSchemaValidationResponse)
async def validate_schema(
    body: ExtractionSchemaValidateRequest,
) -> ExtractionSchemaValidationResponse:
    return validate_extraction_schema(body.json_schema)


@router.post("", response_model=ExtractionSchemaResponse, status_code=status.HTTP_201_CREATED)
async def create_schema(
    body: ExtractionSchemaWrite, db: AsyncSession = Depends(get_db)
) -> ExtractionSchemaResponse:
    schema, digest = _validated(body.json_schema)
    name = _name(body.name)
    item = ExtractionSchema(
        name=name,
        name_key=name.casefold(),
        description=body.description,
        version=1,
        schema_json=schema,
        schema_sha256=digest,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Schema name already exists") from exc
    await db.refresh(item)
    return _serialize(item)


@router.get("", response_model=ExtractionSchemaListResponse)
async def list_schemas(db: AsyncSession = Depends(get_db)) -> ExtractionSchemaListResponse:
    result = await db.execute(select(ExtractionSchema).order_by(ExtractionSchema.updated_at.desc()))
    return ExtractionSchemaListResponse(items=[_serialize(item) for item in result.scalars()])


@router.get("/{schema_id}", response_model=ExtractionSchemaResponse)
async def get_schema(
    schema_id: str, db: AsyncSession = Depends(get_db)
) -> ExtractionSchemaResponse:
    item = await db.get(ExtractionSchema, schema_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Extraction schema not found")
    return _serialize(item)


@router.put("/{schema_id}", response_model=ExtractionSchemaResponse)
async def update_schema(
    schema_id: str, body: ExtractionSchemaWrite, db: AsyncSession = Depends(get_db)
) -> ExtractionSchemaResponse:
    item = await db.get(ExtractionSchema, schema_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Extraction schema not found")
    schema, digest = _validated(body.json_schema)
    name = _name(body.name)
    if digest != item.schema_sha256:
        item.version += 1
    item.name = name
    item.name_key = name.casefold()
    item.description = body.description
    item.schema_json = schema
    item.schema_sha256 = digest
    item.updated_at = dt.datetime.now(dt.UTC)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Schema name already exists") from exc
    await db.refresh(item)
    return _serialize(item)


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schema(schema_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    item = await db.get(ExtractionSchema, schema_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Extraction schema not found")
    await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
