#!/usr/bin/env python3
"""Print a manual on the shelf as a PDF.

    python3 scripts/guide_pdf.py manuals/inside-the-rate.md

**The PDF is derived from the manual and is never a second copy of it.** A
hand-written HTML version of a document that already exists in `docs/` is
this repository's most expensive shape — two structures describing one
thing, free to disagree the day somebody edits one — so the markdown is the
source and this renders it. `tests/test_a_guide_pdf_is_its_own_manual.py`
reads the printed text back and fails a PDF that has fallen behind.

**It refuses what it cannot render rather than dropping it.** A half-renderer
that silently skips a table prints a document missing the row a reader was
sent to find, and nothing anywhere says so. The subset below is what the
manuals on the shelf actually use; anything else stops the run and names the
line. *Nothing is coerced into validity*, applied to a document.

The HTML/Chromium route is `monday_anchor.py`'s, for its reason: no runtime
dependency joins the image for one PDF, and the output is committed beside
the markdown.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


# --------------------------------------------------------------- inline

def inline(s: str) -> str:
    """`code`, **bold** and *emphasis*.

    A code span is lifted out behind a sentinel before emphasis runs, so a
    `*` inside code is not read as emphasis and **bold that spans a code
    span** still closes. The first draft split the string on code and ran
    emphasis on each piece, so `**`/rates` — the Rate tab**` had its opening
    marker in one piece and its closing marker in another and neither
    matched: three paragraphs printed literal asterisks at a reader. Found
    by reading the rendered PDF back, which is the only way any of these
    are found.
    """
    held: list[str] = []

    def keep(m: re.Match) -> str:
        held.append(m.group(1))
        return f"\x00{len(held) - 1}\x00"

    s = re.sub(r"`([^`]+)`", keep, s)
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00",
                  lambda m: f"<code>{html.escape(held[int(m.group(1))])}</code>",
                  s)


# ----------------------------------------------------------------- block

def render_body(md: str, source: str) -> tuple[str, str]:
    """The manual as HTML, and its title. Raises on anything unrecognised."""
    title, out = "", []
    lines = md.splitlines()
    i, n = 0, len(lines)
    para: list[str] = []
    bullets: list[str] = []

    def flush() -> None:
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if bullets:
            out.append("<ul>" + "".join(f"<li>{inline(b)}</li>"
                                        for b in bullets) + "</ul>")
            bullets.clear()

    while i < n:
        ln = lines[i]
        if not ln.strip():
            flush()
        elif ln.startswith("    "):
            flush()
            block = []
            while i < n and (lines[i].startswith("    ") or not lines[i].strip()):
                block.append(lines[i][4:])
                i += 1
            while block and not block[-1].strip():
                block.pop()
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
            continue
        elif ln.startswith("#"):
            flush()
            level = len(ln) - len(ln.lstrip("#"))
            if level > 3 or not ln[level:].startswith(" "):
                raise SystemExit(f"{source}:{i + 1}: heading not h1-h3: {ln!r}")
            text = ln[level:].strip()
            if level == 1 and not title:
                title = text
            out.append(f"<h{level}>{inline(text)}</h{level}>")
        elif ln.startswith("- "):
            if para:
                flush()
            bullets.append(ln[2:].strip())
            while i + 1 < n and lines[i + 1].startswith("  ") \
                    and not lines[i + 1].startswith("    "):
                i += 1
                bullets[-1] += " " + lines[i].strip()
        elif ln[0] in "|>" or re.match(r"^([*+] |\d+\. )", ln):
            # A table, a block quote, an asterisk bullet or a numbered
            # list. None is rendered here, and printing the source text
            # instead would put pipes and carets on a document going to a
            # reader. The bullet test is on `"* "` and not on the first
            # character: a paragraph opening on **bold** starts with an
            # asterisk too, and the first draft refused eleven correct
            # paragraphs — a guard that argues with the document.
            raise SystemExit(
                f"{source}:{i + 1}: this renderer does not handle {ln[0]!r} — "
                f"add it here rather than letting the PDF drop the line:\n"
                f"  {ln}")
        else:
            if bullets:
                flush()
            para.append(ln.strip())
        i += 1
    flush()
    if not title:
        raise SystemExit(f"{source}: no '# ' heading, so the PDF has no title")
    return "\n".join(out), title


CSS = """
@page { size: Letter; margin: 0.8in 0.9in; }
html { -webkit-print-color-adjust: exact; }
body { font: 11pt/1.55 Georgia, "Times New Roman", serif; color: #1c1f22;
       margin: 0; }
