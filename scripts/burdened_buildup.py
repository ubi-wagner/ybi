#!/usr/bin/env python3
"""The 2025 NCDMM invoices, fully burdened on the costs they carry.

**This is not the restatement, and the difference is the whole exercise.**

`POST /api/restate` rebuilds an invoice from the *cost record* — the labour
distribution's wages, the ledger's DIRECT classifications — and asks what the
year supports. That is the right question for a claim, and it is the wrong
question for *what should this invoice have been*, because the cost record
under-attributes these awards. Drive AM's invoices carry $274,757.07 of
non-labour against $181,880.88 the ledger classifies to it: a gap of
$92,876.19, every dollar of it billed at **zero indirect**, worth $115,825.90
once burdened. Rebuilding from the ledger throws that away twice over.

So this takes the cost elements **on the face of the invoices YBI issued** and
runs the whole structure up them — fringe on labour, then overhead and G&A as
separate lines on the MTDC those costs form. It is the answer to the thing the
engagement has said from the beginning: *no America Makes award budgets
meaningful indirect, and that is the recovery the restatement exists to go
after.* The recurring value is indirect on non-labour, which a loaded labour
rate cannot reach at all.

Nothing here is written to any register. It is an exercise and a check on the
rate structure, not a claim.

Two readings of the labour line, printed side by side
─────────────────────────────────────────────────────

The one genuine fork, and it is worth six figures, so it is not decided here.

  AS INVOICED   the labour on the face is direct cost and carries full
                burden. Drive AM bills $304,483.80.
  AT COST       the labour on the face is a loaded rate that already holds
                indirect, so it comes down to the reconstruction's wages plus
                fringe before anything goes on top. Drive AM is $179,571.00.

The ratio between them is 1.70x on Drive AM and 2.25x on Hybrid, against a
full burden of about 1.5x — which reads as a loaded rate. But the labour
distribution is a **management reconstruction**, and if it under-attributes
labour the way it demonstrably under-attributes non-labour, then that ratio is
an artefact of incomplete attribution rather than evidence of loading. Both
are printed; neither is asserted.

What MTDC takes, per 2 CFR 200.1
────────────────────────────────

    LABOR FRINGE TRAVEL MATERIALS CONSULTANT ODC     in full
    SUBAWARD                                        the first $25,000 of each
    EQUIPMENT FEE INDIRECT                          out

`CONSULTANT` is in full because 200.331 makes these contractors rather than
subrecipients — they deliver into YBI's own programme against YBI's scope.
`OTHER` is counted and **flagged**: a category that says nothing about what it
holds cannot be tested against an exclusion, and Digital Engineering is
$579,074.25 of it.

    python scripts/burdened_buildup.py                 # the certified rate
    python scripts/burdened_buildup.py --anticipated   # the measured estate
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query, one  # noqa: E402

PERIOD = "2025"

#: The four awards NCDMM administers. Digital Engineering's prime is
#: N00174-20-1-0031 through Energetics and NSWC Indian Head rather than the
#: AFRL America Makes cooperative agreement, and it is marked so.
AWARDS = [
    ("DRIVE-AM",  "Drive AM",            "FA8650-20-2-5700"),
    ("LTM",       "Last Tactical Mile",  "FA8650-20-2-5700"),
    ("HYBRID-II", "Hybrid Phase 2",      "AFRL FA8650-20-2-5700"),
    ("DIG-ENG",   "Digital Engineering", "N00174-20-1-0031"),
]

#: In the base in full.
IN_MTDC = ("LABOR", "FRINGE", "TRAVEL", "MATERIALS", "CONSULTANT", "ODC")
#: Out of the base: capital expenditure, a fee is not a cost, and an indirect
#: line is not a direct cost to take indirect on.
OUT_OF_MTDC = ("EQUIPMENT", "FEE", "INDIRECT")
#: 200.1 takes the first $25,000 of each subaward and no more.
SUBAWARD_CAP = D("25000")
#: Counted, and said out loud rather than assumed either way.
UNTESTABLE = ("OTHER",)

ORDER = ["LABOR", "FRINGE", "CONSULTANT", "SUBAWARD", "TRAVEL", "MATERIALS",
         "ODC", "OTHER", "EQUIPMENT", "FEE", "INDIRECT"]

#: What each category is called on the page. `.title()` renders ODC as "Odc"
#: and G&A as "G&A" only by luck; a document a payables clerk reads should
#: carry the words the invoice does.
LABEL = {"LABOR": "Direct labour", "FRINGE": "Fringe", "CONSULTANT": "Consultant",
         "SUBAWARD": "Subaward", "TRAVEL": "Travel", "MATERIALS": "Materials",
         "ODC": "Other direct costs", "OTHER": "Other (uncategorised)",
         "EQUIPMENT": "Equipment", "FEE": "Fee", "INDIRECT": "Indirect"}


def money(x) -> D:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def rates(anticipated: bool) -> dict:
    """The structure on the record. Read, never recalled."""
    rows = query("""SELECT kind, rate FROM rate
                     WHERE period = %s AND status <> 'SUPERSEDED'""", (PERIOD,))
    if not rows:
        raise SystemExit("No rate stands on the record. Compute one first.")
    r = {x["kind"]: D(str(x["rate"])) for x in rows}
    for k in ("FRINGE", "OVERHEAD", "G&A"):
        if k not in r:
            raise SystemExit(f"The record carries no {k} rate.")
    return r


def billed(objective: str) -> tuple[dict, list]:
    """Every 2025 invoice on an objective, by category, off the register."""
    per_invoice, totals = [], defaultdict(lambda: D("0.00"))
    for h in query("""SELECT invoice_id, invoice_number, invoice_date, total
                        FROM invoice
                       WHERE period = %s AND objective_id = %s
                         AND status <> 'WITHDRAWN'
                       ORDER BY invoice_date, invoice_number""",
                   (PERIOD, objective)):
        cats = defaultdict(lambda: D("0.00"))
        for l in query("""SELECT category::text AS c, amount
                            FROM invoice_line WHERE invoice_id = %s""",
                       (h["invoice_id"],)):
            cats[l["c"]] += money(l["amount"])
            totals[l["c"]] += money(l["amount"])
        per_invoice.append(dict(number=h["invoice_number"],
                                date=h["invoice_date"],
                                total=money(h["total"] or 0),
                                cats=dict(cats)))
    return dict(totals), per_invoice


def at_cost(objective: str) -> D:
    """The reconstruction's wages for this objective, without fringe."""
    return money(one("""SELECT COALESCE(round(sum(distributed_wages), 2), 0) AS w
                          FROM v_labor_effective
                         WHERE period = %s AND objective_id = %s""",
                     (PERIOD, objective))["w"])


