#!/usr/bin/env python3
"""The invoice register, tied forward and backward against everything else.

    PYTHONPATH=. python3 scripts/drive_invoice_ties.py

The register held three invoices from one month and nothing could be tied to
it. It holds the year now, so the ties can be made — and the ones that cannot
be made are worth more than the ones that can, because each names a specific
thing the record does not carry.

**Forward** is the chain a reviewer walks with the paperwork in front of them:
the invoice foots to its own lines, the year's invoices foot to the ledger's
grant income, and the billed categories meet the cost classified underneath.

**Backward** is the same chain from the other end: a classified ledger line
reaches its objective, its award, and the invoices issued against it.

**Period discipline.** Three invoices carry `period = '2025'` and an invoice
date in **April 2026** — `load_invoices.py` wrote the period as a constant.
Any 2025 tie that includes them is comparing thirteen months to twelve, so
every comparison below filters on the invoice *date*, not the period column.
It is worth 19,145.79 of Drive AM ODCs on its own.

It writes nothing.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query  # noqa: E402

PERIOD = "2025"
CENT = Decimal("0.01")
FINDINGS: list[str] = []
NOTES: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok       {msg}")


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}")


def note(msg: str) -> None:
    """Neither a pass nor a fault: something the record cannot answer."""
    NOTES.append(msg)
    print(f"  note     {msg}")


#: award -> the ledger accounts that carry its income and its non-labour cost.
#: Read rather than inferred: the 2025 chart buries programme identity in the
#: account name, which is the structural defect the 2026 chart fixes.
AWARDS = {
    "DRIVE-AM":  ("%Grant Income:Drive AM%", "%Grant Expenses:Drive AM%"),
    "LTM":       ("%Grant Income:Last Tactical Mile%", "%Grant Expenses:LTM Grant%"),
    "DIG-ENG":   ("%Grant Income:Digital Engineering%", "%Grant Expenses:Digital Engineering%"),
    "HYBRID-II": ("%Grant Income:Hybrid Energy%", "%Grant Expenses:DOE Hybrid%"),
}

#: Differences already established, with what each is. A gap that is not here
#: is a finding; a gap that is here and has moved is also a finding.
DECLARED = {
    ("HYBRID-II", "income"): (Decimal("4222.00"),
        "Oct-Dec on the ledger with no invoice — the tail after billing stopped"),
    ("RISING-TIDES", "income"): (Decimal("-132803.04"),
        "86,281.30 is the 2024 portion, named on the January invoice; the rest "
        "is accrual timing across Jan-May"),
    ("DRIVE-AM", "cost"): (Decimal("-92876.19"),
        "billed in ODCs above the cost classified to Drive AM. Either the "
        "classification under-attributes or the billing over-claimed, and it "
        "is the open question under the largest credit in the restatement"),
    ("LTM", "cost"): (Decimal("32484.07"),
        "cost incurred and never billed — including a 19,500.00 'UNI Q3-Q4 "
        "2025' line with no payee. Unbilled cost, which runs in YBI's favour"),
}

#: A tie that cannot be made, and why. Digital Engineering bills one
#: undifferentiated line a month — "YBI Total: January 2025" — so labour and
#: non-labour are not separable on the face of the document. Comparing its
#: whole invoice to the ledger's non-labour would report a 409,099.24 failure
#: on a document that simply does not carry the split. A control that cannot
#: be evaluated has not passed, and it has not failed either.
NOT_EVALUABLE = {
    ("DIG-ENG", "cost"):
        "its invoices carry a single undifferentiated monthly line, so the "
        "billing does not separate labour from non-labour",
}


def ledger(pattern: str, section: str) -> Decimal:
    return query("""SELECT COALESCE(sum(amount), 0) AS a FROM ledger_line
                     WHERE period = %s AND section = %s AND account LIKE %s""",
                 (PERIOD, section, pattern))[0]["a"]


def main() -> int:
    open_pool()
    print(f"Invoice register — tied both ways, {PERIOD}\n")

    # ── 0 · the register is the right size, and dated in the right year ────
    print("0 · What is on the register")
    rows = query("""SELECT count(*) AS n,
                           count(*) FILTER (WHERE extract(year from invoice_date) = 2025) AS y25,
                           count(*) FILTER (WHERE extract(year from invoice_date) <> 2025) AS other,
                           sum(total) AS total
                      FROM invoice WHERE period = %s""", (PERIOD,))[0]
    print(f"           {rows['n']} invoices on period {PERIOD}, "
          f"{rows['y25']} dated 2025 and {rows['other']} not, "
          f"{rows['total']:,.2f} in total")
    if rows["other"]:
        note(f"{rows['other']} invoice(s) carry period '{PERIOD}' and a date "
             f"outside it. Every tie below filters on the date; a figure that "
             f"filtered on the period column would be comparing more than a "
             f"year to a year.")

    # ── 1 · every invoice foots to its own lines ───────────────────────────
    print("\n1 · Forward: each invoice foots to its own lines")
    bad = query("""
        SELECT i.invoice_number, i.total, COALESCE(sum(l.amount), 0) AS lines
          FROM invoice i LEFT JOIN invoice_line l USING (invoice_id)
         WHERE i.period = %s
         GROUP BY i.invoice_id, i.invoice_number, i.total
        HAVING count(l.*) > 0 AND abs(i.total - COALESCE(sum(l.amount), 0)) > 0.01""",
        (PERIOD,))
    if bad:
        for b in bad:
            finding(f"invoice {b['invoice_number']} states {b['total']:,.2f} "
                    f"and its lines total {b['lines']:,.2f}")
    else:
        n = query("SELECT count(*) AS n FROM invoice WHERE period = %s", (PERIOD,))[0]["n"]
        ok(f"all {n} invoices foot to their lines")

    # ── 2 · the header's indirect is the lines' indirect ───────────────────
    print("\n2 · Forward: the indirect claimed is the indirect billed")
    bad = query("""
        SELECT i.invoice_number, i.indirect_claimed,
               COALESCE(sum(l.amount) FILTER (WHERE l.category = 'INDIRECT'), 0) AS li
          FROM invoice i LEFT JOIN invoice_line l USING (invoice_id)
         WHERE i.period = %s
         GROUP BY i.invoice_id, i.invoice_number, i.indirect_claimed
        HAVING abs(i.indirect_claimed -
               COALESCE(sum(l.amount) FILTER (WHERE l.category='INDIRECT'), 0)) > 0.01""",
        (PERIOD,))
    if bad:
        for b in bad:
            finding(f"invoice {b['invoice_number']} claims indirect "
                    f"{b['indirect_claimed']:,.2f} against lines of {b['li']:,.2f}")
    else:
        ok("every header's indirect equals its INDIRECT lines")

    # ── 3 · the year's invoices against the ledger's income ────────────────
    print("\n3 · Forward: a year of invoices against the ledger's grant income")
    streams = dict(AWARDS)
    streams["AAMEN"] = ("%Grant Income:AAMEN%", None)
    streams["RISING-TIDES"] = ("%Grant Income:Rising Tides%", None)
    for obj, (income_acct, _) in streams.items():
        billed = query("""SELECT COALESCE(sum(total), 0) AS a FROM invoice
                           WHERE objective_id = %s
                             AND extract(year from invoice_date) = 2025""",
                       (obj,))[0]["a"]
        led = ledger(income_acct, "Income")
        gap = (led - billed).quantize(CENT)
        expected, why = DECLARED.get((obj, "income"), (Decimal("0.00"), ""))
        if gap == expected and gap == 0:
            ok(f"{obj:<13} {billed:>13,.2f} = the ledger, to the cent")
        elif gap == expected:
            ok(f"{obj:<13} {billed:>13,.2f}, ledger {led:,.2f}, "
               f"difference {gap:,.2f} — {why}")
        else:
            finding(f"{obj}: invoices {billed:,.2f} against the ledger's "
                    f"{led:,.2f}, a difference of {gap:,.2f} where "
                    f"{expected:,.2f} was established")

    # ── 4 · billed non-labour against the cost classified underneath ───────
    print("\n4 · Forward: billed non-labour against the cost the ledger carries")
    print("           (labour is NOT compared — billed labour is burdened and")
    print("            the ledger's wage accounts are not split by contract)")
    for obj, (_, expense_acct) in AWARDS.items():
        if (obj, "cost") in NOT_EVALUABLE:
            note(f"{obj:<13} NOT EVALUABLE — {NOT_EVALUABLE[(obj, 'cost')]}")
            continue
        cats = query("""
            SELECT l.category, sum(l.amount) AS a
              FROM invoice i JOIN invoice_line l USING (invoice_id)
             WHERE i.objective_id = %s AND extract(year from i.invoice_date) = 2025
               AND l.category IN ('TRAVEL','MATERIALS','CONSULTANT','ODC',
                                  'SUBAWARD','EQUIPMENT','OTHER')
             GROUP BY 1""", (obj,))
        billed = sum(c["a"] for c in cats)
        cost = ledger(expense_acct, "Expense")
        gap = (cost - billed).quantize(CENT)
        shape = ", ".join(f"{c['category']} {c['a']:,.2f}" for c in sorted(
            cats, key=lambda x: -abs(x["a"])) if c["a"])
        expected, why = DECLARED.get((obj, "cost"), (Decimal("0.00"), ""))
        if gap == 0:
            ok(f"{obj:<13} non-labour billed {billed:>12,.2f} = the ledger's "
               f"grant expense, to the cent  [{shape}]")
        elif gap == expected:
            ok(f"{obj:<13} non-labour billed {billed:>12,.2f}, ledger "
               f"{cost:,.2f}, difference {gap:,.2f} — {why}")
        else:
            finding(f"{obj}: non-labour billed {billed:,.2f} against "
                    f"{cost:,.2f} of grant expense — {gap:,.2f} where "
                    f"{expected:,.2f} was established. [{shape}]")

    # ── 5 · backward: a classified line reaches the invoices over it ───────
    print("\n5 · Backward: from classified cost to the invoices issued on it")
    for obj in AWARDS:
        row = query("""
            SELECT count(DISTINCT l.line_id) AS lines, COALESCE(sum(l.amount),0) AS cost
              FROM decision d
              JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
              JOIN ledger_line l ON l.line_id = dl.line_id
             WHERE d.reversed_at IS NULL AND d.objective_id = %s
               AND d.pool = 'DIRECT'""", (obj,))[0]
        inv = query("""SELECT count(*) AS n, COALESCE(sum(total),0) AS t
                         FROM invoice WHERE objective_id = %s
                          AND extract(year from invoice_date) = 2025""", (obj,))[0]
        award = query("""SELECT award_id, ceiling_federal FROM award
                          WHERE objective_id = %s""", (obj,))
        if not award:
            finding(f"{obj}: classified cost reaches no award row")
            continue
        if not inv["n"]:
            finding(f"{obj}: {row['cost']:,.2f} of direct cost and no 2025 invoice")
            continue
        ok(f"{obj:<13} {row['lines']:>3} classified lines "
           f"({row['cost']:>12,.2f}) -> {award[0]['award_id']:<15} -> "
           f"{inv['n']:>2} invoices ({inv['t']:,.2f})")

    # ── 6 · backward: every invoice reaches an objective and an award ──────
    print("\n6 · Backward: every invoice reaches an objective, and a real one")
    orphan = query("""SELECT invoice_number, objective_id, award_id FROM invoice
                       WHERE period = %s AND objective_id IS NULL""", (PERIOD,))
    for o in orphan:
        note(f"invoice {o['invoice_number']} names no cost objective")
    unlinked = query("""
        SELECT i.objective_id, count(*) AS n FROM invoice i
         WHERE i.period = %s AND i.objective_id IS NOT NULL AND i.award_id IS NULL
         GROUP BY 1 ORDER BY 1""", (PERIOD,))
    for u in unlinked:
        note(f"{u['n']} invoice(s) on {u['objective_id']} carry no award — "
             f"the schema allows it, and an award register that has not caught "
             f"up is not a reason to hold evidence out")
    if not orphan and not unlinked:
        ok("every invoice reaches an objective and an award")

    # ── 7 · nothing upstream moved ─────────────────────────────────────────
    print("\n7 · The register changed nothing upstream of it")
    ctl = query("""SELECT count(*) FILTER (WHERE state='TIES') AS t, count(*) AS n
                     FROM v_statement_reconciliation WHERE period = %s""", (PERIOD,))[0]
    anc = query("""SELECT count(*) FILTER (WHERE state='TIES') AS t, count(*) AS n
                     FROM v_rate_anchor WHERE period = %s""", (PERIOD,))[0]
    pool = query("""SELECT count(*) FILTER (WHERE pool_variance = 0) AS t, count(*) AS n
                      FROM v_rate_buildup WHERE period=%s AND status='PROPOSED'""",
                 (PERIOD,))[0]
    cov = query("SELECT * FROM v_classification_coverage WHERE period=%s", (PERIOD,))[0]
    for label, got, want in (("statement controls", ctl["t"], ctl["n"]),
                             ("rate anchors", anc["t"], anc["n"]),
                             ("pools at variance 0.00", pool["t"], pool["n"])):
        (ok if got == want else finding)(f"{label}: {got} of {want}")
    (ok if cov["unclassified"] == 0 else finding)(
        f"coverage {cov['pct_dollars_covered']}%, unclassified "
        f"{cov['unclassified']:,.2f}")

    print()
    if FINDINGS:
        print(f"{len(FINDINGS)} finding(s), {len(NOTES)} note(s)")
        return 1
    print(f"the register ties both ways — {len(NOTES)} note(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
