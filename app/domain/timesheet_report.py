"""The timesheet report — Schedule G.

Two questions a reviewer asks about labour, and until now the system could
answer neither on paper:

    Whose effort is this, and what is it based on?
    Does it agree with what the payroll register says was paid?

The second is the one that matters. The fringe base comes from the effort
distribution and not from the ledger's wage accounts, so a difference between
them is two denominators for one rate. `v_statement_reconciliation` holds that
as the eleventh control; this workbook is where somebody can see *which
people* it consists of.

Nothing here is computed. Every figure is read from the row it was recorded
in — the same rule the review screens follow — and the workbook carries live
formulas only where a reviewer would otherwise have to do the addition
themselves to check a total that is already on the page.

**It states what is unfinished, on the first sheet, above the figures.** A
reviewer handed a distribution has formed a view before they reach a
footnote, and this one is built over a year that was reconstructed after the
fact from calendars and project logs. That is defensible and it is not the
same thing as a contemporaneous timesheet, so it says so.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from .package import (BOLD, BOX, CUR, HEAD_FILL, HEAD_FONT, INK, SUB, TITLE,
                      WARN_FILL, FAIL_FILL, PASS_FILL, _headers, _title)

__all__ = ["build_timesheet_report"]

HRS = "#,##0.00"


def _naive_utc(value):
    """Excel has no concept of a timezone and openpyxl refuses an aware
    datetime outright.

    Every timestamp in this system is stored in UTC, so it is converted to
    UTC and written without the offset rather than being rendered in
    whatever timezone the server happens to be in — a lag figure computed
    against a local-time column would be wrong by the offset, silently, and
    lag is what separates a record made as the work was done from one made
    eleven months later. The column headings say UTC.
    """
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def _cell(ws, row, col, value, *, font=INK, fmt=None, fill=None, wrap=False):
    c = ws.cell(row=row, column=col, value=_naive_utc(value))
    c.font = font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return c


def _caveats(ws, row: int, notes: list[str]) -> int:
    """Above the figures, never below them."""
    for note in notes:
        c = ws.cell(row=row, column=1, value=note)
        c.font = Font(name="Arial", size=10, bold=True, color="7A5B00")
        c.fill = WARN_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        ws.row_dimensions[row].height = 30
        row += 1
    return row + 1


def build_timesheet_report(period: str, *, coverage: list[dict],
                           distribution: list[dict], entries: list[dict],
                           certification: list[dict], reconciliation: dict,
                           caveats: list[str], out_path: Path) -> Path:
    wb = Workbook()

    # ── G — the cover, and what it does not yet prove ────────────────
    ws = wb.active
    ws.title = "G Cover"
    _title(ws, f"Timesheet and effort report — {period}",
           "Youngstown Business Incubator · Schedule G")
    ws.column_dimensions["A"].width = 34
    for col in "BCDEFG":
        ws.column_dimensions[col].width = 17

    row = _caveats(ws, 4, caveats)

    _cell(ws, row, 1, "The eleventh control", font=BOLD)
    row += 1
    _cell(ws, row, 1, "The payroll register against the ledger's wage accounts. "
                      "The fringe base is the effort distribution, so a "
                      "difference here is two denominators for one rate.",
          font=SUB, wrap=True)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    ws.row_dimensions[row].height = 30
    row += 2

    register = reconciliation.get("register_wages")
    ledger = reconciliation.get("ledger_wages")
    named = reconciliation.get("named")
    unexplained = reconciliation.get("unexplained")
    for label, value, fmt in (
            ("Payroll register", register, CUR),
            ("Ledger wage accounts", ledger, CUR),
            ("Difference", reconciliation.get("gross_difference"), CUR),
            ("Named in reconciling items", named, CUR),
            ("Unexplained", unexplained, CUR),
            ("People on the register", reconciliation.get("people"), "#,##0")):
        _cell(ws, row, 1, label, font=BOLD)
        # An unexplained residual is the only figure here that is a finding
        # rather than a fact, so it is the only one that gets a colour.
        fill = None
        if label == "Unexplained" and value is not None:
            fill = PASS_FILL if Decimal(str(value or 0)) == 0 else FAIL_FILL
        _cell(ws, row, 2, value, fmt=fmt, fill=fill)
        row += 1

    row += 1
    _cell(ws, row, 1, "What is in this workbook", font=BOLD)
    row += 1
    for sheet, what in (
            ("G-1 Coverage", "Hours entered against hours expected, per person."),
            ("G-2 Distribution", "Where each person's effort went, and the "
                                 "wages distributed with it."),
            ("G-3 Certification", "Who has signed, who has not, and whose "
                                  "signature has gone stale."),
            ("G-4 Entries", "Every entry: the day, the objective, the hours, "
                            "what it was reconstructed from, and who entered "
                            "it.")):
        _cell(ws, row, 1, sheet, font=BOLD)
        _cell(ws, row, 2, what, font=SUB)
        row += 1

    # ── G-1 — coverage ──────────────────────────────────────────────
    ws = wb.create_sheet("G-1 Coverage")
    _title(ws, "Timesheet coverage", f"{period} · hours entered against hours expected")
    _headers(ws, 4, ["Employee", "Entered", "Chargeable", "Leave", "Donated",
                     "Expected", "Coverage", "Days with time", "First", "Last",
                     "Submitted (UTC)"],
             [18, 12, 12, 10, 10, 12, 11, 14, 12, 12, 12])
    row = 5
    for r in coverage:
        _cell(ws, row, 1, r.get("employee_key"))
        _cell(ws, row, 2, r.get("entered_hours"), fmt=HRS)
        _cell(ws, row, 3, r.get("chargeable_hours"), fmt=HRS)
        _cell(ws, row, 4, r.get("leave_hours"), fmt=HRS)
        _cell(ws, row, 5, r.get("donated_hours"), fmt=HRS)
        _cell(ws, row, 6, r.get("expected_hours"), fmt=HRS)
        cov = r.get("coverage")
        _cell(ws, row, 7, (float(cov) / 100 if cov is not None else None),
              fmt="0.0%",
              fill=None if cov is None else
                   (PASS_FILL if float(cov) >= 95 else
                    WARN_FILL if float(cov) >= 50 else FAIL_FILL))
        _cell(ws, row, 8, r.get("days_with_time"), fmt="#,##0")
        _cell(ws, row, 9, r.get("first_day"), fmt="yyyy-mm-dd")
        _cell(ws, row, 10, r.get("last_day"), fmt="yyyy-mm-dd")
        _cell(ws, row, 11, r.get("submitted_at"), fmt="yyyy-mm-dd")
        row += 1
    _cell(ws, row, 1, "Total", font=BOLD)
    for col in (2, 3, 4, 5, 6):
        letter = get_column_letter(col)
        _cell(ws, row, col, f"=SUM({letter}5:{letter}{row - 1})",
              font=BOLD, fmt=HRS)

    # ── G-2 — distribution ──────────────────────────────────────────
    ws = wb.create_sheet("G-2 Distribution")
    _title(ws, "Effort distribution",
           f"{period} · where each person's effort went, and the wages with it")
    _headers(ws, 4, ["Employee", "Name", "Objective", "Source", "Units",
                     "Share", "Payroll wages", "Distributed wages",
                     "Evidence", "Reconstructed"],
             [16, 22, 20, 16, 12, 10, 15, 17, 13, 13])
    row = 5
    for r in distribution:
        _cell(ws, row, 1, r.get("employee_key"))
        _cell(ws, row, 2, r.get("employee_name"))
        _cell(ws, row, 3, r.get("objective_id"))
        _cell(ws, row, 4, r.get("source"))
        _cell(ws, row, 5, r.get("effective_units"), fmt=HRS)
        share = r.get("share")
        _cell(ws, row, 6, float(share) if share is not None else None, fmt="0.0%")
        _cell(ws, row, 7, r.get("payroll_wages"), fmt=CUR)
        _cell(ws, row, 8, r.get("distributed_wages"), fmt=CUR)
        _cell(ws, row, 9, r.get("evidence_quality"))
        _cell(ws, row, 10, "yes" if r.get("is_reconstructed") else "no")
        row += 1
    _cell(ws, row, 1, "Total distributed", font=BOLD)
    _cell(ws, row, 8, f"=SUM(H5:H{row - 1})", font=BOLD, fmt=CUR)
    # The figure the fringe rate is divided by. Printed next to the total so
    # a reviewer can see the two agree without leaving the sheet.
    _cell(ws, row + 1, 1, "Payroll register", font=BOLD)
    _cell(ws, row + 1, 8, register, font=BOLD, fmt=CUR)
    _cell(ws, row + 2, 1, "Difference", font=BOLD)
    _cell(ws, row + 2, 8, f"=H{row}-H{row + 1}", font=BOLD, fmt=CUR)

    # ── G-3 — certification ─────────────────────────────────────────
    ws = wb.create_sheet("G-3 Certification")
    _title(ws, "Certification under 2 CFR 200.430(i)",
           f"{period} · a statement from the person whose effort it was")
    _headers(ws, 4, ["Employee", "Name", "Payroll wages", "Objectives",
                     "Certified", "Signed (UTC)", "By", "From timesheet",
                     "Stale", "Weakest evidence"],
             [16, 22, 15, 11, 11, 13, 20, 14, 9, 17])
    row = 5
    for r in certification:
        _cell(ws, row, 1, r.get("employee_key"))
        _cell(ws, row, 2, r.get("employee_name"))
        _cell(ws, row, 3, r.get("payroll_wages"), fmt=CUR)
        _cell(ws, row, 4, r.get("objectives"), fmt="#,##0")
        done = bool(r.get("certified"))
        _cell(ws, row, 5, "yes" if done else "NO",
              font=BOLD if not done else INK,
              fill=PASS_FILL if done else FAIL_FILL)
        _cell(ws, row, 6, r.get("signed_at"), fmt="yyyy-mm-dd")
        _cell(ws, row, 7, r.get("signed_by"))
        _cell(ws, row, 8, "yes" if r.get("from_timesheet") else "no")
        _cell(ws, row, 9, "yes" if r.get("stale") else "",
              fill=WARN_FILL if r.get("stale") else None)
        _cell(ws, row, 10, r.get("weakest_grade"))
        row += 1

    # ── G-4 — every entry ───────────────────────────────────────────
    ws = wb.create_sheet("G-4 Entries")
    _title(ws, "Every timesheet entry",
           f"{period} · the day, the objective, the hours, and what it rests on")
    _headers(ws, 4, ["Employee", "Date", "Objective", "Hours", "Basis",
                     "Grade", "Note", "Entered by", "Entered (UTC)", "Lag (days)",
                     "Timing"],
             [16, 12, 20, 9, 20, 11, 34, 20, 12, 11, 13])
    row = 5
    for r in entries:
        _cell(ws, row, 1, r.get("employee_key"))
        _cell(ws, row, 2, r.get("work_date"), fmt="yyyy-mm-dd")
        _cell(ws, row, 3, r.get("objective_id"))
        _cell(ws, row, 4, r.get("hours"), fmt=HRS)
        _cell(ws, row, 5, r.get("basis"))
        _cell(ws, row, 6, r.get("entry_grade"))
        _cell(ws, row, 7, r.get("note"), wrap=True)
        _cell(ws, row, 8, r.get("entered_by_name"))
        _cell(ws, row, 9, r.get("entered_at"), fmt="yyyy-mm-dd")
        _cell(ws, row, 10, r.get("lag_days"), fmt="#,##0")
        _cell(ws, row, 11, r.get("timing"))
        row += 1
    _cell(ws, row, 1, "Total hours", font=BOLD)
    _cell(ws, row, 4, f"=SUM(D5:D{row - 1})", font=BOLD, fmt=HRS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
