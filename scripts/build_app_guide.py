"""Build the reader-friendly HTML capability guide from its Markdown source."""

from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "APP_CAPABILITIES.md"
TARGET = ROOT / "docs" / "APP_CAPABILITIES.html"

STYLE = """
:root{--ink:#18202b;--muted:#5f6b7a;--paper:#fff;--wash:#f3f7fb;--line:#dce5ee;--blue:#155eef;--navy:#0b1f3a;--cyan:#148c99;--radius:14px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.72 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--blue)}
.hero{background:linear-gradient(130deg,#071a33,#123f71 70%,#176975);color:#fff;padding:64px 24px}.hero-inner,.layout{max-width:1180px;margin:auto}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:.76rem;font-weight:800;color:#83e5ed}.hero h1{font-size:clamp(2.3rem,6vw,4.8rem);line-height:1.03;margin:.25em 0}.hero p{max-width:760px;font-size:1.15rem;color:#d9e8f7}.badges{display:flex;flex-wrap:wrap;gap:9px;margin-top:24px}.badge{border:1px solid #ffffff42;background:#ffffff16;border-radius:999px;padding:6px 12px;font-size:.86rem}
.layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:34px;padding:34px 24px 72px}.sidebar{position:sticky;top:20px;align-self:start;background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:18px;box-shadow:0 8px 30px #0b1f3a10}.sidebar strong{display:block;margin-bottom:8px}.sidebar .toc ul{list-style:none;padding:0;margin:0}.sidebar .toc ul ul{display:none}.sidebar a{display:block;color:#465569;text-decoration:none;padding:5px 0;font-size:.9rem}.sidebar a:hover{color:var(--blue)}main{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:clamp(24px,5vw,52px);box-shadow:0 8px 30px #0b1f3a0b}
h1{display:none}h2{line-height:1.2;color:var(--navy);font-size:1.8rem;margin:2.1em 0 .7em;padding-top:.2em;border-top:1px solid var(--line)}main>h2:first-of-type{border:0;margin-top:0}h3{color:#194b7a;margin-top:1.8em;line-height:1.3}p{margin:.8em 0}ul{padding-left:1.3rem}blockquote{margin:22px 0;border-left:4px solid var(--cyan);background:#eefbfc;padding:12px 18px;border-radius:8px}blockquote p{margin:0}
pre{background:#0b1728;color:#d8e9ff;border-radius:11px;padding:18px;overflow:auto;line-height:1.5}code{font-family:"Cascadia Code",Consolas,monospace;font-size:.9em}:not(pre)>code{background:#edf3fa;padding:2px 6px;border-radius:5px;color:#173b66}
table{width:100%;border-collapse:collapse;display:block;overflow-x:auto;margin:18px 0}th,td{padding:11px 13px;border:1px solid var(--line);text-align:left;vertical-align:top}th{background:#eaf2fb;color:var(--navy)}tr:nth-child(even) td{background:#fafcff}.footer{text-align:center;color:var(--muted);padding:26px}.skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:12px;background:#fff;padding:8px;z-index:2}
@media(max-width:850px){.layout{grid-template-columns:1fr}.sidebar{position:static}.hero{padding-top:48px}}@media print{body{background:#fff}.sidebar{display:none}.layout{display:block;padding:0}.hero{padding:28px;color:#000;background:#fff;border-bottom:2px solid #000}.hero p,.eyebrow{color:#333}main{box-shadow:none;border:0}.badge{border-color:#555}.footer{display:none}}
"""


def build() -> None:
    """Render the Markdown source with navigation and accessible page chrome."""
    body = markdown.markdown(
        SOURCE.read_text(encoding="utf-8"),
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
        extension_configs={"toc": {"permalink": True, "toc_depth": "2-3"}},
    )
    # A separate conversion exposes the generated TOC through the Markdown instance.
    converter = markdown.Markdown(extensions=["toc"])
    converter.convert(SOURCE.read_text(encoding="utf-8"))
    toc = converter.toc
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Paperplane stateless document-extraction capabilities and API.">
  <title>Paperplane | Capabilities and Technical Guide</title>
  <style>{STYLE}</style>
</head>
<body>
  <a class="skip" href="#content">Skip to content</a>
  <header class="hero"><div class="hero-inner">
    <div class="eyebrow">Paperplane V2 technical guide</div>
    <h1>From document pages to grounded Markdown</h1>
    <p>A concise guide to the synchronous parser, its evidence contract, and its security boundary.</p>
    <div class="badges"><span class="badge">Stateless</span><span class="badge">Layout aware</span><span class="badge">Luna + Terra</span><span class="badge">Grounded JSON</span></div>
  </div></header>
  <div class="layout">
    <aside class="sidebar"><strong>On this page</strong>{toc}</aside>
    <main id="content">{body}</main>
  </div>
  <footer class="footer">Paperplane V2 · Stateless document extraction</footer>
</body>
</html>
"""
    TARGET.write_text(html, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
