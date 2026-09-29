"""What a document *is* shaped like, apart from what it says.

Every parser in this system was written against **one** instance of the
document it parses, and three of them have already been caught by the second
one:

  * the asset schedule prints a system number only when it changes, so the
    first parser dropped every row that repeated one — $2.5m, including
    $2,388,438.81 of Tech Block phase 2;
  * two of the five executed agreements are ARTICLE-numbered with no
    numbered clause heading anywhere, and three provisions on each were
    cited to `§25` and `§26`, which are ICAM's clauses and appear in neither;
  * one agreement is thirty-six pages and seventy characters, because it has
    no text layer — a *fact about the document* that explains why no clause
    of it had ever been checked.

Each of those is a difference in **form** rather than in content, and each
cost real money to find by reading. This module reads the form off the bytes
so the differences can be compared instead.

**Form and content are kept apart on purpose.** Form is the shape of the
container — sheets, headers, column types, pages, whether there is a text
layer, how headings are numbered. Content is what is in it — how many
figures, over what dates, to what total. Next year's general ledger will
have wholly different content and had better have the same form; an export
somebody saved differently will have the same content and a form that breaks
the parser. Collapsing the two would hide exactly the case worth catching.

Pure: bytes in, dictionaries out. No database, no filesystem, no network —
so a form can be taken in a test, in a drive, in the upload route, or in a
script, and be the same reading every time.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

#: How many rows of a sheet to look at. A ledger is 15,500 lines and the
#: shape of it is settled long before the end; reading all of them would make
#: this too slow to run on an upload, which is where it has to run.
SCAN_ROWS = 400

#: A cell's type, reduced to the four that decide whether a parser copes.
#: Deliberately coarse — `int` against `float` is not a difference anybody
#: has ever been bitten by here, and `date` against `text` is the difference
#: that produced "2019ish" being reported rather than guessed at.
BLANK, TEXT, NUMBER, DATE = "blank", "text", "number", "date"

_MONEY = re.compile(r"-?\$?\(?\d[\d,]*\.\d{2}\)?")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
#: The three heading conventions the five executed agreements actually use.
#: A hand-written list, because what counts as a clause heading is a fact
#: about legal drafting rather than something to infer — and `056` is the
#: record of what guessing at it cost.
_HEADINGS = {
    "article": re.compile(r"^\s*ARTICLE\s+[IVXLC\d]+", re.M),
    "section_sign": re.compile(r"§\s*\d+"),
    "numbered": re.compile(r"^\s*\d+\.\d*\s+[A-Z]", re.M),
    "schedule": re.compile(r"^\s*(SCHEDULE|ATTACHMENT|EXHIBIT)\s+[A-Z\d]", re.M),
}


def _cell_type(v: Any) -> str:
    if v is None or (isinstance(v, str) and not v.strip()):
        return BLANK
    if isinstance(v, (datetime, date)):
        return DATE
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return NUMBER
    return TEXT


def _looks_like_header(row: list[Any]) -> bool:
    """A row of labels over a row of values.

    Not "the first non-empty row": a QuickBooks export opens with a company
    name, a report title and a date range, each one cell wide, and reading
    any of them as the header puts every column one place out.
    """
    kinds = [_cell_type(v) for v in row]
    filled = [k for k in kinds if k != BLANK]
    return len(filled) >= 2 and all(k == TEXT for k in filled)


def _sheet_shape(name: str, rows: list[list[Any]]) -> dict:
    """One sheet's form, and what it holds."""
    header_at, header = None, []
    for i, row in enumerate(rows[:40]):
        if _looks_like_header(row):
            header_at, header = i, [str(v).strip() for v in row if _cell_type(v) == TEXT]
            break

    body = rows[(header_at or 0) + 1:]
    width = max((len(r) for r in rows), default=0)
    # The type each column mostly holds. A column that is 90% numbers with a
    # stray label in it is a number column with a stray label in it, and
    # reporting it as mixed would bury the columns that genuinely are.
    columns = []
    for c in range(width):
        kinds = Counter(_cell_type(r[c]) if c < len(r) else BLANK for r in body)
        kinds.pop(BLANK, None)
        columns.append(kinds.most_common(1)[0][0] if kinds else BLANK)

    numbers = [v for r in body for v in r
               if _cell_type(v) == NUMBER]
    dates = [v for r in body for v in r if _cell_type(v) == DATE]
    return {
        "form": {
            "header_row": header_at,
            "headers": header,
            "width": width,
            "column_types": columns,
            # A blank column inside the used range is the shape that makes a
            # positional parser read every column to its right wrong.
            "interior_blank_columns": sum(
                1 for i, t in enumerate(columns)
                if t == BLANK and any(x != BLANK for x in columns[i + 1:])),
        },
        "content": {
            "rows": len(body),
            "numbers": len(numbers),
            "date_from": min(dates).date().isoformat()
            if dates and hasattr(min(dates), "date") else None,
            "date_to": max(dates).date().isoformat()
            if dates and hasattr(max(dates), "date") else None,
        },
        "sheet": name,
    }


