#!/usr/bin/env python3
"""Open a 200.331 determination for every party the cap could bite.

2 CFR 200.1 takes the first $25,000 of each **subaward** into MTDC and a
contract for services whole. Nothing in this system had recorded which any of
these is, and `burdened_buildup.py` shipped a `SUBAWARD_CAP` that never fired
because the invoices call every one of them `CONSULTANT`.

This opens a row per party over the cap, at `UNDETERMINED`, on every federal
objective. It **makes no determination** — 200.331 turns on the substance of
the relationship, which is read off an agreement and is a judgment with a
person's name on it. Opening the question is the work this can do; answering
it is not.

**`POST /api/rates/seal` does this now, and this is the backfill.** For the
life of the register nothing called this script — not `seed.sh`, not the
boot, not any other script — so a deployment showed the controller *No party
clears the cap* over a register nobody had ever opened, with $313,605.35 of
MTDC turning on it. Anything that only exists because a person remembered to
run it does not survive. The sweep belongs at the seal because it reads the
ledger *through the live DIRECT judgments*, so it has nothing to find until
somebody has classified — which is the one thing a boot cannot wait for.

What is left here is the same sweep for a record sealed before that shipped,
and a dry run for anybody who wants to see what would open without sealing.

Re-runnable: a party already on the register is left exactly as it is, so a
determination somebody has made is never overwritten by a later sweep.

    python scripts/load_party_determinations.py            # say what it would open
    python scripts/load_party_determinations.py --write
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query, execute  # noqa: E402

#: 200.1's cap. Below it the determination cannot change what MTDC takes, so a
#: row would be a question with no consequence.
CAP = D("25000")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()

    rows = query("""SELECT d.objective_id,
                           COALESCE(NULLIF(l.payee, ''), '') AS payee,
                           round(sum(l.amount), 2) AS amount
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                      JOIN cost_objective o ON o.objective_id = d.objective_id
                                           AND o.period = l.period
                     WHERE d.reversed_at IS NULL AND d.pool = 'DIRECT'
                       AND o.is_federal AND l.period = %s
                     GROUP BY 1, 2
                    HAVING sum(l.amount) > %s
                     ORDER BY 3 DESC""", (args.period, CAP))
    if not rows:
        print("No party on a federal objective clears the 200.1 cap.")
        return 0

    have = {(r["objective_id"], r["payee"]) for r in query(
        "SELECT objective_id, payee FROM party_determination WHERE period = %s",
        (args.period,))}

    print(f"  {'objective':14}{'payee':38}{'amount':>13}{'at stake':>13}")
    opened = kept = 0
    for r in rows:
        amt = D(str(r["amount"]))
        name = r["payee"] or "(no payee on the ledger line)"
        if (r["objective_id"], r["payee"]) in have:
            print(f"  {r['objective_id']:14}{name[:37]:38}{amt:>13,.2f}"
                  f"{'already on the register':>13}")
            kept += 1
            continue
        print(f"  {r['objective_id']:14}{name[:37]:38}{amt:>13,.2f}"
              f"{amt - CAP:>13,.2f}")
        opened += 1
        if args.write:
            execute("""INSERT INTO party_determination
                         (period, objective_id, payee, amount)
                       VALUES (%s, %s, %s, %s)""",
                    (args.period, r["objective_id"], r["payee"], amt))

    total = sum(D(str(r["amount"])) - CAP for r in rows)
    print(f"\n  {opened} opened{'' if args.write else ' (dry run — pass --write)'}"
          f", {kept} already on the register.")
    print(f"  {total:,.2f} of MTDC turns on determinations nobody has made.")
    print("  Every one is UNDETERMINED, which is NO DATA and never a pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
