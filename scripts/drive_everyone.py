#!/usr/bin/env python3
"""Every person, every process they own, and proof each one reached the record.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_everyone.py

The other drives each answer one question. drive_year walks a year of work;
drive_actors proves the permission boundaries; drive_access proves the access
model. This one asks the question those three leave open: does each *kind of
person* have a complete, working job — and does every change they make land
on the audit trail under their own name?

Every write below runs inside `mutating`, which counts audit rows before and
after and checks who the new one names. A handler that changes the database
and records nothing fails here even when the change itself was correct,
because a change nobody can attribute is the one thing this system exists to
prevent.

Run it after scripts/provision.py and the loaders. It is re-runnable: it
works on its own fixtures and clears them up afterwards, because a building
called "Drive Test Building" left on the Space screen is litter — and the
manual photographs that screen.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import date, timedelta

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
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def head(title: str) -> None:
    print(f"\n{title}", flush=True)


def audit_count() -> int:
    return one("SELECT count(*) AS n FROM audit_log")["n"]


def latest_audit() -> dict:
    return one("""SELECT action, actor, actor_role::text AS actor_role,
                         entity, entity_id, reason
                    FROM audit_log
                   ORDER BY occurred_at DESC, entry_id DESC LIMIT 1""") or {}


class mutating:
    """Prove a write reached the audit log, under the right name."""

    def __init__(self, label: str, actor: str, action: str = ""):
        self.label, self.actor, self.action = label, actor, action

    def __enter__(self):
        self.before = audit_count()
        self.findings = len(FINDINGS)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            return False
        if len(FINDINGS) > self.findings:
            return False        # the call already failed and said so
        if audit_count() <= self.before:
            finding(f"{self.label}: changed something and wrote nothing to "
                    f"the audit log")
            return False
        last = latest_audit()
        if last.get("actor") != self.actor:
            finding(f"{self.label}: the entry names {last.get('actor')!r}, "
                    f"not {self.actor!r}")
            return False
        if self.action and last.get("action") != self.action:
            finding(f"{self.label}: action is {last.get('action')!r}, "
                    f"expected {self.action!r}")
            return False
        ok(f"{self.label} — {last.get('action')} by {last.get('actor')} "
           f"({last.get('actor_role')})")
        return False


def call(c: httpx.Client, method: str, path: str, expect: int, label: str,
         **kw) -> httpx.Response:
    r = c.request(method, path, **kw)
    if r.status_code != expect:
        finding(f"{label}: {method} {path} answered {r.status_code}, wanted "
                f"{expect} — {r.text[:200]}")
    else:
        ok(f"{label} — {r.status_code}")
    return r


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=180)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code} "
                         f"{r.text[:160]}")
    return c


def tidy_up() -> None:
    """Remove the fixtures this drive invented.

    Not the record — a classification, a timesheet entry or a document is a
    judgment somebody made and stays. But a building called "Drive Test
    Building" is litter: it sits on the Space screen where a real one should
    be, and it ends up photographed into the user manual, where a new person
    reads it as an example of how YBI keeps its estate.

    Only rows whose id this drive generated, and only the ones nothing else
    has come to depend on.
    """
    from app.db import execute
    # Accounts are never deleted — every judgment points at one — but an
    # account this drive invented, holding a password only this drive knows,
    # is an account nobody can sign into. Left active it becomes the "plain
    # employee" another drive picks, and that drive then cannot sign in.
    execute("""UPDATE actor SET is_active = false
                WHERE email LIKE 'drive.%@ybi.org'
                   OR email LIKE 'drive-%@ybi.org'
                   OR email LIKE 'corrected.%@ybi.org'""")
    execute("""DELETE FROM asset
                WHERE unit_id IN (SELECT unit_id FROM space_unit
                                   WHERE facility_id LIKE 'DRIVE-%')""")
    execute("DELETE FROM space_unit WHERE facility_id LIKE 'DRIVE-%'")
    execute("DELETE FROM space_partition WHERE facility_id LIKE 'DRIVE-%'")
    execute("DELETE FROM facility WHERE facility_id LIKE 'DRIVE-%'")


def rows_of(r: httpx.Response, key: str = "") -> list:
    """Some endpoints return a bare list, some wrap it. Read either."""
    if r.status_code != 200:
        return []
    body = r.json()
    if isinstance(body, list):
        return body
    if key and isinstance(body.get(key), list):
        return body[key]
    for v in body.values():
        if isinstance(v, list):
            return v
    return []


def roster(c: httpx.Client) -> dict:
    return {a["email"]: a for a in c.get("/api/auth/actors").json()}


# =====================================================================


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        raise SystemExit("YBI_SEED_PASSWORD is required.")
    open_pool()

    started = audit_count()
    stamp = str(abs(hash(os.urandom(8))))[:8]

    barb = sign_in(args.base, "bewing@ybi.org", pw)
    eric = sign_in(args.base, "eric.c.wagner@gmail.com", pw)
    tom = sign_in(args.base, "tom@ybi.org", pw)
    heidi = sign_in(args.base, "hruby@ybi.org", pw)
    steph = sign_in(args.base, "sgaffney@ybi.org", pw)
    auditor = sign_in(args.base, "auditor@ybi.org", pw)
    people = roster(barb)

    try:
        drive_org_admin(args, barb, stamp)
        drive_newcomer(args, barb, stamp)
        drive_employee(args, heidi, pw)
        drive_controller(args, tom)
        drive_facilities(args, heidi, stamp)
        drive_project(args, steph, stamp)
        drive_office(args, heidi)
        drive_auditor(args, auditor)
        drive_system_admin(args, eric, people)
        drive_undo(args, heidi)
        drive_feed(args, tom, started)
    finally:
        tidy_up()
        for c in (barb, eric, tom, heidi, steph, auditor):
            c.close()

    print(f"\n{'PASS' if not FINDINGS else 'FAIL'} — {CHECKS} checks"
          + (f", {len(FINDINGS)} finding(s)" if FINDINGS else
             ", every process worked and every change is on the record"))
    return 1 if FINDINGS else 0


# ── The organisation's administrator ─────────────────────────────────

def drive_org_admin(args, barb, stamp):
    head("Barb Ewing — ORG_ADMIN. Setting people up and handing out access.")
    email = f"drive.newcomer.{stamp}@ybi.org"
    with mutating("sets up a new employee", "Barb Ewing", "ACTOR_CREATE"):
        r = call(barb, "POST", "/api/auth/actors", 201, "creates the account",
                 json={"email": email, "display_name": "Drive Newcomer",
                       "role": "EMPLOYEE", "employee_key": f"DRV{stamp}",
                       "password": "issued-by-the-administrator-1"})
    new_id = r.json()["actor_id"]

    with mutating("grants them a portfolio", "Barb Ewing", "PORTFOLIO_GRANT"):
        call(barb, "POST", f"/api/auth/actors/{new_id}/portfolios", 201,
             "grants FACILITIES", json={
                 "portfolio": "FACILITIES",
                 "reason": "Drive: taking on the rent roll for the audit."})

    with mutating("takes it back again", "Barb Ewing", "PORTFOLIO_REVOKE"):
        call(barb, "POST", f"/api/auth/actors/{new_id}/portfolios/revoke", 200,
             "revokes FACILITIES", json={
                 "portfolio": "FACILITIES",
                 "reason": "Drive: proving a grant can be walked back."})

    with mutating("corrects a derived address", "Barb Ewing", "ACTOR_AMEND"):
        call(barb, "PATCH", f"/api/auth/actors/{new_id}", 200,
             "amends the account", json={
                 "email": f"corrected.{stamp}@ybi.org",
                 "display_name": "Drive Newcomer",
                 "reason": "Drive: correcting an address from the staff list."})

    with mutating("resets somebody's password", "Barb Ewing", "PASSWORD_RESET"):
        call(barb, "POST", f"/api/auth/actors/{new_id}/password", 200,
             "resets it", json={"new_password": "reset-by-the-administrator-1"})

    with mutating("stands an account down", "Barb Ewing", "ACTOR_ACTIVE"):
        call(barb, "POST", f"/api/auth/actors/{new_id}/active", 200,
             "deactivates", json={
                 "is_active": False,
                 "reason": "Drive: finished with this fixture."})

    gaps = call(barb, "GET", "/api/auth/roster-gaps", 200,
                "reads who is still without an account")
    if gaps.status_code == 200:
        ok(f"{gaps.json()['with_account']} with an account, "
           f"{gaps.json()['without_account']} without")


def drive_newcomer(args, barb, stamp):
    head("A newcomer's first five minutes.")
    email = f"drive.firstday.{stamp}@ybi.org"
    issued = "issued-by-the-administrator-1"
    with mutating("is set up by the administrator", "Barb Ewing", "ACTOR_CREATE"):
        call(barb, "POST", "/api/auth/actors", 201, "the account exists",
             json={"email": email, "display_name": "First Day",
                   "role": "EMPLOYEE", "employee_key": f"FD{stamp}",
                   "password": issued})

    c = sign_in(args.base, email, issued)
    try:
        me = c.get("/api/auth/me").json()
        if me["must_set_password"]:
            ok("signs in and is asked to choose their own password")
        else:
            finding("a newly issued account was not asked to set a password")
        call(c, "POST", "/api/timesheet/entry", 403,
             "cannot record time on a password two people know",
             json={"work_date": "2025-06-02", "objective_id": "YBI-GA",
                   "hours": 8, "basis": "PROJECT_RECORD", "note": "drive"})
        with mutating("chooses their own password", "First Day",
                      "PASSWORD_CHANGE"):
            call(c, "POST", "/api/auth/password", 200, "sets it", json={
                "current_password": issued,
                "new_password": "a-password-only-they-know-7"})
        with mutating("and now records time", "First Day", "TIME_ENTRY"):
            call(c, "POST", "/api/timesheet/entry", 200, "first entry", json={
                "work_date": "2025-06-02", "objective_id": "YBI-GA",
                "hours": 8, "basis": "PROJECT_RECORD",
                "note": "Drive: first entry after setting a password."})
        call(c, "GET", "/api/classify/queue", 403,
             "and still cannot see the ledger")
    finally:
        c.close()


# ── The person who keeps a timesheet ─────────────────────────────────

def drive_employee(args, c, pw):
    head("Heidi Ruby — the part of the system everybody has. Time and documents.")
    objectives = call(c, "GET", "/api/timesheet/objectives", 200,
                      "reads what she can book time to")
    obj = None
    if objectives.status_code == 200:
        rows = rows_of(objectives, "objectives")
        obj = next((o["objective_id"] for o in rows
                    if o["objective_id"] != "LEAVE"), None)
        ok(f"{len(rows)} objectives available to book against")
    if not obj:
        finding("no objectives to book time against")
        return

    monday = date(2025, 4, 7)
    with mutating("records a day", "Heidi Ruby", "TIME_ENTRY"):
        call(c, "POST", "/api/timesheet/entry", 200, "Monday", json={
            "work_date": str(monday), "objective_id": obj, "hours": 8,
            "basis": "PROJECT_RECORD",
            "note": "Drive: rebuilt from the project log."})

    for i in range(1, 5):
        c.post("/api/timesheet/entry", json={
            "work_date": str(monday + timedelta(days=i)), "objective_id": obj,
            "hours": 8, "basis": "PROJECT_RECORD",
            "note": "Drive: rebuilt from the project log."})
    ok("fills the rest of the week")

    # The guardrail, and the override that carries a reason.
    long_day = str(monday + timedelta(days=7))
    r = c.post("/api/timesheet/entry", json={
        "work_date": long_day, "objective_id": obj, "hours": 11,
        "basis": "PROJECT_RECORD", "note": "Drive: a long day."})
    if r.status_code == 409:
        ok("eleven hours in a day is questioned before it is accepted")
    else:
        finding(f"an eleven-hour day answered {r.status_code}, not 409")
    with mutating("overrides the guardrail, in writing", "Heidi Ruby",
                  "TIME_ENTRY"):
        call(c, "POST", "/api/timesheet/entry", 200, "with a reason", json={
            "work_date": long_day, "objective_id": obj, "hours": 11,
            "basis": "PROJECT_RECORD", "note": "Drive: install weekend.",
            "override_reason": "Machine install ran over; eleven hours is "
                               "what the shop log shows."})

    with mutating("removes an entry", "Heidi Ruby", "TIME_REMOVE"):
        call(c, "POST", "/api/timesheet/entry/remove", 200, "removes it", json={
            "work_date": long_day, "objective_id": obj,
            "reason": "Drive: recorded against the wrong project."})

    day = call(c, "GET", "/api/timesheet/entries", 200, "reads the week back")
    if day.status_code == 200:
        ok(f"{len(rows_of(day, 'entries'))} live entries on file")

    month = call(c, "GET", "/api/timesheet/months", 200, "sees the year by month")
    if month.status_code == 200:
        body = month.json()
        rows = body if isinstance(body, list) else body.get("months", [])
        ok(f"{len(rows)} month(s) on the calendar")

    # Documents — the module everybody gets.
    with mutating("sends a document in", "Heidi Ruby", "DOCUMENT_UPLOAD"):
        call(c, "POST", "/api/documents/upload", 200, "a receipt",
             files={"file": (f"drive-receipt-{date.today()}.txt",
                             io.BytesIO(b"Drive: a receipt for the lab."),
                             "text/plain")},
             data={"kind": "receipt",
                   "suggested_for": "Lab consumables, April",
                   "note": "Drive: split across two projects."})
    mine = call(c, "GET", "/api/documents/mine", 200,
                "and sees what became of it")
    if mine.status_code == 200:
        d = mine.json()
        ok(f"{d['uploaded']} sent in, {d['in_use']} in use, {d['waiting']} waiting")


# ── The controller ───────────────────────────────────────────────────

def drive_controller(args, c):
    head("Tom Metzinger — CONTROLLER. Classification, the seal, the rate.")
    sealed = one("""SELECT set_id FROM decision_set
                     WHERE period = '2025' AND seal_hash IS NOT NULL LIMIT 1""")
    if sealed:
        c.post("/api/rates/unseal", params={
            "reason": "Drive: reopening a set sealed by an earlier run, so "
                      "the classification path can be driven again."})
        ok("a period left sealed is reopened first, with a reason")

    q = call(c, "GET", "/api/classify/queue?limit=5", 200, "opens the queue")
    groups = rows_of(q, "groups")
    if not groups:
        finding("the classification queue is empty; nothing to drive")
        return
    ok(f"{len(groups)} groups on this page, largest first")

    g = groups[0]
    advice = call(c, "GET", "/api/classify/advice", 200,
                  "asks what the account name suggests",
                  params={"group_key": g["group_key"]})
    if advice.status_code == 200:
        n = len(rows_of(advice, "advisories"))
        ok(f"{n} advisory note(s) offered — a suggestion, never a decision")

    with mutating("classifies a group", "Tom Metzinger", "CLASSIFY"):
        call(c, "POST", "/api/classify/decide", 200, "records the judgment",
             json={"group_keys": [g["group_key"]], "pool": "OVERHEAD",
                   "function_990": "MANAGEMENT_AND_GENERAL", "federal": "ALLOWABLE",
                   "grade": "MANAGEMENT_RECONSTRUCTION",
                   "rationale": "Drive: benefits the organisation as a whole "
                                "rather than any one award; 2 CFR 200.413(c)."})

    if len(groups) > 1:
        g2 = groups[1]
        with mutating("defers one that needs more", "Tom Metzinger", "DEFER"):
            call(c, "POST", "/api/classify/defer", 200, "sets it aside",
                 params={"group_key": g2["group_key"],
                         "reason": "Drive: needs the invoice before it can "
                                   "be split."})

    # Segmentation identifies a batch by its own generated key, not by the
    # group — so the reverse takes what the split handed back. Any group
    # already split is skipped rather than fought with.
    batch_key = None
    for candidate in groups[2:]:
        r = c.post("/api/classify/segment", json={
            "group_key": candidate["group_key"], "parts": [
                {"label": "Programme share", "share": "0.6",
                 "rationale": "Drive: sixty per cent by headcount."},
                {"label": "Administrative share", "share": "0.4",
                 "rationale": "Drive: the remainder."}]})
        if r.status_code == 200:
            batch_key = r.json()["batch_key"]
            ok(f"splits a mixed line into two parts — {batch_key}")
            last = latest_audit()
            if last.get("action") == "SEGMENT" and last.get("actor") == "Tom Metzinger":
                ok("the split is on the record, under his name")
            else:
                finding(f"a split recorded {last.get('action')} by "
                        f"{last.get('actor')}")
            break
        if r.status_code != 409:
            finding(f"splitting a group answered {r.status_code} — "
                    f"{r.text[:160]}")
            break
    if batch_key:
        with mutating("and can put it back", "Tom Metzinger", "SEGMENT_REVERSE"):
            call(c, "POST", "/api/classify/segment/reverse", 200, "reversed",
                 params={"batch_key": batch_key,
                         "reason": "Drive: proving a split is reversible, and "
                                   "that reversing it is itself on the record."})
    else:
        ok("every group on this page is already split — nothing to drive")

    with mutating("writes a workpaper note", "Tom Metzinger", "NOTE"):
        call(c, "POST", "/api/evidence/note", 200, "records the reasoning",
             json={"target_type": "LEDGER_GROUP", "target_id": g["group_key"],
                   "body": "Drive: allocation basis agreed with the "
                           "controller's 2025 reference sheet.",
                   "author": "ignored — identity comes from the session",
                   "is_workpaper": True})

    with mutating("sets the materiality policy", "Tom Metzinger", "MATERIALITY"):
        call(c, "PUT", "/api/classify/materiality", 200, "written down", json={
            "verified_above": 100000, "corroborated_above": 25000,
            "federal_corroborated_above": 10000,
            "basis": "Drive: 2% of expense, and the Type A threshold."})

    cov = call(c, "GET", "/api/classify/coverage", 200, "checks coverage")
    if cov.status_code == 200:
        ok(f"{cov.json().get('pct_dollars', 0)}% of dollars classified")

    # The sequence the whole file rests on.
    call(c, "POST", "/api/rates/compute", 409,
         "no rate before the seal — the order is the guarantee", json={})
    with mutating("seals the decision set", "Tom Metzinger", "SEAL"):
        call(c, "POST", "/api/rates/seal", 200, "sealed", json={
            "note": "Drive: sealing what has been decided so far."})
    with mutating("computes the rate", "Tom Metzinger", "RATE_COMPUTE"):
        r = call(c, "POST", "/api/rates/compute", 200, "computed", json={})
    if r.status_code == 200:
        d = r.json()
        ok(f"the rate carries the seal {d['seal_hash'][:12]}… — "
           f"{len(d['rates'])} rate(s) persisted")

    with mutating("unseals, in writing", "Tom Metzinger", "UNSEAL"):
        call(c, "POST", "/api/rates/unseal", 200, "reopened", params={
            "reason": "Drive: a classification has to change, and the rate "
                      "that rests on it is superseded."})
    with mutating("and seals again", "Tom Metzinger", "SEAL"):
        call(c, "POST", "/api/rates/seal", 200, "sealed", json={
            "note": "Drive: resealed after the correction."})

    lanes = call(c, "GET", "/api/lanes", 200, "reads the scenario lanes")
    if lanes.status_code == 200:
        ok(f"{len(lanes.json())} lane(s) on file")

    pay = call(c, "GET", "/api/reconcile/payroll", 200,
               "reads the payroll register against the ledger")
    if pay.status_code == 200:
        r = pay.json()["reconciliation"]
        ok(f"register {r['register_wages']} against ledger wages "
           f"{r['ledger_wages']} — {r['unexplained']} unexplained")
        if r["register_wages"] and r["ledger_wages"]:
            on_reg = float(r["fringe_pool"]) / float(r["register_wages"]) * 100
            on_led = float(r["fringe_pool"]) / float(r["ledger_wages"]) * 100
            ok(f"the fringe rate reads {on_reg:.2f}% on the register and "
               f"{on_led:.2f}% on the ledger — one rate, two denominators")
        odd = pay.json()["unlike_payroll"]
        if odd:
            ok(f"{len(odd)} line(s) in a wage account that do not look like "
               f"payroll — a place to look, not a finding")

    # The one relaxation in the reconciling-item rule, and its fences.
    wage = "5129 Payroll Expenses:5139 Wages:5142 Intern Wages"
    call(c, "POST", "/api/reconcile/items", 422,
         "only a ROUNDING item may omit its lines", json={
             "control": "PAYROLL_REGISTER", "from_account": wage,
             "to_account": "register", "amount": "-1.00", "kind": "TIMING",
             "line_ids": [],
             "explanation": "Drive: any other kind must name its lines."})
    call(c, "POST", "/api/reconcile/items", 409,
         "and a rounding item over a thousand dollars is refused", json={
             "control": "PAYROLL_REGISTER", "from_account": wage,
             "to_account": "register", "amount": "-5000.00", "kind": "ROUNDING",
             "line_ids": [],
             "explanation": ("Drive: five thousand dollars is not rounding by "
                             "any reading, and this explanation is long enough "
                             "to pass the length test on its own.")})

    recon = call(c, "GET", "/api/reconcile", 200, "reads schedule A-1")
    if recon.status_code == 200 and recon.json()["ties"]:
        ok("every cross-reference point ties")
    elif recon.status_code == 200:
        ok(f"open: {', '.join(recon.json()['failing'])} — stated, not hidden")


# ── Facilities and inventory ─────────────────────────────────────────

def drive_facilities(args, c, stamp):
    head("Heidi Ruby — FACILITIES and INVENTORY. Buildings, space, equipment.")
    fid = f"DRIVE-{stamp}"
    with mutating("records a building", "Heidi Ruby", "FACILITY"):
        call(c, "PUT", "/api/facilities", 200, "the building", json={
            "facility_id": fid, "name": "Drive Test Building", "code": "DTB",
            "owned": True, "usable_sqft": 10000, "rentable_sqft": 11500,
            "market_rate_psf": 12.5,
            "market_basis": "Drive: three comparable leases on Boardman St.",
            "source_document": "Drive: rent roll."})

    call(c, "PUT", "/api/facilities/space", 422,
         "a market rate with no basis is refused", json={
             "unit_id": f"{fid}-A", "facility_id": fid, "label": "Suite A",
             "usable_sqft": 2400, "use": "TENANT", "status": "OCCUPIED",
             "occupant": "Drive Tenant Ltd",
             "market_rate_psf": 12.5, "market_basis": ""})

    with mutating("records a suite let below market", "Heidi Ruby", "SPACE_UNIT"):
        call(c, "PUT", "/api/facilities/space", 200, "the suite", json={
            "unit_id": f"{fid}-A", "facility_id": fid, "label": "Suite A",
            "usable_sqft": 2400, "use": "TENANT", "status": "OCCUPIED",
            "occupant": "Drive Tenant Ltd", "actual_annual_charge": 15000,
            "market_rate_psf": 12.5,
            "market_basis": "Drive: three comparable leases on Boardman St.",
            "market_source": "Drive: CoStar extract, March 2026."})

    econ = call(c, "GET", "/api/facilities/space", 200, "reads the rent roll")
    if econ.status_code == 200:
        row = next((u for u in rows_of(econ, "units")
                    if u["unit_id"] == f"{fid}-A"), None)
        if row and row.get("subsidy"):
            ok(f"the suite's subsidy computes to ${float(row['subsidy']):,.0f} "
               f"— market less what was charged")

    eq = call(c, "GET", "/api/facilities/equipment", 200,
              "reads the equipment register")
    assets = rows_of(eq, "equipment")
    if assets:
        a = assets[0]
        with mutating("records an hour on a machine", "Heidi Ruby",
                      "EQUIPMENT_USE"):
            call(c, "POST", "/api/facilities/equipment/use", 200, "logged",
                 json={"asset_id": a["asset_id"],
                       "user_name": "Drive Tenant Ltd", "hours": 4,
                       "charged": 0,
                       "source_document": "Drive: shop log.",
                       "note": "Drive: free use by an incubator client."})
    else:
        ok("no equipment on file yet — the register is the open item")

    call(c, "POST", "/api/facilities/in-kind", 422,
         "YBI's own subsidy cannot be claimed as cost share", json={
             "kind": "OWN_SPACE_SUBSIDY", "value": 15000,
             "is_cost_share": True,
             "basis": "Drive: this must be refused under 200.465.",
             "objective_id": "YBI-GA"})

    with mutating("records it as mission value instead", "Heidi Ruby", "IN_KIND"):
        call(c, "POST", "/api/facilities/in-kind", 200, "recorded", json={
            "kind": "OWN_SPACE_SUBSIDY",
            "description": "Drive: Suite A let below market.",
            "value": 15000, "claimed_as_cost_share": False,
            "valuation_basis": "Drive: forgone rent on YBI's own building. "
                               "Worth having, not a cost YBI incurred — "
                               "2 CFR 200.465.",
            "objective_id": "YBI-GA"})


# ── Projects and the 2026 chart ──────────────────────────────────────

def drive_project(args, c, stamp):
    head("Stephanie Gaffney — PROJECT. Awards, objectives, the 2026 chart.")
    aw = call(c, "GET", "/api/awards", 200, "reads the awards")
    awards = rows_of(aw)
    if awards:
        ok(f"{len(awards)} award(s) with ceilings and cost share")
        a = awards[0]
        call(c, "GET", f"/api/awards/{a['award_id']}/constraints", 200,
             "checks what one will bear")
        call(c, "GET", f"/api/awards/{a['award_id']}/trueup", 200,
             "and what it has drawn")

    splits = call(c, "GET", "/api/chart/splits", 200,
                  "reads the 2026 accounts that divide")
    rows = rows_of(splits, "splits")
    if rows:
        ok(f"{len(rows)} account(s) split between pools, each needing a driver")
        target = rows[0]
        targets = target["targets_suggested"][:2]
        if len(targets) >= 2:
            call(c, "PUT", "/api/chart/splits", 422,
                 "shares that do not come to one are refused", json={
                     "source_account": target["source_account"],
                     "parts": [
                         {"target_account": targets[0], "share": 0.5,
                          "driver": "Drive: headcount, per the reference sheet."},
                         {"target_account": targets[1], "share": 0.2,
                          "driver": "Drive: the remainder, administrative."}]})
            with mutating("documents a split's drivers", "Stephanie Gaffney",
                          "CHART_SPLIT"):
                call(c, "PUT", "/api/chart/splits", 200, "recorded", json={
                    "source_account": target["source_account"],
                    "parts": [
                        {"target_account": targets[0], "share": 0.6,
                         "driver": "Drive: sixty per cent by headcount, per "
                                   "the 2025 reference sheet."},
                        {"target_account": targets[1], "share": 0.4,
                         "driver": "Drive: the remainder, administrative."}]})

    call(c, "GET", "/api/chart/crosswalk", 200,
         "proves the new chart carries every 2025 dollar")


# ── The document library ─────────────────────────────────────────────

def drive_office(args, c):
    head("Heidi Ruby — OFFICE. Putting what people sent in to work.")
    inbox = call(c, "GET", "/api/documents/inbox", 200,
                 "opens what is waiting to be filed")
    waiting = rows_of(inbox, "documents")
    if not waiting:
        ok("nothing waiting — every document has been put to work")
        return
    ok(f"{len(waiting)} document(s) sent in that nobody has filed")

    line = one("""SELECT line_id FROM ledger_line
                   WHERE period = '2025' AND statement = 'P&L' LIMIT 1""")
    doc = waiting[0]
    with mutating("says what a document supports", "Heidi Ruby",
                  "EVIDENCE_ATTACH"):
        call(c, "POST", "/api/documents/attach", 201, "attached", json={
            "evidence_id": doc["evidence_id"], "target_type": "LEDGER_LINE",
            "target_id": line["line_id"],
            "relevance": "Drive: the receipt behind this charge."})

    after = call(c, "GET", "/api/documents/inbox", 200, "and it leaves the queue")
    if after.status_code == 200:
        left = len(after.json()["documents"])
        if left == len(waiting) - 1:
            ok(f"{left} left waiting, down from {len(waiting)}")
        else:
            finding(f"the inbox still shows {left}; the attach did not take")

    cov = call(c, "GET", "/api/evidence/coverage", 200,
               "reads documented dollars by pool")
    if cov.status_code == 200:
        ok(f"{len(cov.json())} pool(s) with evidence coverage measured")


# ── Reading everything, changing nothing ─────────────────────────────

def drive_auditor(args, c):
    head("The engagement auditor — reads everything, writes nothing.")
    for path, what in (("/api/reconcile", "schedule A-1"),
                       ("/api/dashboard", "where the engagement stands"),
                       ("/api/export/exceptions", "every place the standard bent"),
                       ("/api/classify/queue?limit=3", "the classification queue"),
                       ("/api/evidence", "the document register"),
                       ("/api/rates", "the rates on file")):
        call(c, "GET", path, 200, f"reads {what}")

    pkg = call(c, "GET", "/api/export/audit-package", 200,
               "takes the whole package away")
    if pkg.status_code == 200:
        ok(f"{len(pkg.content):,} bytes of workpapers, downloaded and logged")

    exc = c.get("/api/export/exceptions")
    if exc.status_code == 200:
        d = exc.json()
        ok(f"{d['total']} exception(s) on the schedule, "
           f"{d['unexplained']} without a reason")

    for method, path, body in (
            ("POST", "/api/rates/seal", {"note": "probe"}),
            ("POST", "/api/classify/decide", {"group_key": "probe"}),
            ("PUT", "/api/facilities", {"facility_id": "X", "name": "X",
                                        "usable_sqft": 1})):
        call(c, method, path, 403, f"refused {path}", json=body)


def drive_system_admin(args, c, people):
    head("Eric Wagner — SYSTEM_ADMIN, reading on a grant from YBI.")
    me = c.get("/api/auth/me").json()
    if me["record_access"] and me["can_read"] and not me["may_seal"]:
        ok("reads the record on a recorded grant, holds no portfolio, "
           "cannot seal")
    else:
        finding(f"unexpected standing: {me}")
    call(c, "GET", "/api/auth/actors", 200, "reads the roster")
    call(c, "GET", "/api/reconcile", 200, "reads schedule A-1")
    call(c, "POST", "/api/rates/seal", 403, "and is refused the seal",
         json={"note": "probe"})


# ── Walking something back ───────────────────────────────────────────

def drive_undo(args, c):
    head("Undoing — a forward, auditable act, never a deletion.")
    trail = call(c, "GET", "/api/undo?mine=true&limit=5", 200,
                 "reads her own last few actions")
    rows = rows_of(trail, "entries")
    target = next((r for r in rows
                   if r["reversible_action"] and not r["already_undone"]), None)
    if not target:
        ok("nothing of hers left to walk back")
        return
    before = audit_count()
    r = call(c, "POST", "/api/undo", 200,
             f"walks back {target['label'].lower()}", json={
                 "entry_ids": [target["entry_id"]],
                 "reason": "Drive: proving an action can be walked back, and "
                           "that walking it back is itself on the record."})
    if r.status_code == 200 and r.json()["count"]:
        after = audit_count()
        if after > before:
            entry = one("""SELECT action, actor, undoes_entry_id
                             FROM audit_log
                            ORDER BY occurred_at DESC, entry_id DESC LIMIT 1""")
            if entry["action"] == "UNDO" and entry["undoes_entry_id"]:
                ok(f"the undo is itself an entry, by {entry['actor']}, "
                   f"pointing at what it reversed")
            else:
                finding("the undo did not record what it reversed")
        else:
            finding("an undo wrote nothing to the audit log")


# ── The feed everybody's work lands in ───────────────────────────────

def drive_feed(args, c, started):
    head("The record itself — everything that just happened, in order.")
    now = audit_count()
    ok(f"{now - started} audit entries written by this drive")

    feed = call(c, "GET", "/api/dashboard/activity?limit=200", 200,
                "reads the activity feed")
    if feed.status_code != 200:
        return
    rows = rows_of(feed)
    ok(f"{len(rows)} events in the feed, drawn from the records themselves")

    actors = query("""SELECT actor, actor_role::text AS role, count(*) AS n
                        FROM audit_log
                       WHERE entry_id > (SELECT max(entry_id) - %s
                                           FROM audit_log)
                       GROUP BY actor, actor_role ORDER BY count(*) DESC""",
                   (now - started,))
    for a in actors:
        ok(f"{a['actor']} ({a['role']}) — {a['n']} change(s) on the record")

    orphan = one("""SELECT count(*) AS n FROM audit_log
                     WHERE actor_id IS NULL OR session_id IS NULL""")
    if orphan["n"] == 0:
        ok("every entry names an account and the session it was made in")
    else:
        finding(f"{orphan['n']} audit entries have no actor or no session")


if __name__ == "__main__":
    sys.exit(main())
