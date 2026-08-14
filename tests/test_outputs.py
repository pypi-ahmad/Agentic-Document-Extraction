from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZipFile

from paperplane.outputs import (
    OutputArchiveEntry,
    build_output_archive,
    paper_html_fragment,
    sanitized_html_fragment,
    standalone_html,
)


def test_standalone_html_preserves_document_structure_and_strips_active_content() -> None:
    rendered = standalone_html(
        "# Report\n\n| Name | Value |\n| --- | --- |\n| A | 1 |\n\n"
        '<script>alert(1)</script><a href="javascript:alert(2)" onclick="alert(3)">link</a>',
        '<Quarterly "report">',
    )

    assert rendered.startswith("<!doctype html>")
    assert "&lt;Quarterly &quot;report&quot;&gt;" in rendered
    assert "<table>" in rendered
    assert "<script" not in rendered
    assert "onclick" not in rendered
    assert "javascript:" not in rendered
    assert 'class="paperplane-html-page"' in rendered
    assert "background: #ffffff" in rendered
    assert "color: #000000" in rendered


def test_paper_html_fragment_is_scoped_responsive_and_printable() -> None:
    rendered = paper_html_fragment("# Report\n\n`value`\n\n[Source](https://example.com)")

    assert rendered.startswith("<style>")
    assert 'class="paperplane-html-canvas"' in rendered
    assert 'class="paperplane-html-page"' in rendered
    assert ".paperplane-html-page" in rendered
    assert "background: #ffffff" in rendered
    assert "color: #000000" in rendered
    assert "max-width: 960px" in rendered
    assert "@media print" in rendered
    assert "<h1>Report</h1>" in rendered
    assert '<a href="https://example.com">Source</a>' in rendered


def test_sanitized_html_fragment_has_no_document_level_style_or_script() -> None:
    rendered = sanitized_html_fragment(
        "# Safe\n\n<style>body{display:none}</style><script>x()</script>"
    )

    assert rendered.startswith("<h1>Safe</h1>")
    assert "<style" not in rendered
    assert "<script" not in rendered
    assert "<html" not in rendered


def test_output_archive_contains_safe_per_document_outputs_and_manifest() -> None:
    archive = build_output_archive(
        (
            OutputArchiveEntry(
                filename="../../unsafe\\invoice.pdf",
                status="completed",
                markdown="# Invoice",
                html="<!doctype html><title>Invoice</title>",
                annotated_pdf=b"%PDF-1.7",
                paperplane_json='{"format":"paperplane"}',
                ade_v2_json='{"format":"ade-v2"}',
            ),
        )
    )

    with ZipFile(BytesIO(archive)) as bundle:
        names = bundle.namelist()
        assert names == [
            "manifest.json",
            "01-invoice/invoice.md",
            "01-invoice/invoice.html",
            "01-invoice/invoice.annotated.pdf",
            "01-invoice/invoice.paperplane.json",
            "01-invoice/invoice.ade-v2.json",
        ]
        assert all(
            ".." not in name and "\\" not in name and not name.startswith("/") for name in names
        )
        manifest = json.loads(bundle.read("manifest.json"))

    assert manifest["version"] == 1
    assert manifest["documents"][0]["status"] == "completed"
    assert manifest["documents"][0]["source_filename"] == "../../unsafe\\invoice.pdf"
    assert len(manifest["documents"][0]["files"]) == 5


def test_output_archive_records_failures_without_fake_outputs() -> None:
    archive = build_output_archive(
        (
            OutputArchiveEntry(
                filename="failed.pdf",
                status="failed",
                error="Parse failed",
            ),
            OutputArchiveEntry(
                filename="partial.pdf",
                status="completed",
                markdown="ok",
                html="<p>ok</p>",
                paperplane_json="{}",
                ade_v2_json="{}",
            ),
        )
    )

    with ZipFile(BytesIO(archive)) as bundle:
        names = bundle.namelist()
        manifest = json.loads(bundle.read("manifest.json"))

    assert names == [
        "manifest.json",
        "02-partial/partial.md",
        "02-partial/partial.html",
        "02-partial/partial.paperplane.json",
        "02-partial/partial.ade-v2.json",
    ]
    assert manifest["documents"][0] == {
        "source_filename": "failed.pdf",
        "status": "failed",
        "error": "Parse failed",
        "files": [],
    }
    assert manifest["documents"][1]["status"] == "completed"
    assert len(manifest["documents"][1]["files"]) == 4
