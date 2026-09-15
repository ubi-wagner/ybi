#!/usr/bin/env python3
"""The 2025 return on the face the 2024 one was filed on.

    DATABASE_URL=... python3 scripts/form_990_replica.py \
        [--period 2025] [--prior 2024] [--out docs/FORM_990_2025_REPLICA.pdf]

Every field of the filed 2024 return, answered for 2025. `form_990_field` is
the register and says where each answer comes from; this reads the record for
the ones the record answers, hands the lot to `domain/form_990_return.py` to
assemble and to `domain/form_990_document.py` to render, and **computes
nothing of its own**.

It writes nothing to the cost record, and the document it produces says on
every page that it is not a filing.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query                          # noqa: E402
from app.domain.form_990_document import (Return, Section,        # noqa: E402
                                          Statement, render)
from app.domain.form_990_return import (Context, Field, assemble, # noqa: E402
                                        carried, outstanding)

D = lambda x: Decimal(str(x or 0))                                # noqa: E731

#: The order the form prints its parts in, and what to call each one.
PARTS = [
    ("HEAD",  "The organisation", ""),
    ("I",     "Part I — Summary", ""),
    ("II",    "Part II — Signature Block",
              "Nothing here is signed. A system that produced a signature "
              "would destroy the only thing a signature is worth."),
    ("III",   "Part III — Statement of Program Service Accomplishments", ""),
    ("IV",    "Part IV — Checklist of Required Schedules", ""),
    ("V",     "Part V — Statements Regarding Other IRS Filings and Tax "
              "Compliance", ""),
    ("VI",    "Part VI — Governance, Management and Disclosure", ""),
    ("VII",   "Part VII — Compensation", ""),
    ("XI",    "Part XI — Reconciliation of Net Assets", ""),
    ("XII",   "Part XII — Financial Statements and Reporting", ""),
    ("SCH_A", "Schedule A — Public Charity Status and Public Support", ""),
    ("SCH_D", "Schedule D — Supplemental Financial Statements", ""),
    ("SCH_F", "Schedule F — Statement of Activities Outside the United "
              "States", ""),
    ("SCH_G", "Schedule G — Fundraising Events", ""),
    ("SCH_I", "Schedule I — Grants to Domestic Organizations", ""),
    ("SCH_J", "Schedule J — Compensation Information", ""),
    ("SCH_O", "Schedule O — Supplemental Information", ""),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2025")
    ap.add_argument("--prior", default="2024")
    ap.add_argument("--out", default="docs/FORM_990_2025_REPLICA.pdf")
    a = ap.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    open_pool()

    ix = {r["line_id"]: r for r in query(
        """SELECT line_id, seq, label, total, program, management,
                  fundraising, not_applicable
             FROM v_form_990_part_ix WHERE period = %s ORDER BY seq""",
        (a.period,))}
    viii = {r["line_id"]: r for r in query(
        """SELECT line_id, seq, label, amount FROM v_form_990_part_viii
            WHERE period = %s ORDER BY seq""", (a.period,))}
    partx = query("""SELECT line_id, seq, side, label, amount
                       FROM v_form_990_part_x WHERE period = %s
                      ORDER BY seq""", (a.period,))
    officers = query("""SELECT seq, name, title, position, employee_key,
                               reportable, other
                          FROM v_form_990_officer WHERE period = %s
                         ORDER BY seq""", (a.period,))

    prior = {r["field_id"]: r["value"] for r in query(
        "SELECT field_id, value FROM form_990_prior_field WHERE period = %s",
        (a.prior,))}
    fields = [Field(r["field_id"], r["part"], r["seq"], r["line_no"],
                    r["label"], r["kind"], r["answer"], r["source"],
                    r["note"], prior.get(r["field_id"], ""))
              for r in query("""SELECT * FROM form_990_field ORDER BY seq""")]

    ctx = Context(
        period=a.period,
        ix={k: {"total": D(v["total"]), "program": D(v["program"]),
                "management": D(v["management"]),
                "fundraising": D(v["fundraising"])} for k, v in ix.items()},
        viii={k: D(v["amount"]) for k, v in viii.items()},
        x={r["line_id"]: D(r["amount"]) for r in partx},
        fn=_computed(a, partx, officers, prior),
    )
    answers = assemble(fields, ctx)
    by_part = {}
    for ans in answers:
        by_part.setdefault(ans.field.part, []).append(ans)

    sections = [Section(key, title, by_part.get(key, []), note)
                for key, title, note in PARTS if by_part.get(key)]

    doc = Return(
        period=a.period,
        organisation=prior.get("H_NAME", "THE YOUNGSTOWN EDISON BUSINESS "
                                         "INCUBATOR"),
        ein=prior.get("H_EIN", ""),
        prior_period=a.prior,
        sections=sections,
        statements=_statements(ix, viii, partx),
        officers=officers,
        outstanding=outstanding(answers),
        carried=carried(answers),
        certification=_band(a, answers),
        controls=_controls(a.period),
    )

    Path(a.out).write_bytes(render(doc))
    print(f"{a.out} — {len(answers)} fields, "
          f"{len(doc.outstanding)} unanswered, {len(doc.carried)} carried")
    return 0


def _computed(a, partx, officers, prior) -> dict:
    """Everything a `fn:` source names. Read, never recalled."""
    x = {r["line_id"]: D(r["amount"]) for r in partx}
    x16 = (sum(D(r["amount"]) for r in partx
               if r["side"] == "ASSET" and r["line_id"] != "X10b")
           - x.get("X10b", Decimal(0)))
    x26 = sum(D(r["amount"]) for r in partx if r["side"] == "LIABILITY")
    x32 = sum(D(r["amount"]) for r in partx if r["side"] == "EQUITY")

    pay = [D(o["reportable"]) for o in officers if o["reportable"] is not None]
    directors = [o for o in officers
                 if o["position"] in ("DIRECTOR", "OFFICER_AND_DIRECTOR")]

    over = one("""SELECT count(*) AS n FROM (
                    SELECT employee_key, max(payroll_wages) AS w
                      FROM labor_allocation WHERE period = %s
                     GROUP BY employee_key) r WHERE r.w >= 100000""",
               (a.period,))["n"]
    top = one("""SELECT COALESCE(max(w), 0) AS w FROM (
                   SELECT max(payroll_wages) AS w FROM labor_allocation
                    WHERE period = %s GROUP BY employee_key) r""",
              (a.period,))["w"]
    employees = one("""SELECT count(DISTINCT employee_key) AS n
                         FROM labor_allocation WHERE period = %s""",
                    (a.period,))["n"]

    payees = query("""SELECT payee, sum(amount) AS amt FROM ledger_line
                       WHERE period = %s AND statement = 'P&L'
                         AND section IN ('Expense', 'COGS') AND payee <> ''
                       GROUP BY payee HAVING sum(amount) >= 100000
                       ORDER BY 2 DESC""", (a.period,))

    grants = query("""SELECT l.payee, sum(l.amount) AS amt
                        FROM ledger_line l
                        JOIN decision_line dl ON dl.line_id = l.line_id
                                             AND dl.live
                        JOIN decision d ON d.decision_id = dl.decision_id
                                        AND d.reversed_at IS NULL
                        JOIN form_990_account_line m
                          ON l.account LIKE m.account_prefix || '%%'
                       WHERE l.period = %s AND m.line_id = '1'
                         AND l.payee <> ''
                       GROUP BY l.payee HAVING sum(l.amount) > 5000
                       ORDER BY 2 DESC""", (a.period,))

    # Net assets at the start of the year are the filed return's own
    # end-of-year figure, which is what the column means — not a second
    # reading of the ledger.
    boy = D((prior.get("P1_22") or "0").replace(",", ""))
    revenue_less = x32 - boy      # what Part XI line 3 plus line 9 must make

    return {
        "tax_year": f"01-01-{a.period} to 12-31-{a.period}",
        "employees": employees,
        "voting_members": len(directors),
        "independent_members": len(directors),
        "officers": f"{len(officers)} persons listed in Section A below",
        "officer_pay": sum(pay, Decimal(0)),
        "over_100k": over,
        "section_4960": "No" if D(top) < 1_000_000 else "Yes",
        "contractors": "; ".join(
            f"{p['payee']} {D(p['amt']):,.2f}" for p in payees)
            or "None above the threshold",
        "contractor_count": len(payees),
        "net_assets_boy": boy,
        "x16": x16, "x26": x26, "x32": x32,
        "schedule_d_vi": (f"Cost {x.get('X10a', 0):,.2f} · accumulated "
                          f"depreciation {x.get('X10b', 0):,.2f} · net "
                          f"{x.get('X10a', 0) - x.get('X10b', 0):,.2f}"),
        "schedule_i": "; ".join(f"{g['payee']} {D(g['amt']):,.2f}"
                                for g in grants) or "None above $5,000",
        "schedule_i_count": len(grants),
        "schedule_j": f"{len([o for o in officers if o['reportable']])} "
                      f"person(s) with reportable compensation",
        "_revenue_less": revenue_less,
    }


def _statements(ix, viii, partx) -> list:
    netted = D(ix.get("8b", {}).get("total"))
    ix_rows = [(f"{r['line_id']}  {r['label']}",
                [D(r["total"]), D(r["program"]), D(r["management"]),
                 D(r["fundraising"])])
               for r in sorted(ix.values(), key=lambda r: r["seq"])
               if r["line_id"] != "8b"]
    ix_total = [sum(D(r["total"]) for r in ix.values()
                    if r["line_id"] != "8b"),
                sum(D(r["program"]) for r in ix.values()
                    if r["line_id"] != "8b"),
                sum(D(r["management"]) for r in ix.values()
                    if r["line_id"] != "8b"),
                sum(D(r["fundraising"]) for r in ix.values()
                    if r["line_id"] != "8b")]

    viii_rows = [(f"{r['line_id']}  {r['label']}", [D(r["amount"])])
                 for r in sorted(viii.values(), key=lambda r: r["seq"])]
    viii_rows.append((f"less 8b  direct expenses of fundraising events, "
                      f"netted here and excluded from Part IX", [-netted]))
    viii_total = sum(D(r["amount"]) for r in viii.values()) - netted

    x_rows = [(f"{r['line_id'][1:]}  {r['label']}", [D(r["amount"])])
              for r in partx]
    x16 = (sum(D(r["amount"]) for r in partx
               if r["side"] == "ASSET" and r["line_id"] != "X10b")
           - D(next((r["amount"] for r in partx
                     if r["line_id"] == "X10b"), 0)))
    x26 = sum(D(r["amount"]) for r in partx if r["side"] == "LIABILITY")
    x32 = sum(D(r["amount"]) for r in partx if r["side"] == "EQUITY")

    return [
        Statement("Part VIII — Statement of Revenue", ["(A) Total"],
                  viii_rows, ("12  Total revenue", [viii_total]),
                  "Line 8b is the direct expenses of the fundraising event. "
                  "The form nets it here and excludes it from Part IX, so it "
                  "appears once and in one place."),
        Statement("Part IX — Statement of Functional Expenses",
                  ["(A) Total", "(B) Program", "(C) Management",
                   "(D) Fundraising"],
                  ix_rows, ("25  Total functional expenses", ix_total),
                  "Cost nobody has judged is never spread across the three "
                  "functions; the columns are short by that amount on purpose "
                  "until the queue is empty."),
        Statement("Part X — Balance Sheet", ["End of year"], x_rows,
                  ("16 / 26 / 32  Assets · liabilities · net assets",
                   [x16]),
                  f"Total assets {x16:,.2f} against liabilities {x26:,.2f} "
                  f"and net assets {x32:,.2f}."),
    ]


def _band(a, answers) -> list:
    asked = len([x for x in answers if x.field.answer == "ask"])
    carr = len([x for x in answers if x.field.answer == "carried"])
    read = len(answers) - asked - carr
    return [
        f"Prepared from the {a.period} cost record on the face of the filed "
        f"{a.prior} return. It is a working paper for the preparer, not a "
        f"return: nothing here is signed and nothing has been submitted.",
        f"{len(answers)} fields — {read} read from the record or referenced "
        f"from another line of this return, {carr} carried from the {a.prior} "
        f"filing and marked for confirmation, {asked} that nobody has "
        f"answered for {a.period} and that print what they need instead.",
        "A carried answer is last year's, not this year's. The organisation "
        "instructed that the officers and directors are unchanged; every "
        "other carried field is one somebody still has to confirm.",
    ]


def _controls(period: str) -> list:
    # Written out rather than looped over a relation name: `test_sql_is_real`
    # hands every literal statement to PREPARE, and an interpolated table is
    # one it cannot check. Six statements the schema had never seen is what a
    # clever helper cost once already.
    return [(r["anchor"], r["state"], r["needs"] or "") for r in query(
        """SELECT anchor, state, needs FROM v_report_tie
            WHERE period = %s
              AND (report = 'FORM_990'
                   OR anchor = 'The eleven cross-reference points')
            ORDER BY seq""", (period,))]


if __name__ == "__main__":
    raise SystemExit(main())
