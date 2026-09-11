"""Reading a filled workbook back, and saying exactly what is wrong with it.

The other half of `request_workbook.py`, through the same form definition, so
a column can only be read if the workbook asked for it.

The whole value of this module is in what it does with an imperfect answer,
because every answer will be imperfect. A register of four hundred assets
comes back with eleven dates typed as "2019ish", two funding columns holding
"EDA I think", and a blank where somebody got bored. The useless response is
to refuse the file. The response that gets the information is to accept the
three hundred and eighty-seven rows that are fine, and to say of the rest:

    Assets, row 214, "Placed in service": "2019ish" is not a date.

A person can act on that in a minute. They cannot act on a stack trace, and
they will not act at all on a silent coercion that turned it into 1 January.

Three rules:

**A blank is unanswered, and unanswered is a value.** Never zero, never false,
never the first choice in the list. `Unanswered` is its own state all the way
through, so "there is no federal money in this asset" and "nobody has looked"
stay different facts — which they are, and the second is the one worth
chasing.

**Columns are found by their heading, not their position.** Somebody will
insert a column, sort by a different one, or fill in last quarter's copy of
the form. Reading by position turns any of those into silently wrong data in
the right-hand columns; reading by heading turns it into nothing worse than a
missing column, named.

**Nothing is coerced into validity.** A value that does not parse is reported
with the cell it is in and the text that was in it, and the row carries on
without that field. The alternative — round it, strip it, guess the format —
is how a number nobody typed ends up in a rate.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from .request_forms import ISSUED, ISSUED_MARKER, Column, Form, Kind
from .request_workbook import IDENTITY_CELL, IDENTITY_SHEET

__all__ = ["read_request_workbook", "Filled", "Problem", "Row",
           "WorkbookNotRecognised"]


class WorkbookNotRecognised(Exception):
    """The file is not a reply to a form we sent.

    Separate from a cell problem on purpose: a cell problem is answered by
    correcting a cell, and this is answered by finding the right file.
    """


@dataclass(frozen=True)
class Problem:
    sheet: str
    row: int | None
    heading: str
    value: str
    says: str

    def __str__(self) -> str:
        where = f"{self.sheet}, row {self.row}" if self.row else self.sheet
        got = f': "{self.value}"' if self.value else ""
        return f"{where}, {self.heading}{got} — {self.says}"


@dataclass
class Row:
    number: int                       # the row in the sheet, as a person sees it
    values: dict[str, Any] = field(default_factory=dict)
    missing_required: tuple[str, ...] = ()
    #: Did a person put anything in this row, or is it only what we sent?
    #: The six balance-sheet rows in the asset workbook arrive back untouched
    #: if nobody got to them, and reporting those as *incomplete* would bury
    #: the rows somebody actually started and left half done — which are the
    #: ones worth a phone call.
    touched: bool = True

    @property
    def usable(self) -> bool:
        return self.touched and not self.missing_required

    def get(self, key: str, default=None):
        v = self.values.get(key)
        return default if v is None else v


@dataclass
class Filled:
    form: Form
    period: str
    rows: list[Row]
    problems: list[Problem]
    #: Headings the form asked for that the workbook does not have. A column
    #: somebody deleted, or an older version of the form.
    missing_columns: tuple[str, ...] = ()
    version_seen: int | None = None

    @property
    def usable(self) -> list[Row]:
        return [r for r in self.rows if r.usable]

    @property
    def incomplete(self) -> list[Row]:
        """Started and left, which is a question for a person."""
        return [r for r in self.rows if r.touched and r.missing_required]

    @property
    def untouched(self) -> list[Row]:
        """Sent out pre-filled and came back the same, which is a queue."""
        return [r for r in self.rows if not r.touched]

    def total(self, key: str) -> Decimal:
        """What one column adds up to, over every row that answered it."""
        out = Decimal("0")
        for r in self.rows:
            v = r.values.get(key)
            if isinstance(v, Decimal):
                out += v
        return out

    def answered(self, key: str) -> int:
        return sum(1 for r in self.rows if r.values.get(key) is not None)


_IDENTITY = re.compile(r"YBI\s*·\s*([A-Z_]+)\s*v(\d+)\s*·\s*([^·]+)·")
_MONEY = re.compile(r"[,$\s]")
_TRUE = {"y", "yes", "true", "t", "1", "✓", "x"}
_FALSE = {"n", "no", "false", "f", "0"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip()


def _number(raw: Any) -> Decimal:
    """A number as typed by somebody in a hurry.

    Accepts what Excel hands back as a float, and what a person types as
    text: thousands separators, a currency symbol, and accounting negatives
    in parentheses. Refuses anything else rather than reaching for the first
    digits it can find — "about 40,000" is a sentence, not a figure, and the
    person who wrote it meant it as one.
    """
    if isinstance(raw, bool):
        raise ValueError("a yes/no where a number belongs")
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))
    text = _text(raw)
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = _MONEY.sub("", text).rstrip("%")
    if not text:
        raise ValueError("empty")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("is not a number") from None
    return -value if negative else value


def _date(raw: Any) -> dt.date:
    if isinstance(raw, dt.datetime):
        return raw.date()
    if isinstance(raw, dt.date):
        return raw
    text = _text(raw)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y", "%b %d %Y",
                "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("is not a date — please use YYYY-MM-DD")


def _cell(col: Column, raw: Any) -> Any:
    """One cell, or a ValueError whose message finishes the sentence
    'row 14, Placed in service: "2019ish" …'."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None                      # unanswered, and that is a value
    if col.kind is Kind.TEXT:
        return _text(raw)
    if col.kind in (Kind.NUMBER, Kind.MONEY):
        return _number(raw)
    if col.kind is Kind.PERCENT:
        value = _number(raw)
        if not (0 <= value <= 100):
            raise ValueError("is not between 0 and 100 — the column is a "
                             "percentage, so half is 50")
        return value
    if col.kind is Kind.DATE:
        return _date(raw)
    if col.kind is Kind.YES_NO:
        if isinstance(raw, bool):
            return raw
        text = _text(raw).lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ValueError("is not a yes or a no")
    if col.kind is Kind.CHOICE:
        text = _text(raw).upper().replace(" ", "_")
        if text in col.choices:
            return text
        raise ValueError("is not one of " + ", ".join(col.choices))
    raise ValueError("cannot be read")           # unreachable by construction


