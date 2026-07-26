"""Create sub-document files from an already parsed parent document."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image

from app.models.enums import ArtifactType
from app.models.schemas import ParseSettings
from app.services.parsing.artifacts import (
    build_bundle,
    build_grounding_pdf,
    build_searchable_pdf,
)
from app.services.parsing.contracts import ContextChunk, DocumentLayout
from app.services.parsing.domain_extraction import extract_domain
from app.services.parsing.markdown import render_llm_markdown
from app.services.parsing.parser import LayoutParser
from app.services.parsing.segmentation import DetectedSubDocument
from app.services.parsing.structured_blocks import build_structured_document

ArtifactPayload = tuple[str, str, bytes, str, str | None]


def build_subdocument_payloads(
    *,
    source: bytes,
    source_filename: str,
    source_sha256: str,
    layout: DocumentLayout,
    segment: DetectedSubDocument,
    settings: ParseSettings,
    figure_crops: dict[str, str],
) -> list[ArtifactPayload]:
    source_pdf = _slice_source(source, source_filename, segment.start_page, segment.end_page)
    local_layout = _slice_layout(layout, segment.start_page, segment.end_page)
    parser = LayoutParser()
    stitched = parser.stitch_layout(local_layout, settings.marginalia_policy)
    structured = build_structured_document(
        local_layout, source_filename=source_filename, source_sha256=source_sha256
    )
    context = {
        "schema_version": "2",
        "complete": segment.complete,
        "missing_pages": [page - segment.start_page + 1 for page in segment.missing_pages],
        "missing_source_pages": segment.missing_pages,
        "chunks": [chunk.model_dump(mode="json") for chunk in stitched.context_chunks],
    }
    chunks = [ContextChunk.model_validate(item) for item in context["chunks"]]
    extraction = extract_domain(
        chunks,
        segment.profile if segment.profile != "unknown" else "general_scanned",
        expected_pages=list(range(1, segment.end_page - segment.start_page + 2)),
    )
    payloads: list[ArtifactPayload] = [
        (ArtifactType.SOURCE_DOCUMENT, "source.pdf", source_pdf, "application/pdf", None),
        (
            ArtifactType.CLEAN_MARKDOWN,
            "document.md",
            stitched.clean_markdown.encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.LLM_MARKDOWN,
            "document.llm.md",
            render_llm_markdown(
                local_layout,
                source_filename=source_filename,
                source_sha256=source_sha256,
                marginalia_policy=settings.marginalia_policy,
            ).encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.GROUNDED_MARKDOWN,
            "document.grounded.md",
            stitched.grounded_markdown.encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.CONTEXT_JSON,
            "document.context.json",
            json.dumps(context, ensure_ascii=False, indent=2).encode(),
            "application/json",
            None,
        ),
        (
            ArtifactType.STRUCTURED_BLOCKS,
            "document.blocks.json",
            structured.model_dump_json(indent=2).encode(),
            "application/json",
            None,
        ),
        (
            ArtifactType.DOMAIN_EXTRACTION,
            "document.extraction.json",
            extraction.model_dump_json(indent=2).encode(),
            "application/json",
            None,
        ),
    ]
    payloads.append(
        (
            ArtifactType.GROUNDING_PDF,
            "annotated.pdf",
            build_grounding_pdf(source_pdf, "source.pdf", local_layout),
            "application/pdf",
            None,
        )
    )
    if settings.searchable_pdf:
        searchable, _ = build_searchable_pdf(source_pdf, "source.pdf", local_layout)
        payloads.append(
            (ArtifactType.SEARCHABLE_PDF, "searchable.pdf", searchable, "application/pdf", None)
        )
    figure_regions = [
        region
        for page in local_layout.pages
        for region in page.regions
        if region.id and region.semantic_metadata.get("source_region_id") in figure_crops
    ]
    for region in figure_regions:
        source_region_id = str(region.semantic_metadata["source_region_id"])
        path = Path(figure_crops[source_region_id])
        if path.is_file():
            payloads.append(
                (
                    ArtifactType.FIGURE,
                    f"figures/{region.id}.png",
                    path.read_bytes(),
                    "image/png",
                    region.id,
                )
            )
    if settings.bundle:
        bundle_files = {filename: data for _, filename, data, _, _ in payloads}
        payloads.append(
            (
                ArtifactType.BUNDLE,
                "document-bundle.zip",
                build_bundle(bundle_files),
                "application/zip",
                None,
            )
        )
    return payloads


def _slice_layout(layout: DocumentLayout, start_page: int, end_page: int) -> DocumentLayout:
    pages = []
    for source_page in layout.pages:
        if not start_page <= source_page.page_number <= end_page:
            continue
        local_page = source_page.model_copy(deep=True)
        local_page.source_page_number = source_page.page_number
        local_page.page_number = source_page.page_number - start_page + 1
        for source_region, local_region in zip(
            source_page.regions, local_page.regions, strict=True
        ):
            local_region.semantic_metadata["source_region_id"] = source_region.id
        pages.append(local_page)
    return DocumentLayout(pages=pages, warnings=list(layout.warnings)).with_stable_ids()


def _slice_source(source: bytes, filename: str, start_page: int, end_page: int) -> bytes:
    if Path(filename).suffix.lower() == ".pdf":
        parent = fitz.open(stream=source, filetype="pdf")
        child = fitz.open()
        try:
            child.insert_pdf(parent, from_page=start_page - 1, to_page=end_page - 1)
            return child.tobytes(garbage=3, deflate=True)
        finally:
            child.close()
            parent.close()
    images: list[Image.Image] = []
    with Image.open(BytesIO(source)) as image:
        for page in range(start_page - 1, end_page):
            image.seek(page)
            images.append(image.convert("RGB").copy())
    output = BytesIO()
    images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
    return output.getvalue()
