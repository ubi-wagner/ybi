"""Any part of the rate build-up, as a file somebody can send.

The build-up workbook has always been all of it or none of it: five sheets,
one button, 171KB. That is the right artefact for a workpaper file and the
wrong one for the conversation it was built for — America Makes asks what is
in the overhead pool, and the answer should be the overhead pool, not a
workbook with the overhead pool on sheet two.

So every section the drill-down shows is its own export, at whatever level
the reader is standing on: a pool by account, one account's transactions,
the base, what sized each carve-out, the estate, the assets, or every
transaction in every pool. **The level is the section somebody is looking
at**, which is why the names here are the screen's own headings rather than
a separate vocabulary.

Three rules, and the first is the one this file exists for.

**The footing line travels.** A breakdown that does not add back to the
figure on the workpaper is worse than no breakdown, in a negotiation most of
all — and a CSV pasted into a sponsor's model has left the screen that said
so. Every section that is a partition carries its own tie on the face of the
file, in the same words the pane uses.

**And so does the signature.** `certification_lines()` is the one
sentence-maker for whether the rate is certified, per `082` and `122`, and a
figure that leaves this building without it is a figure a reader will assume
is final. Six places composed their own version of that sentence once; this
is not a seventh.

**Nothing here reads the database.** The route hands in what it already
fetched through `rate_composition`, `rate_account` and `rate_lines`, so the
file and the screen are one reading. A second query for the export is a
second answer to one question, which is the defect most of this repository
is about.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from app.domain.audit_package import certification_lines


@dataclass
class Sheet:
    """One section, ready to write as any format."""

    name: str
    title: str
    about: str
    columns: list[str]
    keys: list[str]
    rows: list[dict]
    money: set[int] = field(default_factory=set)     # 1-based column numbers
    rate_cols: set[int] = field(default_factory=set)
    foots: str = ""                                  # "" where it is not a partition


@dataclass
class Section:
    """How a section is found, and what it is called.

    `needs` names the extra question a section cannot be asked without — a
    pool by account is *which rate*, an account's transactions are *which
    account*. The route refuses a section whose question was not answered
    rather than quietly exporting the first one, which is the shape
    `_build_model` was caught in: a default applied where a caller made no
    choice.
    """

    title: str
    about: str
    columns: list[str]
    keys: list[str]
    build: Callable[[dict, dict | None, str | None], list[dict]]
    money: set[int] = field(default_factory=set)
    rate_cols: set[int] = field(default_factory=set)
    needs: str = ""          # "kind", "account", or ""
    part: str = ""           # which partition on the rate row foots it


def _rate(comp: dict, kind: str | None) -> dict:
    for r in comp.get("rates") or []:
        if r["kind"] == kind:
            return r
    raise KeyError(kind)


# The sections, named as the pane names them. Adding one here is what puts a
# button on the screen: `test_every_rate_section_has_a_button` derives both
# sides, so a section with no door and a button with no section each fail
# there rather than waiting for somebody to notice.
SECTIONS: dict[str, Section] = {
    "pool": Section(
        title="The pool, as classified",
        about=("Every ledger account classified into a pool this rate is "
               "taken over. The sum is the gross on the build-up."),
        columns=["Account", "Pool", "Amount", "Payees", "Lines"],
        keys=["account", "pool", "amount", "payees", "lines"],
        money={3}, needs="kind", part="gross",
        build=lambda comp, _d, kind: _rate(comp, kind)["gross"]["rows"]),
    "carve-outs": Section(
        title="Carve-outs",
        about=("What was taken out of the pool before the rate was struck, "
               "with the authority it was taken under and the driver that "
               "sized it."),
        columns=["Pool", "What", "Authority", "Amount", "Driver", "Grade"],
        keys=["pool", "name", "citation", "amount", "driver", "grade"],
        money={4}, needs="kind", part="carved",
        build=lambda comp, _d, kind: _rate(comp, kind)["carved"]["rows"]),
    "base": Section(
        title="The base",
        about=("What the pool is spread over. A wage base is one row per "
               "person, read off the payroll register; an MTDC base is one "
               "row per cost objective, as the allocation recorded it."),
        # Set per call: the two bases are different registers and printing
        # one under the other's headings is the count confusion this whole
        # pane was corrected for.
        columns=[], keys=[],
        needs="kind", part="base",
        build=lambda comp, _d, kind: _rate(comp, kind)["base"]["rows"]),
    "drivers": Section(
        title="What floor area drives",
        about=("The square-footage carve-out may only reach the cost square "
               "footage causes. These accounts are the exceptions, and the "
               "default is that floor area drives an account — so one "
               "nobody has considered is carved, which is the conservative "
               "direction."),
        columns=["Account", "Floor area drives it", "Reason"],
        keys=["account_fragment", "driven_by_area", "reason"],
        build=lambda comp, _d, _k: comp.get("overhead_drivers") or []),
    "estate": Section(
        title="The estate the 200.465 share is measured on",
        about=("Square feet, not dollars. A building's let, vacant and "
               "committed space carves its share of the occupancy in the "
               "pool, weighted by what the building is of the whole estate."),
        columns=["Building", "Usable", "Assignable", "Common", "Let",
                 "Vacant", "Committed", "Programme", "Admin", "Shared lab",
                 "Share let"],
        keys=["name", "usable_sqft", "assignable", "common", "tenant_sqft",
              "vacant_sqft", "committed_sqft", "program_sqft", "admin_sqft",
              "shared_lab_sqft", "rental_share"],
        rate_cols={11},
        build=lambda comp, _d, _k: comp.get("estate") or []),
    "assets": Section(
        title="The assets federal money bought",
        about=("2 CFR 200.436(b) makes depreciation on a federally funded "
               "asset unallowable in a federal pool."),
        columns=["Asset", "Account", "Cost", "Depreciation",
                 "Federal funding", "Total funding", "Federal share",
                 "Allowable depreciation"],
        keys=["description", "gl_account", "gross_cost", "depreciation",
              "federal_funding", "total_funding", "federal_share",
              "allowable_depreciation"],
        money={3, 4, 5, 6, 8}, rate_cols={7},
        build=lambda comp, _d, _k: comp.get("federally_funded_assets") or []),
    "admin-labour": Section(
        title="Administrative labour in the pool",
        about=("Where the G&A pool carries it under the POOL basis. It comes "
               "from the effort distribution rather than from a "
               "classification, which is why it is in no account."),
        columns=["Person", "Employee key", "Wages", "From", "Grade"],
        keys=["employee_name", "employee_key", "distributed_wages", "source",
              "grade"],
        money={3}, needs="kind",
        build=lambda comp, _d, kind: (_rate(comp, kind).get("admin_labour")
                                      or {}).get("rows") or []),
    "payees": Section(
        title="Who was paid",
        about="Every payee in this account, largest first.",
        columns=["Payee", "Amount", "Lines"],
        keys=["payee", "amount", "lines"],
        money={2}, needs="account",
        build=lambda _c, detail, _k: (detail or {}).get("payees") or []),
    "account": Section(
        title="Every transaction in this account",
        about=("The ledger lines behind one account, each with the judgment "
               "that put it in its pool."),
        columns=["Date", "Payee", "Description", "Amount", "990 function",
                 "Federal", "Objective", "Grade", "Citation", "Rationale",
                 "Judged by"],
        keys=["date", "payee", "description", "amount", "function_990",
              "federal", "objective_id", "grade", "citation", "rationale",
              "decided_by"],
        money={4}, needs="account",
        build=lambda _c, detail, _k: (detail or {}).get("lines") or []),
    "transactions": Section(
        title="Every transaction in every pool",
        about=("All of it, across every pool a rate is taken over. This is "
               "what goes across the table."),
        columns=["Pool", "Account", "Date", "Payee", "Description", "Amount",
                 "990 function", "Federal", "Objective", "Grade", "Citation",
                 "Rationale", "Judged by"],
        keys=["pool", "account", "date", "payee", "description", "amount",
              "function_990", "federal", "objective_id", "grade", "citation",
              "rationale", "decided_by"],
        money={6},
        build=lambda _c, detail, _k: (detail or {}).get("rows") or []),
}

# A wage base is one row per person and an MTDC base one row per objective,
# and the money is in a different column in each — so the money set travels
# with the columns rather than being written once beside them. The first
# draft kept `money={2}`, which is neither.
BASE_COLUMNS = {
    "PERSON": (["Person", "Employee key", "Wages in the base", "Objectives",
                "From", "Grade"],
               ["employee_name", "employee_key", "base_amount", "objectives",
                "source", "grade"],
               {3}),
    "OBJECTIVE": (["Cost objective", "Label", "Kind", "Federal", "Base",
                   "Indirect allocated"],
                  ["objective_id", "label", "objective_type", "is_federal",
                   "base_amount", "allocated"],
                  {5, 6}),
}


def foots_line(part: dict | None, unit: str) -> str:
    """The partition's own tie, in the pane's words.

    Three states, because `_part` answers `NO DATA` where there is no
    breakdown to draw rather than reporting a failed tie — and a file that
    printed a five-million-dollar variance over a table that was never meant
    to exist is the control crying wolf, on paper, in front of a sponsor.
    """
    if not part:
        return ""
    rec = Decimal(str(part.get("recorded") or 0))
    if part.get("state") == "NO DATA":
        return (f"Nothing breaks the {rec:,.2f} on file down here. "
                + (part.get("needs") or ""))
    total = Decimal(str(part.get("total") or 0))
    n = len(part.get("rows") or [])
    if total == rec:
        return (f"{n:,} {unit} totalling {total:,.2f} — ties to the "
                f"{rec:,.2f} the rate carries.")
    return (f"{n:,} {unit} totalling {total:,.2f} — DOES NOT TIE to the "
            f"{rec:,.2f} the rate carries, out by {total - rec:,.2f}.")


def build_sheet(section: str, *, comp: dict, detail: dict | None = None,
                kind: str | None = None) -> Sheet:
    """One section of the build-up, as rows ready to write.

    Raises `KeyError` on a section nobody offers and on a kind no rate
    carries, so the route answers with the ones that exist rather than with
    an empty file — *a screen offering what the server will not take* read
    from the other end.
    """
    s = SECTIONS[section]
    columns, keys, money = s.columns, s.keys, s.money
    rows = s.build(comp, detail, kind)

    part = None
    if s.part and kind:
        part = _rate(comp, kind).get(s.part)

    if section == "base":
        by = (part or {}).get("by") or "OBJECTIVE"
        columns, keys, money = BASE_COLUMNS[by]
        unit = "people on the payroll register" if by == "PERSON" else "objectives"
        foots = foots_line(part, unit)
    elif section == "pool":
        foots = foots_line(part, "accounts")
    elif section == "carve-outs":
        foots = foots_line(part, "carve-outs")
    elif section == "transactions":
        foots = foots_line((detail or {}).get("part"), "transactions")
    elif section in ("account", "payees") and detail:
        # Not a partition of the rate: it is one account, and what it ties to
        # is its own figure on the pool sheet. Said plainly rather than as a
        # tick, because a reader holding this file alone has nothing to tie
        # it against.
        amt = Decimal(str(detail.get("amount") or 0))
        shown = len(rows)
        total = detail.get("lines_total") if section == "account" else shown
        foots = (f"{shown:,} of {total:,} row(s); the account is "
                 f"{amt:,.2f} in the {detail.get('pool')} pool.")
    else:
        foots = ""

    title = s.title
    if kind:
        title = f"{title} — {kind}"
    if detail and section in ("account", "payees"):
        title = f"{title}: {detail.get('account')}"
    return Sheet(name=section, title=title, about=s.about, columns=columns,
                 keys=keys, rows=rows, money=money, rate_cols=s.rate_cols,
                 foots=foots)


def _cell(value, *, money: bool = False, rate: bool = False):
    """One value, spelled the way this house spells it.

    A boolean is `yes` or `no` — *`true` is what JSON calls it and not what a
    person does* — and `None` stays blank, because *there is no answer* and
    *nobody has answered* are different facts.

    **And a figure is money only where the column says so.** The first draft
    spelled every `Decimal` `{:,.2f}`, which printed 54,308 square feet as
    `54,308.00` beside $850,382.89 in the same file — `money()` and `count()`
    exist as two helpers for exactly that reason, and the estate is measured
    in feet. A plain figure keeps the decimals it has and no more, so Heidi's
    9,326.5 survives and a whole building does not grow cents.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Decimal):
        if rate:
            return f"{value * 100:,.4f}%"
        if money:
            return f"{value:,.2f}"
        return f"{value.normalize():,f}"
    return str(value)


