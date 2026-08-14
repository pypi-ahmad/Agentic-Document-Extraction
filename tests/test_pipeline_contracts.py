import pytest
from pydantic import ValidationError

from paperplane.pipeline_contracts import (
    GroundedChunk,
    Grounding,
    GroundingMethod,
    ProcessingMode,
    VerificationStatus,
    mode_policy,
)
from paperplane.types import BoundingBox


def test_processing_modes_have_distinct_budgets() -> None:
    fast = mode_policy(ProcessingMode.ECONOMY)
    balanced = mode_policy(ProcessingMode.BALANCED)
    audit = mode_policy(ProcessingMode.AUDIT)

    assert fast.base_dpi < balanced.base_dpi < audit.base_dpi
    assert fast.terra_scope == "none"
    assert audit.terra_scope == "complex"


def test_verified_chunk_requires_grounding() -> None:
    with pytest.raises(ValidationError, match="requires grounding"):
        GroundedChunk(
            id="text-1",
            page=1,
            order=1,
            type="text",
            text="hello",
            markdown="hello",
            verification_status=VerificationStatus.VERIFIED,
            source_model="gpt-5.6-luna",
            source_pass="draft",
        )

    chunk = GroundedChunk(
        id="text-1",
        page=1,
        order=1,
        type="text",
        text="hello",
        markdown="hello",
        verification_status=VerificationStatus.VERIFIED,
        source_model="gpt-5.6-luna",
        source_pass="draft",
        grounding=[
            Grounding(
                page=1,
                box=BoundingBox(left=0, top=0, right=1, bottom=1),
                method=GroundingMethod.TEXT_LAYER_EXACT,
                source_box=(0, 0, 100, 100),
                source_unit="image_pixels",
                evidence_artifact_id="page-1",
            )
        ],
    )
    assert chunk.verification_status is VerificationStatus.VERIFIED
