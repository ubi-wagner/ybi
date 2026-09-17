#!/usr/bin/env python3
"""Whether every report ties to the financials, as a document.

    DATABASE_URL=... python3 scripts/report_ties.py \
        [--period 2025] [--out docs/REPORT_TIES_2025.md]

The system carries twenty-two control-shaped views and, until `103`, nothing
that collected them — so the question a reviewer actually arrives with had
twenty-two answers on twenty-two screens and **the reader kept the list**.
This is that register on paper, for the reader who is not at a screen.

Everything is read from `v_report_tie`, `v_report_tie_summary` and the two
breakdowns behind the anchors that do not tie. **Nothing here computes a tie**
— every state, variance and sentence is the one the control recorded, because
a figure derived twice is one that can disagree with itself and the workpaper
would carry the version nobody can reproduce.

It writes nothing to the cost record.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query                          # noqa: E402

D = lambda x: Decimal(str(x or 0))                                # noqa: E731

#: The three words the register speaks, as a reader's tick. `NO DATA` gets a
#: mark of its own and never a pass — a control that cannot be evaluated has
#: not passed, and an empty set matching an empty set perfectly is the oldest
#: defect in this file.
MARK = {"TIES": "✓", "OPEN": "△", "NO DATA": "·"}


def money(x) -> str:
    """A blank is a blank. Several anchors are a state with no amount behind
    them, and `0.00` would say the difference is nothing rather than that
    there is no figure to give — which is the distinction the intake keeps
    all the way down."""
    return "—" if x is None else f"{D(x):,.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2025")
    ap.add_argument("--out", default="docs/REPORT_TIES_2025.md")
    a = ap.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    open_pool()

    s = one("""SELECT anchors, ties, open, no_data, state, open_anchors
                 FROM v_report_tie_summary WHERE period = %s""", (a.period,))
    if not s:
        print(f"no period {a.period} on this record", file=sys.stderr)
        return 2
    rows = query("""SELECT seq, report, anchor, ties_to, state, variance, needs
                      FROM v_report_tie WHERE period = %s
                     ORDER BY seq, anchor""", (a.period,))

    out: list[str] = []
    w = out.append
    w(f"# Do the reports tie to the financials? — {a.period}\n")
    w(f"*Generated from the record on "
      f"{datetime.now(timezone.utc):%d %B %Y}. Every row is read from the "
      f"control that already owns its figure; nothing in this document is "
      f"computed.*\n")

    if s["state"] == "TIES":
        w(f"**All {s['anchors']} anchors tie.**\n")
    else:
        w(f"**{s['ties']} of {s['anchors']} anchors tie.** "
          f"{s['open']} outstanding"
          + (f", {s['no_data']} that cannot be evaluated at all — which is "
             "not a pass" if s["no_data"] else "") + ".\n")

    w("| | Report | Anchor | Against | Difference |")
    w("| --- | --- | --- | --- | ---: |")
    for r in rows:
        w(f"| {MARK.get(r['state'], '·')} | {r['report'].replace('_', ' ')} "
          f"| {r['anchor']} | {r['ties_to']} | {money(r['variance'])} |")
    w("")

    outstanding = [r for r in rows if r["state"] != "TIES"]
    if not outstanding:
        w("Nothing is outstanding.\n")
    else:
        w("## What is outstanding\n")
        w("Each one is named to the cent rather than netted away. *A "
          "difference is closed by naming it*, and which of the two records "
          "is right is a judgment with a person's name on it.\n")
        for r in outstanding:
            w(f"### {r['report'].replace('_', ' ')} · {r['anchor']}\n")
            w(f"{r['needs'] or 'No reason recorded.'}\n")
            if r["report"] == "INVENTORY":
                w(_assets(a.period))
            if r["report"] == "INVOICES":
                w(_invoices(a.period))

    Path(a.out).write_text("\n".join(out) + "\n")
    print(f"{a.out} — {s['ties']}/{s['anchors']} tie, state {s['state']}")
    return 0


def _assets(period: str) -> str:
    """Per cost account, because one number for the whole difference is a
    dead end and per class it is four differences with four causes."""
    rows = query("""SELECT gl_account, assets, ledger, register,
                           register_after_period, variance, state
                      FROM v_asset_register_tie
                     WHERE period = %s AND state <> 'NO DATA'
                     ORDER BY gl_account""", (period,))
    if not rows:
        return ""
    out = ["| Cost account | Assets | Ledger | Register | "
           "of which in service after the year end | Difference |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        out.append(f"| {r['gl_account']} | {r['assets']} | "
                   f"{money(r['ledger'])} | {money(r['register'])} | "
                   f"{money(r['register_after_period'])} | "
                   f"{money(r['variance'])} |")
    out.append("")
    out.append("The register on file is the **2026 print** of the schedule, "
               "so it carries assets placed in service after the year end. "
               "That accounts for part of the difference and not all of it; "
               "the rest is four per-class differences somebody has to "
               "attribute, and which of the two records is right is not "
               "something reading the ledger can settle.")
    out.append("")
    return "\n".join(out)


def _invoices(period: str) -> str:
    """Per objective. An objective missing from this table would be a
    difference reported and not attributed, which is a plug with extra steps.

    The grants with no invoice register are shown apart from the ones that do
    not tie, because they are a different fact: nobody has loaded their
    invoices, so there is nothing to compare — and printing the whole of
    MBAC's income as a variance would say YBI over-billed every dollar of it.
    """
    rows = query("""SELECT objective_id, invoices, billed, grant_income,
                           variance, state
                      FROM v_invoice_income_tie
                     WHERE period = %s ORDER BY abs(variance) DESC""",
                 (period,))
    if not rows:
        return ""
    compared = [r for r in rows if r["state"] != "NO REGISTER"]
    absent = [r for r in rows if r["state"] == "NO REGISTER"]

    out = ["| Objective | Invoices | Billed | Grant income recognised | "
           "Difference |", "| --- | ---: | ---: | ---: | ---: |"]
    for r in compared:
        out.append(f"| {r['objective_id']} | {r['invoices']} | "
                   f"{money(r['billed'])} | {money(r['grant_income'])} | "
                   f"{money(r['variance'])} |")
    out.append("")

    if absent:
        total = sum(D(r["grant_income"]) for r in absent)
        out.append(f"And **{len(absent)} grants carry income and no invoice "
                   f"register at all**, {total:,.2f} in total. That is not a "
                   "difference — there is nothing on the other side to "
                   "compare with, and the anchor says so rather than "
                   "reporting the absence of a register as an over-billing "
                   "of every dollar in it.\n")
        out.append("| Grant income account | Recognised |")
        out.append("| --- | ---: |")
        for r in absent:
            out.append(f"| {r['objective_id']} | {money(r['grant_income'])} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
