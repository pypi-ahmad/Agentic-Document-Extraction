"""Safe, portable output files for completed Parse batches."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

import bleach
import markdown

_HTML_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_HTML_ATTRIBUTES = {
    "a": ["href", "title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}


@dataclass(frozen=True, slots=True)
class OutputArchiveEntry:
    """One source document and its generated, downloadable outputs."""

    filename: str
    status: Literal["completed", "failed"]
    error: str | None = None
    markdown: str | None = None
    html: str | None = None
    annotated_pdf: bytes | None = None
    paperplane_json: str | None = None
    ade_v2_json: str | None = None


def standalone_html(markdown_text: str, title: str) -> str:
    """Convert untrusted layout-aware Markdown into a sanitized HTML document."""

    body = sanitized_html_fragment(markdown_text)
    safe_title = html.escape(title, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{ color: #1f2937; font: 16px/1.6 system-ui, sans-serif; margin: 0 auto;
      max-width: 1100px; padding: 2rem; }}
    table {{ border-collapse: collapse; display: block; max-width: 100%; overflow-x: auto; }}
    th, td {{ border: 1px solid #d1d5db; padding: .45rem .65rem; text-align: left; }}
    pre {{ background: #f3f4f6; border-radius: .35rem; overflow-x: auto; padding: 1rem; }}
    code {{ overflow-wrap: anywhere; }}
    a {{ color: #075985; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def sanitized_html_fragment(markdown_text: str) -> str:
    """Return safe HTML content without page-level styles for in-app preview."""

    converted = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    return bleach.clean(
        converted,
        tags=_HTML_TAGS,
        attributes=_HTML_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def build_output_archive(entries: Sequence[OutputArchiveEntry]) -> bytes:
    """Build a traversal-safe ZIP with a versioned batch manifest."""

    buffer = BytesIO()
    manifest_documents: list[dict[str, object]] = []
    pending_files: list[tuple[str, str | bytes]] = []

    for index, entry in enumerate(entries, start=1):
        stem = safe_output_stem(entry.filename)
        folder = f"{index:02d}-{stem}"
        document_files: list[str] = []
        if entry.status == "completed":
            candidates: tuple[tuple[str, str | bytes | None], ...] = (
                (f"{stem}.md", entry.markdown),
                (f"{stem}.html", entry.html),
                (f"{stem}.annotated.pdf", entry.annotated_pdf),
                (f"{stem}.paperplane.json", entry.paperplane_json),
                (f"{stem}.ade-v2.json", entry.ade_v2_json),
            )
            for filename, payload in candidates:
                if payload is None:
                    continue
                archive_path = f"{folder}/{filename}"
                document_files.append(archive_path)
                pending_files.append((archive_path, payload))

        manifest_documents.append(
            {
                "source_filename": entry.filename,
                "status": entry.status,
                "error": entry.error,
                "files": document_files,
            }
        )

    manifest = {"version": 1, "documents": manifest_documents}
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for archive_path, payload in pending_files:
            bundle.writestr(archive_path, payload)
    return buffer.getvalue()


def safe_output_stem(filename: str) -> str:
    """Return a portable filename stem with no path or device-name semantics."""

    leaf = re.split(r"[/\\]", unicodedata.normalize("NFKC", filename))[-1]
    stem = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(" .-_")[:80]
    safe = safe or "document"
    if safe.casefold() in _WINDOWS_RESERVED_NAMES:
        safe = f"document-{safe}"
    return safe
