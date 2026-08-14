from io import BytesIO

from PIL import Image

from paperplane.ingest import RenderedPage
from paperplane.openai_document import OpenAIUsage, StructuredGeneration
from paperplane.pipeline import (
    CROP_VERIFICATION_SCHEMA,
    PAGE_DRAFT_SCHEMA,
    V2PageProcessor,
    _merge_reconciled_chunks,
    _needs_figure_reconciliation,
    _raw_chunks_agree,
)
from paperplane.pipeline_contracts import (
    GroundingMethod,
    ProcessingMode,
    VerificationStatus,
)
from paperplane.types import BoundingBox, NativeWord


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


def _generation(value: dict) -> StructuredGeneration:
    return StructuredGeneration(value=value, usage=OpenAIUsage(), latency_ms=1)


def test_figure_specialist_ignores_multiple_tiny_decorative_regions() -> None:
    figures = [
        {
            "type": "figure",
            "box": {"left": 0.05, "top": top, "right": 0.15, "bottom": top + 0.05},
        }
        for top in (0.1, 0.2, 0.3)
    ]

    assert not _needs_figure_reconciliation(figures)


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
        if kwargs["schema_name"] == "page_reconciliation_v8":
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
                "markdown": "| Total | 42.00 |",
                "box": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                "verdict": "verified",
                "reason": "crop matches",
            }
        )


class _DisagreeingAdapter(_VerifiedScanAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        if kwargs["model"] == "gpt-5.6-terra":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "table",
                            "text": "Total 24.00",
                            "markdown": "| Total | 24.00 |",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ],
                }
            )
        return result


class _CorrectingAdapter(_VerifiedScanAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        if kwargs["model"] == "gpt-5.6-terra" and kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "table",
                            "text": "Total 24.00",
                            "markdown": "| Total | 24.00 |",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ],
                }
            )
        if kwargs["model"] == "gpt-5.6-terra" and kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "text": "Total 24.00",
                    "markdown": "| Total | 24.00 |",
                    "box": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                    "verdict": "unresolved",
                    "reason": "values disagree",
                }
            )
        if kwargs["model"] == "gpt-5.6-terra":
            return _generation(
                {
                    "text": "Total 24.00",
                    "markdown": "| Total | 24.00 |",
                    "box": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                    "verdict": "verified",
                    "reason": "crop reads 24",
                }
            )
        return result


class _ThousandScaleTerraAdapter(_VerifiedScanAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        if kwargs["model"] == "gpt-5.6-terra" and kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "table",
                            "text": "Total 42.00",
                            "markdown": "| Total | 42.00 |",
                            "box": {"left": 100, "top": 200, "right": 900, "bottom": 800},
                            "parent_order": None,
                        }
                    ],
                }
            )
        return result


class _InvalidTerraBoxAdapter(_VerifiedScanAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        if kwargs["model"] == "gpt-5.6-terra" and kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "table",
                            "text": "Total 42.00",
                            "markdown": "| Total | 42.00 |",
                            "box": {"left": 0.8, "top": 0.1, "right": 0.2, "bottom": 0.9},
                            "parent_order": None,
                        }
                    ],
                }
            )
        return result


class _InvalidLunaBoxAdapter:
    async def generate_structured(self, **kwargs):
        return _generation(
            {
                "chunks": [
                    {
                        "type": "text",
                        "text": "Unmatched scan text",
                        "markdown": "Unmatched scan text",
                        "box": {"left": 0.7, "top": 0.1, "right": 0.2, "bottom": 0.9},
                        "parent_order": None,
                    }
                ]
            }
        )


class _HugeLunaBoxAdapter(_InvalidLunaBoxAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        result.value["chunks"][0]["box"] = {
            "left": 10**1000,
            "top": 0,
            "right": 1,
            "bottom": 1,
        }
        return result


class _ExactTextWithInvalidLunaBoxAdapter(_ExactTextAdapter):
    async def generate_structured(self, **kwargs):
        result = await super().generate_structured(**kwargs)
        result.value["chunks"][0]["box"] = {
            "left": 0.7,
            "top": 0.1,
            "right": 0.2,
            "bottom": 0.9,
        }
        return result


class _EmptyDraftRecoveredByTerraAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation({"chunks": []})
        if kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Recovered page text",
                            "markdown": "Recovered page text",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "Recovered page text",
                "markdown": "Recovered page text",
                "box": {"left": 0.05, "top": 0.05, "right": 0.95, "bottom": 0.95},
                "verdict": "verified",
                "reason": "visible in crop",
            }
        )


