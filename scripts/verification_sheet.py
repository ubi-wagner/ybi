#!/usr/bin/env python3
"""The controller's verification list, as something to work from.

`docs/FOR_TOM_TO_VERIFY.md` is the narrative — what each discrepancy is, how it
was found and why it matters. This turns the same eighteen items into the two
shapes somebody actually settles them in:

    a workbook   one row per item, a status to pick and a box to type in
    a worksheet  the same thing on paper, with a tick box and ruled lines

Both come from the list below, so the sheet cannot describe an item the
document does not have, and `tests/test_verification_sheet.py` fails if the
references in the two ever drift apart.

    PYTHONPATH=. python3 scripts/verification_sheet.py [--out docs/status]

The rules are the ones the request workbooks already follow. A blank is
unanswered rather than a no. The columns we filled in are locked, because a
reference that changes is a row nobody can match back. And the status column is
a dropdown rather than free text, because "yes"/"confirmed"/"OK — see email"
are three answers to a question that has one.
"""

from __future__ import annotations

import argparse
import datetime as dt
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# One list, in the domain, read by the workbook, the worksheet and the
# VERIFICATION request form. It lived here until the form needed it, and two
# copies of one list is the shape that produced 13.0% and 2.2% at the same
# moment over the same single decision.
from app.domain.verification_items import ITEMS, STATUS, Item  # noqa: E402



# ── The workbook ──────────────────────────────────────────────────────

