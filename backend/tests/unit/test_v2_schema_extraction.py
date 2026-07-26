from app.services.parsing.contracts import BoundingBox
from app.services.parsing.openai_document import OpenAIUsage, StructuredGeneration
from app.services.parsing.v2_contracts import (
    GroundedChunk,
    Grounding,
    GroundingMethod,
    VerificationStatus,
)
from app.services.parsing.v2_schema_extraction import (
    V2SchemaExtractor,
    build_grounded_extraction_schema,
)

USER_SCHEMA = {
    "type": "object",
    "properties": {"invoice_number": {"type": "string"}},
    "required": ["invoice_number"],
    "additionalProperties": False,
}


def _chunk() -> GroundedChunk:
    return GroundedChunk(
        id="p0001-c0001",
        page=1,
        order=1,
        type="text",
        text="Invoice Number INV-42",
        markdown="Invoice Number INV-42",
        grounding=[
            Grounding(
                page=1,
                box=BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2),
                method=GroundingMethod.TEXT_LAYER_EXACT,
                source_box=(10, 10, 80, 20),
                source_unit="pdf_points",
                evidence_artifact_id="page:1",
            )
        ],
        verification_status=VerificationStatus.VERIFIED,
        source_model="gpt-5.6-luna",
        source_pass="page_draft",
    )


class _Adapter:
    def __init__(self, citation: str) -> None:
        self.citation = citation

    async def generate_structured(self, **kwargs) -> StructuredGeneration:
        return StructuredGeneration(
            value={
                "data": {"invoice_number": "INV-42"},
                "evidence": [
                    {
                        "path": "invoice_number",
                        "status": "grounded",
                        "citations": [self.citation],
                        "reason": "visible beside invoice label",
                    }
                ],
            },
            usage=OpenAIUsage(input_tokens=10, output_tokens=5),
            latency_ms=1,
        )


def test_extraction_schema_allows_null_abstention_without_relaxing_other_constraints() -> None:
    schema = build_grounded_extraction_schema(USER_SCHEMA)

    value_schema = schema["properties"]["data"]["properties"]["invoice_number"]
    assert value_schema == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert schema["properties"]["data"]["required"] == ["invoice_number"]
    assert schema["properties"]["data"]["additionalProperties"] is False


async def test_verified_citation_accepts_schema_value() -> None:
    outcome = await V2SchemaExtractor(_Adapter("p0001-c0001")).extract(
        markdown="Invoice Number INV-42",
        chunks=[_chunk()],
        user_schema=USER_SCHEMA,
        source_sha256="a" * 64,
        reasoning_effort="medium",
    )

    assert outcome.fields["invoice_number"].value == "INV-42"
    assert outcome.fields["invoice_number"].status == "grounded"
    assert outcome.structured_data == {"invoice_number": "INV-42"}


async def test_unknown_citation_abstains_from_schema_value() -> None:
    outcome = await V2SchemaExtractor(_Adapter("missing")).extract(
        markdown="Invoice Number INV-42",
        chunks=[_chunk()],
        user_schema=USER_SCHEMA,
        source_sha256="b" * 64,
        reasoning_effort="medium",
    )

    field = outcome.fields["invoice_number"]
    assert field.value is None
    assert field.status == "unresolved"
    assert field.reason == "citation_not_verified"
