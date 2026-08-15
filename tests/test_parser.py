from io import BytesIO

import fitz
import pytest
from PIL import Image

import paperplane.parser as parser_module
from paperplane.contracts import AgenticBlockInput, AgenticPageInput, NormalizedBox
from paperplane.docling_parser import DoclingParseResult
from paperplane.openai_document import OpenAIUsage
from paperplane.parser import (
    DEFAULT_MAX_DOCUMENT_PAGES,
    DEFAULT_MAX_UPLOAD_BYTES,
    AgenticDocumentParser,
)
from paperplane.pdf_inspector_parser import PdfInspectorParseResult
from paperplane.pipeline import PageResult
from paperplane.pipeline_contracts import GroundedChunk


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def _pdf(page_count: int = 2) -> bytes:
    document = fitz.open()
    for page_number in range(1, page_count + 1):
        page = document.new_page(width=200, height=300)
        page.insert_text((20, 40), f"Page {page_number}")
    value = document.tobytes()
    document.close()
    return value


class FakeProcessor:
    def __init__(self) -> None:
        self.calls = []
        self.model = "gpt-5.6-luna"
        self.warnings: list[str] = []

    async def process_page(self, **kwargs):
        self.calls.append(kwargs)
        return PageResult(
            page_number=kwargs["page"].page_number,
            chunks=[
                GroundedChunk(
                    id="text-1",
                    page=1,
                    order=1,
                    type="text",
                    text="Invoice total: 42",
                    markdown="Invoice total: 42",
                    source_model="test",
                    source_pass="draft",
                )
            ],
            markdown="Invoice total: 42",
            input_tokens=1_200,
            output_tokens=300,
            cached_input_tokens=200,
            model_usage={
                "gpt-5.6-luna": OpenAIUsage(
                    input_tokens=1_200,
                    output_tokens=300,
                    cached_input_tokens=200,
                )
            },
            warnings=self.warnings,
        )


class FakeDocling:
    def __init__(self, confidence: float | None = 0.9) -> None:
        self.confidence = confidence
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        selected = sorted(kwargs["requested_pages"])
        return DoclingParseResult(
            pages={
                page: AgenticPageInput(
                    page_number=page,
                    parser="docling",
                    blocks=[
                        AgenticBlockInput(
                            type="text",
                            markdown=f"Local page {page}",
                            box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        )
                    ],
                )
                for page in selected
            },
            warnings=[],
            page_confidence=dict.fromkeys(selected, self.confidence),
        )


@pytest.mark.asyncio
async def test_parser_returns_one_grounded_response_without_persistence() -> None:
    processor = FakeProcessor()
    parser = AgenticDocumentParser(processor, object(), vision_enabled=True)  # type: ignore[arg-type]

    result = await parser.parse(
        data=_png(),
        filename="invoice.png",
        model="paperplane-ade-fast-latest",
    )

    assert result.metadata.page_count == 1
    assert result.metadata.ai_model == "gpt-5.6-luna"
    assert result.metadata.input_tokens == 1_200
    assert result.metadata.output_tokens == 300
    assert result.metadata.cached_input_tokens == 200
    assert result.metadata.model_usage["gpt-5.6-luna"].input_tokens == 1_200
    assert result.metadata.model_usage["gpt-5.6-luna"].cached_input_tokens == 200
    assert result.metadata.processing_strategy == "ai"
    assert result.metadata.page_range == (1, 1)
    assert "Invoice total: 42" in result.markdown
    assert len(processor.calls) == 1


@pytest.mark.asyncio
async def test_parser_surfaces_page_processor_warnings() -> None:
    processor = FakeProcessor()
    processor.warnings = ["DeepSeek OCR skipped text region 2 after two attempts"]
    parser = AgenticDocumentParser(processor, object(), vision_enabled=True)  # type: ignore[arg-type]

    result = await parser.parse(
        data=_png(),
        filename="invoice.png",
        model="paperplane-ade-fast-latest",
    )

    assert result.metadata.warnings == [
        "Page 1: DeepSeek OCR skipped text region 2 after two attempts"
    ]


@pytest.mark.asyncio
async def test_parser_processes_only_requested_pages() -> None:
    processor = FakeProcessor()
    parser = AgenticDocumentParser(processor, FakeDocling(), vision_enabled=True)  # type: ignore[arg-type]

    result = await parser.parse(
        data=_pdf(3),
        filename="report.pdf",
        model="paperplane-ade-fast-latest",
        strategy="ai",
        page_start=2,
        page_end=3,
    )

    assert [call["page"].page_number for call in processor.calls] == [2, 3]
    assert result.metadata.source_page_count == 3
    assert result.metadata.page_range == (2, 3)


@pytest.mark.asyncio
async def test_docling_strategy_never_calls_ai() -> None:
    processor = FakeProcessor()
    docling = FakeDocling()
    parser = AgenticDocumentParser(processor, docling, vision_enabled=False)  # type: ignore[arg-type]

    result = await parser.parse(
        data=_png(),
        filename="scan.png",
        model="paperplane-ade-latest",
        strategy="docling",
    )

    assert processor.calls == []
    assert result.metadata.engine == "docling"
    assert result.metadata.ai_model is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("confidence", "ai_calls"), [(0.80, 0), (0.79, 1), (None, 1)])
async def test_docling_ai_refines_only_below_threshold(
    confidence: float | None, ai_calls: int
) -> None:
    processor = FakeProcessor()
    parser = AgenticDocumentParser(
        processor,
        FakeDocling(confidence),
        vision_enabled=True,  # type: ignore[arg-type]
    )

    result = await parser.parse(
        data=_png(),
        filename="scan.png",
        model="paperplane-ade-latest",
        strategy="docling_ai",
    )

    assert len(processor.calls) == ai_calls
    assert result.metadata.ai_refined_pages == ([1] if ai_calls else [])
    if ai_calls:
        assert processor.calls[0]["context"] == "Local page 1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confidence", "ocr_pages", "expected_pages"),
    [(0.79, [], [1, 2]), (0.80, [2], [2])],
)
async def test_pdf_inspector_ai_uses_explicit_refinement_policy(
    monkeypatch, confidence: float, ocr_pages: list[int], expected_pages: list[int]
) -> None:
    local_pages = {
        page_number: AgenticPageInput(
            page_number=page_number,
            parser="pdf_inspector",
            blocks=[
                AgenticBlockInput(
                    type="text",
                    markdown=f"Inspector page {page_number}",
                    box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                )
            ],
        )
        for page_number in (1, 2)
    }
    monkeypatch.setattr(
        parser_module,
        "parse_pdf_with_inspector",
        lambda _data, _pages: PdfInspectorParseResult(
            pages=local_pages,
            confidence=confidence,
            pdf_type="mixed",
            pages_needing_ocr=ocr_pages,
            warnings=[],
        ),
    )
    processor = FakeProcessor()
    parser = AgenticDocumentParser(processor, FakeDocling(), vision_enabled=True)  # type: ignore[arg-type]

    result = await parser.parse(
        data=_pdf(2),
        filename="report.pdf",
        model="paperplane-ade-latest",
        strategy="pdf_inspector_ai",
    )

    assert [call["page"].page_number for call in processor.calls] == expected_pages
    assert result.metadata.ai_refined_pages == expected_pages
    assert result.metadata.pdf_inspector_confidence == confidence


def test_parser_limits_remain_bounded() -> None:
    assert DEFAULT_MAX_UPLOAD_BYTES == 200 * 1024 * 1024
    assert DEFAULT_MAX_DOCUMENT_PAGES == 500