h1 { font: 600 23pt/1.2 "Helvetica Neue", Helvetica, Arial, sans-serif;
     margin: 0 0 4pt; letter-spacing: -0.01em; }
h2 { font: 600 14pt/1.3 "Helvetica Neue", Helvetica, Arial, sans-serif;
     margin: 26pt 0 7pt; padding-top: 7pt; border-top: 1px solid #d8d4cc;
     break-after: avoid; }
h3 { font: 600 11.5pt/1.3 "Helvetica Neue", Helvetica, Arial, sans-serif;
     margin: 16pt 0 5pt; color: #0f5c63; break-after: avoid; }
p { margin: 0 0 8pt; }
ul { margin: 0 0 10pt; padding-left: 17pt; }
li { margin: 0 0 5pt; }
strong { font-weight: 700; }
pre { font: 9.5pt/1.5 "SF Mono", Menlo, Consolas, monospace;
      background: #f6f4f0; border-left: 2px solid #0f5c63;
      padding: 9pt 11pt; margin: 0 0 11pt; white-space: pre-wrap;
      font-variant-numeric: tabular-nums; break-inside: avoid; }
/* The horizontal padding is 1pt rather than 3: a code span ending a
   sentence printed `marked 7-9 .`, a gap before its own full stop. */
code { font: 9.5pt "SF Mono", Menlo, Consolas, monospace;
       background: #f0ede8; padding: 0.5pt 1pt; border-radius: 2px; }
.masthead { font: 600 8.5pt/1 "Helvetica Neue", Helvetica, Arial, sans-serif;
            letter-spacing: 0.09em; text-transform: uppercase;
            color: #0f5c63; margin: 0 0 14pt; }
.sub { font: italic 10.5pt/1.45 Georgia, serif; color: #5a5750;
       margin: 0 0 20pt; padding-bottom: 14pt;
       border-bottom: 1px solid #d8d4cc; }
.foot { margin-top: 26pt; padding-top: 8pt; border-top: 1px solid #d8d4cc;
        font: 8.5pt/1.4 "Helvetica Neue", Helvetica, Arial, sans-serif;
        color: #6b6761; }
"""


def render(md: str, source: str) -> tuple[str, str]:
    body, title = render_body(md, source)
    # The masthead carries the title, so the manual's own `# ` heading comes
    # out of the body: printed, it is the same four words an inch below
    # itself, which reads as a rendering fault rather than as a design.
    body = re.sub(r"<h1>.*?</h1>\n?", "", body, count=1, flags=re.S)
    # The first paragraph is the standfirst. It is the manual's own opening
    # sentence rather than a line written here — a subtitle composed in the
    # renderer is a second copy of what the document already says.
    sub = ""
    m = re.search(r"<p>(.+?)</p>", body, re.S)
    if m:
        sub, body = m.group(1), body.replace(m.group(0), "", 1)
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>
<div class="masthead">Youngstown Business Incubator &middot; 2025 audit</div>
<h1>{html.escape(title)}</h1>
<div class="sub">{sub}</div>
{body}
<div class="foot">Printed from <code>docs/{html.escape(source)}</code>, which
is the source. Correct the manual rather than this page.</div>
</body></html>"""
    return doc, title


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("guide", help="path under docs/, e.g. manuals/x.md")
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    src = DOCS / args.guide
    if not src.exists():
        raise SystemExit(f"{src} is not there")
    doc, title = render(src.read_text(), args.guide)

    page = src.with_suffix(".html")
    page.write_text(doc)
    if args.html_only:
        print(f"wrote {page}")
        return 0

    pdf = src.with_suffix(".pdf")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.goto(page.resolve().as_uri(), wait_until="networkidle")
        pg.pdf(path=str(pdf), format="Letter", print_background=True)
        b.close()
    # The HTML is a rendering step and not an artefact: leaving it beside the
    # PDF puts a third copy of the manual in the repository.
    page.unlink()
    print(f"wrote {pdf} — {title} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
