"""Extraction schema CRUD endpoints."""

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import ExtractionSchema
from app.models.schemas import (
    CreateSchemaFromPresetRequest,
    ExtractionSchemaCreate,
    ExtractionSchemaResponse,
    ExtractionSchemaUpdate,
    LegacyCreateFromPresetRequest,
    SchemaPresetResponse,
)
from app.services.extraction.presets import get_preset, list_presets

router = APIRouter(prefix="/api/schemas", tags=["Extraction Schemas"])


async def _schema_name_exists(
    db: AsyncSession,
    name: str,
    *,
    exclude_schema_id: str | None = None,
) -> bool:
    stmt = select(ExtractionSchema.id).where(ExtractionSchema.name == name)
    if exclude_schema_id is not None:
        stmt = stmt.where(ExtractionSchema.id != exclude_schema_id)
    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none() is not None


def _schema_name_conflict(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Schema name '{name}' already exists.",
    )


async def _flush_schema_or_raise_conflict(db: AsyncSession, name: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _schema_name_conflict(name) from exc


# ── Presets ──────────────────────────────────────────────────────────


async def _instantiate_preset_schema(
    db: AsyncSession,
    *,
    preset_id: str,
    requested_name: str | None = None,
) -> ExtractionSchema:
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    name = requested_name or preset.name
    if await _schema_name_exists(db, name):
        raise _schema_name_conflict(name)

    schema = ExtractionSchema(
        name=name,
        description=preset.description,
        fields=[field.model_dump() for field in preset.fields],
    )
    db.add(schema)
    await _flush_schema_or_raise_conflict(db, name)
    await db.refresh(schema)
    return schema


@router.get("/presets", response_model=list[SchemaPresetResponse])
async def list_schema_presets(response: Response) -> list[SchemaPresetResponse]:
    """List built-in document-type schema presets."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return [
        SchemaPresetResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            doc_type=p.doc_type,
            fields=[field.model_copy(deep=True) for field in p.fields],
        )
        for p in list_presets()
    ]


@router.post(
    "/presets/{preset_id}",
    response_model=ExtractionSchemaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schema_from_preset(
    preset_id: str,
    body: CreateSchemaFromPresetRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Create a new schema by copying fields from a built-in preset."""
    return await _instantiate_preset_schema(
        db,
        preset_id=preset_id,
        requested_name=body.name if body else None,
    )


@router.post(
    "/from-preset",
    response_model=ExtractionSchemaResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_schema_from_preset_legacy(
    body: LegacyCreateFromPresetRequest,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Deprecated compatibility alias for clients still posting preset_id in the body."""
    return await _instantiate_preset_schema(
        db,
        preset_id=body.preset_id,
        requested_name=body.name,
    )


@router.post("/", response_model=ExtractionSchemaResponse, status_code=status.HTTP_201_CREATED)
async def create_schema(
    body: ExtractionSchemaCreate,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Create a new extraction schema with user-defined fields."""
    if await _schema_name_exists(db, body.name):
        raise _schema_name_conflict(body.name)

    schema = ExtractionSchema(
        name=body.name,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
    )
    db.add(schema)
    await _flush_schema_or_raise_conflict(db, body.name)
    await db.refresh(schema)
    return schema


@router.get("/", response_model=list[ExtractionSchemaResponse])
async def list_schemas(
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionSchema]:
    """List all extraction schemas."""
    result = await db.execute(select(ExtractionSchema).order_by(ExtractionSchema.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{schema_id}", response_model=ExtractionSchemaResponse)
async def get_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Get a single extraction schema."""
    schema = await db.get(ExtractionSchema, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema


@router.put("/{schema_id}", response_model=ExtractionSchemaResponse)
async def update_schema(
    schema_id: str,
    body: ExtractionSchemaUpdate,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Update an extraction schema."""
    schema = await db.get(ExtractionSchema, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    if body.name is not None:
        if body.name != schema.name and await _schema_name_exists(
            db, body.name, exclude_schema_id=schema.id
        ):
            raise _schema_name_conflict(body.name)
        schema.name = body.name
    if body.description is not None:
        schema.description = body.description
    if body.fields is not None:
        schema.fields = [f.model_dump() for f in body.fields]

    await _flush_schema_or_raise_conflict(db, schema.name)
    await db.refresh(schema)
    return schema


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an extraction schema."""
    schema = await db.get(ExtractionSchema, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    await db.delete(schema)