def _identity(wb, form: Form) -> tuple[str, int]:
    if IDENTITY_SHEET not in wb.sheetnames:
        raise WorkbookNotRecognised(
            f"This workbook has no '{IDENTITY_SHEET}' sheet, so there is no "
            f"way to tell which request it answers. Please send back the "
            f"file as it was issued rather than a copy of the grid.")
    line = _text(wb[IDENTITY_SHEET][IDENTITY_CELL].value)
    match = _IDENTITY.match(line)
    if not match:
        raise WorkbookNotRecognised(
            f"The first sheet does not carry a request line, so this is not a "
            f"workbook this system issued. It read: {line[:120]!r}")
    name, version, period = match.group(1), int(match.group(2)), match.group(3).strip()
    if name != form.name:
        raise WorkbookNotRecognised(
            f"This is a {name} workbook and it was uploaded against "
            f"{form.name}. Upload it against {name} instead — the columns "
            f"mean different things.")
    return period, version


def read_request_workbook(data: bytes, form: Form) -> Filled:
    """Read a filled workbook against the form it answers.

    Raises `WorkbookNotRecognised` when the file is not a reply to this form
    at all. Everything smaller than that — a missing column, an unreadable
    cell, a row with no identifier — comes back inside `Filled` so the
    preview can show all of it at once. A person correcting a workbook should
    have to make one pass, not discover the next problem each time they
    upload.
    """
    wb = load_workbook(BytesIO(data), data_only=True)
    period, version = _identity(wb, form)

    if form.sheet not in wb.sheetnames:
        raise WorkbookNotRecognised(
            f"The '{form.sheet}' sheet is missing. It may have been renamed — "
            f"the figures are read off it by name.")
    ws = wb[form.sheet]

    # Headings, not positions. Somebody will insert a column, and reading by
    # position would put their new column's contents into the next field
    # along without a word.
    heading_at: dict[str, int] = {}
    for i, cell in enumerate(ws[1], start=1):
        text = _text(cell.value).rstrip(" *")
        if text:
            heading_at.setdefault(text, i)

    columns: list[tuple[Column, int]] = []
    missing: list[str] = []
    marker_at = heading_at.get(ISSUED_MARKER.heading)
    for col in form.columns:
        index = heading_at.get(col.heading)
        if index is None:
            missing.append(col.heading)
        else:
            columns.append((col, index))

    problems: list[Problem] = []
    for heading in missing:
        problems.append(Problem(
            form.sheet, None, heading, "",
            "this column is not in the workbook, so nothing was read for it. "
            "It may be an older copy of the form."))

    rows: list[Row] = []
    # Row 1 is the heading and row 2 the explanation the workbook was issued
    # with. A person who deleted the explanation row shifts everything up, so
    # the second row is skipped only when it still looks like ours.
    start = 3 if _looks_like_the_note_row(ws, columns) else 2
    for r in range(start, ws.max_row + 1):
        raw = {col.key: ws.cell(row=r, column=i).value for col, i in columns}
        if all(v is None or (isinstance(v, str) and not v.strip())
               for v in raw.values()):
            continue                     # an empty row is not an answer
        values: dict[str, Any] = {}
        for col, _ in columns:
            try:
                values[col.key] = _cell(col, raw[col.key])
            except ValueError as exc:
                values[col.key] = None
                problems.append(Problem(form.sheet, r, col.heading,
                                        _text(raw[col.key])[:60], str(exc)))
        absent = tuple(col.heading for col in form.required
                       if values.get(col.key) in (None, ""))
        # A row we did not issue is theirs entirely, whatever is in it. A
        # row we did issue counts as touched only where something outside
        # the columns we pre-filled has been answered.
        prefilled = set(form.prefilled) | {c.key for c in form.columns if c.known}
        ours = (marker_at is not None
                and _text(ws.cell(row=r, column=marker_at).value) == ISSUED)
        touched = (not ours) or any(
            values.get(col.key) not in (None, "")
            for col, _ in columns if col.key not in prefilled)
        rows.append(Row(number=r, values=values, missing_required=absent,
                        touched=touched))

    for row in rows:
        if row.touched and row.missing_required:
            problems.append(Problem(
                form.sheet, row.number, ", ".join(row.missing_required), "",
                "this row has answers but is missing something it cannot be "
                "recorded without, so it is held back rather than half "
                "written"))

    return Filled(form=form, period=period, rows=rows, problems=problems,
                  missing_columns=tuple(missing), version_seen=version)


def _looks_like_the_note_row(ws, columns) -> bool:
    """Is row 2 the explanation the workbook was issued with, or an answer?

    The note row is ours and its text is known, so this compares rather than
    assumes. A person who deleted it and started typing on row 2 gets their
    first row read instead of silently dropped, which is a mistake somebody
    makes exactly once and never finds.
    """
    for col, i in columns:
        if not col.why:
            continue
        if _text(ws.cell(row=2, column=i).value).startswith(col.why[:24]):
            return True
    return False
