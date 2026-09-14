#!/usr/bin/env python3
"""Load YBI's own working calendar and the hours log behind the distribution.

    python3 scripts/load_calendar.py [path-to-workbook]

Two sheets of the controller's grant reconciliation workbook that nothing had
ever read, and between them they answer a question this system had been
guessing at:

  **`Hours available`** is the calendar — a *Work Days* row and an *Hours Per
  Month* row, by month, October 2023 to July 2026. The adopt route had been
  deriving United States federal holidays to work out which days somebody was
  working; YBI counts **261 days and 2,088 hours in 2025**, every weekday with
  nothing deducted. A calendar is an organisational fact, not a rule, and this
  one was on file the whole time.

  **`Hours Log`** is the timesheet as kept: a person, a month, hours by
  objective, `TS Hours` as logged, `Allow Hours` as the month's capacity and
  an `Adj-` set normalising one to the other. `labor_allocation` — the
  distribution the entire rate model rests on — was built from these, and only
  the finished wage figures were loaded.

Neither changes a rate. They are the evidence underneath one.

Re-runnable: both tables are keyed on what they describe and upserted, so a
second run reloads rather than duplicating.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, one, open_pool, query           # noqa: E402

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

SOURCE = Path("docs/source-documents/accounting-records/"
              "2025_Grant-Reconciliation-Workbook_controller.xlsx")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}

BOLD, DIM, OK, WARN, FAIL, END = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")


def cells(path: Path, sheet: str) -> dict[int, dict[str, str]]:
    """Every non-empty cell of a sheet, as {row: {column: text}}.

    Read straight from the XML rather than through a library, the way every
    other loader here does — the workbook is the record and a dependency
    that reinterprets it is one more thing between the two.
    """
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in
            ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    target = None
    for sh in wb.find(NS + "sheets"):
        if sh.get("name") == sheet:
            target = rels[sh.get(NSR + "id")]
    if target is None:
        raise LookupError(f"no sheet named {sheet!r} in {path.name}")
    name = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
    rows: dict[int, dict[str, str]] = {}
    for row in ET.fromstring(z.read(name)).iter(NS + "row"):
        r, out = int(row.get("r")), {}
        for c in row.iter(NS + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            t, v = c.get("t"), c.find(NS + "v")
            if t == "s" and v is not None:
                out[col] = shared[int(v.text)]
            elif t == "inlineStr":
                out[col] = "".join(x.text or "" for x in c.iter(NS + "t"))
            elif v is not None:
                out[col] = v.text
        if out:
            rows[r] = out
    return rows


def num(row: dict, col: str) -> Decimal:
    """A cell as a number, or zero. A blank and a zero are the same thing in
    an hours column — nobody writes 0.00 for an objective they did not touch."""
    try:
        return Decimal(str(row.get(col) or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(0)


def load_calendar(rows: dict, period: str, source: str) -> tuple[int, int]:
    """The `Hours available` sheet: a year marker row, a month row, and the
    two figures under each."""
    years, months = rows.get(1, {}), rows.get(2, {})
    days, hours = rows.get(3, {}), rows.get(4, {})
    # The year is printed once, on the column its January falls in, so it is
    # carried forward across the row rather than looked up per column.
    year, loaded, skipped = None, 0, 0
    for col in sorted(months, key=lambda c: (len(c), c)):
        if col in years:
            year = years[col]
        month = months.get(col, "").strip()
        if not year or month not in MONTHS:
            continue
        if str(year) != period:
            skipped += 1
            continue
        if col not in days or col not in hours:
            continue          # 2026 is printed to July and blank after it
        execute("""INSERT INTO work_month (period, month_start, work_days,
                                           available_hours, source_document,
                                           loaded_by)
                   VALUES (%s,%s,%s,%s,%s,'load_calendar.py')
                   ON CONFLICT (period, month_start) DO UPDATE
                     SET work_days = EXCLUDED.work_days,
                         available_hours = EXCLUDED.available_hours,
                         source_document = EXCLUDED.source_document,
                         loaded_at = now()""",
                (period, date(int(year), MONTHS[month], 1),
                 int(float(days[col])), Decimal(str(hours[col])), source))
        loaded += 1
    return loaded, skipped


def load_hours(rows: dict, period: str, source: str):
    """The `Hours Log` sheet. Columns are found by their heading, never by
    position: somebody will insert one, and reading by position turns that
    into silently wrong data in every column to the right.

    **Thirty-six of the forty-five people carry a single row labelled
    December**, sitting in a block at the bottom of the sheet, with
    `Allow Hours` equal to `TS Hours` — and for thirty of them the figure is
    a round 100. That is a summary line, not a December: loading it would
    assert those people worked 100 hours in December and nothing in the
    other eleven months. A person with one row has no monthly record, and
    saying so is worth more than a number.
    """
    header = rows[1]
    skip = {"Name", "Month", "Year", "Hourly Rate", "Fringe Rate", "FB Rate",
            "TS Hours", "Allow Hours", "Variance", "ADJ TS Hours"}
    logged = {c: h for c, h in header.items()
              if h and h not in skip
              and not h.startswith(("Adj-", "X-", "X="))}
    adjusted = {c: h[4:] for c, h in header.items() if h.startswith("Adj-")}
    by_label = {r["source_label"]: r["objective_id"]
                for r in query("SELECT source_label, objective_id "
                               "FROM labor_objective_map")}
    unmapped: set[str] = set()

    # Which people have a month-by-month record at all, decided before
    # anything is written. One row cannot be a monthly record of a year,
    # whatever month it is labelled with.
    months_of: dict[str, set] = {}
    for i in sorted(rows):
        if i == 1:
            continue
        row = rows[i]
        name, month, year = (row.get("A") or "").strip(), row.get("B"), row.get("C")
        if name and str(year) == period and month in MONTHS:
            months_of.setdefault(name.upper(), set()).add(month)
    monthly = {k for k, ms in months_of.items() if len(ms) > 1}
    summary = sorted(k for k, ms in months_of.items() if len(ms) == 1)

    written = 0
    for i in sorted(rows):
        if i == 1:
            continue
        row = rows[i]
        name, month, year = (row.get("A") or "").strip(), row.get("B"), row.get("C")
        if not name or str(year) != period or month not in MONTHS:
            continue
        key = name.upper()
        if key not in monthly:
            continue
        month_start = date(int(year), MONTHS[month], 1)
        # Every objective named in either half of the row, so one with
        # logged hours and no adjustment still lands, and one adjusted from
        # nothing does too.
        combined: dict[str, list] = {}
        for col, label in logged.items():
            v = num(row, col)
            if v:
                combined.setdefault(label, [Decimal(0), Decimal(0)])[0] = v
        for col, label in adjusted.items():
            v = num(row, col)
            if v:
                combined.setdefault(label, [Decimal(0), Decimal(0)])[1] = v
        for label, (lg, adj) in combined.items():
            # `Xjet (AM-O)` logged against `Adj-Xjet` adjusted: the
            # parenthetical says which pool it rolls up into, not what the
            # objective is, so it is not part of the name to match on.
            objective = by_label.get(label) or by_label.get(
                re.sub(r"\s*\([^)]*\)\s*$", "", label).strip())
            if objective is None:
                unmapped.add(label)
                continue
            execute("""INSERT INTO labor_month
                         (period, employee_key, month_start, objective_id,
                          logged_hours, adjusted_hours, source_document,
                          source_label, loaded_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'load_calendar.py')
                       ON CONFLICT (period, employee_key, month_start,
                                    objective_id) DO UPDATE
                         SET logged_hours = EXCLUDED.logged_hours,
                             adjusted_hours = EXCLUDED.adjusted_hours,
                             loaded_at = now()""",
                    (period, key, month_start, objective, lg, adj, source, label))
            written += 1
    return written, sorted(monthly), summary, sorted(unmapped)


#: Who in the hours log is paid as which ledger payee.
#:
#: **A contractor is paid as a company, so a search for their name finds
#: nothing.** `v_labor_hours_check` reported Tom Metzinger as HOURS WITHOUT
#: WAGES — 781 hours across twelve months, no payroll row, and no payment to
#: "Metzinger" anywhere in the general ledger. He is 1099, and the expense is
#: `5202 Accounting` / `Metz Consulting, LLC.`, $73,024.44. The link took a
#: trip through a spreadsheet to find; it is a fact, so it is written down.
CONTRACTORS = [
    ("METZINGER", "Metz Consulting, LLC.", "W9_1099",
     "Fractional controller on a semi-monthly retainer, 1099. The hours log "
     "carries him below the payroll block of the Time Breakdown sheet, "
     "headed 5202 Accounting, at $72,375 — the ledger's $73,024.44 less one "
     "December payment still at the old $3,000 rate ($375) and $274.44 of "
     "1099 filing fees."),
]


def load_contractors(period: str) -> tuple[int, list[str]]:
    """Record who is paid as whom, and report a link with no ledger behind it.

    A payee that matches nothing is not written: an identity pointing at no
    money is the citation-with-no-document shape, and it would report a
    contractor as unclassified for ever.
    """
    written, missing = 0, []
    for key, payee, basis, note in CONTRACTORS:
        hit = one("""SELECT count(*) AS n FROM ledger_line
                      WHERE period = %s AND payee = %s""", (period, payee))
        if not hit or not hit["n"]:
            missing.append(f"{key} -> {payee}")
            continue
        execute("""INSERT INTO contractor_identity
                     (period, employee_key, payee, basis, note, recorded_by)
                   VALUES (%s,%s,%s,%s,%s,'load_calendar.py')
                   ON CONFLICT (period, employee_key, payee) DO UPDATE
                     SET basis = EXCLUDED.basis, note = EXCLUDED.note""",
                (period, key, payee, basis, note))
        written += 1
    return written, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=str(SOURCE))
    ap.add_argument("--period", default="2025")
    a = ap.parse_args()

    path = Path(a.path)
    if not path.exists():
        print(f"{path} not found", file=sys.stderr)
        return 2

    open_pool()
    months, _ = load_calendar(cells(path, "Hours available"), a.period, path.name)
    rows, monthly, summary, unmapped = load_hours(
        cells(path, "Hours Log"), a.period, path.name)

    cal = one("""SELECT count(*) AS months, sum(work_days) AS days,
                        sum(available_hours) AS hours
                   FROM work_month WHERE period = %s""", (a.period,))
    print(f"  calendar   {cal['months']} month(s), {cal['days']} work days, "
          f"{cal['hours']:,} hours")
    print(f"  hours log  {rows} row(s) for {len(monthly)} people with a "
          f"month-by-month record")
    if summary:
        print(f"  {WARN}{len(summary)} people carry one summary row and no "
              f"monthly record — their hours cannot be placed in a month:{END}")
        print(f"     {DIM}{', '.join(summary)}{END}")
    if unmapped:
        print(f"  {WARN}unmapped objective(s): {', '.join(unmapped)}{END}")

    linked, missing = load_contractors(a.period)
    if linked or missing:
        print(f"  contractors {linked} identity(ies) recorded")
        for m in missing:
            print(f"     {WARN}no ledger lines for {m} — not recorded{END}")
    for r in query("""SELECT employee_key, payee, account, expense, pools,
                             project_pct, at_stake, objectives, state
                        FROM v_contractor_effort_check
                       WHERE period = %s
                       ORDER BY employee_key, expense DESC""", (a.period,)):
        mark = {"OPEN": WARN, "TIES": OK}.get(r["state"], DIM)
        leaf = r["account"].split(":")[-1]
        print(f"     {mark}{r['state']:<14}{END} {leaf:<34} "
              f"${r['expense']:>10,} {r['pools'] or '—'}")
        if r["state"] == "OPEN":
            print(f"       {DIM}{r['project_pct']}% of {r['employee_key']}'s "
                  f"hours are on {r['objectives']} — ${r['at_stake']:,} of "
                  f"this group. 2 CFR 200.413(c) decides it, not "
                  f"arithmetic.{END}")

    off = query("""SELECT month_label, says, weekdays, difference
                     FROM v_work_calendar_check
                    WHERE period = %s AND state = 'OPEN'
                    ORDER BY month_start""", (a.period,))
    if off:
        print(f"  {WARN}{len(off)} month(s) where their calendar is not the "
              f"weekday count — a fact about the organisation, not a "
              f"defect:{END}")
        for m in off:
            print(f"     {m['month_label']}: says {m['says']}, "
                  f"{m['weekdays']} weekdays ({m['difference']:+})")
    else:
        print(f"  {OK}every month ties to its weekday count{END}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