class _TerraOnlyFallbackAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "",
                            "markdown": "",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ]
                }
            )
        if kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Recovered by Terra",
                            "markdown": "Recovered by Terra",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "Recovered by Terra",
                "markdown": "Recovered by Terra",
                "box": {"left": 0.8, "top": 0.1, "right": 0.2, "bottom": 0.9},
                "verdict": "unresolved",
                "reason": "box could not be localized",
            }
        )


class _EmptyFigureAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["schema_name"] in {"page_draft_v8", "page_reconciliation_v8"}:
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "figure",
                            "text": "",
                            "markdown": "",
                            "box": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "",
                "markdown": "",
                "box": {"left": 0.05, "top": 0.05, "right": 0.95, "bottom": 0.95},
                "verdict": "unresolved",
                "reason": "description unavailable",
            }
        )


class _ReconciliationOmitsDraftRegionAdapter:
    async def generate_structured(self, **kwargs):
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "1. First step",
                            "markdown": "1. First step",
                            "box": {"left": 0.2, "top": 0.1, "right": 0.8, "bottom": 0.2},
                            "parent_order": None,
                        },
                        {
                            "type": "text",
                            "text": "9. Final shipping step",
                            "markdown": "9. Final shipping step",
                            "box": {"left": 0.2, "top": 0.8, "right": 0.8, "bottom": 0.9},
                            "parent_order": None,
                        },
                    ]
                }
            )
        if kwargs["schema_name"] == "page_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "1. First step",
                            "markdown": "1. First step",
                            "box": {"left": 0.2, "top": 0.1, "right": 0.8, "bottom": 0.2},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "9. Final shipping step",
                "markdown": "9. Final shipping step",
                "box": {"left": 0.05, "top": 0.05, "right": 0.95, "bottom": 0.95},
                "verdict": "unresolved",
                "reason": "single model region",
            }
        )


class _CapturingAdapter(_VerifiedScanAdapter):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return await super().generate_structured(**kwargs)


class _CapturingDisagreeingAdapter(_DisagreeingAdapter):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return await super().generate_structured(**kwargs)


class _PrecisionIdentifierAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Contact the laboratory at labwebl@health.mo.gov.",
                            "markdown": "Contact the laboratory at labwebl@health.mo.gov.",
                            "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
                            "parent_order": None,
                        }
                    ]
                }
            )
        if kwargs["schema_name"].startswith("page_reconciliation"):
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Contact the laboratory at labwebl@health.mo.gov.",
                            "markdown": "Contact the laboratory at labwebl@health.mo.gov.",
                            "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "Contact the laboratory at labweb1@health.mo.gov.",
                "markdown": "Contact the laboratory at labweb1@health.mo.gov.",
                "box": {"left": 0.05, "top": 0.05, "right": 0.95, "bottom": 0.95},
                "verdict": "verified",
                "reason": "identifier inspected character by character",
            }
        )


class _GroupedFigureAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] == "gpt-5.6-luna":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Procedure introduction",
                            "markdown": "Procedure introduction",
                            "box": {"left": 0.2, "top": 0.1, "right": 0.8, "bottom": 0.2},
                            "parent_order": None,
                        },
                        {
                            "type": "figure",
                            "text": "Step one illustration",
                            "markdown": "<figure><description>Step one illustration</description></figure>",
                            "box": {"left": 0.05, "top": 0.25, "right": 0.35, "bottom": 0.45},
                            "parent_order": None,
                        },
                        {
                            "type": "figure",
                            "text": "Step two illustration",
                            "markdown": "<figure><description>Step two illustration</description></figure>",
                            "box": {"left": 0.05, "top": 0.46, "right": 0.35, "bottom": 0.66},
                            "parent_order": None,
                        },
                        {
                            "type": "text",
                            "text": "Procedure conclusion",
                            "markdown": "Procedure conclusion",
                            "box": {"left": 0.2, "top": 0.7, "right": 0.8, "bottom": 0.8},
                            "parent_order": None,
                        },
                    ]
                }
            )
        if kwargs["schema_name"].startswith("page_reconciliation"):
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "text",
                            "text": "Procedure introduction",
                            "markdown": "Procedure introduction",
                            "box": {"left": 0.2, "top": 0.1, "right": 0.8, "bottom": 0.2},
                            "parent_order": None,
                        },
                        {
                            "type": "text",
                            "text": "Procedure conclusion",
                            "markdown": "Procedure conclusion",
                            "box": {"left": 0.2, "top": 0.7, "right": 0.8, "bottom": 0.8},
                            "parent_order": None,
                        },
                    ]
                }
            )
        if kwargs["schema_name"] == "figure_reconciliation_v8":
            return _generation(
                {
                    "chunks": [
                        {
                            "type": "figure",
                            "text": "A numbered two-step illustration sequence.",
                            "markdown": (
                                '<figure type="FLOWCHART"><description>A numbered two-step '
                                "illustration sequence.</description></figure>"
                            ),
                            "box": {"left": 0.04, "top": 0.24, "right": 0.36, "bottom": 0.67},
                            "parent_order": None,
                        }
                    ]
                }
            )
        return _generation(
            {
                "text": "A numbered two-step illustration sequence.",
                "markdown": (
                    '<figure type="FLOWCHART"><description>A numbered two-step '
                    "illustration sequence.</description></figure>"
                ),
                "box": {"left": 0.05, "top": 0.05, "right": 0.95, "bottom": 0.95},
                "verdict": "verified",
                "reason": "figure group is visible",
            }
        )


