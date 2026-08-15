"""ReportLab renderer for the Paperplane Markdown handbook."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

import markdown
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

INK = colors.HexColor("#10233f")
MUTED = colors.HexColor("#52647d")
ACCENT = colors.HexColor("#2563eb")
ACCENT_DARK = colors.HexColor("#1e40af")
TEAL = colors.HexColor("#0f766e")
LINE = colors.HexColor("#cbd5e1")
PANEL = colors.HexColor("#f4f7fb")
CODE = colors.HexColor("#0f172a")


class NumberedCanvas(canvas.Canvas):
    """Canvas that renders stable Page X of Y footers."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(page_count)
            super().showPage()
        super().save()

    def _draw_header_footer(self, page_count: int) -> None:
        if self._pageNumber == 1:
            return
        width, _ = A4
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED)
        self.drawString(16 * mm, 286 * mm, "PAPERPLANE - ZERO TO MASTERY")
        self.drawRightString(width - 16 * mm, 10 * mm, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


class HandbookTemplate(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title="Paperplane Zero to Mastery",
            author="Ahmad",
            subject="Code-grounded tutorial for mastering Paperplane v5.1.1",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="body",
        )
        self.addPageTemplates(PageTemplate(id="handbook", frames=[frame]))

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        levels = {"ModuleHeading": 0, "SectionHeading": 1, "SubsectionHeading": 2}
        level = levels.get(flowable.style.name)
        if level is None:
            return
        text = flowable.getPlainText()
        key = f"heading-{self.seq.nextf('heading')}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
        self.notify("TOCEntry", (level, text, self.page, key))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=29,
            leading=34,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#dbeafe"),
            alignment=TA_CENTER,
        ),
        "module": ParagraphStyle(
            "ModuleHeading",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=ACCENT_DARK,
            borderColor=ACCENT,
            borderWidth=0,
            borderPadding=(0, 0, 5, 0),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "section": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#12325c"),
            borderColor=TEAL,
            borderWidth=0,
            leftIndent=7,
            spaceBefore=11,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "subsection": ParagraphStyle(
            "SubsectionHeading",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#24496f"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13.7,
            textColor=INK,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            textColor=INK,
            leftIndent=13,
            firstLineIndent=-7,
            spaceAfter=2.5,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#294766"),
            backColor=colors.HexColor("#eef6ff"),
            borderColor=ACCENT,
            borderWidth=0.8,
            borderPadding=7,
            leftIndent=8,
            rightIndent=8,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName="Courier",
            fontSize=7.2,
            leading=10,
            textColor=colors.HexColor("#e2e8f0"),
            backColor=CODE,
            borderPadding=8,
            leftIndent=0,
            rightIndent=0,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "toc_title": ParagraphStyle(
            "TOCTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=ACCENT_DARK,
            spaceAfter=12,
        ),
    }


def _inline(value: str) -> str:
    rendered = markdown.markdown(value, extensions=["sane_lists"]).strip()
    if rendered.startswith("<p>") and rendered.endswith("</p>"):
        return rendered[3:-4]
    return rendered


def _table(lines: list[str], width: float, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[Paragraph]] = []
    for index, line in enumerate(lines):
        if index == 1:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append([Paragraph(_inline(cell), styles["body"]) for cell in cells])
    columns = max(len(row) for row in rows)
    for row in rows:
        row.extend(Paragraph("", styles["body"]) for _ in range(columns - len(row)))
    table = Table(rows, colWidths=[width / columns] * columns, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfeaf8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#14375e")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
            ]
        )
    )
    return table


def _is_table_separator(line: str) -> bool:
    cells = line.strip().strip("|").split("|")
    return bool(cells) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells)


def _code_block(value: str, width: float, style: ParagraphStyle) -> Table:
    block = Table([[Preformatted(value, style, maxLineLength=105)]], colWidths=[width])
    block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CODE),
                ("BOX", (0, 0), (-1, -1), 0.5, CODE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return block


def _story(source: str, width: float, styles: dict[str, ParagraphStyle]) -> list:
    lines = source.splitlines()
    title = lines[0].removeprefix("# ").strip()
    subtitle = "Docling, PDF Inspector, cloud AI, and local Ollama document intelligence"
    story: list = [
        Spacer(1, 25 * mm),
        Table(
            [
                [Paragraph(title, styles["cover"])],
                [Paragraph(escape(subtitle), styles["cover_sub"])],
            ],
            colWidths=[width],
            rowHeights=[120 * mm, 90 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#173e78")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0, colors.HexColor("#173e78")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ]
            ),
        ),
        PageBreak(),
        Paragraph("Table of Contents", styles["toc_title"]),
    ]
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", fontName="Helvetica-Bold", fontSize=10, leading=14, leftIndent=0),
        ParagraphStyle("TOC1", fontName="Helvetica", fontSize=8.5, leading=12, leftIndent=12),
        ParagraphStyle("TOC2", fontName="Helvetica", fontSize=8, leading=11, leftIndent=24),
    ]
    story.extend([toc, PageBreak()])

    index = 1
    paragraph: list[str] = []
    in_code = False
    code: list[str] = []
    skip_manual_toc = False

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(_inline(" ".join(paragraph)), styles["body"]))
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                story.append(_code_block("\n".join(code), width, styles["code"]))
                code.clear()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue
        if stripped == "## Table of Contents":
            flush_paragraph()
            skip_manual_toc = True
            index += 1
            continue
        if skip_manual_toc:
            if stripped.startswith("## "):
                skip_manual_toc = False
            else:
                index += 1
                continue
        if stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(escape(stripped[3:]), styles["module"]))
        elif stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(escape(stripped[4:]), styles["section"]))
        elif stripped.startswith("#### "):
            flush_paragraph()
            story.append(Paragraph(escape(stripped[5:]), styles["subsection"]))
        elif (
            stripped.startswith("| ")
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.extend([_table(table_lines, width, styles), Spacer(1, 4)])
            continue
        elif re.match(r"^[-*] ", stripped):
            flush_paragraph()
            story.append(Paragraph(_inline(stripped[2:]), styles["bullet"], bulletText="-"))
        elif match := re.match(r"^(\d+)\.\s+(.*)", stripped):
            flush_paragraph()
            story.append(
                Paragraph(
                    _inline(match.group(2)), styles["bullet"], bulletText=match.group(1) + "."
                )
            )
        elif stripped.startswith("> "):
            flush_paragraph()
            story.append(Paragraph(_inline(stripped[2:]), styles["quote"]))
        elif not stripped:
            flush_paragraph()
        elif stripped == "---":
            flush_paragraph()
            story.append(Spacer(1, 5))
        elif not stripped.startswith("# "):
            paragraph.append(stripped)
        index += 1
    flush_paragraph()
    return story


def build_pdf(source_path: Path, output_path: Path) -> None:
    source = source_path.read_text(encoding="utf-8")
    styles = _styles()
    document = HandbookTemplate(str(output_path))
    story = _story(source, document.width, styles)
    document.multiBuild(story, canvasmaker=NumberedCanvas)
