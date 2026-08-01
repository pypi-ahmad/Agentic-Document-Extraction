import pytest

from app.services.parsing.contracts import (
    BoundingBox,
    DocumentLayout,
    PageLayout,
    Region,
    TableCell,
)
from app.services.parsing.markdown import MarkdownRenderer, render_llm_markdown


def _box(top: float, bottom: float) -> BoundingBox:
    return BoundingBox(left=0.1, top=top, right=0.9, bottom=bottom)


def test_clean_markdown_preserves_semantics_without_grounding() -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=200,
                regions=[
                    Region(
                        type="title",
                        bbox=_box(0.05, 0.1),
                        content="Quarterly Report",
                        source="native",
                    ),
                    Region(
                        type="text",
                        bbox=_box(0.2, 0.3),
                        content="Revenue grew.\nacross regions",
                        source="native",
                    ),
                    Region(
                        type="table",
                        bbox=_box(0.4, 0.7),
                        content="",
                        table_rows=[["Region", "Revenue"], ["East", "$10"]],
                    ),
                    Region(type="page_number", bbox=_box(0.95, 0.99), content="1", source="native"),
                ],
            )
        ]
    ).with_stable_ids()

    rendered = MarkdownRenderer().render(document)

    assert (
        rendered.clean
        == "# Quarterly Report\n\nRevenue grew. across regions\n\n| Region | Revenue |\n| --- | --- |\n| East | $10 |\n"
    )
    assert "region:" not in rendered.clean
    assert "page_number" in rendered.grounded
    assert "bbox=0.1000,0.0500,0.9000,0.1000" in rendered.grounded


def test_llm_markdown_preserves_hierarchy_and_grounded_citations() -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=200,
                regions=[
                    Region(
                        id="p0001-r0001",
                        type="title",
                        heading_level=1,
                        bbox=_box(0.05, 0.1),
                        content="Quarterly Report",
                        source="cloud_vlm",
                    ),
                    Region(
                        id="p0001-r0002",
                        type="heading",
                        heading_level=2,
                        bbox=_box(0.15, 0.2),
                        content="Revenue",
                        source="cloud_vlm",
                    ),
                    Region(
                        id="p0001-r0003",
                        type="text",
                        bbox=_box(0.25, 0.35),
                        content="Revenue grew.",
                        source="cloud_vlm",
                    ),
                ],
            )
        ]
    )

    rendered = render_llm_markdown(
        document,
        source_filename="quarterly-report.pdf",
        source_sha256="a" * 64,
    )

    assert "paperplane_schema: llm-markdown/v2" in rendered
    assert "# Quarterly Report" in rendered
    assert "## Revenue" in rendered
    assert '"region_id":"p0001-r0003"' in rendered
    assert '"parent_id":"p0001-r0002"' in rendered
    assert '"bbox":[0.1,0.25,0.9,0.35]' in rendered


def test_llm_markdown_emits_cell_level_table_citation_manifest() -> None:
    table = Region(
        id="p0001-r0001",
        type="table",
        bbox=_box(0.1, 0.7),
        content="",
        table_rows=[["Item", "Amount"], ["Widget", "$10"]],
        table_cells=[
            TableCell(
                bbox=BoundingBox(left=0.1, top=0.1, right=0.5, bottom=0.2),
                row=0,
                column=0,
                text="Item",
            ),
            TableCell(
                bbox=BoundingBox(left=0.5, top=0.1, right=0.9, bottom=0.2),
                row=0,
                column=1,
                text="Amount",
            ),
        ],
    )
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1, width=612, height=792, coordinate_unit="pdf_points", regions=[table]
            )
        ]
    )

    rendered = render_llm_markdown(document, source_filename="invoice.pdf", source_sha256="a" * 64)

    assert "paperplane-table-citations: table-citations/v1" in rendered
    assert '"cell_id":"p0001-r0001-c0001"' in rendered
    assert '"source_bbox":[61.2,79.2,306.0,158.4]' in rendered


def test_complex_table_html_is_sanitized() -> None:
    region = Region(
        type="table",
        bbox=_box(0.1, 0.5),
        content='<table><tr><td rowspan="2">A<script>alert(1)</script></td></tr></table>',
    )
    document = DocumentLayout(
        pages=[PageLayout(page_number=1, width=100, height=100, regions=[region])]
    ).with_stable_ids()

    clean = MarkdownRenderer().render(document).clean

    assert "<table>" in clean
    assert 'rowspan="2"' in clean
    assert "<script>" not in clean
    assert "alert(1)" not in clean


