from io import BytesIO

from PIL import Image, ImageDraw

from paperplane.pipeline_contracts import GroundedChunk, VerificationStatus
from paperplane.reconciliation import (
    assess_page_quality,
    clean_repeated_labels,
    extract_critical_tokens,
    normalize_extracted_text,
    overlap_over_smaller_area,
    requires_precision_verification,
    suppress_duplicate_chunks,
)
from paperplane.types import BoundingBox


def _chunk(identifier: str, text: str, box: BoundingBox, *, status="candidate"):
    chunk = GroundedChunk(
        id=identifier,
        page=1,
        order=int(identifier[-1]),
        type="text",
        text=text,
        markdown=text,
        source_model="gpt-5.6-luna",
        source_pass="page_draft",
        verification_status=VerificationStatus.CANDIDATE,
    )
    return chunk.model_copy(update={"verification_status": VerificationStatus(status)}), box


def test_normalizer_preserves_digit_hyphens_but_joins_word_fragments() -> None:
    assert normalize_extracted_text("573-751-\n3334") == "573-751-3334"
    assert normalize_extracted_text("environ-\nmental") == "environmental"
    assert (
        normalize_extracted_text("A paragraph\nwrapped normally.")
        == "A paragraph wrapped normally."
    )


def test_normalizer_removes_hidden_unicode_formatting_characters() -> None:
    assert normalize_extracted_text("Lys\u00adkowski\u200b") == "Lyskowski"


def test_repeated_label_cleanup_is_exact_and_local() -> None:
    assert clean_repeated_labels("Routine \u2013 Routine \u2013 Regular monthly monitoring") == (
        "Routine \u2013 Regular monthly monitoring"
    )
    assert clean_repeated_labels(
        "No Paper Label:\nThere is no longer a label", "No Paper Label:"
    ) == ("There is no longer a label")
    assert clean_repeated_labels("Very very cold water") == "Very very cold water"


def test_repeated_label_cleanup_normalizes_basic_block_html_to_markdown() -> None:
    assert (
        clean_repeated_labels("<p><strong>Order #:</strong> Laboratory use only.</p>")
        == "**Order #:** Laboratory use only."
    )
    assert clean_repeated_labels("First line<br>Second line") == "First line\nSecond line"


def test_precision_verification_detects_identifiers_and_dense_regions() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3)

    assert "labweb1@health.mo.gov" in extract_critical_tokens("Email: labweb1@health.mo.gov")
    assert requires_precision_verification("text", "Email: labweb1@health.mo.gov", box)
    assert requires_precision_verification("form_field", "PWS ID: MO#######", box)
    assert requires_precision_verification("form_field", "", box)
    assert not requires_precision_verification("form_field", "County: BATES", box)
    assert not requires_precision_verification("text", "word " * 100, box)
    assert not requires_precision_verification("text", "Short ordinary sentence.", box)


def test_overlap_uses_intersection_over_smaller_area() -> None:
    outer = BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9)
    inner = BoundingBox(left=0.2, top=0.2, right=0.4, bottom=0.4)
    assert overlap_over_smaller_area(outer, inner) == 1.0


def test_quality_gate_flags_overlaps_and_uncovered_ink() -> None:
    image = Image.new("L", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((70, 10, 90, 90), fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    chunks = [
        _chunk("p1-c1", "Alpha", BoundingBox(left=0.05, top=0.05, right=0.5, bottom=0.5)),
        _chunk("p1-c2", "Alpha detail", BoundingBox(left=0.1, top=0.1, right=0.45, bottom=0.45)),
    ]

    assessment = assess_page_quality(chunks, output.getvalue())

    assert assessment.flagged
    assert "overlapping_siblings" in assessment.reasons
    assert "uncovered_ink" in assessment.reasons


def test_quality_gate_detects_duplicate_text_inside_parent_hierarchy() -> None:
    image = Image.new("L", (100, 100), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2)
    parent, _ = _chunk("p1-c1", "Requested analysis", box)
    child, _ = _chunk("p1-c2", "Requested analysis", box)
    child = child.model_copy(update={"parent_id": parent.id})

    assessment = assess_page_quality([(parent, box), (child, box)], output.getvalue())

    assert "duplicate_text" in assessment.reasons


def test_duplicate_suppression_prefers_verified_then_longer() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2)
    candidate, _ = _chunk("p1-c1", "Public water sample", box)
    verified, _ = _chunk("p1-c2", "Public water sample", box, status="verified")

    kept = suppress_duplicate_chunks([(candidate, box), (verified, box)])

    assert [chunk.id for chunk, _ in kept] == ["p1-c2"]


def test_duplicate_suppression_keeps_long_recovered_content_containing_short_text() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.4)
    verified, _ = _chunk("p1-c1", "Sample instructions", box, status="verified")
    recovered, _ = _chunk(
        "p1-c2",
        "Sample instructions collect the water in the morning and seal the shipping box.",
        box,
        status="unresolved",
    )

    kept = suppress_duplicate_chunks([(verified, box), (recovered, box)])

    assert [chunk.id for chunk, _ in kept] == ["p1-c1", "p1-c2"]


def test_duplicate_suppression_collapses_same_region_across_semantic_types() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2)
    text, _ = _chunk("p1-c1", "Requested analysis", box, status="verified")
    heading = text.model_copy(update={"id": "p1-c2", "order": 2, "type": "heading"})

    kept = suppress_duplicate_chunks([(text, box), (heading, box)])

    assert [chunk.id for chunk, _ in kept] == ["p1-c2"]


def test_duplicate_suppression_keeps_verified_longer_contained_content() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.4)
    fragment, _ = _chunk("p1-c1", "There is no longer a lab", box, status="verified")
    paragraph, _ = _chunk(
        "p1-c2",
        "No Paper Label: There is no longer a label to record sample information.",
        box,
        status="verified",
    )

    kept = suppress_duplicate_chunks([(fragment, box), (paragraph, box)])

    assert [chunk.id for chunk, _ in kept] == ["p1-c2"]


def test_contained_duplicate_prefers_more_tokens_over_more_characters() -> None:
    box = BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.4)
    text, _ = _chunk(
        "p1-c1",
        (
            "Missouri Department of Health & Senior Services State Public Health Laboratory "
            "101 N. Chestnut PO Box 570 Jefferson City, MO 65102 "
            "http://www.health.mo.gov/lab/index.php Online Laboratory Directory SD 062015"
        ),
        box,
        status="verified",
    )
    footer = text.model_copy(
        update={
            "id": "p1-c2",
            "order": 2,
            "type": "footer",
            "text": (
                "Missouri Department of Health & Senior Services State Public Health Laboratory "
                "101 N. Chestnut PO Box 570 Jefferson City, MO 65102 "
                "http://www.health.mo.gov/lab/index.php email: labweb@dhss.mo.gov SD 062015"
            ),
            "markdown": (
                "Missouri Department of Health & Senior Services State Public Health Laboratory "
                "101 N. Chestnut PO Box 570 Jefferson City, MO 65102 "
                "http://www.health.mo.gov/lab/index.php email: labweb@dhss.mo.gov SD 062015"
            ),
        }
    )

    kept = suppress_duplicate_chunks([(text, box), (footer, box)])

    assert [chunk.id for chunk, _ in kept] == ["p1-c2"]
