#!/usr/bin/env python3
"""What is on each person's desk, generated from the record.

Three documents answer three different questions and none of them is a copy
of another:

    docs/MONDAY_RUNBOOK.md   the order a year is closed in     (runbook.py)
    scripts/readiness.py     can the machinery do its job      (read-only)
    docs/RUN_SHEET_2025.md   what is on whose desk             (this)

That is `v_worklist` and `v_worklist_owned` one level up: the first has always
known *what* is outstanding and the second *which portfolio* can act. Neither
says **who is waiting on whom**, and on a two-person close that is the thing
that decides whether Monday moves.

**It writes nothing and performs nothing.** Every item here is a judgment with
somebody's name on it — accepting a measurement, determining a relationship,
resolving a federal treatment, signing a rate. A script that did any of them
would put the machine's name where a person's belongs, which is the whole
reason the seal is worth anything.

    python scripts/stage_the_run.py            # to stdout
    python scripts/stage_the_run.py --write    # docs/RUN_SHEET_2025.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import open_pool, query, one  # noqa: E402

PERIOD = "2025"
OUT = Path(__file__).resolve().parent.parent / "docs" / "RUN_SHEET_2025.md"


def money(v) -> str:
    return f"{D(str(v or 0)):,.2f}"


def heidi(w) -> None:
    w("## Heidi — facilities and inventory\n")

    req = one("""SELECT request_id, state::text AS state, received_from
                   FROM information_request
                  WHERE period = %s AND form = 'SPACE_INVENTORY'
                  ORDER BY issued_at DESC LIMIT 1""", (PERIOD,))
    if req and req["state"] == "RECEIVED":
        w("### 1. Three rows of your own floor plan cannot be read\n")
        w("Everything else on your desk waits behind these. `/requests` → "
          f"request {req['request_id']} → **What it says**.\n")
        w("| row | what it says | what is needed |")
        w("| --- | --- | --- |")
        w("| `Taft/semple · suites 2A,2B & building` | area reads "
          "**\"3630 and 25,809\"**, which is not a number | is that one "
          "building or two? The rent says Taft — that row plus the vacant "
          "Taft suite are **237,081.48**, which is `4021 TTC Rent` to the "
          "cent — but it is yours to confirm |")
        w("| Semple | your rows account for **49,527.00** of "
          "**109,932.32** of Semple rent | rows appear to be missing |")
        w("| YBI Incubator | **5,459.8 sq ft** of vacant entered twice, once "
          "as \"floors 2-5\" and once as \"unoccupied offices F3-5\" | one "
          "area entered twice, or two different areas? |\n")
        w("### 2. Then accept it\n")
        w("Same screen, **Accept**. Until you do, the measurement is filed as "
          "evidence and **no register has it** — it moves no figure at all. "
          "It is the single largest adjustment in the rate model.\n")
    elif req:
        w("### 1. The floor plan\n")
        w(f"Request {req['request_id']} is {req['state'].lower()}.\n")

    unmeasured = one("""SELECT count(*) AS n FROM facility f
                         WHERE NOT EXISTS (SELECT 1 FROM space_unit u
                                            WHERE u.facility_id = f.facility_id
                                              AND u.period = %s)""", (PERIOD,))
    if unmeasured and unmeasured["n"]:
        w("### Buildings with no space recorded\n")
        w(f"{unmeasured['n']} of them. `/classify/space`.\n")

    acc = one("""SELECT count(*) AS n FROM asset
                  WHERE access = 'INTERNAL'""")
    if acc and acc["n"]:
        w("### 3. Which machines are lent out, and on what terms\n")
        w(f"All {acc['n']:,} assets read `INTERNAL`, which is the column's "
          "default and not an answer anybody gave. Nothing has ever written "
          "it, so `v_equipment_subsidy` can only report zero given "
          "equipment. `/classify/assets`.\n")


def tom(w) -> None:
    w("## Tom — controller\n")

    rows = query("""SELECT payee, objective_id, amount, at_stake
                      FROM v_subaward_exposure
                     WHERE period = %s AND determination = 'UNDETERMINED'
                     ORDER BY at_stake DESC""", (PERIOD,))
    if rows:
        stake = sum((D(str(x["at_stake"])) for x in rows), D(0))
        w("### 1. Contractor or subrecipient — six determinations\n")
        w(f"**{money(stake)} of MTDC** turns on these. 2 CFR 200.1 takes the "
          "first $25,000 of each **subaward** and a contract for services "
          "**whole**, so the same payment sits in the base or mostly outside "
          "it depending on 200.331.\n")
        w("| party | award | paid | at stake |")
        w("| --- | --- | ---: | ---: |")
        for x in rows:
            w(f"| {x['payee'] or '*(no payee on the ledger line)*'} | "
              f"{x['objective_id']} | {money(x['amount'])} | "
              f"{money(x['at_stake'])} |")
        blank = [x for x in rows if not x["payee"]]
        if blank:
            w(f"\n**{len(blank)} of them name no payee at all** on the ledger "
              "line, which is a separate question and a worse one.\n")
        w("\n200.331 turns on the **substance** of the relationship, not on "
          "what the invoice called it — all six are categorised `CONSULTANT` "
          "and that settles nothing. The register refuses a determination "
          "without who made it, when, and forty characters of why.\n")

    pend = query("""SELECT d.pool, round(sum(l.amount), 2) AS amt
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND d.federal = 'PENDING'
                       AND d.pool IN ('OVERHEAD', 'G&A', 'FRINGE')
                     GROUP BY 1""")
    for x in pend:
        w(f"### 2. {money(x['amt'])} of {x['pool']} is still `PENDING`\n")
        w("The depreciation judgment named its own release condition — *the "
          "unallowable share is an adjustment against this pool the day the "
          "register arrives*. **The register has arrived**: all 263 assets "
          "carry a funding answer, 20 are federally funded, and their "
          "156,235.27 is already carved under 200.436(b).\n")
        w("Resolving it to `ALLOWABLE` **moves no rate** — the cost is already "
          "in the pool and `PENDING` only ever held it out of the *claim*. It "
          "costs two deliberate acts: withdraw the signature, then unseal, "
          "each with a written reason.\n")

    cert = one("""SELECT certified, certified_by, certified_at
                    FROM v_rate_certified WHERE period = %s""", (PERIOD,))
    rates = {x["kind"]: D(str(x["rate"])) for x in query(
        """SELECT kind, rate FROM rate
            WHERE period = %s AND status <> 'SUPERSEDED'""", (PERIOD,))}
    w("### 3. The rate that stands, and the one the analysis supports\n")
    w("| | on the record | what the measured estate supports |")
    w("| --- | ---: | ---: |")
    w(f"| Fringe | {rates.get('FRINGE', 0) * 100:.2f}% | 21.90% *(anchored — "
      "cannot move on a floor plan)* |")
    w(f"| Overhead | {rates.get('OVERHEAD', 0) * 100:.2f}% | 7.58% *(band "
      "5.46 – 13.69)* |")
    w(f"| G&A | {rates.get('G&A', 0) * 100:.2f}% | 12.37% *(carries no "
      "occupancy)* |")
    w(f"| **Combined** | **{rates.get('INDIRECT_COMBINED', 0) * 100:.2f}%** | "
      "**19.95%** *(band 17.83 – 26.05)* |")
    if cert and cert["certified"]:
        w(f"\nCertified by {cert['certified_by']}. **Recomputing supersedes "
          "the rate and the certificate dies with it** — that is the design, "
          "not a fault.\n")
    w("\nThe difference is not a correction to the arithmetic. It is whether "
      "the overhead **pool** was ever the right size: the certified rate is "
      "31.62% with 61% carved back out, and on the measured estate the "
      "carve-out exceeds the pool. See `docs/DEFENSIBLE_RATE_2025.md`.\n")

    stale = query("""SELECT objective_id, invoices, register_invoices
                       FROM v_restatement
                      WHERE period = %s AND status <> 'SUPERSEDED'
                        AND still_agrees IS FALSE""", (PERIOD,))
    if stale:
        w("### 4. Restatements measured against a register that has moved\n")
        for x in stale:
            w(f"- **{x['objective_id']}** measured {x['invoices']} invoice(s); "
              f"the register holds {x['register_invoices']}. Recompute before "
              "anything goes to a sponsor.\n")

    cites = one("""SELECT count(*) AS n FROM v_worklist
                    WHERE kind = 'NEEDS_EVIDENCE'""")
    if cites and cites["n"]:
        w(f"### 5. {cites['n']:,} judgments cite no document\n")
        w("Every one is classified and sealed; what is outstanding is the "
          "citation to the paper behind it. `/evidence`.\n")


def waiting(w) -> None:
    w("## Waiting on other people\n")
    w("Neither of you is blocked on these, and neither of you can do them.\n")
    # DISTINCT: `v_labor_effective` is one row per person **per objective**,
    # so a plain count is person-objective pairs and reads 97 where the
    # answer is 43 — a figure on a run sheet that nobody can tie to the 43
    # the rest of the page talks about.
    terms = one("""SELECT count(DISTINCT employee_key) AS n
                     FROM v_labor_effective
                    WHERE period = %s AND employee_key NOT IN
                      (SELECT employee_key FROM employment)""", (PERIOD,))
    if terms and terms["n"]:
        w(f"- **{terms['n']} people have no employment terms on the record**, "
          "so no timesheet draft can be built for them — there is no "
          "denominator to divide. That is the roster reply.\n")
    certs = one("""SELECT count(*) AS n FROM v_certification_status
                    WHERE period = %s AND NOT certified""", (PERIOD,))
    if certs and certs["n"]:
        w(f"- **{certs['n']} of the payroll have not certified their 2025 "
          "effort** under 200.430(i). Theirs to sign and nobody else's. It "
          "moves no figure in the rate; it moves whether the direct labour "
          "charge is supportable.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set.")
    open_pool()

    out: list[str] = []
    w = out.append
    w(f"# Run sheet — {PERIOD} close\n")
    w(f"*Generated from the record by `scripts/stage_the_run.py` on "
      f"{dt.date.today():%d %B %Y}. Nothing here has been done on anybody's "
      f"behalf.*\n")
    w("Four acts are staged and deliberately not performed, because each is a "
      "judgment with a person's name on it: **accepting a measurement**, "
      "**determining a relationship**, **sealing or certifying**, and "
      "**anything sent to a sponsor**.\n")
    w("---\n")
    heidi(w)
    w("---\n")
    tom(w)
    w("---\n")
    waiting(w)
    w("---\n")
    w("## The order it has to go in\n")
    w("1. **Heidi answers the three rows** and accepts the floor plan. "
      "Everything about the rate waits behind this.\n")
    w("2. **Tom determines the six parties.** Independent of the space — it "
      "can happen in parallel.\n")
    w("3. **Tom resolves the depreciation `PENDING`**, which needs a withdraw "
      "and an unseal.\n")
    w("4. **Recompute, re-seal, re-certify** on whatever the answers produce.\n")
    w("5. **Recompute the restatements** against the new rate, and only then "
      "does anything go to NCDMM.\n")

    text = "\n".join(out) + "\n"
    if args.write:
        OUT.write_text(text)
        print(f"wrote {OUT}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