def test_unreadable_empty_region_is_explicit() -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=10,
                height=10,
                regions=[Region(type="text", bbox=_box(0.1, 0.2), content="")],
            )
        ]
    ).with_stable_ids()

    assert "[unclear]" in MarkdownRenderer().render(document).clean


def test_chart_renders_as_llm_ready_text_instead_of_an_image_link() -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                regions=[
                    Region(
                        type="chart",
                        bbox=_box(0.1, 0.9),
                        content="Revenue by year: 2024 = 35; 2025 = 42.",
                    )
                ],
            )
        ]
    ).with_stable_ids()

    clean = MarkdownRenderer().render(document).clean

    assert "### Chart\n\nRevenue by year" in clean
    assert "![" not in clean


def test_figure_without_real_crop_renders_as_llm_ready_text() -> None:
    region = Region(type="figure", bbox=_box(0.1, 0.9), content="A labelled turbine diagram.")
    document = DocumentLayout(
        pages=[PageLayout(page_number=1, width=100, height=100, regions=[region])]
    ).with_stable_ids()
    clean = MarkdownRenderer().render(document).clean
    assert clean == "**Figure:** A labelled turbine diagram.\n"
    assert "](#)" not in clean


def test_figure_with_real_crop_retains_image_markdown() -> None:
    region = Region(
        type="figure",
        bbox=_box(0.1, 0.9),
        content="A labelled turbine diagram.",
        crop_path="figures/p1-r1.png",
    )
    document = DocumentLayout(
        pages=[PageLayout(page_number=1, width=100, height=100, regions=[region])]
    ).with_stable_ids()
    assert MarkdownRenderer().render(document).clean == (
        "![A labelled turbine diagram.](figures/p1-r1.png)\n"
    )


def test_marginalia_policy_keeps_unique_headers_and_removes_repeated_headers() -> None:
    pages = {
        1: [
            Region(type="header", bbox=_box(0.01, 0.05), content="Repeated header"),
            Region(type="text", bbox=_box(0.1, 0.4), content="First body"),
        ],
        2: [
            Region(type="header", bbox=_box(0.01, 0.05), content="Repeated header"),
            Region(type="footer", bbox=_box(0.9, 0.99), content="Unique note"),
            Region(type="text", bbox=_box(0.1, 0.4), content="Second body"),
        ],
    }
    parser = __import__("app.services.parsing.parser", fromlist=["LayoutParser"]).LayoutParser()

    removed = parser.stitch_document(pages, marginalia_policy="remove_repeated")
    kept = parser.stitch_document(pages, marginalia_policy="keep_all")

    assert "Repeated header" not in removed.clean_markdown
    assert "Unique note" in removed.clean_markdown
    assert kept.clean_markdown.count("Repeated header") == 2


@pytest.mark.parametrize(
    ("content", "body"),
    [
        ("E = mc^2", "E = mc^2"),
        ("$E = mc^2$", "E = mc^2"),
        ("$$E = mc^2$$", "E = mc^2"),
        (r"\(E = mc^2\)", "E = mc^2"),
        (r"\[E = mc^2\]", "E = mc^2"),
        (r"$R = \$42 + x$", r"R = \$42 + x"),
    ],
)
def test_formula_renderer_emits_exactly_one_display_wrapper(content: str, body: str) -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=10,
                height=10,
                regions=[Region(type="formula", bbox=_box(0.1, 0.2), content=content)],
            )
        ]
    ).with_stable_ids()

    clean = MarkdownRenderer().render(document).clean

    assert clean == f"$$\n{body}\n$$\n"
    assert clean.count("$$") == 2


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("print('ok')", "```\nprint('ok')\n```\n"),
        ("```python\nprint('ok')\n```", "```python\nprint('ok')\n```\n"),
        ("```python\nvalue = ```marker```\n```", "````python\nvalue = ```marker```\n````\n"),
    ],
)
def test_code_renderer_normalizes_outer_fence_and_avoids_internal_runs(content, expected) -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=10,
                height=10,
                regions=[Region(type="code", bbox=_box(0.1, 0.2), content=content)],
            )
        ]
    ).with_stable_ids()
    assert MarkdownRenderer().render(document).clean == expected