def build(cats: dict, r: dict, labour: D) -> dict:
    """Run the structure up one set of costs. `labour` is the direct labour
    to burden — which is the fork the caller decides, not this function."""
    fringe = money(labour * r["FRINGE"])
    base = labour + fringe
    parts = {"LABOR": labour, "FRINGE": fringe}
    excluded = D("0.00")
    for c, amt in cats.items():
        if c in ("LABOR", "FRINGE"):
            continue          # replaced by the two figures above
        if c in OUT_OF_MTDC:
            parts[c] = amt
            excluded += amt
            continue
        if c == "SUBAWARD":
            took = min(amt, SUBAWARD_CAP)
            parts[c] = amt
            base += took
            excluded += amt - took
            continue
        parts[c] = amt
        base += amt
    overhead = money(base * r["OVERHEAD"])
    ga = money(base * r["G&A"])
    return dict(parts=parts, mtdc=base, excluded=excluded,
                overhead=overhead, ga=ga,
                total=base + overhead + ga + excluded)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anticipated", action="store_true",
                    help="label the run as the measured-estate rate")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()
    r = rates(args.anticipated)

    print(f"\n  THE RATE STRUCTURE ON THE RECORD"
          f"{'  (anticipated — measured estate)' if args.anticipated else ''}")
    print(f"    fringe    {r['FRINGE']*100:>7.2f}%  of direct labour")
    print(f"    overhead  {r['OVERHEAD']*100:>7.2f}%  of MTDC")
    print(f"    G&A       {r['G&A']*100:>7.2f}%  of MTDC")
    parts = r["OVERHEAD"] + r["G&A"]
    combined = r.get("INDIRECT_COMBINED")
    print(f"    combined  {parts*100:>7.2f}%  of MTDC  (overhead + G&A)")
    if combined is not None and combined != parts:
        # Two readings of one rate, and the build-up applies the parts because
        # that is what a build-up is. The engine computes each pool over the
        # base and rounds, so the sum of the parts and the recorded combined
        # differ in the last place. Stated rather than reconciled away — a
        # figure that appears twice at two values is the defect this
        # engagement has paid for more than any other.
        print(f"              {combined*100:>7.2f}%  recorded as "
              f"INDIRECT_COMBINED — {abs(parts-combined)*10000:.0f} basis "
              f"point{'s' if abs(parts-combined)*10000 != 1 else ''} apart, "
              f"which is each pool rounded over the same base")
    print(f"    a dollar of direct non-labour carries "
          f"{(r['OVERHEAD']+r['G&A'])*100:.2f} cents that was never billed\n")

    grand = defaultdict(lambda: D("0.00"))
    for obj, title, prime in AWARDS:
        cats, invoices = billed(obj)
        if not invoices:
            print(f"  {title}: no invoices on the 2025 register\n")
            continue
        face = sum(cats.values(), D("0.00"))
        wages = at_cost(obj)
        detail = [c for c in cats if c not in UNTESTABLE and cats[c] != 0]

        print(f"  ── {title} · {prime} · {len(invoices)} invoices "
              f"{'─' * max(0, 42 - len(title) - len(prime))}")
        if not detail:
            print(f"     The face carries no cost detail — "
                  f"{face:,.2f} of {', '.join(sorted(cats))} and nothing else.")
            print("     This exercise cannot be run on it. The cost record is "
                  "the only route,\n     and that is what the restatement "
                  "already measures.\n")
            grand["no_detail"] += face
            continue

        a = build(cats, r, cats.get("LABOR", D("0.00")))
        b = build(cats, r, wages)
        print(f"     {'':26}{'AS INVOICED':>16}{'LABOUR AT COST':>16}")
        for c in ORDER:
            if c not in a["parts"] and c not in b["parts"]:
                continue
            av, bv = a["parts"].get(c, D(0)), b["parts"].get(c, D(0))
            mark = "" if c in IN_MTDC or c == "SUBAWARD" else "   out of MTDC"
            print(f"     {LABEL.get(c, c):26}{av:>16,.2f}{bv:>16,.2f}{mark}")
        print(f"     {'─'*58}")
        print(f"     {'MTDC (200.1)':26}{a['mtdc']:>16,.2f}{b['mtdc']:>16,.2f}")
        oh_label = f"Overhead @ {r['OVERHEAD'] * 100:.2f}%"
        ga_label = f"G&A @ {r['G&A'] * 100:.2f}%"
        print(f"     {oh_label:26}{a['overhead']:>16,.2f}{b['overhead']:>16,.2f}")
        print(f"     {ga_label:26}{a['ga']:>16,.2f}{b['ga']:>16,.2f}")
        print(f"     {'─'*58}")
        print(f"     {'FULLY BURDENED':26}{a['total']:>16,.2f}{b['total']:>16,.2f}")
        print(f"     {'as billed':26}{face:>16,.2f}{face:>16,.2f}")
        ind = cats.get("INDIRECT", D("0.00"))
        if ind:
            print(f"     {'  of which indirect':26}{ind:>16,.2f}{ind:>16,.2f}")
        print(f"     {'UNDER-RECOVERED':26}"
              f"{a['total']-face:>16,.2f}{b['total']-face:>16,.2f}\n")
        grand["a"] += a["total"] - face
        grand["b"] += b["total"] - face
        grand["face"] += face

    print(f"  ── Across the awards this can be run on "
          f"{'─'*22}")
    print(f"     {'as billed':26}{grand['face']:>16,.2f}")
    print(f"     {'UNDER-RECOVERED':26}{grand['a']:>16,.2f}{grand['b']:>16,.2f}")
    if grand["no_detail"]:
        print(f"\n     {grand['no_detail']:,.2f} of billing carries no cost "
              f"detail on its face and is not in either column.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
