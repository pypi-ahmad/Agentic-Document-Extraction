from io import BytesIO

import pytest
from PIL import Image

from paperplane.parser import (
    DEFAULT_MAX_DOCUMENT_PAGES,
    DEFAULT_MAX_UPLOAD_BYTES,
    AgenticDocumentParser,
)
from paperplane.pipeline import PageResult
from paperplane.pipeline_contracts import GroundedChunk


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


class FakeProcessor:
    def __init__(self) -> None:
        self.calls = []
        self.model = "gpt-5.6-luna"

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
    assert "Invoice total: 42" in result.markdown
    assert len(processor.calls) == 1


def test_parser_limits_remain_bounded() -> None:
    assert DEFAULT_MAX_UPLOAD_BYTES == 200 * 1024 * 1024
    assert DEFAULT_MAX_DOCUMENT_PAGES == 500
