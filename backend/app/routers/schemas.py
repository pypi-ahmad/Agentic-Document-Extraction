"""Extraction schema CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.db_models import ExtractionSchema
from app.models.schemas import (
    CreateFromPresetRequest,
    ExtractionSchemaCreate,
    ExtractionSchemaResponse,
    ExtractionSchemaUpdate,
    SchemaPresetResponse,
)
from app.services.extraction.presets import get_preset, list_presets

router = APIRouter(prefix="/api/schemas", tags=["Extraction Schemas"])


# ── Presets ──────────────────────────────────────────────────────────


@router.get("/presets", response_model=list[SchemaPresetResponse])
async def get_presets(response: Response) -> list[SchemaPresetResponse]:
    """List built-in document-type schema presets."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return [
        SchemaPresetResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            doc_type=p.doc_type,
            fields=[
                {"name": f.name, "description": f.description,
                 "field_type": f.field_type, "required": f.required}
                for f in p.fields
            ],
        )
        for p in list_presets()
    ]


@router.post(
    "/from-preset",
    response_model=ExtractionSchemaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_from_preset(
    body: CreateFromPresetRequest,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Create a new schema by copying fields from a built-in preset."""
    preset = get_preset(body.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    name = body.name or preset.name
    schema = ExtractionSchema(
        name=name,
        description=preset.description,
        fields=[
            {"name": f.name, "description": f.description,
             "field_type": f.field_type, "required": f.required}
            for f in preset.fields
        ],
    )
    db.add(schema)
    await db.flush()
    await db.refresh(schema)
    return schema


@router.post("/", response_model=ExtractionSchemaResponse, status_code=status.HTTP_201_CREATED)
async def create_schema(
    body: ExtractionSchemaCreate,
    db: AsyncSession = Depends(get_db),
) -> ExtractionSchema:
    """Create a new extraction schema with user-defined fields."""
    schema = ExtractionSchema(
        name=body.name,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
    )
    db.add(schema)
    await db.flush()
    await db.refresh(schema)
    return schema


@router.get("/", response_model=list[ExtractionSchemaResponse])
async def list_schemas(
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionSchema]:
    """List all extraction schemas."""
    result = await db.execute(
        select(ExtractionSchema).order_by(ExtractionSchema.created_at.desc())
    )
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
        schema.name = body.name
    if body.description is not None:
        schema.description = body.description
    if body.fields is not None:
        schema.fields = [f.model_dump() for f in body.fields]

    await db.flush()
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
