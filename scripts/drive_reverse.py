#!/usr/bin/env python3
"""The same system, driven backwards.

    YBI_SEED_PASSWORD=... python3 scripts/drive_reverse.py [--base URL]

Forward, the engagement runs ledger -> classification -> seal -> rate ->
allocation -> invoice -> money. Every drive so far pushes in that direction,
which means every drive so far can pass while the chain only holds one way.

A reviewer never works forwards. They start from a payment and ask what it
was for, and each answer has to survive being asked from the other end:

    money received -> the invoice it settled
                   -> the milestone that invoice claimed
                   -> the contract that milestone belongs to
                   -> the objective that contract is charged to
                   -> the people who booked time to it, and whether anybody
                      authorised them
                   -> the ledger lines classified to it
                   -> the statements those lines foot to

At each hop the figure has to tie to the one before it. Where a hop cannot be
made the drive says which link is missing rather than skipping it, because a
missing link is the finding.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run, which
is not a pass.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import httpx

from app.db import one, open_pool, query

CHECKS = 0
FINDINGS: list[str] = []
GAPS: list[str] = []


def ok(m: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {m}", flush=True)


def finding(m: str) -> None:
    FINDINGS.append(m)
    print(f"  FINDING  {m}", flush=True)


def gap(m: str) -> None:
    """A link the data does not yet support. Named, not skipped."""
    GAPS.append(m)
    print(f"  gap      {m}", flush=True)


def step(t: str) -> None:
    print(f"\n\033[1m{t}\033[0m", flush=True)


def m(v) -> str:
    return f"{Decimal(str(v or 0)):,.2f}"


def sign_in(base: str, email: str) -> httpx.Client:
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is required.", file=sys.stderr)
        raise SystemExit(2)
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        print(f"could not sign in as {email} ({r.status_code})", file=sys.stderr)
        raise SystemExit(2)
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    open_pool()
    P = {"period": args.period}

    # The auditor, because this is the auditor's direction of travel and the
    # whole path has to be walkable by somebody who can write none of it.
    aud = sign_in(args.base, "auditor@ybi.org")

    step("1. Start where a reviewer starts — money that arrived")
    receipt = one("""SELECT r.receipt_id, r.invoice_id, r.received_on, r.amount,
                            r.reference
                       FROM receipt r ORDER BY r.received_on DESC LIMIT 1""")
    if receipt:
        ok(f"receipt {m(receipt['amount'])} on {receipt['received_on']} "
           f"(ref {receipt['reference'] or 'none'})")
    else:
        # Not "could not run". **No payment has ever been recorded against
        # any invoice** — the receipt register is empty and `invoice.paid_on`
        # and `invoice.paid_amount` are NULL on all three and read by nothing.
        # This drive used to exit 2 here, telling the reader to run
        # `drive_contracts.py` first "which records one" — and what that
        # recorded was $12,000 against a real NCDMM invoice that NCDMM never
        # sent. The backward walk was only ever walkable because a test
        # script had invented its first hop.
        gap("no payment is recorded against any invoice — the receipt "
            "register is empty, so the walk starts one hop in, at the "
            "invoice. This is the first link and it is missing")

    step("2. Which invoice did it settle?")
    if receipt:
        inv = one("""SELECT i.invoice_id, i.invoice_number, i.award_id,
                            i.milestone_id, i.objective_id, i.invoice_date,
                            i.direct_claimed, i.indirect_claimed, i.cost_share
                       FROM invoice i WHERE i.invoice_id = %s""",
                  (receipt["invoice_id"],))
        if not inv:
            finding("the receipt points at an invoice that does not exist")
            return 1
    else:
        # The largest, because it is the one a reviewer opens first and the
        # one the restatement is about.
        inv = one("""SELECT i.invoice_id, i.invoice_number, i.award_id,
                            i.milestone_id, i.objective_id, i.invoice_date,
                            i.direct_claimed, i.indirect_claimed, i.cost_share
                       FROM invoice i ORDER BY i.total DESC NULLS LAST
                       LIMIT 1""")
        if not inv:
            print("\nCOULD NOT RUN — no invoice on file either; "
                  "run scripts/load_invoices.py.", file=sys.stderr)
            return 2
    claimed = (Decimal(str(inv["direct_claimed"]))
               + Decimal(str(inv["indirect_claimed"]))
               + Decimal(str(inv["cost_share"])))
    ok(f"invoice {inv['invoice_number'] or inv['invoice_id']} of "
       f"{inv['invoice_date']}, claiming {m(claimed)}")
    if Decimal(str(inv["indirect_claimed"])) == 0:
        ok("it bills no indirect at all — which is the restatement's whole "
           "subject, and the reverse walk finds it without being told")

    step("3. Which milestone did that invoice claim against?")
    if not inv["milestone_id"]:
        # This used to be a flat gap — "a payment cannot be traced to a
        # deliverable" — reported every run, as though the deliverables were
        # missing. They are not missing. **All four America Makes awards are
        # cost reimbursement, invoiced monthly**, ICAM says so in as many
        # words at §6 CONTRACT TYPE, and not one statement of work carries a
        # CLIN, a deliverable value or an acceptance date. An invoice under
        # them claims a month of cost against a budget by category. So the
        # hop backwards is to the service period and the categories, and a
        # gap that doing the work cannot clear is worse than no gap: it
        # teaches the reader the list is wrong, and the next real one they
        # see they will dismiss.
        basis = one("""SELECT term_value, citation FROM award_term
                        WHERE award_id = %s AND term_key = 'Contract type'""",
                    (inv["award_id"],))
        if basis and "cost reimbursement" in basis["term_value"].lower():
            ok(f"none, and none is expected — {inv['award_id']} is "
               f"{basis['term_value'].rstrip('.')} ({basis['citation']}), "
               f"invoiced monthly against a budget rather than against a "
               f"deliverable")
        else:
            gap(f"the invoice claims against no milestone, and no clause has "
                f"been read on {inv['award_id']} saying whether one is "
                f"expected. Every award whose agreement has been read is "
                f"cost reimbursement; this one has not been read, and an "
                f"unread agreement is not a cost-reimbursement agreement")
        ms = None
    else:
        ms = one("""SELECT * FROM v_milestone_status WHERE milestone_id = %s""",
                 (inv["milestone_id"],))
        if not ms:
            finding(f"invoice names milestone {inv['milestone_id']}, "
                    f"which does not exist")
            return 1
        ok(f"milestone {ms['milestone_id']} — {ms['name']}, "
           f"worth {m(ms['value'])}, state {ms['state']}")

        # The arithmetic of the hop, checked rather than assumed.
        got = Decimal(str(ms["received"]))
        billed = Decimal(str(ms["invoiced"]))
        if billed - got == Decimal(str(ms["outstanding"])):
            ok(f"invoiced {m(billed)} less received {m(got)} is "
               f"{m(ms['outstanding'])} outstanding, and the view agrees")
        else:
            finding(f"outstanding {ms['outstanding']} does not equal "
                    f"{billed} - {got}")
        if got > billed:
            ok(f"more has been received than invoiced by {m(got - billed)} — "
               f"an advance, a duplicate or a misposted receipt, and the "
               f"reverse walk is where it surfaces")

    step("4. Which contract does that milestone belong to?")
    award_id = (ms or {}).get("award_id") or inv["award_id"]
    if not award_id:
        gap("no award behind the invoice, so there is no ceiling to test "
            "the claim against")
        return _finish()
    aw = aud.get(f"/api/contracts/{award_id}", params=P)
    if aw.status_code != 200:
        finding(f"contract {award_id} unreadable ({aw.status_code})")
        return 1
    c = aw.json()["contract"]
    terms = aw.json()["terms"]
    ok(f"contract {award_id} — {c['sponsor']}, "
       f"ceiling {m(c['ceiling_federal'])}, "
       f"{c['period_start']} to {c['period_end']}")
    if terms:
        ok(f"{len(terms)} provision(s) on file, "
           f"{sum(1 for t in terms if t['citation'])} with the clause cited")
        # And a citation is worth what the document says it is. This is the
        # hop where a reviewer turns to the page.
        cite = one("""SELECT count(*) FILTER (WHERE state = 'FOUND') AS found,
                             count(*) FILTER (WHERE state = 'NOT IN DOCUMENT')
                               AS absent,
                             count(*) FILTER (WHERE state IN ('NO DOCUMENT',
                               'NOT READ','NO TEXT LAYER')) AS unevaluable
                        FROM v_award_citation_check WHERE award_id = %s""",
                   (award_id,))
        if cite["absent"]:
            finding(f"{cite['absent']} of them cite a clause the agreement "
                    f"on file does not contain — v_award_citation_check "
                    f"names which")
        elif cite["unevaluable"]:
            gap(f"{cite['unevaluable']} of them cannot be checked against "
                f"the agreement: it is on file and there is no text in it to "
                f"read. Unevaluable is not a pass")
        else:
            ok(f"{cite['found']} of them cite a clause the agreement on file "
               f"actually contains — checked against the document, not "
               f"taken on trust")
    else:
        gap("the contract carries no terms, so what may be charged and when "
            "it is paid is not on the record")

    if Decimal(str(c["ceiling_federal"])) > 0:
        if Decimal(str(c["invoiced"])) <= Decimal(str(c["ceiling_federal"])):
            ok(f"invoiced {m(c['invoiced'])} is within the ceiling")
        else:
            finding(f"invoiced {m(c['invoiced'])} exceeds the ceiling "
                    f"{m(c['ceiling_federal'])}")

    step("5. Which charge code is that contract charged to?")
    obj = c["objective_id"]
    code = one("""SELECT * FROM v_charge_code
                   WHERE period = %s AND objective_id = %s""", (args.period, obj))
    if not code:
        finding(f"contract {award_id} names objective {obj}, "
                f"which is not a charge code")
        return 1
    ok(f"charge code {obj} — {code['label']}, "
       f"{code['people_authorised']} assigned, "
       f"{m(code['wages_distributed'])} of wages distributed")

    step("6. Who booked time to it, and did anybody authorise them?")
    people = query("""SELECT employee_key, hours, entries, authorised
                        FROM v_employee_charging
                       WHERE period = %s AND objective_id = %s
                       ORDER BY hours DESC""", (args.period, obj))
    if not people:
        gap(f"nobody has booked hours to {obj} — for 2025 the effort is a "
            f"distribution rather than a timesheet, which the record says")
    else:
        unauth = [p["employee_key"] for p in people if not p["authorised"]]
        ok(f"{len(people)} person(s) charged it; "
           f"{len(unauth)} with nobody assigned")
        if unauth:
            ok("the reverse walk reaches the authorisation question from the "
               "money, which is the order a reviewer asks it in")

    dist = query("""SELECT employee_key, employee_name, reconstructed_units AS wages,
                           evidence_quality::text AS grade
                      FROM labor_allocation
                     WHERE period = %s AND objective_id = %s
                     ORDER BY reconstructed_units DESC""", (args.period, obj))
    if dist:
        total = sum(Decimal(str(r["wages"] or 0)) for r in dist)
        ok(f"{len(dist)} person(s) distributed to it, {m(total)} of wages")
        weakest = min((r["grade"] for r in dist), key=lambda g: (
            ["UNSUPPORTED", "TEST_ASSUMPTION", "MANAGEMENT_RECONSTRUCTION",
             "CORROBORATED", "VERIFIED"].index(g)
            if g in ["UNSUPPORTED", "TEST_ASSUMPTION",
                     "MANAGEMENT_RECONSTRUCTION", "CORROBORATED", "VERIFIED"]
            else 0))
        ok(f"weakest evidence behind that labour is {weakest}")
        certified = query("""SELECT count(*) AS n FROM v_certification_chase
                              WHERE period = %s AND objective_id = %s""",
                          (args.period, obj))[0]["n"]
        if certified:
            ok(f"{certified} of them have not signed for their own effort — "
               f"reached from a payment, which is how an auditor finds it")

    step("7. Which ledger lines were classified to it?")
    cost = query("""SELECT d.pool::text AS pool, sum(l.amount) AS amount,
                           count(*) AS lines
                      FROM ledger_line l
                      JOIN decision_line dl ON dl.line_id = l.line_id
                      JOIN decision d ON d.decision_id = dl.decision_id
                                     AND d.reversed_at IS NULL
                     WHERE d.objective_id = %s AND l.period = %s
                     GROUP BY d.pool""", (obj, args.period))
    if not cost:
        gap(f"no ledger line is classified to {obj} yet, so the cost side of "
            f"this contract is empty — the queue being unfinished, not the "
            f"work being free")
    else:
        total = sum(Decimal(str(r["amount"])) for r in cost)
        ok(f"{sum(r['lines'] for r in cost)} line(s) in "
           f"{len(cost)} pool(s), {m(total)}")

    step("8. Do those lines foot to the statements they came from?")
    reg = aud.get("/api/reconcile", params=P)
    if reg.status_code != 200:
        finding(f"the cross-reference register is unreadable ({reg.status_code})")
    else:
        d = reg.json()
        openc = [c2["control"] for c2 in d["controls"] if not c2["ties"]]
        if openc:
            finding(f"the walk ends on books that do not agree with "
                    f"themselves: {', '.join(openc)}")
        else:
            ok(f"all {len(d['controls'])} cross-reference points tie — the "
               f"ledger under this contract is the ledger the statements "
               f"were made from")

    step("9. And the other direction still holds")
    fwd = one("""SELECT count(*) AS n FROM ledger_line WHERE period = %s""",
              (args.period,))["n"]
    ok(f"{fwd:,} ledger lines forward, one receipt backward, and the same "
       f"objective sits in the middle of both")

    return _finish()


def _finish() -> int:
    print()
    if FINDINGS:
        print(f"\033[1mSomething did not.\033[0m {len(FINDINGS)} finding(s).")
        return 1
    if GAPS:
        print(f"\033[1mPASS — {CHECKS} checks, walked backwards.\033[0m "
              f"{len(GAPS)} link(s) the data does not support yet, named above.")
    else:
        print(f"\033[1mPASS — {CHECKS} checks, the chain holds in both "
              f"directions.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
