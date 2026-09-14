#!/usr/bin/env python3
"""What 2025 would have supported at a different indirect loading.

    PYTHONPATH=. python3 scripts/indirect_loading_analysis.py
    PYTHONPATH=. python3 scripts/indirect_loading_analysis.py --rate 33.00

Now that the register holds the year as issued rather than three invoices from
one month, the question can be asked properly: **against what was actually
billed, what does the cost record support at each candidate rate?**

**A restatement is a rebuild, not an addition**, and getting that wrong is the
one mistake that makes the whole exercise wrong in YBI's favour. The labour
billed on these awards is already burdened — the Hybrid cost proposal shows
the arithmetic explicitly, $403,570 of personnel and fringe plus $45,457 of
10% ICR presented as a single labour line of $449,043.40. So a restated claim
takes labour **down** to wages plus fringe and then puts indirect on MTDC.
Adding a rate on top of the billed labour would claim indirect twice.

Nothing here is computed that the engine already computed. The MTDC base and
the wage distribution are read from `allocation` and `v_labor_effective` as
the sealed rate recorded them; the fringe rate is read off the rate table.
What this adds is only the comparison against billing, which nothing could do
while the register held a sample.

It writes nothing. No restatement is recorded, no rate is computed — the
positions this produces are arithmetic to look at, not claims to make, and
`POST /api/restate` against a sealed rate is what makes one.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import one, open_pool, query  # noqa: E402

PERIOD = "2025"

#: Each candidate, and where it comes from. A rate with no provenance is a
#: number somebody remembered.
CANDIDATES = [
    ("10.00", "the de minimis election these invoices were issued under"),
    ("33.00", "YBI's own Hybrid Phase 2 cost proposal — $150,008.10 over a "
              "$454,570 base, its 'what would have been' column"),
    ("34.82", "the sealed classification on the OBJECTIVE basis, no carve-out"),
    ("37.67", "the POOL basis at a provisional 20% tenant carve-out"),
    ("43.99", "the POOL basis as sealed and computed, no carve-out"),
]

#: The awards a rate can be applied to. AAMEN is firm fixed price and Rising
#: Tides is a non-federal programme — neither bills cost, so neither has an
#: indirect position, and printing one for them would invite somebody to
#: claim it.
COST_REIMBURSEMENT = ["DRIVE-AM", "LTM", "DIG-ENG", "HYBRID-II"]


def money(v) -> str:
    return f"{Decimal(v):>14,.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rate", action="append", default=[],
                    help="an extra rate to price, as a percentage")
    args = ap.parse_args()

    open_pool()
    fringe_rate = one("""SELECT rate FROM rate WHERE period=%s AND kind='FRINGE'
                          AND status='PROPOSED'""", (PERIOD,))
    if not fringe_rate:
        raise SystemExit("no sealed FRINGE rate on file — nothing to build a "
                         "burdened labour figure from")
    fringe_rate = fringe_rate["rate"]

    basis = one("""SELECT admin_labour_basis, rate FROM rate WHERE period=%s
                    AND kind='INDIRECT_COMBINED' AND status='PROPOSED'""",
                (PERIOD,))

    print(f"Indirect loading analysis — {PERIOD}")
    print(f"  fringe {fringe_rate*100:.2f}% on wages, read from the sealed rate")
    print(f"  the rate on file is {basis['rate']*100:.2f}% on the "
          f"{basis['admin_labour_basis']} basis\n")

    # Header figures and line figures are aggregated SEPARATELY and joined
    # after. Summing i.total across a join to invoice_line multiplies every
    # header by its line count — Drive AM read $3,084,173.85 against a
    # $1,103,594 ceiling, which is the only reason it was caught. It is the
    # same defect the decision_line rule exists for, in a new table.
    rows = query("""
        WITH head AS (
          SELECT objective_id, count(*) AS invoices, sum(total) AS billed,
                 sum(indirect_claimed) AS billed_indirect
            FROM invoice WHERE period = %s AND objective_id = ANY(%s)
           GROUP BY 1),
        lines AS (
          SELECT i.objective_id,
                 sum(l.amount) FILTER (WHERE l.category='LABOR')    AS billed_labour,
                 sum(l.amount) FILTER (WHERE l.category='INDIRECT') AS line_indirect
            FROM invoice i JOIN invoice_line l USING (invoice_id)
           WHERE i.period = %s AND i.objective_id = ANY(%s)
           GROUP BY 1)
        SELECT h.objective_id, h.invoices, h.billed, h.billed_indirect,
               COALESCE(x.billed_labour, 0)  AS billed_labour,
               COALESCE(x.line_indirect, 0)  AS line_indirect
          FROM head h LEFT JOIN lines x USING (objective_id)
         ORDER BY h.billed DESC""",
        (PERIOD, COST_REIMBURSEMENT, PERIOD, COST_REIMBURSEMENT))
    # The header's indirect and the lines' indirect are two records of one
    # fact and must agree; if they do not, one of them is wrong.
    for r in rows:
        if abs(r["billed_indirect"] - r["line_indirect"]) > Decimal("0.01"):
            raise SystemExit(
                f"{r['objective_id']}: header indirect "
                f"{r['billed_indirect']:,.2f} against lines "
                f"{r['line_indirect']:,.2f} — the register disagrees with "
                f"itself and no figure below would mean anything.")

    cost = {r["objective_id"]: r for r in query("""
        SELECT a.objective_id, a.base_amount AS mtdc, a.allocated
          FROM allocation a JOIN rate r USING (rate_id)
         WHERE r.status='PROPOSED' AND r.kind='INDIRECT_COMBINED'""")}
    wages = {r["objective_id"]: r["w"] for r in query("""
        SELECT objective_id, round(sum(distributed_wages),2) AS w
          FROM v_labor_effective WHERE period=%s GROUP BY 1""", (PERIOD,))}
    nonlab = {r["objective_id"]: r["amt"] for r in query("""
        SELECT d.objective_id, sum(l.amount) AS amt
          FROM decision d
          JOIN decision_line dl ON dl.decision_id=d.decision_id AND dl.live
          JOIN ledger_line l ON l.line_id=dl.line_id
         WHERE d.reversed_at IS NULL AND d.pool='DIRECT' GROUP BY 1""")}
    ceilings = {r["objective_id"]: r for r in query(
        "SELECT objective_id, award_id, ceiling_federal FROM award")}

    rates = [(Decimal(p), why) for p, why in CANDIDATES]
    rates += [(Decimal(p), "asked for on the command line") for p in args.rate]

    print("As billed, and what the cost record supports\n")
    print(f"{'award':<12}{'inv':>5}{'billed':>15}{'  of which labour':>19}"
          f"{'  billed indirect':>18}")
    grand = {}
    for r in rows:
        o = r["objective_id"]
        print(f"  {o:<10}{r['invoices']:>5}{money(r['billed'])}"
              f"{money(r['billed_labour']):>19}{money(r['billed_indirect']):>18}")
    print()

    print(f"{'award':<12}{'wages':>14}{'fringe':>13}{'non-labour':>14}"
          f"{'MTDC base':>15}")
    for r in rows:
        o = r["objective_id"]
        w = wages.get(o, Decimal(0)); f = (w * fringe_rate).quantize(Decimal("0.01"))
        n = nonlab.get(o, Decimal(0)); m = cost.get(o, {}).get("mtdc", Decimal(0))
        grand[o] = dict(w=w, f=f, n=n, m=m, billed=r["billed"],
                        billed_indirect=r["billed_indirect"])
        print(f"  {o:<10}{money(w)}{money(f):>13}{money(n):>14}{money(m):>15}")
    print()

    print("Supported claim at each loading, against what was billed")
    print("  (labour rebuilt to wages + fringe; indirect on the MTDC base)\n")
    hdr = "".join(f"{p:>8.2f}%" for p, _ in rates)
    print(f"{'award':<12}{'billed':>15}" + hdr)
    totals = {p: Decimal(0) for p, _ in rates}
    tot_billed = Decimal(0)
    for o, g in grand.items():
        tot_billed += g["billed"]
        cells = ""
        for p, _ in rates:
            supported = g["w"] + g["f"] + g["n"] + (g["m"] * p / 100).quantize(Decimal("0.01"))
            totals[p] += supported
            cells += f"{supported/1000:>8,.1f}k"
        print(f"  {o:<10}{money(g['billed'])}" + cells)
    print(f"  {'TOTAL':<10}{money(tot_billed)}"
          + "".join(f"{totals[p]/1000:>8,.1f}k" for p, _ in rates))
    print()

    print("Movement against billing — positive is under-recovered\n")
    print(f"{'award':<12}" + hdr)
    for o, g in grand.items():
        cells = ""
        for p, _ in rates:
            supported = g["w"] + g["f"] + g["n"] + (g["m"] * p / 100).quantize(Decimal("0.01"))
            cells += f"{(supported - g['billed'])/1000:>8,.1f}k"
        print(f"  {o:<10}" + cells)
    print(f"  {'NET':<10}"
          + "".join(f"{(totals[p]-tot_billed)/1000:>8,.1f}k" for p, _ in rates))

    print("\nWhat each rate is\n")
    for p, why in rates:
        print(f"  {p:>6.2f}%  {why}")

    print("\nHeadroom — a claim cannot exceed the ceiling, and these are "
          "cumulative-to-date figures against a 2025 slice\n")
    for o, g in grand.items():
        c = ceilings.get(o)
        if not c or not c["ceiling_federal"]:
            print(f"  {o:<10} no ceiling on the record")
            continue
        print(f"  {o:<10} ceiling {c['ceiling_federal']:>13,.2f}   "
              f"2025 billed {g['billed']:>13,.2f}   "
              f"{g['billed']/c['ceiling_federal']*100:>5.1f}% of it in this year alone")

    print("\nNot priced here: AAMEN is firm fixed price and Rising Tides is a "
          "non-federal programme.\n  Neither bills cost, so neither has an "
          "indirect position to restate.")
    print("Nothing was written. A position becomes a claim through "
          "POST /api/restate against a sealed rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
