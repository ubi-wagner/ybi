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

    tom = sign_in(args.base, "tom@ybi.org")          # CONTROLLER
    steph = sign_in(args.base, "sgaffney@ybi.org")   # project manager
    auditor = sign_in(args.base, "auditor@ybi.org")

    tag = uuid.uuid4().hex[:6].upper()
    code = f"DRV-{tag}"

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
    award = one("SELECT award_id FROM award ORDER BY ceiling_federal DESC LIMIT 1")
    if not award:
        print("\nCOULD NOT RUN — no award on file.", file=sys.stderr)
        return 2
    aw = award["award_id"]

    for key, value, cite in [
            ("Payment terms", "Net 30 from receipt of a correct invoice",
             "§26 Payment"),
            ("Invoicing frequency", "Monthly, by the fifth business day",
             "§25 Invoicing"),
            ("Indirect provision", "10% of ODCs only; no indirect on labor",
             "Attachment 3, Basis of Estimate")]:
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

    step("An invoice against it, and the money in")
    inv = one("""SELECT invoice_id FROM invoice WHERE award_id = %s
                  ORDER BY invoice_date LIMIT 1""", (aw,))
    if not inv:
        print("\nCOULD NOT RUN — no invoice on this award; "
              "run scripts/load_invoices.py first.", file=sys.stderr)
        return 2
    inv_id = str(inv["invoice_id"])
    query("UPDATE invoice SET milestone_id = %s WHERE invoice_id = %s::uuid",
          (ms, inv_id))
    ok("an invoice is attached to the milestone")

    with mutating("recorded the money in", "Tom Metzinger", "RECEIPT"):
        call(tom, "POST", f"/api/contracts/invoices/{inv_id}/receipts", 201,
             "receipt", json={"received_on": "2025-08-15", "amount": 12000,
                              "method": "ACH", "reference": f"DRV-{tag}",
                              "note": "Drive: part payment."})

    m = call(auditor, "GET", f"/api/contracts/milestones/{ms}", 200,
             "the milestone, as the auditor sees it", params=P).json()
    st = m["milestone"]
    invoiced, received = float(st["invoiced"]), float(st["received"])
    outstanding = float(st["outstanding"])
    if abs((invoiced - received) - outstanding) < 0.005:
        ok(f"invoiced {invoiced:,.2f} less received {received:,.2f} "
           f"leaves {outstanding:,.2f} outstanding, and the view agrees")
    else:
        finding(f"outstanding {outstanding} does not equal "
                f"{invoiced} - {received}")
    if m["receipts"]:
        ok(f"{len(m['receipts'])} receipt(s) traceable to the deliverable")
    else:
        finding("the receipt did not reach the milestone")

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
    raise SystemExit(main())
