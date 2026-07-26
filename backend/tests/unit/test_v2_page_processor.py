from io import BytesIO

from PIL import Image

from app.services.parsing.contracts import BoundingBox, NativeWord
from app.services.parsing.ingest import RenderedPage
from app.services.parsing.openai_document import OpenAIUsage, StructuredGeneration
from app.services.parsing.v2_contracts import (
    GroundingMethod,
    ProcessingMode,
    VerificationStatus,
)
from app.services.parsing.v2_pipeline import V2PageProcessor


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


def _generation(value: dict) -> StructuredGeneration:
    return StructuredGeneration(value=value, usage=OpenAIUsage(), latency_ms=1)


class _ExactTextAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["model"] != "gpt-5.6-luna":
            raise AssertionError("exact native text must not require Terra")
        return _generation(
            {
                "chunks": [
                    {
                        "type": "text",
                        "text": "Invoice Number INV-42",
                        "markdown": "Invoice Number INV-42",
                        "box": {"left": 0.05, "top": 0.05, "right": 0.6, "bottom": 0.3},
                        "parent_order": None,
                    }
                ]
            }
        )


class _VerifiedScanAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "table",
                            "text": "Total 42.00",
                            "markdown": "| Total | 42.00 |",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "Total 42.00",
                "box": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                "verdict": "verified",
                "reason": "crop independently matches",
            }
        )


class _DisagreeingAdapter(_VerifiedScanAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        if kwargs["model"] == "gpt-5.6-terra":
            return _generation(
                {
                    "text": "Total 24.00",
                    "box": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                    "verdict": "unresolved",
                    "reason": "values disagree",
                }
            )
        return result


async def test_native_text_is_grounded_exactly_without_terra() -> None:
    page = RenderedPage(
        page_number=1,
        image_png=_png(),
        width=200,
        height=300,
        native_words=[
            NativeWord(text="Invoice", bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.2)),
            NativeWord(text="Number", bbox=BoundingBox(left=0.21, top=0.1, right=0.3, bottom=0.2)),
            NativeWord(text="INV-42", bbox=BoundingBox(left=0.31, top=0.1, right=0.42, bottom=0.2)),
        ],
    )

    result = await V2PageProcessor(_ExactTextAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="a" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.grounding[0].method == GroundingMethod.TEXT_LAYER_EXACT
    assert chunk.grounding[0].box.right == 0.42


async def test_scanned_table_is_verified_against_refined_crop() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_VerifiedScanAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="b" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.grounding[0].method == GroundingMethod.VISION_REFINED
    assert chunk.grounding[0].evidence_artifact_id.startswith("crop:")
    assert set(result.model_usage) == {"gpt-5.6-luna", "gpt-5.6-terra"}


async def test_disagreement_abstains_instead_of_emitting_candidate_value() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_DisagreeingAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="c" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.UNRESOLVED
    assert chunk.text == ""
    assert "Total 42.00" not in result.markdown
    assert "Unresolved table" in result.markdown