def to_csv(sheet: Sheet, *, period: str, certification: dict | None) -> str:
    """The section as a file a sponsor's analyst opens in Excel.

    The caveat is at the top, above the figures, which costs a reader three
    rows to delete and is the rule this repository holds everywhere else: *a
    reviewer handed a total has formed a view before they reach a footnote.*
    A CSV is exactly the artefact that travels furthest from the screen that
    would have said so.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([sheet.title])
    w.writerow([sheet.about])
    w.writerow([f"Period {period} · prepared "
                f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"])
    for line in certification_lines(certification):
        w.writerow([line])
    if sheet.foots:
        w.writerow([sheet.foots])
    w.writerow([])
    # No column headings over nothing: the footing line above has already
    # said what is missing, and headers with no rows under them say less
    # than that. The Base sheet of the build-up workbook was corrected for
    # the same thing.
    if sheet.rows:
        w.writerow(sheet.columns)
        for r in sheet.rows:
            w.writerow([_cell(r.get(k), money=i in sheet.money,
                              rate=i in sheet.rate_cols)
                        for i, k in enumerate(sheet.keys, start=1)])
    return buf.getvalue()


def _widths(sheet: Sheet) -> list[int]:
    """Columns sized to what is in them, within reason.

    The sections are generic, so there is no hand-written width per column
    the way the five-sheet build-up has — and a uniform 18 put a
    seventy-character account path behind `####`. Read off the longest value
    and clamped: 12 so a heading is legible, 70 so a rationale does not take
    the screen. The caller still has to widen one occasionally, which is a
    spreadsheet and is fine; what is not fine is a figure nobody can read.
    """
    out = []
    for i, (head, key) in enumerate(zip(sheet.columns, sheet.keys), start=1):
        longest = max([len(head)]
                      + [len(_cell(r.get(key), money=i in sheet.money,
                                   rate=i in sheet.rate_cols))
                         for r in sheet.rows] or [len(head)])
        out.append(max(12, min(70, longest + 2)))
    return out


def to_xlsx(sheet: Sheet, path, *, period: str,
            certification: dict | None):
    """The same section as a workbook, for the file rather than the email.

    Through `audit_package`'s own `_sheet`, `_table` and `_caveat`, so a
    figure here and the same figure in the five-sheet build-up carry the same
    number format and the same band. A second table writer is a second house
    style.
    """
    from openpyxl import Workbook

    from app.domain.audit_package import BOLD, _sheet, _table
    from app.domain.review_workbooks import RULE, _caveat, _as_rate

    wb = Workbook()
    wb.remove(wb.active)
    ws = _sheet(wb, sheet.name[:31], sheet.title, sheet.about)
    ws.cell(row=3, column=1,
            value=(f"Period {period} · prepared "
                   f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")).font = RULE
    r = _caveat(ws, 5, certification_lines(certification))
    if sheet.foots:
        c = ws.cell(row=r, column=1, value=sheet.foots)
        c.font = BOLD if "DOES NOT TIE" in sheet.foots else RULE
        r += 2
    if not sheet.rows:
        return path
    last = _table(ws, r, sheet.columns, sheet.rows, sheet.keys,
                  _widths(sheet), sheet.money)
    for col in sheet.rate_cols:
        _as_rate(ws, r + 1, last, col)
    wb.save(path)
    return path