def _xlsx(raw: bytes) -> tuple[dict, dict]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    sheets, formulas = [], False
    for ws in wb.worksheets:
        rows = [list(r) for _, r in zip(range(SCAN_ROWS), ws.iter_rows(values_only=True))]
        sheets.append(_sheet_shape(ws.title, rows))
    # Read a second time without `data_only`, because an export saved with no
    # cached values reads as zero and reconciles against zero — the general
    # ledger's printed subtotals did exactly that, and it is a fact about the
    # file rather than about the books.
    wb2 = load_workbook(io.BytesIO(raw), data_only=False, read_only=True)
    cached_values = True
    for ws in wb2.worksheets:
        for _, row in zip(range(SCAN_ROWS), ws.iter_rows(values_only=True)):
            for v in row:
                if isinstance(v, str) and v.startswith("="):
                    formulas = True
    if formulas:
        live = any(s["content"]["numbers"] for s in sheets)
        cached_values = live
    return ({"container": "spreadsheet",
             "sheets": [s["sheet"] for s in sheets],
             "sheet_count": len(sheets),
             "has_formulas": formulas,
             "cached_values": cached_values,
             "per_sheet": {s["sheet"]: s["form"] for s in sheets}},
            {"per_sheet": {s["sheet"]: s["content"] for s in sheets},
             "rows": sum(s["content"]["rows"] for s in sheets),
             "numbers": sum(s["content"]["numbers"] for s in sheets)})


def _xls(raw: bytes) -> tuple[dict, dict]:
    import xlrd

    bk = xlrd.open_workbook(file_contents=raw)
    sheets = []
    for ws in bk.sheets():
        rows = []
        for r in range(min(ws.nrows, SCAN_ROWS)):
            row = []
            for c in range(ws.ncols):
                cell = ws.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    # A date cell holding something that is not a date — the
                    # 2026 asset schedule has one, and xlrd raises `year 0
                    # is out of range` on it. That is a fact about the
                    # document, so it is read as text rather than taking the
                    # whole reading down.
                    try:
                        row.append(datetime(
                            *xlrd.xldate_as_tuple(cell.value, bk.datemode)))
                    except (ValueError, OverflowError):
                        row.append(str(cell.value))
                elif cell.ctype == xlrd.XL_CELL_NUMBER:
                    row.append(cell.value)
                elif cell.ctype == xlrd.XL_CELL_EMPTY:
                    row.append(None)
                else:
                    row.append(cell.value)
            rows.append(row)
        sheets.append(_sheet_shape(ws.name, rows))
    return ({"container": "spreadsheet",
             "sheets": [s["sheet"] for s in sheets],
             "sheet_count": len(sheets),
             "has_formulas": False,
             "cached_values": True,
             "per_sheet": {s["sheet"]: s["form"] for s in sheets}},
            {"per_sheet": {s["sheet"]: s["content"] for s in sheets},
             "rows": sum(s["content"]["rows"] for s in sheets),
             "numbers": sum(s["content"]["numbers"] for s in sheets)})