def build_workbook() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    from app.domain.package import BOLD, BOX, HEAD_FILL, HEAD_FONT, INK, SUB, TITLE

    OURS = PatternFill("solid", fgColor="EFEFEF")
    YOURS = PatternFill("solid", fgColor="FFFDF5")
    DONE = PatternFill("solid", fgColor="E7F0EA")
    WARM = Font(name="Arial", size=9, italic=True, color="7A5B00")

    wb = Workbook()
    wb.remove(wb.active)

    # ── Start here ────────────────────────────────────────────────────
    ws = wb.create_sheet("Start here")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 104
    r = 1
    ws.cell(row=r, column=1,
            value="YBI · VERIFICATION · 2025 · Discrepancies for the "
                  "controller to settle").font = TITLE
    r += 2
    for head, body in (
        ("What this is",
         f"{len(ITEMS)} things the record has found and cannot resolve on its "
         f"own. Every one was found by a control rather than by somebody "
         f"reading. Every one is answerable from what you already know or can "
         f"reach this week — nothing here needs counsel, an outside document, "
         f"or a decision from a sponsor."),
        ("How to fill it in",
         "One row per item on the Verify sheet. Pick a status from the "
         "dropdown and write what you found in 'Your answer'. The grey "
         "columns are ours and are locked; everything cream is yours."),
        ("A blank is a blank",
         "Leave anything you have not settled empty, or mark it STILL "
         "CHECKING. We record an empty cell as unanswered and come back to "
         "it. Guessing to finish the sheet is the one thing that would do "
         "real harm, because a guess is indistinguishable from a fact once "
         "it is in a column."),
        ("Row 0 is the worked example",
         "The Bacon $45,000, already confirmed, filled in the way the rest "
         "should be. It shows the shape: what was found, what it moved, and "
         "what is still outstanding on it."),
        ("Order",
         "Ordered by how much each moves the rate. The six depreciation items "
         "are worth roughly three points of the indirect rate between them, "
         "which is more than everything below them combined."),
    ):
        ws.cell(row=r, column=1, value=head).font = BOLD
        r += 1
        c = ws.cell(row=r, column=1, value=body)
        c.font = INK
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 15 * max(2, len(body) // 95 + 1)
        r += 2
    ws.cell(row=r, column=1,
            value=f"Figures read from the live record on "
                  f"{dt.date(2026, 9, 11):%d %B %Y}. The narrative version, "
                  f"with the working behind each figure, is "
                  f"docs/FOR_TOM_TO_VERIFY.md.").font = SUB

    # ── Choices ───────────────────────────────────────────────────────
    ch = wb.create_sheet("Choices")
    ch.column_dimensions["A"].width = 34
    ch.cell(row=1, column=1, value="Status").font = BOLD
    for i, s in enumerate(STATUS, start=2):
        ch.cell(row=i, column=1, value=s).font = INK

    # ── Verify ────────────────────────────────────────────────────────
    COLS = [
        ("Ref", 7, True), ("Area", 14, True), ("What we found", 58, True),
        ("Figure", 14, True), ("What we need from you", 46, True),
        ("What turns on it", 40, True),
        ("Status", 30, False), ("Your answer", 52, False),
        ("Answered by", 18, False), ("Date", 12, False),
    ]
    vs = wb.create_sheet("Verify")
    vs.freeze_panes = "A2"
    for i, (head, width, ours) in enumerate(COLS, start=1):
        vs.column_dimensions[get_column_letter(i)].width = width
        c = vs.cell(row=1, column=i, value=head)
        c.font = HEAD_FONT
        c.fill = HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    vs.row_dimensions[1].height = 26

    for n, item in enumerate(ITEMS, start=2):
        values = [item.ref, item.area, f"{item.title}. {item.found}",
                  item.figure, item.asks, item.moves]
        answered = list(item.answered) or ["", "", ""]
        values += [answered[0], answered[1], answered[2],
                   dt.date(2026, 9, 11) if item.answered else None]
        for i, value in enumerate(values, start=1):
            c = vs.cell(row=n, column=i, value=value)
            c.font = INK
            c.border = BOX
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ours = COLS[i - 1][2]
            c.protection = Protection(locked=ours)
            c.fill = OURS if ours else (DONE if item.answered else YOURS)
            if COLS[i - 1][0] == "Date":
                c.number_format = "yyyy-mm-dd"
            if COLS[i - 1][0] == "Figure":
                c.alignment = Alignment(horizontal="right", vertical="top")
        vs.row_dimensions[n].height = 74

    dv = DataValidation(type="list",
                        formula1=f"'Choices'!$A$2:$A${len(STATUS) + 1}",
                        allow_blank=True, showDropDown=False)
    dv.errorTitle = "Status"
    dv.error = ("Pick one of: " + "; ".join(STATUS) +
                ". Leave it blank if you have not settled it.")
    dv.showErrorMessage = True
    vs.add_data_validation(dv)
    dv.add(f"G2:G{len(ITEMS) + 40}")

    vs.protection.sheet = True
    vs.protection.password = "ybi"
    vs.protection.formatCells = False
    vs.protection.formatColumns = False
    vs.protection.formatRows = False

    wb.properties.title = "YBI · VERIFICATION · 2025"
    wb.properties.creator = "YBI cost allocation"
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


# ── The paper worksheet ───────────────────────────────────────────────

def build_worksheet_html() -> str:
    """The same list, laid out to be printed and written on."""
    def esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))

    blocks = []
    area_seen = set()
    for item in ITEMS:
        head = ""
        if item.area not in area_seen:
            area_seen.add(item.area)
            head = f'<h2>{esc(item.area)}</h2>'
        done = " done" if item.answered else ""
        ticks = "".join(
            f'<span class="tick{"  on" if item.answered and s == item.answered[0] else ""}">'
            f'<b></b>{esc(s.split(" — ")[0])}</span>' for s in STATUS)
        prefilled = ""
        if item.answered:
            prefilled = (f'<div class="pre">{esc(item.answered[1])}<br>'
                         f'<span class="by">— {esc(item.answered[2])}, '
                         f'11 September 2026</span></div>')
        blocks.append(f'''{head}
<section class="item{done}">
  <div class="hd"><span class="ref">{esc(item.ref)}</span>
    <span class="ttl">{esc(item.title)}</span>
    <span class="fig">{esc(item.figure)}</span></div>
  <p class="found">{esc(item.found)}</p>
  <p class="ask"><strong>{esc(item.asks)}</strong></p>
  <p class="moves">{esc(item.moves)}</p>
  <div class="ticks">{ticks}</div>
  {prefilled or '<div class="lines"><span></span><span></span><span></span></div>'}
  <div class="sig"><span>Answered by</span><span>Date</span></div>
</section>''')

    return f'''<!doctype html><meta charset="utf-8">
<title>Verification worksheet</title>
<style>
  @page {{ size: letter; margin: 15mm 14mm 12mm; }}
  :root {{ --ink:#1a1a1a; --mute:#5f6b6b; --rule:#cfd6d2; --accent:#1f4e4a;
           --warm:#7a5b00; }}
  body {{ font: 9.4pt/1.38 Georgia, "Times New Roman", serif; color: var(--ink);
          margin: 0; }}
  h1 {{ font-size: 16pt; margin: 0 0 1pt; }}
  .sub {{ color: var(--mute); font-size: 8.6pt; margin: 0 0 4pt; }}
  .intro {{ font-size: 9pt; margin: 0 0 10pt; }}
  h2 {{ font-size: 10.5pt; color: var(--accent); margin: 13pt 0 5pt;
        border-bottom: 1px solid var(--rule); padding-bottom: 2pt;
        break-after: avoid; }}
  .item {{ break-inside: avoid; border: 1px solid var(--rule);
           border-left: 3px solid var(--accent); padding: 6pt 9pt 7pt;
           margin: 0 0 7pt; }}
  .item.done {{ border-left-color: #6f8f76; background: #f6faf7; }}
  .hd {{ display: flex; align-items: baseline; gap: 8pt; margin-bottom: 3pt; }}
  .ref {{ font-weight: bold; color: var(--accent); min-width: 22pt; }}
  .ttl {{ font-weight: bold; flex: 1; }}
  .fig {{ font-variant-numeric: tabular-nums; color: var(--mute);
          white-space: nowrap; }}
  .found {{ margin: 0 0 3pt; }}
  .ask {{ margin: 0 0 2pt; }}
  .moves {{ margin: 0 0 5pt; font-size: 8.4pt; color: var(--warm);
            font-style: italic; }}
  .ticks {{ display: flex; gap: 12pt; margin: 0 0 5pt; font-size: 8.2pt;
            color: var(--mute); }}
  .tick b {{ display: inline-block; width: 8pt; height: 8pt; border: 1px solid #97a29d;
             margin-right: 3.5pt; vertical-align: -.5pt; background: #fff; }}
  .tick.on b {{ background: var(--accent); border-color: var(--accent); }}
  .tick.on {{ color: var(--ink); font-weight: bold; }}
  .lines span {{ display: block; border-bottom: 1px solid #dfe5e1; height: 15pt; }}
  .pre {{ font-size: 8.8pt; background: #fff; border: 1px solid #dfe5e1;
          padding: 4pt 6pt; }}
  .by {{ color: var(--mute); font-size: 8pt; }}
  .sig {{ display: flex; gap: 24pt; margin-top: 6pt; font-size: 7.6pt;
          color: var(--mute); }}
  .sig span {{ flex: 1; border-top: 1px solid #b9c2bd; padding-top: 2pt; }}
  .sig span:last-child {{ flex: 0 0 110pt; }}
  footer {{ margin-top: 10pt; padding-top: 4pt; border-top: 1px solid var(--rule);
            font-size: 7.6pt; color: var(--mute); }}
</style>
<h1>Discrepancies to settle</h1>
<p class="sub">Youngstown Business Incubator · 2025 cost allocation ·
for Tom Metzinger · figures as at 11 September 2026</p>
<p class="intro">{len(ITEMS)} items, each found by a control rather than by
somebody reading, and each answerable from what you already know or can reach
this week. Ordered by how much each moves the rate — the six depreciation items
are worth roughly three points of the indirect rate between them. Tick a status,
write what you found. <strong>Leave anything unsettled blank</strong>: we record
an empty box as unanswered and come back to it.</p>
{"".join(blocks)}
<footer>The narrative version, with the working behind every figure, is
docs/FOR_TOM_TO_VERIFY.md. Not on this list and not yours to settle: the Drive
AM cost-share contradiction (counsel), the $617,065 of untracked cost share
(partner evidence), asset funding source and square footage (those are the
request workbooks), and the three untranscribed award budgets (ours).</footer>
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "status"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    xlsx = out / "YBI_Verification_2025.xlsx"
    xlsx.write_bytes(build_workbook())
    print(f"  {xlsx.name:<34} {xlsx.stat().st_size:>8,} bytes  "
          f"{len(ITEMS)} items")

    html = out / "YBI_Verification_2025.html"
    html.write_text(build_worksheet_html())

    pdf = out / "YBI_Verification_2025.pdf"
    try:
        from playwright.sync_api import sync_playwright
        chrome = next(p for p in Path("/opt/pw-browsers")
                      .glob("chromium*/chrome-linux/chrome"))
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=str(chrome))
            page = b.new_page()
            page.goto(html.resolve().as_uri(), wait_until="networkidle")
            page.pdf(path=str(pdf), format="Letter", print_background=True,
                     margin={"top": "15mm", "bottom": "12mm",
                             "left": "14mm", "right": "14mm"},
                     display_header_footer=True,
                     header_template="<div></div>",
                     footer_template=(
                         '<div style="width:100%;font:7pt Georgia,serif;'
                         'color:#8a9290;padding:0 14mm;display:flex;'
                         'justify-content:space-between">'
                         '<span>YBI 2025 — discrepancies to settle</span>'
                         '<span class="pageNumber"></span></div>'))
            b.close()
        print(f"  {pdf.name:<34} {pdf.stat().st_size:>8,} bytes")
    except Exception as exc:                                 # noqa: BLE001
        print(f"  no PDF ({type(exc).__name__}: {exc}); the HTML prints fine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
