from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

from paperplane.docling_parser import DOCLING_FORMATS, create_docling_converter


def test_docling_converter_supports_native_formats_without_torch_compilation() -> None:
    converter = create_docling_converter()
    options = converter.format_to_options[InputFormat.PDF].pipeline_options

    assert isinstance(options, PdfPipelineOptions)
    assert options.layout_options.engine_options.compile_model is False
    assert set(DOCLING_FORMATS) == {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".odt",
        ".odp",
        ".ods",
        ".csv",
    }
