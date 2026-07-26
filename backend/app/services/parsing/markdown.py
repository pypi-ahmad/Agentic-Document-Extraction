"""Deterministic clean and grounded Markdown assembly."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar

from app.services.parsing.contracts import DocumentLayout, Region
from app.services.parsing.structured_blocks import source_bbox


@dataclass(frozen=True)
class MarkdownOutput:
    clean: str
    grounded: str


class _TableSanitizer(HTMLParser):
    allowed_tags: ClassVar[set[str]] = {
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
    }
    allowed_attrs: ClassVar[set[str]] = {"rowspan", "colspan", "scope"}
    blocked_tags: ClassVar[set[str]] = {"script", "style", "iframe", "object"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.blocked_tags:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in self.allowed_tags:
            return
        clean_attrs = "".join(
            f' {name.lower()}="{html.escape(value or "", quote=True)}"'
            for name, value in attrs
            if name.lower() in self.allowed_attrs
        )
        self.parts.append(f"<{tag}{clean_attrs}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.blocked_tags and self.blocked_depth:
            self.blocked_depth -= 1
            return
        if not self.blocked_depth and tag in self.allowed_tags:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(html.escape(data))


def _sanitize_table(value: str) -> str:
    parser = _TableSanitizer()
    parser.feed(value)
    return "".join(parser.parts).strip()


def _normalize_text(value: str) -> str:
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return re.sub(r"[ \t]+", " ", value).strip()


def _table_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return "[unclear]"
    width = max(len(row) for row in rows)

    def cells(row: list[str]) -> list[str]:
        padded = row + [""] * (width - len(row))
        return [cell.replace("|", "\\|").strip() for cell in padded]

    lines = ["| " + " | ".join(cells(rows[0])) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    lines.extend("| " + " | ".join(cells(row)) + " |" for row in rows[1:])
    return "\n".join(lines)


def _region_markdown(region: Region) -> str:
    content = (
        region.content.strip()
        if region.type in {"table", "code"}
        else _normalize_text(region.content)
    )
    if region.type == "table":
        if region.table_rows is not None:
            return _table_markdown(region.table_rows)
        return _sanitize_table(content) or "[unclear]"
    if not content:
        content = "[unclear]"
    if region.type == "title":
        return f"{'#' * (region.heading_level or 1)} {content}"
    if region.type == "heading":
        return f"{'#' * (region.heading_level or 2)} {content}"
    if region.type == "formula":
        return f"$$\n{_formula_body(content)}\n$$"
    if region.type == "chart":
        return f"### Chart\n\n{content}"
    if region.type == "quote":
        return "> " + content
    if region.type == "code":
        return _code_block(content)
    if region.type == "figure":
        if region.crop_path:
            return f"![{content}]({region.crop_path})"
        return f"**Figure:** {content}"
    return content


def _code_block(content: str) -> str:
    language = ""
    match = re.fullmatch(r"(`{3,})([^`\n]*)\n([\s\S]*?)\n\1\s*", content)
    if match:
        language = match.group(2).strip()
        content = match.group(3)
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{content}\n{fence}"


def _formula_body(content: str) -> str:
    """Remove one outer math wrapper and keep remaining dollars literal."""
    pairs = (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"))
    for opening, closing in pairs:
        if content.startswith(opening) and content.endswith(closing):
            content = content[len(opening) : -len(closing)].strip()
            break
    else:
        unescaped = re.findall(r"(?<!\\)\$", content)
        if content.startswith("$") and content.endswith("$") and len(unescaped) == 2:
            content = content[1:-1].strip()
    return re.sub(r"(?<!\\)\$", r"\\$", content)


class MarkdownRenderer:
    def render(
        self, document: DocumentLayout, marginalia_policy: str = "remove_repeated"
    ) -> MarkdownOutput:
        clean_blocks: list[str] = []
        grounded_blocks: list[str] = []
        suppressed = self.suppressed_marginalia(document, marginalia_policy)

        for page in document.pages:
            grounded_blocks.append(f"<!-- page: {page.page_number} -->")
            for region in page.regions:
                body = _region_markdown(region)
                if region.id not in suppressed:
                    clean_blocks.append(body)
                box = region.bbox
                grounded_blocks.append(
                    "<!-- region: "
                    f"{region.id} type={region.type} "
                    f"bbox={box.left:.4f},{box.top:.4f},{box.right:.4f},{box.bottom:.4f} "
                    f"source={region.source} -->\n{body}"
                )

        clean = "\n\n".join(clean_blocks).strip() + "\n"
        grounded = "\n\n".join(grounded_blocks).strip() + "\n"
        return MarkdownOutput(clean=clean, grounded=grounded)

    @staticmethod
    def suppressed_marginalia(document: DocumentLayout, policy: str) -> set[str | None]:
        if policy == "keep_all":
            return set()
        counts: dict[str, int] = {}
        for page in document.pages:
            for region in page.regions:
                if region.type in {"header", "footer"}:
                    key = _normalize_text(region.content).casefold()
                    counts[key] = counts.get(key, 0) + 1
        return {
            region.id
            for page in document.pages
            for region in page.regions
            if region.type == "page_number"
            or (
                region.type in {"header", "footer"}
                and counts.get(_normalize_text(region.content).casefold(), 0) > 1
            )
        }


def render_llm_markdown(
    document: DocumentLayout,
    *,
    source_filename: str,
    source_sha256: str,
    marginalia_policy: str = "remove_repeated",
) -> str:
    """Render hierarchy-preserving Markdown with machine-readable source anchors."""
    renderer = MarkdownRenderer()
    suppressed = renderer.suppressed_marginalia(document, marginalia_policy)
    heading_stack: list[tuple[int, str]] = []
    blocks = [
        "---",
        "paperplane_schema: llm-markdown/v2",
        f"source_filename: {json.dumps(source_filename, ensure_ascii=False)}",
        f"source_sha256: {json.dumps(source_sha256)}",
        f"page_count: {len(document.pages)}",
        "coordinate_system: normalized_top_left",
        "---",
    ]
    for page in document.pages:
        for index, region in enumerate(page.regions, start=1):
            if region.id in suppressed:
                continue
            region_id = region.id or f"p{page.page_number:04d}-r{index:04d}"
            level = region.heading_level or (1 if region.type == "title" else 2)
            if region.type in {"title", "heading"}:
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None
                heading_stack.append((level, region_id))
            else:
                parent_id = heading_stack[-1][1] if heading_stack else None
            citation = {
                "page": page.page_number,
                "source_page": page.source_page_number or page.page_number,
                "region_id": region_id,
                "bbox": [
                    region.bbox.left,
                    region.bbox.top,
                    region.bbox.right,
                    region.bbox.bottom,
                ],
                "type": region.type,
                "parent_id": parent_id,
                "source_bbox": list(
                    source_bbox(region.bbox, page.width, page.height, page.coordinate_unit)
                    .model_dump(exclude={"unit"})
                    .values()
                ),
                "coordinate_unit": page.coordinate_unit,
            }
            table_manifest = ""
            if region.type == "table" and region.table_cells:
                cells = []
                for cell_index, cell in enumerate(region.table_cells, start=1):
                    cell_id = cell.id or f"{region_id}-c{cell_index:04d}"
                    absolute = source_bbox(cell.bbox, page.width, page.height, page.coordinate_unit)
                    cells.append(
                        {
                            "cell_id": cell_id,
                            "row": cell.row,
                            "column": cell.column,
                            "rowspan": cell.rowspan,
                            "colspan": cell.colspan,
                            "page": page.page_number,
                            "bbox": list(cell.bbox.model_dump().values()),
                            "source_bbox": list(absolute.model_dump(exclude={"unit"}).values()),
                            "coordinate_unit": page.coordinate_unit,
                        }
                    )
                table_manifest = (
                    "<!-- paperplane-table-citations: table-citations/v1 "
                    + json.dumps(cells, ensure_ascii=False, separators=(",", ":"))
                    + " -->\n"
                )
            blocks.append(
                "<!-- paperplane-citation: "
                + json.dumps(citation, ensure_ascii=False, separators=(",", ":"))
                + " -->\n"
                + table_manifest
                + _region_markdown(region)
            )
    return "\n\n".join(blocks).strip() + "\n"