class _ParentChainAdapter:
    async def generate_structured(self, **kwargs):
        return _generation(
            {
                "chunks": [
                    {
                        "type": "heading",
                        "text": "Shipping Instructions",
                        "markdown": "## Shipping Instructions",
                        "box": {"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.2},
                        "parent_order": None,
                    },
                    {
                        "type": "text",
                        "text": "Send samples by overnight courier.",
                        "markdown": "Send samples by overnight courier.",
                        "box": {"left": 0.1, "top": 0.25, "right": 0.8, "bottom": 0.4},
                        "parent_order": 1,
                    },
                ]
            }
        )


class _MalformedFigureAdapter:
    async def generate_structured(self, **kwargs):
        return _generation(
            {
                "chunks": [
                    {
                        "type": "figure",
                        "text": "Repeated page prose presented as a figure",
                        "markdown": "Repeated page prose presented as a figure",
                        "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.8},
                        "parent_order": None,
                    }
                ]
            }
        )


def test_reconciliation_uses_luna_as_reading_order_spine_and_remaps_parents() -> None:
    draft = [
        {
            "type": "heading",
            "text": "Instructions",
            "markdown": "## Instructions",
            "box": {"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.2},
            "parent_order": None,
        },
        {
            "type": "figure",
            "text": "Visible figure",
            "markdown": "<figure>Visible figure</figure>",
            "box": {"left": 0.1, "top": 0.25, "right": 0.3, "bottom": 0.45},
            "parent_order": 1,
        },
        {
            "type": "text",
            "text": "Original body",
            "markdown": "Original body",
            "box": {"left": 0.35, "top": 0.25, "right": 0.9, "bottom": 0.45},
            "parent_order": 1,
        },
    ]
    reconciled = [
        {
            "type": "text",
            "text": "Corrected body",
            "markdown": "Corrected body",
            "box": {"left": 0.35, "top": 0.25, "right": 0.9, "bottom": 0.45},
            "parent_order": 2,
        },
        {
            "type": "heading",
            "text": "Instructions",
            "markdown": "## Instructions",
            "box": {"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.2},
            "parent_order": None,
        },
    ]

    merged = _merge_reconciled_chunks(draft, reconciled)

    assert [chunk["text"] for chunk in merged] == [
        "Instructions",
        "Visible figure",
        "Corrected body",
    ]
    assert merged[1]["parent_order"] == 1
    assert merged[2]["parent_order"] == 1
    assert merged[1]["_draft_fallback"] is True
    assert merged[0]["_reconciled"] is True
    assert merged[2]["_reconciled"] is True


def test_chunk_agreement_rejects_critical_identifier_mismatch() -> None:
    first = {
        "type": "text",
        "text": "For information email labwebl@health.mo.gov about sample collection.",
        "markdown": "For information email labwebl@health.mo.gov about sample collection.",
        "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
    }
    second = {**first, "text": first["text"].replace("labwebl", "labweb1")}

    assert not _raw_chunks_agree(first, second, strict=True)


async def test_page_markdown_includes_parented_chunks_in_reading_order() -> None:
    result = await V2PageProcessor(_ParentChainAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="8" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    assert result.chunks[1].parent_id == result.chunks[0].id
    assert result.markdown == ("## Shipping Instructions\n\nSend samples by overnight courier.")


async def test_malformed_figure_markdown_becomes_unresolved_semantic_placeholder() -> None:
    result = await V2PageProcessor(_MalformedFigureAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="9" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.UNRESOLVED
    assert chunk.text == ""
    assert chunk.markdown.startswith('<figure type="figure"><description>')
    assert chunk.markdown.endswith("</description></figure>")
    assert "figure_description_unavailable" in chunk.warnings


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


async def test_scanned_table_is_verified_by_full_page_reconciliation() -> None:
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
    assert chunk.grounding[0].evidence_artifact_id.startswith("page:")
    assert chunk.source_pass == "page_reconciliation"
    assert set(result.model_usage) == {"gpt-5.6-luna", "gpt-5.6-terra"}


async def test_balanced_disagreement_preserves_the_luna_candidate() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_DisagreeingAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="c" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.CANDIDATE
    assert chunk.text == "Total 42.00"
    assert chunk.markdown == "| Total | 42.00 |"
    assert chunk.source_model == "gpt-5.6-luna"
    assert chunk.source_pass == "page_draft"
    assert chunk.warnings


async def test_audit_uses_full_page_reconciliation_for_ordinary_disagreement() -> None:
    result = await V2PageProcessor(_DisagreeingAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="c" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.text == "Total 24.00"
    assert chunk.markdown == "| Total | 24.00 |"
    assert "[!WARNING]" not in result.markdown
    assert chunk.source_pass == "page_reconciliation"


async def test_verified_terra_correction_replaces_luna_text_and_markdown() -> None:
    result = await V2PageProcessor(_CorrectingAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="4" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.text == "Total 24.00"
    assert chunk.markdown == "| Total | 24.00 |"
    assert chunk.source_model == "gpt-5.6-terra"
    assert chunk.source_pass == "crop_verification"
    assert chunk.warnings == []


async def test_terra_thousand_scale_page_box_is_normalized() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_ThousandScaleTerraAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="d" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.grounding[0].box == BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.8)


async def test_balanced_invalid_terra_box_preserves_luna_at_the_draft_page_box() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_InvalidTerraBoxAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="e" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.CANDIDATE
    assert chunk.text == "Total 42.00"
    assert chunk.markdown == "| Total | 42.00 |"
    assert chunk.source_model == "gpt-5.6-luna"
    assert chunk.source_pass == "page_draft"
    assert chunk.grounding[0].box == BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.8)
    assert "page_reconciliation_failed" in chunk.warnings


async def test_invalid_scanned_luna_box_preserves_content_without_false_grounding() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_InvalidLunaBoxAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="f" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.CANDIDATE
    assert chunk.text == "Unmatched scan text"
    assert chunk.markdown == "Unmatched scan text"
    assert chunk.grounding == []
    assert "invalid_draft_box" in chunk.warnings
    assert "scan_fallback_used" in chunk.warnings
    assert chunk.source_pass == "page_draft"
    assert result.markdown == "Unmatched scan text"


async def test_invalid_digital_audit_box_keeps_strict_abstention_out_of_markdown() -> None:
    page = RenderedPage(
        1,
        _png(),
        100,
        100,
        [NativeWord(text="Different", bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.2))],
    )

    result = await V2PageProcessor(_InvalidLunaBoxAdapter()).process_page(
        source=_png(),
        filename="digital.pdf",
        source_sha256="1" * 64,
        page=page,
        mode=ProcessingMode.AUDIT,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.UNRESOLVED
    assert chunk.text == ""
    assert chunk.markdown == ""
    assert chunk.grounding == []
    assert chunk.warnings == ["invalid_draft_box"]
    assert result.markdown == ""


async def test_empty_scanned_draft_uses_full_page_terra_recovery() -> None:
    result = await V2PageProcessor(_EmptyDraftRecoveredByTerraAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="2" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].text == "Recovered page text"
    assert result.chunks[0].verification_status == VerificationStatus.VERIFIED
    assert result.markdown == "Recovered page text"


async def test_scanned_audit_uses_terra_fallback_when_luna_is_empty() -> None:
    result = await V2PageProcessor(_TerraOnlyFallbackAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="3" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.VERIFIED
    assert chunk.text == "Recovered by Terra"
    assert chunk.markdown == "Recovered by Terra"
    assert chunk.source_model == "gpt-5.6-terra"
    assert chunk.source_pass == "page_reconciliation"
    assert not chunk.warnings


async def test_empty_figure_gets_semantic_placeholder_not_warning_admonition() -> None:
    result = await V2PageProcessor(_EmptyFigureAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="4" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    chunk = result.chunks[0]
    assert chunk.verification_status == VerificationStatus.UNRESOLVED
    assert chunk.text == ""
    assert chunk.markdown == (
        '<figure type="figure"><description>Visual content present; '
        "description unavailable.</description></figure>"
    )
    assert "figure_description_unavailable" in chunk.warnings
    assert "[!WARNING]" not in result.markdown


async def test_reconciliation_preserves_draft_regions_that_terra_omits() -> None:
    result = await V2PageProcessor(_ReconciliationOmitsDraftRegionAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="5" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    assert [chunk.text for chunk in result.chunks] == [
        "1. First step",
        "9. Final shipping step",
    ]
    assert result.chunks[1].verification_status == VerificationStatus.UNRESOLVED
    assert "scan_fallback_used" in result.chunks[1].warnings
    assert "9. Final shipping step" in result.markdown


async def test_unrepresentable_scanned_luna_box_preserves_candidate_text() -> None:
    page = RenderedPage(1, _png(), 100, 100, [])

    result = await V2PageProcessor(_HugeLunaBoxAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="0" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    assert result.chunks[0].verification_status == VerificationStatus.CANDIDATE
    assert result.chunks[0].text == "Unmatched scan text"
    assert result.chunks[0].grounding == []
    assert result.chunks[0].warnings == ["invalid_draft_box", "scan_fallback_used"]


async def test_exact_native_text_bypasses_an_invalid_luna_box() -> None:
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

    result = await V2PageProcessor(_ExactTextWithInvalidLunaBoxAdapter()).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="1" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    assert result.chunks[0].verification_status == VerificationStatus.VERIFIED
    assert result.chunks[0].grounding[0].method == GroundingMethod.TEXT_LAYER_EXACT


async def test_page_reconciliation_uses_v8_prompt_cache_key() -> None:
    adapter = _CapturingAdapter()
    await V2PageProcessor(adapter).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="2" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.BALANCED,
    )

    for schema in (PAGE_DRAFT_SCHEMA, CROP_VERIFICATION_SCHEMA):
        box = (
            schema["properties"]["chunks"]["items"]["properties"]["box"]
            if "chunks" in schema["properties"]
            else schema["properties"]["box"]
        )
        for coordinate in box["properties"].values():
            assert coordinate["minimum"] == 0
            assert coordinate["maximum"] == 1
    luna_call, terra_call = adapter.calls
    assert CROP_VERIFICATION_SCHEMA["properties"]["markdown"] == {"type": "string"}
    assert "markdown" in CROP_VERIFICATION_SCHEMA["required"]
    assert luna_call["schema_name"] == "page_draft_v8"
    assert terra_call["schema_name"] == "page_reconciliation_v8"
    assert ":v8:" in luna_call["prompt_cache_key"]
    assert ":v8:" in terra_call["prompt_cache_key"]
    assert "decimal coordinates 0-1 relative to the page" in luna_call["instructions"]
    assert "mutually exclusive top-level regions" in terra_call["instructions"]
    assert "<figure" in luna_call["instructions"]


async def test_disagreement_runs_one_targeted_crop_after_page_reconciliation() -> None:
    adapter = _CapturingDisagreeingAdapter()
    await V2PageProcessor(adapter).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="3" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.BALANCED,
    )

    terra_calls = [call for call in adapter.calls if call["model"] == "gpt-5.6-terra"]
    assert len(terra_calls) == 2
    assert terra_calls[0]["schema_name"] == "page_reconciliation_v8"
    assert terra_calls[1]["schema_name"] == "crop_verification_v8"
    assert "decimal coordinates 0-1 relative to the crop" in terra_calls[1]["instructions"]


async def test_audit_identifier_chunk_is_crop_verified_even_when_page_models_agree() -> None:
    adapter = _PrecisionIdentifierAdapter()

    result = await V2PageProcessor(adapter).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="6" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    assert result.chunks[0].text == "Contact the laboratory at labweb1@health.mo.gov."
    assert result.chunks[0].source_pass == "precision_crop"
    assert [call["schema_name"] for call in adapter.calls] == [
        "page_draft_v8",
        "page_reconciliation_v8",
        "crop_verification_v8",
    ]


async def test_audit_groups_connected_figures_and_keeps_them_at_the_luna_anchor() -> None:
    adapter = _GroupedFigureAdapter()

    result = await V2PageProcessor(adapter).process_page(
        source=_png(),
        filename="scan.png",
        source_sha256="7" * 64,
        page=RenderedPage(1, _png(), 100, 100, []),
        mode=ProcessingMode.AUDIT,
    )

    assert [chunk.type for chunk in result.chunks] == ["text", "figure", "text"]
    assert [chunk.text for chunk in result.chunks] == [
        "Procedure introduction",
        "A numbered two-step illustration sequence.",
        "Procedure conclusion",
    ]
    assert any(call["schema_name"] == "figure_reconciliation_v8" for call in adapter.calls)
