#!/usr/bin/env python3
"""A rate that survives a reviewer reading it line by line.

The certified 24.71% is arithmetically right and hard to defend, for one
reason: **it is a 31.62% overhead rate with 61% carved back out**, and on
Heidi's measured estate the carve-out reaches 102.4% and the rate goes
negative. A carve-out that approaches its own pool is the model saying the
pool was never the right size — and a reviewer who sees it will test every
carve-out line by line rather than accept the rate.

Three things make it hard to defend, and each has a citation:

  1. **The pool was never segregated by activity.** Appendix IV B.2.a requires
     the costs of an organisation's activities to be separated. YBI runs two:
     an incubator and a landlord. The occupancy cost of let and vacant space
     belongs to the second and should not enter a federal pool at all, rather
     than entering it and being carved back out.

  2. **A square-footage driver was applied to cost square footage does not
     drive.** $181,276.15 of the pool is T1 access, telephone, equipment and
     insurance. Carving those by floor area over-carves the occupancy it is
     meant to reach.

  3. **The tenants have already paid some of it back.** $133,998.11 of credits
     sit inside these accounts — Steelite for property tax, NCDMM for Boardman
     electric and gas, Semple utilities. Carving a space share off a figure
     already net of tenant recovery removes the same money twice, and errs
     against YBI.

So this rebuilds the overhead pool the way Appendix IV asks for it:

      occupancy cost, GROSS of tenant reimbursements
      x  the share of the estate that is YBI's own
      +  overhead that floor area does not drive
      -  200.436(b) depreciation on federally funded assets
      =  the federal overhead pool

**The share is a band, not a figure, and the width is one honest question.**
Common area — corridors, restrooms, conference rooms — serves tenants and the
incubator both. Apportioned pro rata to assignable space it follows the
tenants, which is the conventional treatment and the low end. Treated as the
incubator's own shared facility it stays with YBI, which is arguable for an
incubator and is the high end. Nothing here picks one.

Fringe and G&A do not appear in the band. Fringe is anchored at both ends to
source documents and G&A carries no occupancy, so neither moves on a floor
plan.

    python scripts/defensible_rate.py
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query, one  # noqa: E402

PERIOD = "2025"

#: Overhead accounts that floor area does **not** drive. A transcription of a
#: judgment, written down once, the way `v_payroll_reconciliation` names the
#: six fringe accounts by hand. Insurance is here because its policy schedule
#: has not arrived and property cannot be told from general liability — which
#: leaves it in the federal pool, the conservative direction for a reviewer
#: rather than for YBI.
NOT_SPACE_DRIVEN = {
    "5056 T1 Access", "5065 Telephone", "5020 Equipment Rental/Leases",
    "5015 Equipment Expenses", "5016 Equipment Purchases", "5075 Insurance",
}

AWARDS = [("DRIVE-AM", "Drive AM"), ("LTM", "Last Tactical Mile"),
          ("HYBRID-II", "Hybrid Phase 2"), ("DIG-ENG", "Digital Engineering")]


def money(x) -> D:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def overhead_split() -> tuple[D, D, D]:
    """Occupancy gross of reimbursements, the reimbursements, and the rest."""
    rows = query("""SELECT split_part(l.account, ':',
                             array_length(string_to_array(l.account, ':'), 1)) AS acct,
                           sum(l.amount) AS net,
                           COALESCE(sum(l.amount) FILTER (WHERE l.amount < 0), 0) AS credits
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND d.pool = 'OVERHEAD'
                     GROUP BY 1""")
    occ_net = sum((money(r["net"]) for r in rows
                   if r["acct"] not in NOT_SPACE_DRIVEN), D("0.00"))
    credits = sum((money(r["credits"]) for r in rows
                   if r["acct"] not in NOT_SPACE_DRIVEN), D("0.00"))
    other = sum((money(r["net"]) for r in rows
                 if r["acct"] in NOT_SPACE_DRIVEN), D("0.00"))
    return occ_net - credits, -credits, other


#: Common area that is a *shared facility of the incubator* rather than
#: circulation serving whoever is in the building. A conference room an
#: incubator books for its programme is not a corridor. Matched on the label
#: because that is what the floor plan calls it; a row the list does not name
#: is treated as circulation, which is the conservative direction.
PROGRAMME_COMMON = ("conf", "meeting")


def is_programme_common(label: str) -> bool:
    return any(w in (label or "").lower() for w in PROGRAMME_COMMON)


def estate_share(common: str) -> tuple[D, D, D]:
    """The share of the measured estate that is let, committed or vacant.

    Weighted by building, because there is one overhead pool carrying every
    building's occupancy and the honest driver is floor area across the whole
    estate. `months_occupied` weights a suite let for part of the year.
    """
    rows = query("""SELECT facility_id, use::text AS use, label,
                           sum(usable_sqft * months_occupied / 12) AS sqft
                      FROM space_unit WHERE period = %s
                     GROUP BY 1, 2, 3""", (PERIOD,))
    if not rows:
        raise SystemExit("No space is on the record for this period.")
    if common == "pro-rata" and not any(r["use"] == "COMMON" for r in rows):
        # The two readings differ only in what COMMON does. If the register
        # carries none, the choice was made when the space was loaded and the
        # band collapses to a point that looks like agreement — a check that
        # cannot fail, which this repository has shipped four times.
        raise SystemExit(
            "  The space register carries no COMMON at all, so the two "
            "readings\n  cannot differ and the band would be a point. Load the "
            "measured estate\n  with common areas AS COMMON and run this again.")
    per = {}
    for r in rows:
        f = per.setdefault(r["facility_id"], {"rental": D(0), "ours": D(0)})
        q = D(str(r["sqft"]))
        if r["use"] in ("TENANT", "VACANT", "COMMITTED"):
            f["rental"] += q
        elif r["use"] == "COMMON":
            if common == "ours":
                f["ours"] += q
            elif common == "split" and is_programme_common(r["label"]):
                f["ours"] += q        # a booked shared facility is programme
            # otherwise it rides pro rata — out of both sides
        else:
            f["ours"] += q
    estate = sum((f["rental"] + f["ours"] for f in per.values()), D(0))
    rental = sum((f["rental"] for f in per.values()), D(0))
    share = (rental / estate).quantize(D("0.000001")) if estate else D(0)
    return share, rental, estate


def rate_for(share: D, occ_gross: D, other: D, b436: D, base: D) -> dict:
    """YBI's own share of occupancy, less the 200.436(b) depreciation **in it**.

    The first draft subtracted the whole 156,235.27 from a figure the space
    split had already cut to 13.73% — the same money out twice, costing 2.85
    points of overhead against YBI. Depreciation on federally funded assets
    sits *inside* occupancy, so the let share of it is already gone with the
    let share of everything else; only the part riding on YBI's own floor is
    still there to remove.

    The asset register names no building on any of the eighteen, so this
    spreads them like the estate. If they turn out to sit disproportionately
    on YBI's own floor the adjustment is larger, and `b436_ours` is the line
    to argue about.
    """
    ours = (occ_gross * (1 - share)).quantize(D("0.01"))
    b436_ours = (b436 * (1 - share)).quantize(D("0.01"))
    pool = ours + other - b436_ours
    return dict(share=share, ours=ours, b436_ours=b436_ours, pool=pool,
                rate=(pool / base).quantize(D("0.000001")) if base else D(0))


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()

    occ_gross, credits, other = overhead_split()
    b436 = money(one("""SELECT COALESCE(sum(amount), 0) AS a FROM carve_out
                         WHERE period = %s AND citation LIKE %s""",
                     (PERIOD, "%436%"))["a"])
    ga = one("""SELECT pool_amount, base_amount FROM rate
                 WHERE period = %s AND kind = 'G&A' AND status <> 'SUPERSEDED'
                 ORDER BY computed_at DESC LIMIT 1""", (PERIOD,))
    fringe = one("""SELECT rate FROM rate WHERE period = %s AND kind = 'FRINGE'
                      AND status <> 'SUPERSEDED'
                     ORDER BY computed_at DESC LIMIT 1""", (PERIOD,))
    base = money(ga["base_amount"])
    ga_rate = (money(ga["pool_amount"]) / base).quantize(D("0.000001"))
    f_rate = D(str(fringe["rate"]))

    print("\n  HOW THE OVERHEAD POOL IS BUILT")
    print(f"    occupancy, gross of tenant reimbursement  {occ_gross:>14,.2f}")
    print(f"      of which tenants have already repaid    {credits:>14,.2f}")
    print(f"    overhead floor area does not drive        {other:>14,.2f}")
    print(f"    200.436(b) federally funded depreciation  {-b436:>14,.2f}")
    print("      spread like the estate, so only the share riding on YBI's")
    print("      own floor is still in the pool to remove")
    print(f"    MTDC base                                 {base:>14,.2f}\n")

    print("  THE BAND, AND WHAT SETS ITS WIDTH")
    scen = []
    for label, flag in (("all common follows the tenants", "pro-rata"),
                        ("shared facilities ours, circulation pro rata", "split"),
                        ("all common is the incubator's own", "ours")):
        share, rental, estate = estate_share(flag)
        r = rate_for(share, occ_gross, other, b436, base)
        scen.append((label, r, rental, estate))
        print(f"    {label:38}{share*100:>7.2f}% of {estate:,.0f} sq ft let")
        print(f"      YBI's own share of occupancy          {r['ours']:>14,.2f}")
        print(f"      less 200.436(b) in that share         {-r['b436_ours']:>14,.2f}")
        print(f"      federal overhead pool                 {r['pool']:>14,.2f}")
        print(f"      overhead rate                         {r['rate']*100:>13.2f}%")
    lo = min(s[1]["rate"] for s in scen)
    hi = max(s[1]["rate"] for s in scen)
    # **Not the midpoint.** Splitting the difference between two readings is
    # an average of two arguments rather than an argument. The middle scenario
    # is the one with a reason on it: a conference room an incubator books for
    # its programme is the incubator's; a corridor serves whoever is in the
    # building and follows them pro rata.
    mid = next(x[1]["rate"] for x in scen if x[0].startswith("shared"))

    print("\n  THE DEFENSIBLE STRUCTURE")
    print(f"    fringe, of salaries and wages             {f_rate*100:>13.2f}%")
    print(f"    overhead, of MTDC        {lo*100:>6.2f}% – {hi*100:.2f}%, "
          f"take {mid*100:>7.2f}%")
    print(f"    G&A, of MTDC                              {ga_rate*100:>13.2f}%")
    print(f"    combined, of MTDC        {(lo+ga_rate)*100:>6.2f}% – "
          f"{(hi+ga_rate)*100:.2f}%, take {(mid+ga_rate)*100:>7.2f}%")
    print(f"    fully loaded on labour                    "
          f"{(1+f_rate)*(1+mid+ga_rate):>13.4f}x\n")

    print("  APPLIED TO EACH CONTRACT, ON ITS OWN BASE")
    print("    One rate structure, four bases. An indirect rate is the")
    print("    organisation's; what differs per award is the MTDC it carries,")
    print("    the ceiling it sits under, and what its schedule budgets.\n")
    print(f"    {'award':22}{'MTDC':>14}{'indirect':>17}"
          f"{'ceiling':>14}{'headroom':>14}")
    for obj, title in AWARDS:
        a = one("""SELECT a.base_amount FROM allocation a JOIN rate r USING (rate_id)
                    WHERE r.kind = 'INDIRECT_COMBINED' AND r.status <> 'SUPERSEDED'
                      AND a.objective_id = %s
                    ORDER BY r.computed_at DESC LIMIT 1""", (obj,))
        aw = one("""SELECT ceiling_federal FROM award WHERE objective_id = %s""",
                 (obj,))
        if not a:
            print(f"    {title:22}{'no allocation on the rate':>45}")
            continue
        mtdc = money(a["base_amount"])
        ind = (mtdc * (mid + ga_rate)).quantize(D("0.01"))
        ceil = money(aw["ceiling_federal"]) if aw else None
        head = f"{ceil - mtdc - ind:,.2f}" if ceil else "—"
        print(f"    {title:22}{mtdc:>14,.2f}{ind:>17,.2f}"
              f"{(f'{ceil:,.2f}' if ceil else '—'):>14}{head:>14}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
