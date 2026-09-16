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


def steps(w):
    """A numbered heading that counts what actually printed.

    Every section on this sheet is conditional, so a number written beside one
    is wrong the first time that section does not print — and Tom's already
    read 1, 2, 3, **5** on a record with no overtaken restatement. A reader
    who meets a missing 4 reasonably assumes there is a step nobody wrote
    down, which on a run sheet is the worst thing it can say.
    """
    n = 0

    def head(text: str) -> None:
        nonlocal n
        n += 1
        w(f"### {n}. {text}\n")
    return head


def heidi(w) -> None:
    w("## Heidi — facilities and inventory\n")
    head = steps(w)

    req = one("""SELECT request_id, form_version, state::text AS state,
                        received_from
                   FROM information_request
                  WHERE period = %s AND form = 'SPACE_INVENTORY'
                  ORDER BY issued_at DESC LIMIT 1""", (PERIOD,))
    if req and req["state"] == "ISSUED":
        # A second pass. The workbook carries her own floor plan back with
        # every column filled in, so the ask is the two columns that are new
        # — which is the whole reason it is a second workbook rather than an
        # email asking her to look at twenty-six rows again.
        head(f"The floor-space workbook, version {req['form_version']}")
        w(f"`/requests` → request {req['request_id']} → **Download**. It is "
          "your own floor plan, filled in — the ask is two columns.\n")
        w("**What it is used for.** Version 1 explained TENANT as *leased to "
          "a third party*, which is true of a portfolio company paying rent, "
          "so all twenty-six tenancies came back TENANT and every one of them "
          "left the federal pool. The question is not whether they pay rent. "
          "It is whether YBI is letting the space commercially — a "
          "manufacturer, an unrelated business — or **housing a client "
          "company as part of what a programme does for them**, which is "
          "incubation and not property. Steelite in two buildings and "
          "America Makes are the ones nobody argues about; the small suites "
          "in YBI Main and Tech Block 5 are the question.\n")
        w("**The agreement that says which.** A commercial lease, or an "
          "incubation or residency agreement. Blank is a fine answer and "
          "means nobody has read one — it is never taken as a claim that "
          "none exists. A paid tenancy called programme space with nothing "
          "named is refused, because that is the reading that moves the "
          "rate.\n")
        w("**It is worth 2.72 points of combined rate** with the client "
          "companies' rent credited under 200.406, and it is the largest "
          "single reading still open. `docs/RATE_HEADROOM_2025.md` §2a lists "
          "all twenty-four occupants with what the analysis assumed, and "
          "some of those assumptions are plainly wrong — a maintenance "
          "contractor, a charity, an appraiser. The agreements decide it, "
          "not the suite number.\n")
        w("**And the rows held back last time come back in it**, each "
          "carrying what the intake could not read, so they are answered in "
          "the same sitting rather than tracked separately.\n")
        head("Send it back, and then accept it")
        w("Same screen: **Reply**, then **What it says**, then **Accept**. "
          "Until it is accepted the measurement is filed as evidence and "
          "**no register has it** — it moves no figure at all. It is the "
          "single largest adjustment in the rate model.\n")
        derived = query("""SELECT f.name, count(*) AS units,
                                  sum(u.usable_sqft) AS sqft
                             FROM space_unit u
                             JOIN facility f ON f.facility_id = u.facility_id
                            WHERE u.period = %s
                            GROUP BY f.name ORDER BY f.name""", (PERIOD,))
        if derived:
            w("**Read *What it says* before you accept, and read the "
              "*what it will land on* panel.** The register already carries "
              "an estate derived from the documents while we waited for "
              "yours, and accepting **adds** to it rather than replacing "
              "it — driven on a copy of this record, that turned five "
              "buildings into nine and left one carrying twice its own floor "
              "area, with the 200.465 carve-out taken over the result. What "
              "is there now:\n")
            w("| building | rows | sq ft |")
            w("| --- | ---: | ---: |")
            for x in derived:
                w(f"| {x['name']} | {x['units']} | {money(x['sqft'])} |")
            w("\nThe rows these replace come off first. The panel names them "
              "building by building, and a building you name under a "
              "different spelling is created beside the one you meant rather "
              "than corrected.\n")
    elif req and req["state"] == "RECEIVED":
        head("Three rows of your own floor plan cannot be read")
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
        head("Then accept it")
        w("Same screen, **Accept**. Until you do, the measurement is filed as "
          "evidence and **no register has it** — it moves no figure at all. "
          "It is the single largest adjustment in the rate model.\n")
    elif req:
        head("The floor plan")
        w(f"Request {req['request_id']} is {req['state'].lower()}.\n")

    # Only where no workbook is out. While one is, the roster to work
    # through is *in it*, suite by suite, and the register holds whatever
    # coarser rows were derived while waiting — five lumped "let and
    # committed" rows on this record against twenty-six real tenancies. A
    # count off the register would say five things to do where the job is
    # twenty-six, which is two true figures about one thing on one page.
    basis = one("SELECT * FROM v_tenancy_basis_check WHERE period = %s",
                (PERIOD,))
    outstanding = req and req["state"] in ("ISSUED", "RECEIVED")
    if basis and basis["state"] == "OPEN" and not outstanding:
        head("Charged space that names no agreement")
        w(f"{basis['charged_units']:,} charged space(s) are on the register "
          f"and {basis['named_units']:,} name the agreement that settles "
          "whether the occupant is a commercial tenant or a client company "
          "in residence. `/classify/space`, or the workbook above.\n")

    unmeasured = one("""SELECT count(*) AS n FROM facility f
                         WHERE NOT EXISTS (SELECT 1 FROM space_unit u
                                            WHERE u.facility_id = f.facility_id
                                              AND u.period = %s)""", (PERIOD,))
    if unmeasured and unmeasured["n"]:
        head("Buildings with no space recorded")
        w(f"{unmeasured['n']} of them. `/classify/space`.\n")

    acc = one("""SELECT count(*) AS n FROM asset
                  WHERE access = 'INTERNAL'""")
    if acc and acc["n"]:
        head("Which machines are lent out, and on what terms")
        w(f"All {acc['n']:,} assets read `INTERNAL`, which is the column's "
          "default and not an answer anybody gave. Nothing has ever written "
          "it, so `v_equipment_subsidy` can only report zero given "
          "equipment. `/classify/assets`.\n")


def tom(w) -> None:
    w("## Tom — controller\n")
    head = steps(w)

    rows = query("""SELECT payee, objective_id, amount, at_stake
                      FROM v_subaward_exposure
                     WHERE period = %s AND determination = 'UNDETERMINED'
                     ORDER BY at_stake DESC""", (PERIOD,))
    if rows:
        stake = sum((D(str(x["at_stake"])) for x in rows), D(0))
        head("Contractor or subrecipient — six determinations")
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
        head(f"{money(x['amt'])} of {x['pool']} is still `PENDING`")
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
    head("The rate that stands, and the one the analysis supports")
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
        head("Restatements measured against a register that has moved")
        for x in stale:
            w(f"- **{x['objective_id']}** measured {x['invoices']} invoice(s); "
              f"the register holds {x['register_invoices']}. Recompute before "
              "anything goes to a sponsor.\n")

    cites = one("""SELECT count(*) AS n FROM v_worklist
                    WHERE kind = 'NEEDS_EVIDENCE'""")
    if cites and cites["n"]:
        head(f"{cites['n']:,} judgments cite no document")
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
    w("1. **Heidi answers the floor-space workbook** — the tenancy question, "
      "the agreement behind each answer, and the rows held back last time — "
      "and it is accepted. Everything about the rate waits behind this.\n")
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
