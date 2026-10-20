#!/usr/bin/env python3
"""Render the MOU and the agreement amendment that close 2025 with a sponsor.

    python scripts/settlement_papers.py --prime FA8650-20-2-5700

Reads the record and renders; it writes nothing to the cost record and
performs none of the four acts that are judgments with a person's name on
them. Two things it is deliberately strict about:

  * **The rate printed is the rate the restatements were measured on**, read
    by `rate_id`, and its sibling pools are read from the *same* computation.
    The live rate is 22.48% and the restatements name 24.71%; printing the
    live overhead beside the recorded combined rate would be a decomposition
    that does not add up — a figure that checks out and is about something
    else, which this repository calls worse than a blank.
  * **It refuses rather than guessing.** A prime with no standing
    restatement, a restatement whose invoice population has moved
    (`still_agrees` false), or a set spanning two primes stops the run and
    says which.

And it reports the rehearsal residue rather than rendering over it: the
reference record carries `status = 'ACCEPTED'` on every restatement because
`drive_the_close.py --rehearsal` wrote it, and NCDMM has accepted nothing.
The papers never print an acceptance, and this script says so out loud so
nobody mistakes the record for the sponsor's answer.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import one, open_pool, query  # noqa: E402
from app.domain.core import money  # noqa: E402
from app.domain.invoice_document import Party  # noqa: E402
from app.domain.settlement_document import (AwardPosition,  # noqa: E402
                                            SettlementPapers, _prime_key,
                                            render_amendment, render_mou)

YBI = Party("Youngstown Business Incubator",
            "241 W Federal St\nYoungstown, OH 44503", "ybi.org")
SPONSOR_ADDRESS = "6800 Innovation Blvd\nJohnstown, PA 15904"

#: The restatement statuses that stand as a position, as `restate.py` defines
#: them. Imported there rather than spelled a second time would be better;
#: this script only reads, so it asks for the same three by name and a test
#: holds the two together.
STANDING = ("PROPOSED", "SUBMITTED", "ACCEPTED")

OUT = Path("docs/settlement-2025")


def positions_for(prime: str, period: str) -> list[dict]:
    rows = query(
        """select r.award_id, r.objective_id, r.invoices, r.billed_total,
                  r.supported_total, r.over_collected, r.under_recovered,
                  r.indirect_billed,
                  r.rate_id, r.status, r.still_agrees, r.rate_is_live,
                  r.rate_status, r.sponsor, r.decided_note,
                  a.agreement_name, a.prime_agreement
             from v_restatement r join award a on a.award_id = r.award_id
            where r.period = %s and r.status = ANY(%s)
            order by r.over_collected desc, r.award_id""",
        (period, list(STANDING)))
    want = _prime_key(prime)
    return [r for r in rows if _prime_key(r["prime_agreement"] or "") == want]


def the_rate(rate_id: str) -> dict:
    """The computation the restatements name, and its siblings.

    `rate` carries one row per kind per computation, so the fringe and the
    two indirect pools behind a combined rate are the rows sharing its
    `seal_hash` and `computed_at`. Reading the *live* rows instead would
    print 10.11% overhead under a 24.71% combined rate.
    """
    named = one("""select kind, rate, pool_amount, base_amount, status,
                          seal_hash, computed_at, admin_labour_basis
                     from rate where rate_id = %s""", (rate_id,))
    if not named:
        raise SystemExit(f"no rate row for {rate_id}")
    siblings = {r["kind"]: r for r in query(
        """select kind, rate, pool_amount, base_amount from rate
            where period = '2025' and seal_hash = %s and computed_at = %s""",
        (named["seal_hash"], named["computed_at"]))}
    return {"named": named, "siblings": siblings}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prime", default="FA8650-20-2-5700",
                    help="the prime agreement whose awards this settles")
    ap.add_argument("--period", default="2025")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    open_pool()
    rows = positions_for(args.prime, args.period)
    if not rows:
        raise SystemExit(f"no standing {args.period} restatement is primed "
                         f"through {args.prime}. Nothing to settle.")

    moved = [r["award_id"] for r in rows if not r["still_agrees"]]
    if moved:
        raise SystemExit(
            f"the invoice population has moved under "
            f"{', '.join(moved)} — recompute on /restate before issuing a "
            f"paper measured against it.")

    rate_ids = {r["rate_id"] for r in rows}
    if len(rate_ids) != 1:
        raise SystemExit(f"these {len(rows)} positions were measured on "
                         f"{len(rate_ids)} different rates; one instrument "
                         f"cannot state two.")
    r = the_rate(rate_ids.pop())
    named, sib = r["named"], r["siblings"]

    overhead = sib.get("OVERHEAD", {}).get("rate") or Decimal("0")
    ga = sib.get("G&A", {}).get("rate") or Decimal("0")
    fringe = sib.get("FRINGE", {}).get("rate") or Decimal("0")
    # The pools have to add; the rounded percentages need not, and the paper
    # prints the pools for exactly that reason. `SettlementPapers` refuses a
    # set whose pools do not, so this only reports.
    parts = money((overhead + ga) * 100)
    whole = money(Decimal(named["rate"]) * 100)

    clauses = {c["award_id"]: c["citation"] for c in query(
        """select award_id, citation from award_term
            where term_key = 'Change of basis' and award_id = ANY(%s)""",
        ([x["award_id"] for x in rows],))}

    positions = tuple(
        AwardPosition(
            award=x["award_id"],
            title=(x["agreement_name"] or x["objective_id"]).replace("-", " "),
            objective=x["objective_id"],
            prime=x["prime_agreement"] or "",
            invoices=int(x["invoices"]),
            billed=money(x["billed_total"]),
            restated=money(x["supported_total"]),
            over_collected=money(x["over_collected"]),
            under_recovered=money(x["under_recovered"]),
            indirect_billed=money(x["indirect_billed"]))
        for x in rows)

    papers = SettlementPapers(
        remit_to=YBI,
        bill_to=Party(_addressee(rows), SPONSOR_ADDRESS),
        period=args.period,
        issued_on=date.today(),
        reference=f"{args.period} close-out · {args.prime}",
        positions=positions,
        rate_kind=named["kind"],
        rate_applied=Decimal(named["rate"]),
        fringe_rate=Decimal(fringe),
        overhead_rate=Decimal(overhead),
        ga_rate=Decimal(ga),
        rate_pool=money(named["pool_amount"]),
        rate_base=money(named["base_amount"]),
        overhead_pool=money(sib.get("OVERHEAD", {}).get("pool_amount") or 0),
        ga_pool=money(sib.get("G&A", {}).get("pool_amount") or 0),
        fringe_pool=money(sib.get("FRINGE", {}).get("pool_amount") or 0),
        fringe_base=money(sib.get("FRINGE", {}).get("base_amount") or 0),
        rate_is_live=bool(rows[0]["rate_is_live"]),
        rate_status=named["status"],
        certification=one("select * from v_rate_certified where period = %s",
                          (args.period,)),
        basis_clauses=tuple((p.title, clauses.get(p.award, "no clause on the "
                                                           "record"))
                            for p in positions),
        awards_without_a_clause=tuple(p.title for p in positions
                                      if p.award not in clauses))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    mou = out / f"MOU_{args.period}_indirect_cost_settlement.pdf"
    amd = out / f"Amendment_{args.period}_{args.prime}.pdf"
    mou.write_bytes(render_mou(papers))
    amd.write_bytes(render_amendment(papers))

    print(f"prime {papers.prime} · {len(positions)} award(s) · "
          f"{papers.bill_to.name}")
    print(f"{'award':<34}{'billed':>14}{'restated':>14}"
          f"{'to return':>13}{'to claim':>12}")
    for p in positions:
        print(f"{p.title[:33]:<34}{p.billed:>14,.2f}{p.restated:>14,.2f}"
              f"{p.over_collected:>13,.2f}{p.under_recovered:>12,.2f}")
    print(f"{'all ' + str(len(positions)):<34}{papers.billed_total:>14,.2f}"
          f"{papers.restated_total:>14,.2f}{papers.to_return:>13,.2f}"
          f"{papers.to_claim:>12,.2f}")
    print(f"\nnet declared unrecoverable  {abs(papers.net):>14,.2f}"
          f"   running to {papers.net_runs_to}")
    if parts != whole:
        print(f"\n      overhead {overhead*100:.2f}% + G&A {ga*100:.2f}% = "
              f"{parts}% against a combined {whole}% — each rounded "
              f"independently.\n      The papers print the pools, which add "
              f"exactly, rather than two percentages that do not.")
    print(f"rate on the papers          {Decimal(named['rate'])*100:>13.2f}% "
          f"{named['kind']} · {named['status']}"
          f"{'' if papers.rate_is_live else '  ← superseded'}")

    rehearsed = [x["award_id"] for x in rows if x["status"] == "ACCEPTED"
                 and "Accepted by NCDMM" in (x["decided_note"] or "")]
    if rehearsed:
        print(f"\nNOTE  {len(rehearsed)} of these restatements read ACCEPTED "
              f"on the record and no sponsor has answered:")
        print(f"      {', '.join(rehearsed)} — written by "
              f"drive_the_close.py --rehearsal.")
        print("      The papers print no acceptance. Withdraw or recompute "
              "the rows before they are read as NCDMM's position.")
    print(f"\n{mou}\n{amd}")
    return 0


def _addressee(rows: list[dict]) -> str:
    """The sponsor they have in common, never the first row's.

    `reconciliation_document.py` took the sponsor off whichever award had the
    largest give-back and addressed a four-award page to one award's sponsor.
    """
    names = {(r["sponsor"] or "").strip() for r in rows if r["sponsor"]}
    return names.pop() if len(names) == 1 else "NCDMM"


if __name__ == "__main__":
    raise SystemExit(main())
