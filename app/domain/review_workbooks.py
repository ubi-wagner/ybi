"""The three workbooks that leave the building.

Each one is a deliverable somebody signs: the rate a sponsor is asked to
accept, the report an auditor works from, and the functional allocation the
return prints. They share the audit package's sheet helpers so the whole set
reads as one body of work rather than three exports written by three people.

Every one of them states what is unfinished on its first sheet. A workbook
that looks complete and is not is worse than no workbook, because it travels
— somebody forwards it, somebody quotes a figure out of it, and the caveat
that lived on a screen does not go with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from app.domain.audit_package import (BOLD, TITLE, WRAP, certification_lines,
                                      _sheet, _table)

RULE = Font(italic=True, size=9)


def _stamp(ws, period: str, row: int = 3) -> None:
    ws.cell(row=row, column=1,
            value=(f"Period {period} · prepared "
                   f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")).font = RULE


def _caveat(ws, row: int, lines: list[str]) -> int:
    """What is not finished, at the top, before any figure.

    Deliberately above the numbers rather than in a footnote. A reader who
    has already read the total has already formed a view.
    """
    for text in lines:
        c = ws.cell(row=row, column=1, value=text)
        c.alignment = WRAP
        c.font = (BOLD if text.startswith(("NOT ", "CERTIFIED"))
                  else Font(size=10))
        ws.row_dimensions[row].height = 28
        row += 1
    return row + 1



def _as_rate(ws, first_row: int, last_row: int, col: int) -> None:
    """A rate is read as a percentage to four places, not rounded to cents.

    _table money-formats with #,##0.00, which turned 0.914400 into 0.91 — a
    rate reported to two decimal places of a ratio is a rate nobody can
    reproduce, and 0.91 on a workpaper reads as ninety-one cents.
    """
    for r in range(first_row, last_row + 1):
        c = ws.cell(row=r, column=col)
        if isinstance(c.value, (int, float)):
            c.number_format = "0.0000%"


# ------------------------------------------------------------------ rate


def build_rate_buildup(*, period: str, out_path: Path, rates: list[dict],
                       carve_outs: list[dict], coverage: dict | None,
                       open_controls: list[dict], final: bool,
                       certification: dict | None = None,
                       composition: dict | None = None) -> Path:
    wb = Workbook()
    wb.remove(wb.active)

    ws = _sheet(wb, "Rate", "Indirect rate build-up",
                "The pool, what was taken out of it and under what authority, "
                "the base, and the seal the whole thing hangs off.")
    _stamp(ws, period)
    pct = Decimal(str((coverage or {}).get("pct_dollars_covered") or 0))
    # The signature first, because it is the question a reader asks of a rate
    # before they ask how complete it is.
    r = _caveat(ws, 5, certification_lines(certification))
    if not final:
        why = []
        if open_controls:
            why.append(f"{len(open_controls)} cross-reference point(s) are open: "
                       + ", ".join(c["control"] for c in open_controls))
        if pct < 100:
            why.append(f"classification is {pct}% complete by dollars — cost "
                       f"nobody has judged is not in any pool, so the rate "
                       f"reads high")
        r = _caveat(ws, r, ["NOT FINAL — this rate is a working figure.", *why])

    head = r
    r = _table(ws, r,
               ["Rate", "Pool", "Base", "Base amount", "Rate", "Status",
                "Sealed by", "Sealed at", "Seal"],
               rates,
               ["kind", "pool_amount", "base_type", "base_amount", "rate",
                "status", "sealed_by", "sealed_at", "seal_hash"],
               [20, 16, 18, 16, 12, 14, 20, 22, 66], {2, 4})
    _as_rate(ws, head + 1, r, 5)

    if carve_outs:
        r += 2
        ws.cell(row=r, column=1, value="Carve-outs").font = BOLD
        r += 1
        ws.cell(row=r, column=1, value=(
            "What was removed from a pool before the rate was struck. Each "
            "one names the authority it was removed under and the driver that "
            "sized it — a reduction without both is an adjustment, not a "
            "carve-out.")).alignment = WRAP
        r = _table(ws, r + 2,
                   ["Pool", "What", "Authority", "Amount", "Driver", "Grade",
                    "Recorded by"],
                   carve_outs,
                   ["pool", "name", "citation", "amount", "driver", "grade",
                    "created_by"],
                   [16, 30, 26, 16, 40, 22, 20], {4})

    # ------------------------------------------------ and what is inside it
    #
    # The four rows above are the build-up. What a negotiation opens with is
    # the question underneath them, and the controller asked for it in those
    # words after downloading this file and finding it was the same four rows
    # he was already reading on the screen.
    #
    # Each sheet carries **its own footing line**: what the rows come to, the
    # figure the rate recorded, and the difference. A breakdown that does not
    # add back to the workpaper is worse than none at all once it is in a
    # sponsor's hands, and a workbook travels further than a screen does.
    if composition:
        _composition_sheets(wb, period, composition)

    wb.save(out_path)
    return out_path


def _foots(ws, row: int, part: dict | None, what: str) -> int:
    """What the rows come to, against the figure on file."""
    if not part:
        return row
    total = Decimal(str(part.get("total") or 0))
    rec = Decimal(str(part.get("recorded") or 0))
    # Three states. `NO DATA` is no breakdown to draw, not a failed tie, and
    # printing it as one puts a variance the width of the whole base on a
    # workpaper a sponsor reads. A sweep that cries wolf teaches the reader
    # to dismiss the next real one.
    if part.get("state") == "NO DATA":
        text = (f"Nothing breaks the {rec:,.2f} on file down here. "
                + (part.get("needs") or ""))
        ok = None
    else:
        ok = total == rec
        text = (f"{len(part.get('rows') or [])} {what} totalling {total:,.2f} "
                + (f"— ties to the {rec:,.2f} the rate carries" if ok else
                   f"— DOES NOT TIE to the {rec:,.2f} the rate carries, out "
                   f"by {total - rec:,.2f}"))
    c = ws.cell(row=row, column=1, value=text)
    c.font = RULE if ok else BOLD
    c.alignment = WRAP
    return row + 2


def _composition_sheets(wb: Workbook, period: str, comp: dict) -> None:
    """The pool by account, every transaction under it, the drivers, the base.

    One sheet per question rather than one per rate: the four rates are drawn
    from three pools and INDIRECT_COMBINED is two of them, so a sheet per
    rate would print OVERHEAD and G&A twice and leave a reader working out
    which copy to add up.
    """
    rates = comp.get("rates") or []

    ws = _sheet(wb, "Pool detail", "What the pools are made of",
                "Every account classified into a pool a rate is taken over, "
                "with the rate it serves. The sum of each pool is the gross "
                "on the build-up.")
    _stamp(ws, period)
    r = 5
    for rate in rates:
        # INDIRECT_COMBINED is the two pools under it, so printing it as well
        # would be the same accounts twice. The pools are the unit here and
        # the kind is named on each.
        if len(rate.get("pools") or []) != 1:
            continue
        ws.cell(row=r, column=1, value=f"{rate['kind']} — {rate['pools'][0]}").font = BOLD
        r = _foots(ws, r + 1, rate.get("gross"), "account(s)")
        r = _table(ws, r, ["Pool", "Account", "Amount", "Payees", "Lines"],
                   rate["gross"]["rows"],
                   ["pool", "account", "amount", "payees", "lines"],
                   [16, 62, 16, 10, 10], {3}) + 3

    ws = _sheet(wb, "Transactions", "Every transaction in the pools",
                "The ledger lines behind the accounts on the previous sheet, "
                "each with the judgment that put it in its pool.")
    _stamp(ws, period)
    r = _foots(ws, 5, comp.get("lines_part"), "transaction(s)")
    _table(ws, r,
           ["Pool", "Account", "Date", "Payee", "Description", "Amount",
            "990 function", "Federal", "Objective", "Grade", "Citation",
            "Rationale", "Judged by"],
           comp.get("lines") or [],
           ["pool", "account", "date", "payee", "description", "amount",
            "function_990", "federal", "objective_id", "grade", "citation",
            "rationale", "decided_by"],
           [14, 46, 12, 26, 40, 16, 20, 14, 16, 24, 26, 60, 20], {6})

    ws = _sheet(wb, "Carve-out drivers", "What sized each carve-out",
                "A carve-out without the register that sized it is an "
                "adjustment. 200.465 is sized by floor area and 200.436(b) "
                "by what bought the asset.")
    _stamp(ws, period)
    r = 5
    split = next((x.get("driver_split") for x in rates
                  if x.get("driver_split")), None)
    if split:
        ws.cell(row=r, column=1, value="What floor area drives").font = BOLD
        ws.cell(row=r + 1, column=1, value=(
            "The square-footage carve-out may only reach the cost square "
            "footage causes. The rest of the pool — T1 access, telephone, "
            "insurance, equipment — is the floor under the overhead rate."
        )).alignment = WRAP
        r = _table(ws, r + 3, ["Part of the pool", "Amount"],
                   [{"what": "Occupancy — floor area drives it",
                     "amount": split["occupancy"]},
                    {"what": "Not driven by floor area",
                     "amount": split["not_area_driven"]},
                    {"what": "Pool gross", "amount": split["pool_gross"]}],
                   ["what", "amount"], [44, 18], {2}) + 3
    if comp.get("overhead_drivers"):
        ws.cell(row=r, column=1, value=(
            "Which accounts are the exception, and why. The default is that "
            "floor area drives an account, so one nobody has considered is "
            "carved — the conservative direction.")).alignment = WRAP
        r = _table(ws, r + 2, ["Account", "Floor area drives it", "Reason"],
                   comp["overhead_drivers"],
                   ["account_fragment", "driven_by_area", "reason"],
                   [40, 18, 70]) + 3
    if comp.get("estate"):
        ws.cell(row=r, column=1,
                value="The estate the 200.465 share is measured on "
                      "(square feet, not dollars)").font = BOLD
        last = _table(ws, r + 2,
                   ["Building", "Usable", "Assignable", "Common", "Let",
                    "Vacant", "Committed", "Programme", "Admin",
                    "Shared lab", "Share let"],
                   comp["estate"],
                   ["name", "usable_sqft", "assignable", "common",
                    "tenant_sqft", "vacant_sqft", "committed_sqft",
                    "program_sqft", "admin_sqft", "shared_lab_sqft",
                    "rental_share"],
                   [34, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12])
        _as_rate(ws, r + 3, last, 11)
        r = last + 3
    if comp.get("federally_funded_assets"):
        ws.cell(row=r, column=1,
                value="The assets federal money bought, which 200.436(b) "
                      "makes unallowable to depreciate into a federal "
                      "pool").font = BOLD
        last = _table(ws, r + 2,
               ["Asset", "Account", "Cost", "Depreciation", "Federal funding",
                "Total funding", "Federal share", "Allowable depreciation"],
               comp["federally_funded_assets"],
               ["description", "gl_account", "gross_cost", "depreciation",
                "federal_funding", "total_funding", "federal_share",
                "allowable_depreciation"],
               [44, 18, 16, 16, 16, 16, 14, 20], {3, 4, 5, 6, 8})
        _as_rate(ws, r + 3, last, 7)

    ws = _sheet(wb, "Base", "What each pool is spread over",
                "The denominator of each rate, read off the register it was "
                "taken over: the payroll register for a wage base, the "
                "allocation for an MTDC base — and the administrative "
                "labour, where the G&A pool carries it.")
    _stamp(ws, period)
    r = 5
    for rate in rates:
        ws.cell(row=r, column=1,
                value=f"{rate['kind']} — base {rate['base_type']}").font = BOLD
        # A wage base is one row per person and an MTDC base is one row per
        # objective, and the unit is not cosmetic: printing 43 people as "43
        # objective(s)" under objective headings is the count confusion that
        # put 97 on the run sheet where the answer was 43. The register the
        # base was taken over decides both the word and the columns.
        base = rate.get("base") or {}
        by_person = base.get("by") == "PERSON"
        r = _foots(ws, r + 1, base,
                   "people on the payroll register" if by_person
                   else "objective(s)")
        if base.get("state") == "NO DATA":
            # The footing line above has already said what is missing;
            # column headings with nothing under them say less than that.
            r += 1
        elif by_person:
            r = _table(ws, r,
                       ["Person", "Employee key", "Wages in the base",
                        "Objectives", "From", "Grade"],
                       base.get("rows") or [],
                       ["employee_name", "employee_key", "base_amount",
                        "objectives", "source", "grade"],
                       [30, 20, 20, 12, 22, 30], {3}) + 3
        else:
            r = _table(ws, r,
                       ["Cost objective", "Label", "Kind", "Federal", "Base",
                        "Indirect allocated"],
                       base.get("rows") or [],
                       ["objective_id", "label", "objective_type", "is_federal",
                        "base_amount", "allocated"],
                       [20, 40, 18, 10, 18, 18], {5, 6}) + 3
        adm = rate.get("admin_labour")
        if adm:
            ws.cell(row=r, column=1, value=(
                f"Administrative labour in the {rate['kind']} pool — "
                f"{adm['objective']}, under the {adm['basis']} basis. "
                f"Wages {Decimal(str(adm['wages'])):,.2f} plus fringe "
                f"{Decimal(str(adm['fringe_on_it'])):,.2f} is the "
                f"{Decimal(str(adm['recorded'])):,.2f} the pool carries. It "
                f"comes from the effort distribution rather than from a "
                f"classification, which is why it is in no account above."
            )).alignment = WRAP
            r = _table(ws, r + 2,
                       ["Person", "Employee key", "Wages", "From", "Grade"],
                       adm["rows"],
                       ["employee_name", "employee_key", "distributed_wages",
                        "source", "grade"],
                       [30, 20, 18, 16, 28], {3}) + 3


# -------------------------------------------------------- auditor's report


def build_auditors_report(*, period: str, out_path: Path, controls: list[dict],
                          asset_control: dict | None, exceptions: list[dict],
                          coverage: dict | None, evidence_coverage: list[dict],
                          rates: list[dict],
                          reconciling_items: list[dict],
                          certification: dict | None = None) -> Path:
    wb = Workbook()
    wb.remove(wb.active)

    # ── Opinion-bearing summary ──────────────────────────────────────
    ws = _sheet(wb, "Report", "Auditor's report",
                "What the engagement asserts, and what proves each assertion.")
    _stamp(ws, period)
    open_controls = [c for c in controls if not c.get("ties")]
    pct = Decimal(str((coverage or {}).get("pct_dollars_covered") or 0))
    r = _caveat(ws, 5, certification_lines(certification))
    r = _caveat(ws, r, [
        ("All cross-reference points tie."
         if not open_controls else
         f"NOT FINAL — {len(open_controls)} cross-reference point(s) open: "
         + ", ".join(c["control"] for c in open_controls)),
        f"Classification is {pct}% complete by dollars. Unclassified cost sits "
        f"in no pool and is never defaulted into one, so any rate below reads "
        f"high while the queue is open — which is the honest direction to err.",
        (f"Asset register: {asset_control.get('state')}"
         + (f" — needs {asset_control.get('needs')}."
            if asset_control.get("needs") else ".")
         ) if asset_control else "",
    ])

    r = _table(ws, r,
               ["Control", "What it proves", "Ledger side", "", "Statement side",
                "", "Variance", "State", "Ties"],
               controls,
               ["control", "description", "left_label", "left_value",
                "right_label", "right_value", "variance", "state", "ties"],
               [24, 50, 24, 16, 24, 16, 16, 12, 10], {4, 6, 7})

    # ── Reconciling items ────────────────────────────────────────────
    ws = _sheet(wb, "Reconciling items", "Differences, named",
                "Each carries the ledger lines it consists of. A deferred "
                "trigger refuses one whose lines do not add to the amount "
                "claimed, which is what separates an item from a plug.")
    _stamp(ws, period)
    _table(ws, 5,
           ["Control", "Ledger puts it in", "The statement puts it in",
            "Amount", "Lines", "Kind", "Recorded by", "Explanation"],
           reconciling_items,
           ["control", "from_account", "to_account", "amount", "lines",
            "kind", "recorded_by", "explanation"],
           [22, 40, 40, 16, 8, 24, 20, 90], {4})

    # ── Evidence ─────────────────────────────────────────────────────
    ws = _sheet(wb, "Evidence", "Documented cost by pool",
                "The proportion of each pool that has a document behind it.")
    _stamp(ws, period)
    _table(ws, 5, ["Pool", "Dollars", "Documented", "% documented"],
           evidence_coverage, ["pool", "dollars", "documented", "pct_documented"],
           [24, 18, 18, 16], {2, 3})

    # ── Exceptions ───────────────────────────────────────────────────
    ws = _sheet(wb, "Exceptions", "Where the standard bent",
                "Every departure, with the reason given at the time. An "
                "exception without a reason is the finding.")
    _stamp(ws, period)
    _table(ws, 5,
           ["Kind", "Subject", "Detail", "Amount", "Reason", "Who", "When"],
           exceptions,
           ["kind", "subject", "detail", "amount", "reason", "actor",
            "occurred_at"],
           [26, 34, 46, 16, 60, 20, 22], {4})

    # ── Rates ────────────────────────────────────────────────────────
    ws = _sheet(wb, "Rates", "Rates on file",
                "Each carries the seal of the decision set it came from. A "
                "database trigger refuses a rate whose seal does not match a "
                "sealed set.")
    _stamp(ws, period)
    last = _table(ws, 5,
                  ["Rate", "Pool", "Base", "Base amount", "Rate", "Status",
                   "Sealed by", "Seal"],
                  rates,
                  ["kind", "pool_amount", "base_type", "base_amount", "rate",
                   "status", "sealed_by", "seal_hash"],
                  [20, 16, 18, 16, 12, 14, 20, 66], {2, 4})
    _as_rate(ws, 6, last, 5)

    wb.save(out_path)
    return out_path


# ------------------------------------------------------------------- 990


def build_form_990(*, period: str, out_path: Path, functions: list[str],
                   categories: list[dict], totals: dict,
                   readiness: dict | None, documents: list[dict],
                   certification: dict | None = None) -> Path:
    wb = Workbook()
    wb.remove(wb.active)

    ws = _sheet(wb, "Part IX", "Statement of Functional Expenses",
                "Form 990 Part IX. Natural category down the side, function "
                "across the top, as the classification queue recorded it.")
    _stamp(ws, period)

    unallocated = Decimal(str((readiness or {}).get("unallocated") or 0))
    r = _caveat(ws, 5, certification_lines(certification))
    if unallocated:
        r = _caveat(ws, r, [
            "NOT FILEABLE — the allocation is incomplete.",
            f"{unallocated:,.2f} of expense has not been classified to a "
            f"function. It appears in its own column and is never spread "
            f"across the three the return prints: an allocation that "
            f"distributes unjudged cost is one nobody can support.",
            "The column totals are therefore short by that amount, on purpose.",
        ])

    # "Not applicable" is printed, not dropped. The handler has always
    # accumulated it and the sheet has never shown it, so a row whose total
    # exceeded its three functions gave the reader nothing to reconcile to —
    # and until `092` that was the entire payroll, $2,191,777.54 of it, on a
    # tax return. A column that is usually zero is cheaper than a total that
    # does not foot.
    headers = ["Natural category", "Lines", "Program", "Management and general",
               "Fundraising", "Not yet classified", "Not applicable", "Total"]
    keys = ["natural_category", "lines", "PROGRAM", "MANAGEMENT_AND_GENERAL",
            "FUNDRAISING", "NOT_YET_CLASSIFIED", "NOT_APPLICABLE", "total"]
    r = _table(ws, r, headers, categories, keys,
               [42, 10, 18, 24, 18, 22, 18, 18], {3, 4, 5, 6, 7, 8})

    r += 1
    ws.cell(row=r, column=1, value="Total").font = BOLD
    for i, key in enumerate(keys[2:], start=3):
        c = ws.cell(row=r, column=i, value=float(totals.get(key) or 0))
        c.font = BOLD
        c.number_format = "#,##0.00"

    # ── Attachments ──────────────────────────────────────────────────
    ws = _sheet(wb, "Attachments", "Documents on file",
                "What the return rests on. A document the register lists but "
                "cannot produce is a citation, not evidence.")
    _stamp(ws, period)
    _table(ws, 5,
           ["Document", "Kind", "Supports", "Received", "From", "Bytes",
            "SHA-256"],
           documents,
           ["filename", "kind", "supports", "received_at", "from_whom",
            "byte_size", "sha256"],
           [52, 26, 12, 22, 24, 14, 66])

    wb.save(out_path)
    return out_path
