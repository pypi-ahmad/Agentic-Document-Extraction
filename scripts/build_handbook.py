#!/usr/bin/env python3
"""Build the styled HTML and PDF editions of the Paperplane study handbook."""

from __future__ import annotations

import argparse
from pathlib import Path

import markdown
from handbook_pdf import build_pdf

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "ZERO_TO_MASTERY.md"
RICH_HTML = ROOT / "docs" / "ZERO_TO_MASTERY.rich.html"
PDF = ROOT / "docs" / "ZERO_TO_MASTERY.pdf"

CSS = r"""
@page {
  size: A4;
  margin: 18mm 16mm 19mm;
  @top-left {
    content: "PAPERPLANE - ZERO TO MASTERY";
    color: #64748b;
    font-family: "DejaVu Sans", sans-serif;
    font-size: 8pt;
    letter-spacing: 0.08em;
  }
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    color: #64748b;
    font-family: "DejaVu Sans", sans-serif;
    font-size: 8pt;
  }
}

@page:first {
  @top-left { content: none; }
  @bottom-right { content: none; }
}

:root {
  --ink: #10233f;
  --muted: #52647d;
  --accent: #2563eb;
  --accent-dark: #1e40af;
  --teal: #0f766e;
  --line: #cbd5e1;
  --panel: #f4f7fb;
  --code: #0f172a;
}

html { color: var(--ink); font-family: "DejaVu Sans", Arial, sans-serif; }
body { font-size: 10.3pt; line-height: 1.52; margin: 0; }

h1 {
  align-items: center;
  background: linear-gradient(145deg, #0f172a 0%, #173e78 58%, #0f766e 100%);
  box-sizing: border-box;
  color: white;
  display: flex;
  font-size: 29pt;
  line-height: 1.15;
  margin: -18mm -16mm 16mm;
  min-height: 297mm;
  padding: 42mm 22mm;
  page-break-after: always;
}

h2 {
  border-bottom: 2px solid var(--accent);
  color: var(--accent-dark);
  font-size: 18pt;
  line-height: 1.2;
  margin: 1.35em 0 0.55em;
  padding-bottom: 0.2em;
  page-break-after: avoid;
}

h3 {
  border-left: 4px solid var(--teal);
  color: #12325c;
  font-size: 13pt;
  line-height: 1.3;
  margin: 1.1em 0 0.45em;
  padding-left: 0.55em;
  page-break-after: avoid;
}

h4 { color: #24496f; font-size: 11pt; margin: 1em 0 0.35em; page-break-after: avoid; }
p { margin: 0.35em 0 0.65em; }
ul, ol { margin: 0.35em 0 0.8em 1.25em; padding: 0; }
li { margin: 0.22em 0; }
a { color: var(--accent-dark); text-decoration: none; }
strong { color: #0b2342; }

blockquote {
  background: #eef6ff;
  border-left: 4px solid var(--accent);
  border-radius: 0 5px 5px 0;
  color: #294766;
  margin: 0.9em 0;
  padding: 0.7em 0.9em;
}

code {
  background: #e8eef7;
  border-radius: 3px;
  color: #0f3159;
  font-family: "DejaVu Sans Mono", Consolas, monospace;
  font-size: 0.88em;
  padding: 1px 4px;
}

pre {
  background: var(--code);
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 8.4pt;
  line-height: 1.42;
  margin: 0.75em 0 1em;
  overflow-wrap: anywhere;
  padding: 10px 12px;
  page-break-inside: avoid;
  white-space: pre-wrap;
}

pre code { background: transparent; color: inherit; padding: 0; }
table { border-collapse: collapse; font-size: 8.8pt; margin: 0.8em 0 1.1em; width: 100%; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid var(--line); padding: 5px 6px; text-align: left; vertical-align: top; }
th { background: #dfeaf8; color: #14375e; }
tbody tr:nth-child(even) { background: #f8fafc; }
hr { border: 0; border-top: 1px solid var(--line); margin: 1.2em 0; }

#table-of-contents + ul {
  columns: 2;
  column-gap: 2em;
  list-style: none;
  margin-left: 0;
}

#table-of-contents + ul li { break-inside: avoid; margin-bottom: 0.45em; }
"""


def build() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    body = markdown.markdown(
        source,
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
        output_format="html5",
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="author" content="Ahmad">
  <meta name="description" content="A code-grounded tutorial for mastering Paperplane v5.3.0">
  <title>Paperplane Zero to Mastery</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
    RICH_HTML.write_text(document, encoding="utf-8", newline="\n")
    build_pdf(SOURCE, PDF)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build()
    print(f"Wrote {RICH_HTML.relative_to(ROOT)}")
    print(f"Wrote {PDF.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