def _pdf(raw: bytes) -> tuple[dict, dict]:
    from pypdf import PdfReader

    rd = PdfReader(io.BytesIO(raw))
    pages = [(p.extract_text() or "") for p in rd.pages]
    text = "\n".join(pages)
    chars = len(text.strip())
    # Three answers, kept apart, which is `056`'s rule: no text layer at all,
    # a text layer with nothing in it, and a readable document. Collapsing
    # the first two turns "this cannot be checked" into "this checks out".
    per_page = [len(p.strip()) for p in pages]
    headings = {k: len(rx.findall(text)) for k, rx in _HEADINGS.items()}
    per_page_chars = round(chars / len(rd.pages), 1) if rd.pages else 0
    # `056`'s rule, applied to the form rather than to the stored text: NULL,
    # empty and readable are three different facts, and collapsing the middle
    # one turns "this cannot be checked" into "this checks out". The cut is
    # 50 characters a page — below that there is not a sentence on a page,
    # let alone a clause — and `chars_per_page` stays beside it so the
    # judgment is visible instead of buried in a boolean.
    layer = ("none" if chars == 0
             else "sparse" if per_page_chars < 50
             else "text")
    return ({"container": "pdf",
             "pages": len(rd.pages),
             "text_layer": layer,
             # A scan and a born-digital document differ here by two orders
             # of magnitude, and the whole of whether a clause can be checked
             # rides on it.
             "chars_per_page": per_page_chars,
             "pages_without_text": sum(1 for n in per_page if n == 0),
             "heading_style": sorted(k for k, n in headings.items() if n >= 3)},
            {"characters": chars,
             "headings": headings,
             "money_figures": len(_MONEY.findall(text)),
             "years": sorted({m.group(0) for m in _YEAR.finditer(text)})})


def _delimited(raw: bytes) -> tuple[dict, dict]:
    text = raw.decode("utf-8", "replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    shaped = _sheet_shape("(file)", rows[:SCAN_ROWS])
    return ({"container": "delimited", "delimiter": delimiter,
             "sheets": ["(file)"], "sheet_count": 1,
             "per_sheet": {"(file)": shaped["form"]}},
            {"per_sheet": {"(file)": shaped["content"]},
             "rows": len(rows), "numbers": shaped["content"]["numbers"]})


def shape_of(raw: bytes, mime: str) -> tuple[dict, dict]:
    """The form and the content of one document, read from its bytes.

    It never raises on a document it cannot read. A file that defeats the
    parser is a *finding* — it is the one a person has to go and look at —
    and a reader that fell over would take the whole drive with it and say
    less than a row that names the problem.
    """
    try:
        if mime in ("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",):
            return _xlsx(raw)
        if mime == "application/vnd.ms-excel":
            return _xls(raw)
        if mime == "application/pdf":
            return _pdf(raw)
        if mime in ("text/csv", "text/plain"):
            return _delimited(raw)
    except Exception as exc:                       # noqa: BLE001 — see above
        return ({"container": "unreadable",
                 "why": f"{type(exc).__name__}: {exc}"[:200]}, {})
    return ({"container": "opaque", "mime": mime}, {})


def differences(forms: list[dict]) -> dict[str, list]:
    """Which top-level form attributes differ across a family, and how.

    **Named rather than scored.** A single "variability index" over a
    handful of documents is a figure nobody can reproduce and nobody can act
    on; what a person needs is *which* attribute differs and what the values
    are, which is the same reason a reconciling item carries its lines
    instead of a plug.
    """
    out: dict[str, list] = {}
    keys = {k for f in forms for k in f if k != "per_sheet"}
    for k in sorted(keys):
        seen = []
        for f in forms:
            v = f.get(k)
            v = tuple(v) if isinstance(v, list) else v
            if v not in seen:
                seen.append(v)
        if len(seen) > 1:
            out[k] = [list(v) if isinstance(v, tuple) else v for v in seen]
    return out
