import pytest
from pydantic import ValidationError

from app.models.schemas import ParseSettings
from app.services.parsing.contracts import BoundingBox, DocumentLayout, PageLayout, Region


def test_parse_settings_defaults_are_safe() -> None:
    settings = ParseSettings()

    assert settings.ocr_provider == "glmocr"
    assert settings.review_provider == "ollama"
    assert settings.processing_mode == "local_only"
    assert settings.cloud_mode == "off"
    assert settings.blind_local_retry is False
    assert settings.start_page == 1
    assert settings.end_page is None
    assert settings.input_mode == "mixed"
    assert settings.dpi == 200
    assert settings.layout_device == "auto"
    assert settings.region_concurrency == 2
    assert settings.describe_figures is True
    assert settings.document_profile == "auto"
    assert settings.structured_extraction is True
    assert settings.allow_sensitive_cloud is False
    assert settings.segment_documents is True


def test_parse_settings_rejects_unknown_model_provider() -> None:
    with pytest.raises(ValidationError):
        ParseSettings(ocr_provider="unknown")  # type: ignore[arg-type]


def test_parse_settings_rejects_unknown_input_mode() -> None:
    with pytest.raises(ValidationError):
        ParseSettings(input_mode="auto")  # type: ignore[arg-type]


def test_cloud_context_requires_a_model_when_enabled() -> None:
    with pytest.raises(ValidationError, match="review_model"):
        ParseSettings(cloud_mode="adaptive", review_provider="openai")


def test_legacy_review_selection_enables_adaptive_context() -> None:
    settings = ParseSettings.model_validate(
        {"review_provider": "openai", "review_model": "vision-model"}
    )

    assert settings.cloud_mode == "adaptive"
    assert settings.processing_mode == "hybrid"


def test_processing_presets_normalize_low_level_routing() -> None:
    hybrid = ParseSettings(
        processing_mode="hybrid",
        review_provider="openai",
        review_model="vision-model",
    )
    maximum = ParseSettings(
        processing_mode="maximum_accuracy",
        review_provider="openai",
        review_model="vision-model",
        blind_local_retry=True,
    )

    assert hybrid.cloud_mode == "adaptive"
    assert hybrid.blind_local_retry is False
    assert maximum.cloud_mode == "all_pages"
    assert maximum.blind_local_retry is True


@pytest.mark.parametrize("value", [0, 9])
def test_parse_settings_rejects_unsafe_region_concurrency(value: int) -> None:
    with pytest.raises(ValidationError):
        ParseSettings(region_concurrency=value)


def test_parse_settings_rejects_reversed_page_range() -> None:
    with pytest.raises(ValidationError, match="end_page"):
        ParseSettings(start_page=5, end_page=4)


def test_sensitive_profile_requires_explicit_cloud_consent() -> None:
    with pytest.raises(ValidationError, match="allow_sensitive_cloud"):
        ParseSettings(
            processing_mode="hybrid",
            review_provider="openai",
            review_model="vision-model",
            document_profile="healthcare_form",
        )


def test_sensitive_profile_accepts_explicit_cloud_consent() -> None:
    settings = ParseSettings(
        processing_mode="hybrid",
        review_provider="openai",
        review_model="vision-model",
        document_profile="insurance_claim",
        allow_sensitive_cloud=True,
    )

    assert settings.cloud_mode == "adaptive"


def test_legacy_grounding_pdf_false_is_normalized_to_required_output() -> None:
    settings = ParseSettings(grounding_pdf=False)

    assert settings.grounding_pdf is True


def test_bounding_box_requires_normalized_coordinates() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(left=-0.1, top=0, right=1, bottom=1)


def test_document_layout_assigns_stable_region_ids() -> None:
    page = PageLayout(
        page_number=1,
        width=100,
        height=200,
        regions=[
            Region(
                type="text", bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2), content="A"
            ),
            Region(
                type="table",
                bbox=BoundingBox(left=0.1, top=0.3, right=0.9, bottom=0.8),
                content="B",
            ),
        ],
    )

    document = DocumentLayout(pages=[page]).with_stable_ids()

    assert [region.id for region in document.pages[0].regions] == ["p0001-r0001", "p0001-r0002"]


def test_document_layout_assigns_stable_table_cell_ids() -> None:
    from app.services.parsing.contracts import TableCell

    page = PageLayout(
        page_number=1,
        width=100,
        height=200,
        regions=[
            Region(
                type="table",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9),
                content="",
                table_cells=[
                    TableCell(
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.4, bottom=0.2), row=0, column=0
                    )
                ],
            )
        ],
    )

    document = DocumentLayout(pages=[page]).with_stable_ids()

    assert document.pages[0].regions[0].table_cells[0].id == "p0001-r0001-c0001"
    assert document.pages[0].regions[0].table_cells[0].page == 1
    assert document.pages[0].regions[0].table_cells[0].parent_region_id == "p0001-r0001"


def test_region_accepts_chart_type() -> None:
    region = Region(
        type="chart",
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9),
        content="Quarterly revenue",
    )

    assert region.type == "chart"


def test_region_accepts_cloud_vlm_source_and_reading_order() -> None:
    region = Region(
        type="text",
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9),
        content="Body",
        source="cloud_vlm",
        order=3,
    )

    assert region.source == "cloud_vlm"
    assert region.order == 3


@pytest.mark.parametrize("region_type", ["form_field", "checkbox", "signature", "seal"])
def test_region_accepts_auditable_form_types(region_type: str) -> None:
    region = Region(
        type=region_type,  # type: ignore[arg-type]
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9),
        content="value",
    )

    assert region.type == region_type
