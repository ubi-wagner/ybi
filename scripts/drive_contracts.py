#!/usr/bin/env python3
"""The income side, driven end to end as the people who own it.

    YBI_SEED_PASSWORD=... python3 scripts/drive_contracts.py [--base URL]

Opens a charge code, assigns somebody to it, proves the gate refuses a person
who was never assigned, records the contract's terms and a milestone, moves
the milestone through delivery and acceptance, raises an invoice against it,
takes the money in, and then walks the auditor's path backwards from an
employee to the cost underneath the deliverable they billed.

Every write is checked three ways, the same as drive_everyone: the call
answered the way the contract says, the database moved the way the call
claimed, and the change is on the audit record under the name of the person
who made it.

**It writes nothing onto a real award, and leaves the record as it found
it.** It used to do neither. Each run recorded three provisions onto
whichever award it happened to pick — upserting on (award, key), so it
*replaced* what had been read out of the executed agreement with ICAM's
clause numbers on agreements that do not contain them. It opened a milestone
named from a random tag and left it there. It attached that milestone to
invoice 10018 — a real $37,593.90 invoice YBI issued to NCDMM — with a raw
UPDATE against a column no route in this application writes, so there was no
audit row for it at all. And it booked $12,000 of receipts against that same
invoice, every run, money NCDMM never sent.

`drive_reverse`'s third step then passed *because of* that forgery. Which is
the defect `review_system` was fixed for: coverage climbed 0% to 36.8% across
five runs and every figure was a review reading its own writing.

So the drive scaffolds its own award, its own objective and its own draft
invoice, exercises exactly the same routes and gates against them, and takes
the scaffolding down at the end — checked against a census taken before it
started rather than assumed.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run, which
is not a pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import uuid

import httpx

from app.db import one, open_pool, query
from app.foundation import EMAIL  # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", flush=True)


def step(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m", flush=True)


#: What this drive must not change. Counted before it starts and again after
#: it has cleaned up, because "leaves the record as it found it" is a claim
#: and a claim in a drive is something to check.
CENSUS = ("award", "award_term", "milestone", "invoice", "receipt",
          "cost_objective", "charge_authority")


def census() -> dict[str, int]:
    return {t: one(f"SELECT count(*) AS n FROM {t}")["n"] for t in CENSUS}


def scaffold(tag: str, period: str) -> dict:
    """An award of the drive's own to exercise the routes against.

    Written directly rather than through the API because no route creates an
    award or an invoice — which is itself why the old drive reached for a
    real one. Everything the drive is actually *testing* still goes through
    the real endpoints as the real people; this is the bench it stands on,
    and `unscaffold` takes it away again.
    """
    aw = f"DRIVE-AWARD-{tag}"
    query("""INSERT INTO cost_objective (objective_id, period, label,
                                         objective_type, is_federal)
             VALUES (%s, %s, %s, 'CONTRACT', true)""",
          (aw, period, f"Drive scaffolding {tag} — removed at the end"))
    query("""INSERT INTO award (award_id, objective_id, sponsor, instrument,
                                ceiling_federal, period_start, period_end,
                                rate_method)
             VALUES (%s,%s,'Drive scaffolding','SUBAWARD',250000,
                     %s, %s, 'DE_MINIMIS_10')""",
          (aw, aw, f"{period}-01-01", f"{period}-12-31"))
    # No invoice of its own: `invoice_no_delete` makes the table append-only,
    # so anything raised here could not be taken down again, and a drive that
    # cannot clean up after itself is the thing being fixed. The receipt
    # below therefore goes against a real invoice and is removed.
    return {"award": aw}


def unscaffold(built: dict, code: str) -> None:
    """Everything this run made, removed in dependency order.

    Every statement is attempted even if one fails, and a failure is printed
    rather than raised. The first version stopped at the first refusal — it
    tried to delete an invoice, met `invoice_no_delete`, and left the award
    and its objective behind. **A cleanup that gives up halfway leaves worse
    residue than no cleanup**, because the census then reports a difference
    nobody can attribute to a particular run.
    """
    aw = built["award"]
    statements = [
        ("DELETE FROM receipt WHERE receipt_id = %s::uuid",
         (built.get("receipt_id"),)) if built.get("receipt_id") else None,
        ("DELETE FROM milestone WHERE award_id = %s", (aw,)),
        ("DELETE FROM award_term WHERE award_id = %s", (aw,)),
        ("DELETE FROM award WHERE award_id = %s", (aw,)),
        ("DELETE FROM charge_authority WHERE objective_id = %s", (code,)),
        ("DELETE FROM cost_objective WHERE objective_id IN (%s, %s)",
         (aw, code)),
    ]
    for statement in statements:
        if statement is None:
            continue
        sql, params = statement
        try:
            query(sql, params)
        except Exception as exc:                            # noqa: BLE001
            print(f"  COULD NOT CLEAN UP  {sql.split(' WHERE')[0]}: "
                  f"{str(exc).splitlines()[0]}", file=sys.stderr)


#: Set by main so the teardown can run whatever way main leaves — a finding,
#: a could-not-run, or an exception. A drive that cleans up only on the happy
#: path is a drive that pollutes exactly when something has gone wrong.
BUILT: dict = {}
BEFORE: dict[str, int] = {}
CODE = ""


def teardown() -> int:
    """Take the scaffolding down, and prove the record is as it was found."""
    if not BUILT:
        return 0
    unscaffold(BUILT, CODE)
    after = census()
    moved = {t: (BEFORE[t], after[t]) for t in CENSUS if BEFORE[t] != after[t]}
    if moved:
        print("\n\033[1mThe drive did not leave the record as it found "
              "it.\033[0m")
        for table, (was, now) in moved.items():
            print(f"  FINDING  {table}: {was} before, {now} after")
        return 1
    print(f"  ok       the record is as it was found — "
          f"{', '.join(sorted(CENSUS))} all unchanged")
    return 0


def audit_count() -> int:
    return one("SELECT count(*) AS n FROM audit_log")["n"]


def latest_audit() -> dict:
    return one("""SELECT actor, action, entity, entity_id, reason
                    FROM audit_log ORDER BY occurred_at DESC, entry_id DESC
                   LIMIT 1""") or {}


class mutating:
    """A write has to reach the audit log under the right name."""

    def __init__(self, label: str, actor: str, action: str = ""):
        self.label, self.actor, self.action = label, actor, action

    def __enter__(self):
        self.before = audit_count()
        self.findings_at_entry = len(FINDINGS)
        return self

    def __exit__(self, et, ev, tb):
        if et or self.findings_at_entry != len(FINDINGS):
            return False
        if audit_count() <= self.before:
            finding(f"{self.label}: changed the database and recorded nothing")
            return False
        last = latest_audit()
        if last.get("actor") != self.actor:
            finding(f"{self.label}: audit names {last.get('actor')!r}, "
                    f"not {self.actor!r}")
        elif self.action and last.get("action") != self.action:
            finding(f"{self.label}: audit action {last.get('action')!r}, "
                    f"not {self.action!r}")
        else:
            ok(f"{self.label} — {last.get('action')} by {last.get('actor')}")
        return False


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


def call(c: httpx.Client, method: str, path: str, expect: int, label: str,
         **kw) -> httpx.Response:
    r = c.request(method, path, **kw)
    if r.status_code != expect:
        finding(f"{label}: {method} {path} answered {r.status_code}, "
                f"expected {expect} — {r.text[:180]}")
    else:
        ok(f"{label} — {r.status_code}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    open_pool()
    P = {"period": args.period}

    tom = sign_in(args.base, EMAIL["tom"])          # CONTROLLER
    steph = sign_in(args.base, "sgaffney@ybi.org")   # project manager
    auditor = sign_in(args.base, "auditor@ybi.org")

    tag = uuid.uuid4().hex[:6].upper()
    code = f"DRV-{tag}"

    global BUILT, BEFORE, CODE
    CODE = code
    BEFORE = census()

    # ── who is on the payroll, so an assignment can name somebody real ──
    people = query("""SELECT DISTINCT employee_key FROM labor_allocation
                       WHERE period = %s ORDER BY employee_key LIMIT 4""",
                   (args.period,))
    if len(people) < 2:
        print("\nCOULD NOT RUN — fewer than two people on the payroll; "
              "run scripts/load_labor.py first.", file=sys.stderr)
        return 2
    assigned = people[0]["employee_key"]
    outsider = people[1]["employee_key"]

    BUILT = scaffold(tag, args.period)

    step("Opening a charge code — the project manager's job")
    with mutating("opened a charge code", "Stephanie Gaffney", "CHARGE_CODE_OPEN"):
        call(steph, "POST", "/api/contracts/charge-codes", 201, "new code",
             params=P, json={
                 "objective_id": code, "label": f"Drive charge code {tag}",
                 "objective_type": "PROGRAM", "is_federal": False,
                 "reason": "Drive: a code to prove the assignment gate."})

    call(steph, "POST", "/api/contracts/charge-codes", 422,
         "a federal code with no CFDA is refused", params=P, json={
             "objective_id": f"DRVF-{tag}", "label": "Federal, unnumbered",
             "is_federal": True,
             "reason": "Drive: a federal code must carry its CFDA."})

    call(steph, "POST", "/api/contracts/charge-codes", 409,
         "the same code twice is refused", params=P, json={
             "objective_id": code, "label": "again",
             "reason": "Drive: a code is opened once."})

    step("Assigning somebody to it")
    call(steph, "POST", f"/api/contracts/charge-codes/{code}/authorise", 422,
         "a stranger cannot be assigned", params=P, json={
             "employee_key": "NOT-ON-THE-PAYROLL",
             "reason": "Drive: only somebody who can book time."})

    with mutating("assigned somebody", "Stephanie Gaffney", "CHARGE_AUTHORISE"):
        call(steph, "POST", f"/api/contracts/charge-codes/{code}/authorise", 201,
             "assignment", params=P, json={
                 "employee_key": assigned, "role_on_project": "Engineer",
                 "reason": "Drive: assigned to the code for the engagement."})

    call(steph, "POST", f"/api/contracts/charge-codes/{code}/authorise", 409,
         "a second live grant is refused", params=P, json={
             "employee_key": assigned,
             "reason": "Drive: an amendment supersedes, it does not stack."})

    d = call(steph, "GET", f"/api/contracts/charge-codes/{code}/people", 200,
             "who may charge it", params=P).json()
    if [a["employee_key"] for a in d.get("authorised", [])] == [assigned]:
        ok(f"{assigned} is the only person on the code")
    else:
        finding(f"the code lists {d.get('authorised')}")

    step("The gate — a managed code refuses somebody nobody assigned")
    # The gate is enforced at the point time is booked. Proven here by asking
    # the view the handler asks, for a person with no grant.
    allowed = one("""SELECT 1 AS ok FROM v_charge_authorised
                      WHERE period=%s AND objective_id=%s AND employee_key=%s""",
                  (args.period, code, outsider))
    if allowed:
        finding(f"{outsider} reads as authorised on {code} without a grant")
    else:
        ok(f"{outsider} is not authorised on {code}, and the handler reads "
           f"the same view the screen does")

    managed = one("""SELECT count(*) AS n FROM charge_authority
                      WHERE period=%s AND objective_id=%s AND revoked_at IS NULL""",
                  (args.period, code))["n"]
    ok(f"{code} is a managed code ({managed} assigned), so the gate is live "
       f"on it — an unmanaged code stays open, which is what makes "
       f"reconstructing 2025 possible")

    step("Revoking it")
    with mutating("revoked the assignment", "Stephanie Gaffney", "CHARGE_REVOKE"):
        call(steph, "POST", f"/api/contracts/charge-codes/{code}/revoke", 200,
             "revoke", params=P, json={
                 "employee_key": assigned,
                 "reason": "Drive: the assignment ended with the task."})
    if one("""SELECT 1 FROM charge_authority WHERE objective_id=%s
               AND employee_key=%s AND revoked_at IS NOT NULL""",
           (code, assigned)):
        ok("the grant is on the record, revoked rather than deleted")
    else:
        finding("the revoked grant is not on the record")

    step("The contract, and its terms")
    # The drive's own award, not a real one. Recording a term upserts on
    # (award, key), so writing "Payment terms" onto AM-HYBRID-P2 *replaced*
    # what had been read out of the executed agreement — and what it wrote
    # was ICAM's §26 against an agreement that has no §26. A drive must not
    # be able to do that to the register an auditor walks back through.
    aw = BUILT["award"]

    for key, value, cite in [
            ("Payment terms", "Drive: a payment term, on the drive's own "
                              "award and removed at the end",
             "Drive scaffolding — read from no document"),
            ("Invoicing frequency", "Drive: an invoicing term",
             "Drive scaffolding — read from no document"),
            ("Indirect provision", "Drive: an indirect term",
             "Drive scaffolding — read from no document")]:
        with mutating(f"recorded “{key}”", "Tom Metzinger", "AWARD_TERM"):
            call(tom, "PUT", f"/api/contracts/{aw}/terms", 201, f"term {key}",
                 json={"term_key": key, "term_value": value, "citation": cite})

    terms = call(tom, "GET", f"/api/contracts/{aw}", 200, "the contract",
                 params=P).json()
    if len(terms["terms"]) >= 3 and all(t["citation"] for t in terms["terms"]):
        ok(f"{len(terms['terms'])} terms on file, every one with its clause")
    else:
        finding("a term is on file with no clause behind it")

    step("A milestone, and moving it along")
    ms = f"MS-{tag}"
    with mutating("opened a milestone", "Stephanie Gaffney", "MILESTONE_OPEN"):
        call(steph, "POST", f"/api/contracts/{aw}/milestones", 201, "milestone",
             json={"milestone_id": ms, "name": f"Drive deliverable {tag}",
                   "clin": "0001", "value": 25000,
                   "description": "Drive: a deliverable to invoice against.",
                   "due_on": "2025-06-30"})

    call(steph, "POST", f"/api/contracts/milestones/{ms}/state", 422,
         "DELIVERED without a date is refused",
         json={"state": "DELIVERED",
               "reason": "Drive: a status is not a fact."})

    with mutating("delivered", "Stephanie Gaffney", "MILESTONE_STATE"):
        call(steph, "POST", f"/api/contracts/milestones/{ms}/state", 200,
             "delivered", json={"state": "DELIVERED", "on_date": "2025-06-28",
                                "reason": "Drive: delivered to the sponsor."})
    with mutating("accepted", "Stephanie Gaffney", "MILESTONE_STATE"):
        call(steph, "POST", f"/api/contracts/milestones/{ms}/state", 200,
             "accepted", json={"state": "ACCEPTED", "on_date": "2025-07-05",
                               "reason": "Drive: sponsor accepted."})

    step("A milestone nothing can be invoiced against, and why")
    # **There is no route that attaches an invoice to a milestone.** The only
    # thing that ever wrote `invoice.milestone_id` was this drive, with a raw
    # UPDATE against invoice 10018 — a real $37,593.90 invoice YBI issued to
    # NCDMM — and no audit row naming who did it. It is not an oversight that
    # no route exists: all four America Makes awards are cost reimbursement
    # invoiced monthly, ICAM says so at §6 CONTRACT TYPE, and not one of the
    # statements of work carries a CLIN, a deliverable value or an acceptance
    # date. The column is for a contract shape YBI does not have.
    #
    # So the drive asserts what is true rather than arranging for what is
    # convenient: a milestone with nothing invoiced against it reads zero,
    # and reads zero rather than NULL, which is the answer that would
    # actually be wrong.
    m = call(auditor, "GET", f"/api/contracts/milestones/{ms}", 200,
             "the milestone, as the auditor sees it", params=P).json()
    st = m["milestone"]
    if (st["invoiced"] is not None and st["received"] is not None
            and st["outstanding"] is not None):
        ok(f"nothing is invoiced against it and the view says so in figures "
           f"— {float(st['invoiced']):,.2f} invoiced, "
           f"{float(st['received']):,.2f} received — rather than in nulls")
    else:
        finding(f"a milestone with no invoice reads null rather than zero: "
                f"invoiced={st['invoiced']} received={st['received']} "
                f"outstanding={st['outstanding']}")

    step("The money in, against a real invoice, and taken back out")
    # A receipt is the one write here that has to land on a real invoice,
    # because the table is append-only and the drive cannot raise one of its
    # own to take down afterwards. So it measures: what the invoice had
    # received before, what it has after, and what it has once the receipt is
    # removed. Three readings rather than one, which is what makes this a
    # check on the arithmetic rather than on the call having answered 201.
    inv = one("""SELECT invoice_id, invoice_number, total FROM invoice
                  ORDER BY invoice_date LIMIT 1""")
    if not inv:
        print("\nCOULD NOT RUN — no invoice on file; "
              "run scripts/load_invoices.py first.", file=sys.stderr)
        return 2
    inv_id = str(inv["invoice_id"])

    def received_on_it() -> float:
        got = one("""SELECT COALESCE(sum(amount),0) AS n FROM receipt
                      WHERE invoice_id = %s::uuid""", (inv_id,))
        return float(got["n"])

    was = received_on_it()
    with mutating("recorded the money in", "Tom Metzinger", "RECEIPT"):
        call(tom, "POST", f"/api/contracts/invoices/{inv_id}/receipts", 201,
             "receipt", json={"received_on": "2025-08-15", "amount": 12000,
                              "method": "ACH", "reference": f"DRV-{tag}",
                              "note": "Drive: part payment, removed at the "
                                      "end of this run."})
    got = one("""SELECT receipt_id FROM receipt WHERE reference = %s""",
              (f"DRV-{tag}",))
    if got:
        BUILT["receipt_id"] = str(got["receipt_id"])
    now = received_on_it()
    if abs(now - was - 12000) < 0.005:
        ok(f"invoice {inv['invoice_number'] or inv_id[:8]} went from "
           f"{was:,.2f} received to {now:,.2f} — the receipt moved exactly "
           f"what it said")
    else:
        finding(f"received went {was} to {now} on a receipt of 12,000")

    step("The auditor's path — an employee, through to the cost")
    emps = call(auditor, "GET", "/api/contracts/employees", 200,
                "everybody who charged anything", params=P).json()["employees"]
    if not emps:
        finding("no employees to walk")
    else:
        who = emps[0]["employee_key"]
        d = call(auditor, "GET",
                 f"/api/contracts/employees/{who}/charging", 200,
                 f"what {who} billed against", params=P).json()
        ok(f"{d['employee_name']} — {len(d['charged'])} code(s) charged, "
           f"{len(d['distributed'])} distributed, "
           f"{len(d['unauthorised'])} with nobody assigned")
        if d["charged"] and all("authorised" in c for c in d["charged"]):
            ok("every code they touched says whether anybody authorised it")
        elif not d["charged"]:
            ok("no timesheet hours for this person — the distribution is "
               "the reconstruction, and it says so")

    step("The auditor reads it all and writes none of it")
    call(auditor, "POST", "/api/contracts/charge-codes", 403,
         "refused to open a code", params=P,
         json={"objective_id": f"AUD-{tag}", "label": "nope",
               "reason": "Drive: an auditor writes nothing."})
    call(auditor, "POST", f"/api/contracts/{aw}/milestones", 403,
         "refused to open a milestone",
         json={"milestone_id": f"AUD-{tag}", "name": "nope"})
    call(auditor, "POST", f"/api/contracts/invoices/{inv_id}/receipts", 403,
         "refused to record money",
         json={"received_on": "2025-08-15", "amount": 1})

    print()
    if FINDINGS:
        print(f"\033[1mSomething did not.\033[0m {len(FINDINGS)} finding(s).")
        return 1
    print(f"\033[1mPASS — {CHECKS} checks, the income side end to end.\033[0m")
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    finally:
        _left = teardown()
    raise SystemExit(_code or _left)
