import pytest
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions

from paperplane.docling_parser import (
    DOCLING_FORMATS,
    DoclingDocumentParser,
    create_docling_converter,
)


def test_docling_converter_supports_native_formats_without_torch_compilation() -> None:
    converter = create_docling_converter()
    options = converter.format_to_options[InputFormat.PDF].pipeline_options

    assert isinstance(options, PdfPipelineOptions)
    assert options.layout_options.engine_options.compile_model is False
    assert options.do_ocr is True
    assert isinstance(options.ocr_options, RapidOcrOptions)
    assert options.ocr_options.backend == "torch"
    assert InputFormat.IMAGE in converter.allowed_formats
    assert set(DOCLING_FORMATS) == {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".odt",
        ".odp",
        ".ods",
        ".csv",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
    }


@pytest.mark.asyncio
async def test_plain_docling_uses_figure_placeholder_without_failure_warning() -> None:
    class Picture:
        @staticmethod
        def caption_text(_document):
            return "Chart"

        @staticmethod
        def get_image(_document):
            return None

    warnings: list[str] = []
    parser = DoclingDocumentParser(object())  # type: ignore[arg-type]

    markdown = await parser._figure_markdown(
        object(), Picture(), describe_figure=None, warnings=warnings  # type: ignore[arg-type]
    )

    assert "description unavailable" in markdown
    assert warnings == []
