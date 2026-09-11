"""The ask, as a workbook somebody can actually fill in.

A form definition in `request_forms.py` becomes three sheets:

    Start here   what this is, why it matters, what it changes, and the
                 totals the answers have to tie to
    <the grid>   one row per thing, with what we already know filled in
    Choices      the permitted values, which the dropdowns point at

Pure: no database, no filesystem. It is handed the rows we already hold and
returns bytes, so the whole thing is testable without Postgres and the same
function serves the download route, a script and a test.

Four decisions worth keeping:

**What we know is already in the cells.** The balance sheet accounts, the
payroll surnames, the buildings. A form that makes somebody retype what we
already hold comes back late and wrong, and the person filling it has no way
to tell which parts we could have filled in ourselves — so they reasonably
assume none of it, and check everything.

**Dropdowns, not free text, wherever the column feeds an enum.** The
allowability test reads the funding column. "EDA grant (I think)" is not an
answer it can read, and the person typing it has no way to know that. The
choices come from the same tuple the database enum is built from.

**Nothing is protected except the structure.** Header rows and the columns we
filled in are locked; every answer cell is open. This is not security — the
password is on the sheet in plain sight and openpyxl would hand it over
anyway. It stops a column being dragged somewhere else, which is the one
edit that silently breaks the parser, and it does so without the person
noticing there was a rule.

**The identity of the form is in the file.** Name, version and period, on the
first sheet where a person can read them and in a defined cell where the
parser can. A workbook filled in from last quarter's copy of the form is a
thing that will happen, and answering it with a column-count mismatch deep in
a stack trace is not a reply anybody can act on.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .package import (BOLD, BOX, CUR, HEAD_FILL, HEAD_FONT, INK, SUB, TITLE,
                      WARN_FILL)
from .request_forms import ISSUED, ISSUED_MARKER, Column, Form, Kind

__all__ = ["build_request_workbook", "IDENTITY_CELL", "IDENTITY_SHEET"]

#: Where the parser looks for "which form is this". A named sheet and a fixed
#: cell rather than a filename, because a filename is the first thing that
#: changes when a workbook is emailed around.
IDENTITY_SHEET = "Start here"
IDENTITY_CELL = "A1"

KNOWN_FILL = PatternFill("solid", fgColor="EFEFEF")
ANSWER_FILL = PatternFill("solid", fgColor="FFFDF5")
NOTE_FONT = Font(name="Arial", size=9, italic=True, color="7A5B00")

NUM = "#,##0.00"
PCT_PLAIN = "0.00"
DATE = "yyyy-mm-dd"

_FORMATS = {
    Kind.MONEY: CUR,
    Kind.NUMBER: NUM,
    Kind.PERCENT: PCT_PLAIN,
    Kind.DATE: DATE,
}


def identity_line(form: Form, period: str) -> str:
    """The one string that says what this workbook is.

    Read by a person at the top of the first sheet and by the parser out of
    the same cell, so the two cannot disagree about which form arrived.
    """
    return f"YBI · {form.name} v{form.version} · {period} · {form.title}"


def _write_start_here(wb: Workbook, form: Form, period: str,
                      controls: dict[str, Decimal] | None = None) -> None:
    ws = wb.create_sheet(IDENTITY_SHEET, 0)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 104

    row = 1
    c = ws.cell(row=row, column=1, value=identity_line(form, period))
    c.font = TITLE
    row += 2

    for label, body in (("For", form.for_whom),
                        ("Why we are asking", form.purpose),
                        ("What it changes", form.consequence)):
        ws.cell(row=row, column=1, value=label).font = BOLD
        row += 1
        cell = ws.cell(row=row, column=1, value=body)
        cell.font = INK
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        # Four lines of wrapped text at this width, near enough. Excel will
        # not compute a wrapped row height for us and a clipped paragraph
        # reads as though the sentence simply ended.
        ws.row_dimensions[row].height = 15 * max(2, len(body) // 95 + 1)
        row += 2

    if form.instructions:
        ws.cell(row=row, column=1, value="How to fill it in").font = BOLD
        row += 1
        for line in form.instructions:
            cell = ws.cell(row=row, column=1, value=f"·  {line}")
            cell.font = INK
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[row].height = 15 * max(1, len(line) // 95 + 1)
            row += 1
        row += 1

    if form.controls:
        ws.cell(row=row, column=1,
                value="What the answers have to add up to").font = BOLD
        row += 1
        for ctl in form.controls:
            expect = (controls or {}).get(ctl.column, ctl.expect)
            shown = f"{expect:,.2f}" if expect is not None else "—"
            cell = ws.cell(row=row, column=1,
                           value=f"·  {ctl.label}:  {shown}\n   {ctl.note}")
            cell.font = INK
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[row].height = 30
            row += 1
        row += 1

    ws.cell(row=row, column=1, value="A blank is not a zero").font = BOLD
    row += 1
    cell = ws.cell(row=row, column=1, value=(
        "Leave anything you do not know empty. We record an empty cell as "
        "unanswered and come back to it; we record a zero as an answer and "
        "rely on it. Guessing to fill the sheet in is the one thing that "
        "would do real harm here, because a guess is indistinguishable from "
        "a fact once it is in a column."))
    cell.font = INK
    cell.fill = WARN_FILL
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[row].height = 60
    row += 2

    ws.cell(row=row, column=1, value=(
        f"Please send it back however it reached you. Prepared "
        f"{dt.date.today():%d %B %Y}. Do not rename the "
        f"'{form.sheet}' sheet or move its columns — the figures are read "
        f"back automatically.")).font = SUB


def _write_choices(wb: Workbook, form: Form) -> dict[str, str]:
    """One column per choice list, and the range each dropdown points at."""
    choice_columns = [c for c in form.columns if c.kind is Kind.CHOICE and c.choices]
    ranges: dict[str, str] = {}
    if not choice_columns:
        return ranges
    ws = wb.create_sheet("Choices")
    ws.sheet_state = "visible"          # hidden sheets make a dropdown look broken
    for i, col in enumerate(choice_columns, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = 22
        ws.cell(row=1, column=i, value=col.heading).font = BOLD
        for j, choice in enumerate(col.choices, start=2):
            ws.cell(row=j, column=i, value=choice).font = INK
        ranges[col.key] = (f"'Choices'!${letter}$2:${letter}"
                           f"${len(col.choices) + 1}")
    return ranges


def _write_grid(wb: Workbook, form: Form, period: str,
                known_rows: list[dict], rows_for_answers: int,
                ranges: dict[str, str]) -> None:
    ws = wb.create_sheet(form.sheet)
    ws.freeze_panes = "A3"
    columns = (*form.columns, ISSUED_MARKER)

    # Row 1: the heading. Row 2: why it is being asked. Two rows rather than
    # a cell comment, because a comment is invisible until hovered and half
    # the people filling this in will print it.
    for i, col in enumerate(columns, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = col.width

        head = ws.cell(row=1, column=i,
                       value=col.heading + (" *" if col.required else ""))
        head.font = HEAD_FONT
        head.fill = HEAD_FILL
        head.alignment = Alignment(wrap_text=True, vertical="center")
        if col.citation:
            head.comment = Comment(f"{col.heading}\n{col.citation}\n\n{col.why}",
                                   "YBI cost allocation")

        why = ws.cell(row=2, column=i,
                      value=col.why + (f"  ({col.citation})" if col.citation else ""))
        why.font = NOTE_FONT
        why.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 46

    first = 3
    last = first + max(len(known_rows), 0) + rows_for_answers - 1
    for r in range(first, last + 1):
        known = known_rows[r - first] if r - first < len(known_rows) else {}
        for i, col in enumerate(columns, start=1):
            cell = ws.cell(row=r, column=i)
            cell.border = BOX
            cell.font = INK
            fmt = _FORMATS.get(col.kind)
            if fmt:
                cell.number_format = fmt
            value = (ISSUED if (col is ISSUED_MARKER and known)
                     else known.get(col.key))
            if value is not None:
                cell.value = value
            if col.known and value is not None:
                # Ours, and locked: changing a payroll id or a GL account
                # here breaks the join it exists to make.
                cell.fill = KNOWN_FILL
                cell.protection = Protection(locked=True)
            else:
                cell.fill = ANSWER_FILL
                cell.protection = Protection(locked=False)

    # Dropdowns over the whole answer range, so they work on a row somebody
    # inserts as well as on the ones we drew.
    for col_key, ref in ranges.items():
        i = next(n for n, c in enumerate(columns, start=1)
                 if c.key == col_key)
        letter = get_column_letter(i)
        dv = DataValidation(type="list", formula1=ref, allow_blank=True,
                            showDropDown=False)
        # A refusal has to say what is allowed. openpyxl's default message is
        # "The value you entered is not valid", which tells somebody staring
        # at a spreadsheet precisely nothing.
        column = form.column(col_key)
        dv.errorTitle = column.heading
        dv.error = ("Pick one of: " + ", ".join(column.choices) +
                    ". Leave it blank if you do not know.")
        dv.promptTitle = column.heading
        dv.prompt = column.why or "Pick from the list."
        dv.showInputMessage = True
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        dv.add(f"{letter}{first}:{letter}{last + 200}")

    ws.protection.sheet = True
    ws.protection.password = "ybi"      # structure, not security — see the docstring
    ws.protection.insertRows = False
    ws.protection.formatCells = False
    ws.protection.formatColumns = False


def build_request_workbook(form: Form, period: str, *,
                           known_rows: list[dict] | None = None,
                           blank_rows: int = 40,
                           controls: dict[str, Decimal] | None = None) -> bytes:
    """The workbook to send out, as bytes.

    `known_rows` are what we already hold, keyed by column key — they are
    written into the grid and, where the column is marked `known`, locked.
    `blank_rows` are the empty rows after them; the sheet is not the limit,
    a person may add more and the parser reads to the end.
    """
    wb = Workbook()
    wb.remove(wb.active)
    _write_start_here(wb, form, period, controls)
    ranges = _write_choices(wb, form)
    _write_grid(wb, form, period, known_rows or [], blank_rows, ranges)
    wb.properties.title = identity_line(form, period)
    wb.properties.creator = "YBI cost allocation"
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
