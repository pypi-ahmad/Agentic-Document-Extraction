"""Schema-defined Terra extraction with value-level evidence enforcement."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel

from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.v2_contracts import ExtractionField, GroundedChunk, VerificationStatus
from app.services.parsing.v2_pipeline import StructuredAdapter


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(schema)
    if "anyOf" in value:
        options = value["anyOf"]
        if not any(option == {"type": "null"} for option in options):
            value["anyOf"] = [*options, {"type": "null"}]
        return value
    if value.get("type") == "object":
        properties = value.get("properties", {})
        value["properties"] = {name: _nullable(item) for name, item in properties.items()}
        value["required"] = list(properties)
        value["additionalProperties"] = False
        return value
    if value.get("type") == "array" and isinstance(value.get("items"), dict):
        value["items"] = _nullable(value["items"])
    return {"anyOf": [value, {"type": "null"}]}


def build_grounded_extraction_schema(user_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "data": _nullable(user_schema),
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "status": {"type": "string", "enum": ["grounded", "unresolved"]},
                        "citations": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                    },
                    "required": ["path", "status", "citations", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["data", "evidence"],
        "additionalProperties": False,
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(_flatten(item, path))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


class ExtractionOutcome(BaseModel):
    fields: dict[str, ExtractionField]
    structured_data: Any
    usage: OpenAIUsage


class V2SchemaExtractor:
    def __init__(self, adapter: StructuredAdapter) -> None:
        self.adapter = adapter

    async def extract(
        self,
        *,
        markdown: str,
        chunks: list[GroundedChunk],
        user_schema: dict[str, Any],
        source_sha256: str,
        reasoning_effort: Literal["medium", "high"],
    ) -> ExtractionOutcome:
        schema = build_grounded_extraction_schema(user_schema)
        schema_hash = hashlib.sha256(
            json.dumps(user_schema, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result = await self.adapter.generate_structured(
            model="gpt-5.6-terra",
            image=None,
            instructions=(
                "Extract the requested schema only from cited document chunks. Every non-null leaf "
                "must cite one or more chunk IDs. Return null and unresolved when evidence is absent."
            ),
            context=markdown,
            schema_name="grounded_schema_extraction_v2",
            schema=schema,
            reasoning_effort=reasoning_effort,
            detail="original",
            prompt_cache_key=f"schema-extract:v2:{schema_hash[:12]}:shard-{int(source_sha256[:8], 16) % 4}",
        )
        data = result.value.get("data", {})
        evidence_by_path = {
            item.get("path"): item
            for item in result.value.get("evidence", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        verified_ids = {
            chunk.id
            for chunk in chunks
            if chunk.verification_status == VerificationStatus.VERIFIED and chunk.grounding
        }
        fields: dict[str, ExtractionField] = {}
        for path, value in _flatten(data).items():
            evidence = evidence_by_path.get(path, {})
            citations = [
                citation for citation in evidence.get("citations", []) if isinstance(citation, str)
            ]
            valid = (
                value is not None
                and evidence.get("status") == "grounded"
                and bool(citations)
                and all(citation in verified_ids for citation in citations)
            )
            if valid:
                fields[path] = ExtractionField(
                    value=value,
                    status="grounded",
                    citations=citations,
                    reason=str(evidence.get("reason", "")),
                )
            else:
                reason = "value_unresolved" if value is None else "citation_not_verified"
                fields[path] = ExtractionField(
                    value=None, status="unresolved", citations=[], reason=reason
                )
        return ExtractionOutcome(fields=fields, structured_data=data, usage=result.usage)
