#!/usr/bin/env python3
"""Which readings would raise the indirect rate, and which way each runs.

The fair question about 19.95% is why it is so far below the rates other
non-profits carry and an order of magnitude below a research university's.
Most of the answer is structural rather than a deficiency, and the part that
is not is a short list of judgments nobody has made yet.

**Structure, before any leg.** A university's F&A rate has two components
(Appendix III): Facilities — building and equipment depreciation, interest,
operations and maintenance, library — and Administration, which is *capped at
26 points of MTDC*. YBI's overhead is the facilities analogue and its G&A is
the administration analogue. Two things make the comparison not hold:

  1. **YBI lets most of its estate.** On the measured floor plan the let,
     committed and vacant share is what `estate_share` reports; a university
     does not rent that proportion of its laboratories to third parties, so
     its facilities component keeps occupancy cost YBI's has to give up under
     200.465. A low facilities component is the correct answer here, not a
     shortfall.
  2. **The base is every activity, not one.** A university computes F&A over
     organized research MTDC alone. YBI's base is the whole organisation —
     eight non-federal programmes included — so the same pool is spread over
     several times the volume. The federal share of the base is reported
     below; it is the single largest reason the rate reads low.

Neither is fixed by finding more cost. What *would* move the rate is on the
list below, and this prints each one alone, in points, with the direction it
runs — because a list of only the ones that help is a rate reverse-engineered,
which is the thing the seal exists to rule out.

Nothing here is written to the record.

    python scripts/rate_headroom.py            # to the terminal
    python scripts/rate_headroom.py --write    # and docs/RATE_HEADROOM_2025.md
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.db import open_pool, query, one  # noqa: E402
from defensible_rate import (  # noqa: E402
    PERIOD, money, overhead_split, estate_share, rate_for)

DOC = ROOT / "docs" / "RATE_HEADROOM_2025.md"

#: Tenancies that are plainly a commercial letting rather than an incubator
#: client in residence, matched on the occupant the floor plan names. Steelite
#: International is a manufacturer occupying two buildings; NCDMM/America Makes
#: is a federal institute co-located here, which is the arguable middle case
#: and is kept separate for that reason. Everything else on the plan is a
#: small suite in YBI Main or Tech Block 5 — which is what an incubator's
#: client companies look like.
COMMERCIAL = ("steelite",)
PARTNER = ("ncdmm",)


def occupant_is(row, words) -> bool:
    return any(w in (row["occupant"] or "").lower() for w in words)


def tenancy_predicate(clients: bool, partner: bool):
    """Which tenancies count as programme space rather than let space."""
    if not clients and not partner:
        return None

    def p(row) -> bool:
        if occupant_is(row, COMMERCIAL):
            return False
        return partner if occupant_is(row, PARTNER) else clients
    return p


def tenancy_rent(clients: bool, partner: bool) -> tuple[D, D]:
    """Square feet and rent carried by the tenancies moved to programme space.

    The rent matters: space whose cost stays in the federal overhead pool and
    which somebody pays YBI for carries an applicable credit under 200.406,
    so moving the floor area without the money would take the cost into the
    pool twice over.
    """
    pred = tenancy_predicate(clients, partner)
    if pred is None:
        return D(0), D("0.00")
    rows = query("""SELECT use::text AS use, occupant,
                           sum(usable_sqft * months_occupied / 12) AS sqft,
                           sum(COALESCE(actual_annual_charge, 0)) AS rent
                      FROM space_unit WHERE period = %s AND use = 'TENANT'
                     GROUP BY 1, 2""", (PERIOD,))
    hit = [r for r in rows if pred(r)]
    return (sum((D(str(r["sqft"])) for r in hit), D(0)),
            sum((money(r["rent"]) for r in hit), D("0.00")))


class Model:
    """The reference structure, and one scenario at a time over it."""

    def __init__(self) -> None:
        self.occ_gross, self.credits, self.other = overhead_split()
        self.b436 = money(one("""SELECT COALESCE(sum(amount), 0) AS a
                                   FROM carve_out
                                  WHERE period = %s AND citation LIKE %s""",
                              (PERIOD, "%436%"))["a"])
        ga = one("""SELECT pool_amount, base_amount FROM rate
                     WHERE period = %s AND kind = 'G&A' AND status <> 'SUPERSEDED'
                     ORDER BY computed_at DESC LIMIT 1""", (PERIOD,))
        if not ga:
            raise SystemExit("No G&A rate on this record — compute one first.")
        self.ga_pool = money(ga["pool_amount"])
        self.base = money(ga["base_amount"])
        self.fringe = D(str(one("""SELECT rate FROM rate WHERE period = %s
                                     AND kind = 'FRINGE' AND status <> 'SUPERSEDED'
                                   ORDER BY computed_at DESC LIMIT 1""",
                                (PERIOD,))["rate"]))
        self.reference = self.run()

    def run(self, *, common: str = "split", clients: bool = False,
            partner: bool = False, credit_rent: bool = True,
            rental_bears_ga: bool = False, base_cut: D = D("0.00")) -> dict:
        share, rental, estate = estate_share(
            common, tenancy_predicate(clients, partner))
        oh = rate_for(share, self.occ_gross, self.other, self.b436, self.base)
        pool = oh["pool"]
        _, rent = tenancy_rent(clients, partner)
        if credit_rent:
            pool -= rent
        base = self.base - base_cut
        ga_base = base
        if rental_bears_ga:
            # Appendix IV B.2.a asks for an organisation's activities to be
            # segregated — and the same segregation that keeps let occupancy
            # out of the federal overhead pool makes the letting an activity
            # that has to bear its share of general administration. Its direct
            # cost is the let share of occupancy, net of what the tenants have
            # already repaid into those accounts.
            ga_base += ((self.occ_gross * share).quantize(D("0.01"))
                        - self.credits)
        oh_rate = (pool / base).quantize(D("0.000001")) if base else D(0)
        ga_rate = (self.ga_pool / ga_base).quantize(D("0.000001")) if ga_base else D(0)
        return dict(share=share, estate=estate, pool=pool, base=base,
                    ga_base=ga_base, overhead=oh_rate, ga=ga_rate,
                    combined=oh_rate + ga_rate, rent=rent)


def federal_share(base: D) -> tuple[D, D, int]:
    """The federal slice of the base, and how many objectives share the rest.

    Counted rather than written down: the number of non-federal activities
    carrying this pool is the argument, and a hand-kept count of them is the
    map this repository has been wrong about more often than anything else.
    """
    rows = query("""SELECT o.is_federal, a.objective_id, a.base_amount AS b
                      FROM allocation a
                      JOIN rate r USING (rate_id)
                      JOIN cost_objective o ON o.objective_id = a.objective_id
                     WHERE r.kind = 'INDIRECT_COMBINED' AND r.status <> 'SUPERSEDED'
                       AND r.period = %s""", (PERIOD,))
    fed = sum((money(r["b"]) for r in rows if r["is_federal"]), D("0.00"))
    others = len([r for r in rows if not r["is_federal"]])
    return fed, ((fed / base).quantize(D("0.0001")) if base else D(0)), others


def subaward_excess() -> tuple[D, D, int, int]:
    """What leaves MTDC if the parties over the cap are subrecipients.

    200.1 takes the first $25,000 of each subaward into MTDC and a contract
    for services whole, so the same payment sits in the base or mostly outside
    it depending on a 200.331 determination. Two populations: the six on
    federal objectives that `party_determination` already carries as
    UNDETERMINED, and the 5227 portfolio consultants, which this record
    settled as contractors and which a reviewer may reopen.
    """
    fed = one("""SELECT COALESCE(sum(at_stake), 0) AS a, count(*) AS n
                   FROM v_subaward_exposure""")
    rows = query("""SELECT COALESCE(NULLIF(l.payee, ''), '(no payee)') AS payee,
                           sum(l.amount) AS amt
                      FROM decision d
                      JOIN decision_set s ON s.set_id = d.set_id
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND s.period = %s
                       AND l.account LIKE %s
                     GROUP BY 1""", (PERIOD, "%5227%"))
    over = [r for r in rows if money(r["amt"]) > D("25000")]
    ex = sum((money(r["amt"]) - D("25000") for r in over), D("0.00"))
    return money(fed["a"]), ex, int(fed["n"]), len(over)


def report(m: Model) -> list[str]:
    ref = m.reference
    fed, fed_pct, n_other = federal_share(m.base)
    fed_at_stake, ex5227, n_fed, n_5227 = subaward_excess()
    o: list[str] = []
    w = o.append
    w("# Where the indirect rate has room, and where it does not")
    w("")
    w("**Regenerate with `python scripts/rate_headroom.py --write`.** Nothing "
      "here is written to the record. The certified rate is 24.71%; the "
      "structure this measures against is the built one in "
      "`docs/DEFENSIBLE_RATE_2025.md`.")
    w("")
    w(f"It reads **Heidi's measured estate** — {ref['estate']:,.0f} usable "
      f"square feet across the buildings on the floor plan of 15 September "
      f"2026, which is filed as evidence and **has not been accepted into "
      f"`space_unit` on the reference record**, because accepting it "
      f"supersedes a certified rate and that is Tom's act. Run it against a "
      f"record where that estate is loaded, or every figure below is about a "
      f"different building.")
    w("")
    w("---")
    w("")
    w("## 1. Why it reads low, and how much of that is structural")
    w("")
    w("| | |")
    w("| --- | ---: |")
    w(f"| overhead — the facilities component | **{ref['overhead']*100:.2f}%** |")
    w(f"| G&A — the administration component | **{ref['ga']*100:.2f}%** |")
    w(f"| combined, of MTDC | **{ref['combined']*100:.2f}%** |")
    w(f"| fringe, of salaries and wages | {m.fringe*100:.2f}% |")
    w("")
    w("Two facts account for most of the distance to a peer figure, and "
      "neither is a cost somebody forgot to collect.")
    w("")
    w(f"**The estate is mostly somebody else's.** "
      f"{ref['share']*100:.2f}% of the {ref['estate']:,.0f} measured square "
      f"feet is let, committed or vacant, so that share of "
      f"${m.occ_gross:,.2f} of occupancy cost never enters the federal pool "
      f"at all. A university's Facilities component keeps the occupancy YBI "
      f"has to give up under 200.465. **This is the largest single reason "
      f"the overhead component is small, and it is the right answer.**")
    w("")
    w(f"**The base is the whole organisation, not one activity.** MTDC is "
      f"${m.base:,.2f} and the federal share of it is **${fed:,.2f}, "
      f"{fed_pct*100:.1f}%**. A university's F&A rate is computed over "
      f"organized research MTDC alone; this pool is spread over "
      f"{n_other} non-federal objectives as well, which is correct — every "
      f"activity "
      f"bears indirect — and it is why one pool over this base produces a "
      f"small number.")
    w("")
    w("Appendix IV B.2 permits **separate rates by function or location** "
      "where activities benefit differently. That is the one structural "
      "change that could raise the federal rate without finding a dollar of "
      "new cost, and it is not free: it needs evidence that federal work "
      "draws administration disproportionately, which this record does not "
      "yet carry. It is named here as the largest unexplored option, not as "
      "a recommendation.")
    w("")
    w("---")
    w("")
    w("## 2. Every leg, alone, in points of combined rate")
    w("")
    w("Each row moves one judgment and holds the rest at the reference. They "
      "interact, so they do not add; §3 runs the two packages.")
    w("")
    w("| leg | reading | combined | Δ pts |")
    w("| --- | --- | ---: | ---: |")

    def row(leg, reading, **kw):
        r = m.run(**kw)
        w(f"| {leg} | {reading} | {r['combined']*100:.2f}% | "
          f"{(r['combined'] - ref['combined'])*100:+.2f} |")
        return r

    row("Client space", "incubator client companies are programme space, "
        "their rent credited under 200.406", clients=True)
    row("Client space", "the same, **without** crediting the rent — shown to "
        "price the credit, not to propose it", clients=True, credit_rent=False)
    row("Client space", "America Makes counted as programme too, rent "
        "credited", clients=True, partner=True)
    row("Common area", "all common is the incubator's own", common="ours")
    row("Common area", "all common follows the tenants", common="pro-rata")
    row("200.331", f"the {n_fed} federal parties over the cap are "
        f"subrecipients — ${fed_at_stake:,.2f} leaves MTDC",
        base_cut=fed_at_stake)
    row("200.331", f"and the {n_5227} portfolio consultants over the cap as "
        f"well — a further ${ex5227:,.2f}",
        base_cut=fed_at_stake + ex5227)
    row("Segregation", "the letting bears its share of G&A, as Appendix IV "
        "B.2.a requires of an activity", rental_bears_ga=True)
    w("")
    w("**The last row is the one nobody has looked at, and it runs against "
      "YBI.** The same argument that keeps let occupancy out of the federal "
      "overhead pool makes the letting an *activity*, and an activity bears "
      "general administration. `cost_objective` has carried a `RENTAL` row "
      "since the master was built and **nothing is classified to it, nothing "
      "is allocated to it and no labour sits on it** — the dead-register "
      "shape, in the one place it costs rather than pays.")
    w("")
    w("## 2a. The tenancy roster the client-space leg turns on")
    w("")
    w("Matched on the occupant the floor plan names, which is a **starting "
      "list and not the answer**. Some of these are plainly not incubator "
      "clients — a maintenance contractor, a charity, an appraiser — and the "
      "test is the tenancy agreement, not the suite number. A wrong row here "
      "moves the rate, so it is printed rather than summarised.")
    w("")
    w("| occupant | sq ft | rent | this run treated it as |")
    w("| --- | ---: | ---: | --- |")
    pred = tenancy_predicate(True, False)
    for r in query("""SELECT occupant,
                             sum(usable_sqft) AS s,
                             sum(COALESCE(actual_annual_charge, 0)) AS r
                        FROM space_unit
                       WHERE period = %s AND use = 'TENANT'
                       GROUP BY 1 ORDER BY 2 DESC""", (PERIOD,)):
        how = "**programme**" if pred(r) else (
            "let — America Makes, the arguable middle case"
            if occupant_is(r, PARTNER) else "let — commercial")
        w(f"| {r['occupant']} | {D(str(r['s'])):,.0f} | "
          f"{money(r['r']):,.2f} | {how} |")
    w("")
    w("---")
    w("")
    w("## 3. The two packages")
    w("")
    w("| | overhead | G&A | combined | loaded on labour |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for label, kw in (("reference — `DEFENSIBLE_RATE_2025.md`", {}),
                      ("**defensible**: client space in, rent credited, "
                       "the letting bears G&A",
                       dict(clients=True, rental_bears_ga=True)),
                      ("stretch: + America Makes, + all common ours, "
                       "+ 200.331 on the federal six",
                       dict(clients=True, partner=True, common="ours",
                            rental_bears_ga=True, base_cut=fed_at_stake))):
        r = m.run(**kw)
        loaded = (1 + m.fringe) * (1 + r["combined"])
        w(f"| {label} | {r['overhead']*100:.2f}% | {r['ga']*100:.2f}% | "
          f"**{r['combined']*100:.2f}%** | {loaded:.4f}× |")
    w("")
    w("**The defensible package is the recommendation to test, not to "
      "adopt.** Every part of it is a judgment somebody at YBI has to make "
      "and sign: which occupants are client companies in residence and which "
      "are commercial lettings is Heidi's and Tom's answer off the tenancy "
      "agreements, not an inference from a suite number.")
    w("")
    w("---")
    w("")
    w("## 4. What has no room, and why saying so is the point")
    w("")
    w("| | |")
    w("| --- | --- |")
    w(f"| **Fringe, {m.fringe*100:.2f}%** | Anchored at both ends to source "
      f"documents — the P&L's six benefit accounts over the payroll "
      f"register. No floor plan, no determination and no reading of an "
      f"agreement touches it. |")
    w("| **Leave** | 200.431(b) makes paid leave a fringe cost and YBI pays "
      "it through the wage accounts as regular compensation, so it is "
      "already inside the denominator. Adding it to the numerator would "
      "count it twice. |")
    w("| **The certified 24.71%** | Not a leg in either direction. It is the "
      "same cost with the pool carved back rather than built, and on the "
      "measured estate its carve-out exceeds its own pool. |")
    w("| **The de minimis floor** | Raised from 10% to 15% by the 2024 "
      "revision, for awards issued **on or after 1 October 2024**. All four "
      "America Makes awards start before that date — Last Tactical Mile by "
      "nine days — so the 10% figure in each agreement is the one that "
      "governs unless a modification reissued it. Worth confirming against "
      "each subaward instrument rather than the prime's period. |")
    w("")
    w("---")
    w("")
    w("## 5. The rule this list is written under")
    w("")
    w("Classifications are sealed before any rate is computed so that a "
      "reviewer can be told the rate was not reverse-engineered. A list of "
      "only the readings that raise the number would undo that, whatever the "
      "seal says. So three of the eight legs above run **against** YBI and "
      "are on the page at the same size as the rest, and the two largest "
      "movements in the whole file — the measured estate and the "
      "administrative labour basis — are already taken.")
    w("")
    w("The honest summary is short: **the rate is low because YBI is a "
      "landlord to a largely non-federal tenancy and spends a quarter of its "
      "base on federal work.** The room that exists is in whether the "
      "incubator's client companies are tenants or programme, and that is a "
      "question about tenancy agreements rather than about accounting.")
    return o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="also write docs/RATE_HEADROOM_2025.md")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()
    text = "\n".join(report(Model())) + "\n"
    print(text)
    if args.write:
        DOC.write_text(text)
        print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
