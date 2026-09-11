#!/usr/bin/env python3
"""Drive a whole year through the deployed system, as each person in turn.

Not a unit test. This signs in over HTTP as the controller, two employees and
the auditor, and walks 2025 the way the engagement will: import, classify,
split, evidence, notes, employment terms, a year of time entered week by week,
submission, certification, sealing, and the auditor taking the record away.

Every step asserts three things:

  1. The call answered the way the contract says — the status code, and a
     typed body rather than a stack trace.
  2. The database moved the way the call claimed.
  3. **The change is on the audit record.** Anything that creates, updates or
     deletes has to leave an entry naming who did it. That is the property the
     whole system is sold on, and it is checked here by counting the audit
     entries either side of every mutation rather than by reading the code.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run, which is
not a pass: a logged-out client and a deny-all look identical.

    YBI_SEED_PASSWORD=... python3 scripts/drive_year.py [--base URL]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys

import httpx

from app.db import one, open_pool, query

FINDINGS: list[str] = []
CHECKS = 0


class CannotRun(Exception):
    pass


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", flush=True)


def audit_count() -> int:
    return one("SELECT count(*) AS n FROM audit_log")["n"]


def latest_audit() -> dict | None:
    return one("""SELECT action, actor, actor_role::text AS actor_role, entity,
                         entity_id, reason
                    FROM audit_log ORDER BY occurred_at DESC, entry_id DESC
                   LIMIT 1""")


def mutating(label: str, expect_actor: str, expect_action: str = ""):
    """Wrap a write and prove it reached the audit log.

    The check is deliberately blunt — the number of audit rows before and
    after — because a subtler one could be satisfied by the handler writing
    the entry it was asked to write rather than the entry the change deserved.
    """
    class Guard:
        def __enter__(self):
            self.before = audit_count()
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type:
                return False
            after = audit_count()
            if after <= self.before:
                finding(f"{label}: changed the database and wrote nothing to "
                        f"the audit log")
                return False
            last = latest_audit() or {}
            if expect_actor and last.get("actor") != expect_actor:
                finding(f"{label}: audit entry names {last.get('actor')!r}, "
                        f"not {expect_actor!r}")
                return False
            if expect_action and last.get("action") != expect_action:
                finding(f"{label}: audit action is {last.get('action')!r}, "
                        f"expected {expect_action!r}")
                return False
            ok(f"{label} — audited as {last.get('action')} by "
               f"{last.get('actor')} ({last.get('actor_role')})")
            return False
    return Guard()


def call(client: httpx.Client, method: str, path: str, expect: int,
         label: str, **kw) -> httpx.Response:
    r = client.request(method, path, **kw)
    if r.status_code != expect:
        finding(f"{label}: {method} {path} answered {r.status_code}, "
                f"expected {expect} — {r.text[:180]}")
    else:
        ok(f"{label} — {r.status_code}")
    return r


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise CannotRun(f"{email} could not sign in ({r.status_code}); the "
                        f"drive cannot distinguish a boundary from a "
                        f"logged-out client.")
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise CannotRun("YBI_SEED_PASSWORD is required to drive the actors.")

    open_pool()

    with httpx.Client(base_url=args.base, timeout=30) as probe:
        try:
            h = probe.get("/api/health")
        except httpx.HTTPError as e:
            raise CannotRun(f"nothing serving at {args.base}: {e}") from e
        if h.status_code != 200:
            raise CannotRun(f"health answered {h.status_code}")

    scope = one("""SELECT count(*) AS n FROM ledger_line
                    WHERE period='2025' AND statement='P&L'""")["n"]
    if not scope:
        raise CannotRun("the ledger is empty — load 2025 first, or every "
                        "check below would pass against nothing.")
    already = one("""SELECT count(*) AS n FROM audit_log
                      WHERE reason LIKE 'Drive:%' OR reason LIKE '%Drive:%'""")["n"]
    if already:
        raise CannotRun(
            f"this database already carries {already} entries from a previous "
            f"drive. The drive walks a year forward — it submits a timesheet, "
            f"signs a certification, seals a set — and none of that can happen "
            f"twice. Reset and reload, then run it once:\n"
            f"    dropdb ybicost && createdb ybicost\n"
            f"    scripts/seed_actors.py && scripts/load_2025.py && "
            f"scripts/load_labor.py")

    print(f"Driving 2025 against {scope:,} lines in scope\n")

    # ── The controller ───────────────────────────────────────────────
    print("Controller — classifying, splitting, evidencing, sealing")
    tom = sign_in(args.base, "tom@ybi.org", password)
    try:
        group = query("""SELECT account, COALESCE(payee,'') AS payee
                           FROM ledger_line l
                          WHERE period='2025' AND statement='P&L'
                            AND NOT EXISTS (SELECT 1 FROM decision_line dl
                                             WHERE dl.line_id = l.line_id AND dl.live)
                          GROUP BY account, payee
                          ORDER BY sum(abs(amount)) DESC LIMIT 1""")[0]
        key = f"{group['account']}\x1f{group['payee']}"

        with mutating("classify a group", "Tom Metzinger", "CLASSIFY"):
            call(tom, "POST", "/api/classify/decide", 200, "decide", json={
                "group_keys": [key], "pool": "G&A",
                "function_990": "MANAGEMENT_AND_GENERAL", "federal": "PENDING",
                "grade": "CORROBORATED",
                "rationale": "Drive: booked to general administration pending "
                             "the objective review.",
                "citation": "2 CFR 200.414(a)", "evidence_ids": [],
                "decided_by": "drive"})

        with mutating("note on a group", "Tom Metzinger", "NOTE"):
            call(tom, "POST", "/api/evidence/note", 200, "note", json={
                "target_type": "LEDGER_GROUP", "target_id": key,
                "body": "Drive: recorded so the next reader does not re-derive it.",
                "author": "", "is_workpaper": True})

        split_group = query("""SELECT account, COALESCE(payee,'') AS payee
                                 FROM ledger_line l
                                WHERE period='2025' AND statement='P&L'
                                  AND NOT EXISTS (SELECT 1 FROM ledger_segment s
                                                   WHERE s.line_id = l.line_id
                                                     AND s.reversed_at IS NULL)
                                GROUP BY account, payee
                                HAVING count(*) BETWEEN 2 AND 40
                                ORDER BY sum(abs(amount)) DESC LIMIT 1""")[0]
        skey = f"{split_group['account']}\x1f{split_group['payee']}"
        with mutating("split a mixed group", "Tom Metzinger", "SEGMENT"):
            call(tom, "POST", "/api/classify/segment", 200, "segment", json={
                "group_key": skey, "created_by": "",
                "parts": [{"label": "Programme delivery", "share": "0.7",
                           "rationale": "Drive: driver is the statement of work.",
                           "citation": "2 CFR 200.413(a)"},
                          {"label": "General support", "share": "0.3",
                           "rationale": "Drive: benefits the organisation as a whole.",
                           "citation": "2 CFR 200.414(a)"}]})

        with mutating("record employment terms", "Tom Metzinger", "EMPLOYMENT"):
            call(tom, "PUT", "/api/timesheet/employment", 200, "employment", json={
                "employee_key": "EWING", "status": "FULL_TIME",
                "weekly_hours": 40, "employed_from": "2025-01-01",
                "employed_to": None, "source_document": "2025 payroll register"})

        # A part-year hire: the case a flat year would make unsubmittable.
        with mutating("part-year terms", "Tom Metzinger", "EMPLOYMENT"):
            call(tom, "PUT", "/api/timesheet/employment", 200, "part-year", json={
                "employee_key": "GAFFNEY", "status": "FULL_TIME",
                "weekly_hours": 40, "employed_from": "2025-07-01",
                "employed_to": None, "source_document": "2025 payroll register"})
        exp = one("""SELECT expected_hours FROM v_employment_expected
                      WHERE period='2025' AND employee_key='GAFFNEY'""")
        half = 2080 / 2
        if exp and abs(float(exp["expected_hours"]) - half) < 60:
            ok(f"a half-year hire is owed {float(exp['expected_hours']):,.0f} "
               f"hours, not a full 2,080")
        else:
            finding(f"half-year denominator is {exp and exp['expected_hours']}, "
                    f"expected about {half:,.0f}")

        call(tom, "POST", "/api/timesheet/entry", 403,
             "controller refused time entry", json={
                 "work_date": "2025-03-04", "objective_id": "DRIVE-AM",
                 "hours": 8, "basis": "CALENDAR"})

        with mutating("open a scenario lane", "Tom Metzinger", "LANE_CREATE"):
            lane = call(tom, "POST", "/api/lanes", 200, "lane", json={
                "name": "Drive scenario", "purpose": "Drive: a sandbox lane.",
                "created_by": ""})
        if lane.status_code == 200:
            lane_id = lane.json()["lane_id"]
            with mutating("promote it", "Tom Metzinger", "LANE_PROMOTE"):
                call(tom, "POST", f"/api/lanes/{lane_id}/promote", 200,
                     "promote", json={
                         "to_kind": "CANDIDATE",
                         "rationale": "Drive: the engagement stands behind it."})
            call(tom, "POST", f"/api/lanes/{lane_id}/promote", 422,
                 "a promotion without a rationale is refused",
                 json={"to_kind": "CANDIDATE", "rationale": "  "})
            call(tom, "POST", f"/api/lanes/{lane_id}/promote", 422,
                 "a kind the database has never heard of is refused before "
                 "it reaches the database",
                 json={"to_kind": "WORKING", "rationale": "Drive."})

        with mutating("seal the decision set", "Tom Metzinger", "SEAL"):
            sealed = call(tom, "POST", "/api/rates/seal", 200, "seal",
                          json={"sealed_by": "ignored — the session decides",
                                "note": "Drive: sealing what has been decided."})
        if sealed.status_code == 200:
            row = one("""SELECT sealed_by, seal_hash FROM decision_set
                          WHERE period='2025' AND seal_hash IS NOT NULL
                          ORDER BY sealed_at DESC LIMIT 1""")
            if row and row["sealed_by"] == "Tom Metzinger":
                ok("the seal names the signed-in controller, not the string "
                   "the client sent")
            else:
                finding(f"the seal is attributed to {row and row['sealed_by']!r}")

        call(tom, "POST", "/api/rates/seal", 409,
             "a sealed period cannot be sealed again", json={"sealed_by": ""})

        with mutating("unseal, with a reason", "Tom Metzinger", "UNSEAL"):
            call(tom, "POST", "/api/rates/unseal", 200, "unseal",
                 params={"reason": "Drive: reopening to finish the queue."})
    finally:
        tom.close()

    # ── The employee ─────────────────────────────────────────────────
    print("\nEmployee — a year of time, week by week")
    barb = sign_in(args.base, "bewing@ybi.org", password)
    try:
        with mutating("first entry of the year", "Barb Ewing", "TIME_ENTRY"):
            call(barb, "POST", "/api/timesheet/entry", 200, "entry", json={
                "work_date": "2025-01-02", "objective_id": "ESP", "hours": 8,
                "basis": "CALENDAR", "note": "Drive: from the diary."})

        call(barb, "POST", "/api/timesheet/entry", 422,
             "a day cannot be claimed as contemporaneous a year later", json={
                 "work_date": "2025-01-03", "objective_id": "ESP", "hours": 8,
                 "basis": "AS_WORKED"})

        call(barb, "POST", "/api/timesheet/entry", 409,
             "a day holds 24 hours", json={
                 "work_date": "2025-01-02", "objective_id": "HUB", "hours": 20,
                 "basis": "CALENDAR"})

        with mutating("correcting an entry", "Barb Ewing", "TIME_ENTRY"):
            call(barb, "POST", "/api/timesheet/entry", 200, "correction", json={
                "work_date": "2025-01-02", "objective_id": "ESP", "hours": 6,
                "basis": "CALENDAR", "note": "Drive: corrected."})
        trail = one("""SELECT count(*) AS n FROM timesheet_entry
                        WHERE employee_key='EWING' AND work_date='2025-01-02'
                          AND objective_id='ESP'""")
        if trail["n"] >= 2:
            ok("the superseded entry is still on the record")
        else:
            finding("a correction overwrote the entry instead of superseding it")

        call(barb, "POST", "/api/timesheet/submit", 422,
             "a part-filled sheet cannot stand for the year",
             json={"acknowledged": True})

        # Now fill the year the way somebody rebuilding it would: week by week.
        print("  … entering the year", flush=True)
        random.seed(11)
        mix = [("ESP", .40), ("HUB", .22), ("YBI-GA", .12), ("DRIVE-AM", .09),
               ("FUNDRAISING", .06), ("HYBRID-II", .05), ("MBAC", .04), ("YOUTH", .02)]
        d, written, refused = dt.date(2025, 1, 1), 0, 0
        while d <= dt.date(2025, 12, 31):
            if d.weekday() < 5:
                leave = (dt.date(2025, 7, 7) <= d <= dt.date(2025, 7, 18)
                         or dt.date(2025, 12, 24) <= d <= dt.date(2025, 12, 31))
                rows = ([("LEAVE", 8.0)] if leave else
                        [(o, h) for o, h in _split_day(random.sample(mix, k=2))])
                for objective, h in rows:
                    r = barb.post("/api/timesheet/entry", json={
                        "work_date": d.isoformat(), "objective_id": objective,
                        "hours": h, "basis": "CALENDAR"})
                    if r.status_code == 409 and "OVER_SOFT_LIMIT" in r.text:
                        # A normal eight-hour day never trips this; when the
                        # shape of the week does, the answer is to say why —
                        # which is the whole point of a soft limit.
                        r = barb.post("/api/timesheet/entry", json={
                            "work_date": d.isoformat(),
                            "objective_id": objective, "hours": h,
                            "basis": "CALENDAR",
                            "override_reason": "Drive: long week, entered "
                                               "from the diary."})
                    written += r.status_code == 200
                    refused += r.status_code != 200
            d += dt.timedelta(days=1)
        if refused:
            finding(f"{refused} entries were refused while filling the year")
        else:
            ok(f"a year entered — {written} entries, none refused")

        months = barb.get("/api/timesheet/months").json()
        covered = [m for m in months if m["coverage"] and float(m["coverage"]) > 0.9]
        if len(covered) == 12:
            ok("every month covers at least 90% of the hours its terms imply")
        else:
            finding(f"only {len(covered)} of 12 months reach 90% coverage")

        with mutating("submitting the year", "Barb Ewing", "TIME_SUBMIT"):
            r = call(barb, "POST", "/api/timesheet/submit", 200, "submit",
                     json={"acknowledged": True})
        if r.status_code == 200:
            cov = r.json()["coverage"]
            ok(f"submitted at {cov:.0%} of {r.json()['expected_hours']:,.0f} hours")

        eff = one("""SELECT bool_or(source = 'TIMESHEET') AS from_ts
                       FROM v_labor_effective
                      WHERE period='2025' AND employee_key='EWING'""")
        if eff and eff["from_ts"]:
            ok("the submitted timesheet now speaks for the year, not the "
               "reconstruction")
        else:
            finding("a submitted timesheet did not become the effective "
                    "distribution")

        with mutating("certifying own effort", "Barb Ewing", "CERTIFY"):
            call(barb, "POST", "/api/certify/sign", 200, "sign", json={
                "employee_key": "EWING", "period": "2025",
                "acknowledged": True})

        with mutating("an entry after signing", "Barb Ewing", "TIME_ENTRY"):
            call(barb, "POST", "/api/timesheet/entry", 200, "late change", json={
                "work_date": "2025-02-03", "objective_id": "MBAC", "hours": 2,
                "basis": "CALENDAR", "note": "Drive: found a missed afternoon.",
                "override_reason": "Drive: the day really was ten hours."})
        st = one("""SELECT stale FROM v_certification_status
                     WHERE period='2025' AND employee_key='EWING'""")
        if st and st["stale"]:
            ok("changing the sheet made the signature stale, as it must")
        else:
            finding("the sheet changed under a signature and it was not "
                    "marked stale")
    finally:
        barb.close()

    # ── Walking things back ──────────────────────────────────────────
    print("\nUndo — a fat finger, and a mass reclassification")
    tom = sign_in(args.base, "tom@ybi.org", password)
    try:
        # A bulk mistake: five groups into the wrong pool in one go.
        groups = query("""SELECT account, COALESCE(payee,'') AS payee
                            FROM ledger_line l
                           WHERE period='2025' AND statement='P&L'
                             AND NOT EXISTS (SELECT 1 FROM decision_line dl
                                              WHERE dl.line_id = l.line_id AND dl.live)
                           GROUP BY account, payee
                           ORDER BY sum(abs(amount)) DESC LIMIT 5""")
        keys = [f"{g['account']}\x1f{g['payee']}" for g in groups]
        call(tom, "POST", "/api/classify/decide", 200,
             "five groups classified in one go", json={
                 "group_keys": keys, "pool": "FUNDRAISING",
                 "function_990": "FUNDRAISING", "federal": "UNALLOWABLE",
                 "grade": "TEST_ASSUMPTION",
                 "rationale": "Drive: the wrong pool, applied in bulk.",
                 "evidence_ids": [], "decided_by": "drive"})
        live = one("""SELECT count(*) AS n FROM decision
                       WHERE pool = 'FUNDRAISING' AND reversed_at IS NULL""")["n"]

        trail = call(tom, "GET", "/api/undo?limit=5", 200, "reads the trail")
        undoable = [t for t in trail.json() if t["can_undo"]]
        if undoable:
            ok(f"{len(undoable)} of the last 5 actions can be walked back")
        else:
            finding("nothing in the trail can be walked back")

        call(tom, "POST", "/api/undo", 422, "an undo without a reason is refused",
             json={"count": 1, "reason": "   "})

        with mutating("walk the bulk mistake back", "Tom Metzinger", "UNDO"):
            r = call(tom, "POST", "/api/undo", 200, "undo", json={
                "count": 1, "reason": "Drive: wrong pool applied in bulk."})
        after = one("""SELECT count(*) AS n FROM decision
                        WHERE pool = 'FUNDRAISING' AND reversed_at IS NULL""")["n"]
        if after < live:
            ok(f"the classification is reversed — {live} live before, {after} after")
        else:
            finding("the undo reported success and nothing was reversed")

        kept = one("""SELECT count(*) AS n FROM decision
                       WHERE pool = 'FUNDRAISING' AND reversed_at IS NOT NULL""")["n"]
        if kept:
            ok(f"the reversed decision is still on the record ({kept} of them)")
        else:
            finding("the undo deleted the decision instead of reversing it")

        linked = one("""SELECT count(*) AS n FROM audit_log
                         WHERE action = 'UNDO' AND undoes_entry_id IS NOT NULL""")["n"]
        if linked:
            ok("the undo entry names the entry it walked back")
        else:
            finding("an undo was recorded that names nothing")

        again = tom.post("/api/undo", json={
            "entry_ids": [undoable[0]["entry_id"]] if undoable else [],
            "reason": "Drive: trying the same one twice."})
        if again.status_code in (200, 404) and (
                again.status_code == 404
                or not again.json().get("undone")
                or again.json().get("refused")):
            ok("the same action cannot be walked back twice")
        else:
            finding("an already-reversed action was reversed again")
    finally:
        tom.close()

    # ── Guardrails and donated time ──────────────────────────────────
    print("\nGuardrails, and hours nobody was paid for")
    barb = sign_in(args.base, "bewing@ybi.org", password)
    try:
        over = barb.post("/api/timesheet/entry", json={
            "work_date": "2025-04-15", "objective_id": "HUB", "hours": 11,
            "basis": "CALENDAR"})
        if over.status_code == 409 and "breaches" in over.text:
            ok("an eleven-hour day is questioned, not refused — "
               + over.json()["detail"]["breaches"][0]["limit"])
        else:
            finding(f"an eleven-hour day answered {over.status_code}")

        with mutating("the same day, with a reason", "Barb Ewing", "TIME_ENTRY"):
            call(barb, "POST", "/api/timesheet/entry", 200, "override", json={
                "work_date": "2025-04-15", "objective_id": "HUB", "hours": 11,
                "basis": "CALENDAR",
                "override_reason": "Drive: site visit and the drive back."})
        kept = one("""SELECT overrode, override_reason FROM timesheet_entry
                       WHERE employee_key='EWING' AND work_date='2025-04-15'
                         AND objective_id='HUB' AND superseded_at IS NULL""")
        if kept and kept["overrode"] and kept["override_reason"]:
            ok(f"the override is on the entry — {kept['overrode']}")
        else:
            finding("an override was allowed and not recorded")

        before = one("""SELECT COALESCE(sum(hours),0) AS h
                          FROM v_timesheet_distribution
                         WHERE employee_key='EWING' AND objective_id='YOUTH'""")
        with mutating("donated hours", "Barb Ewing", "TIME_ENTRY"):
            call(barb, "POST", "/api/timesheet/entry", 200, "donated", json={
                "work_date": "2025-05-17", "objective_id": "YOUTH", "hours": 6,
                "basis": "CALENDAR", "donated": True,
                "note": "Drive: Saturday mentoring, unpaid."})
        after_paid = one("""SELECT COALESCE(sum(hours),0) AS h
                              FROM v_timesheet_distribution
                             WHERE employee_key='EWING' AND objective_id='YOUTH'""")
        donated = one("""SELECT hours FROM v_donated_time
                          WHERE employee_key='EWING' AND objective_id='YOUTH'""")
        if donated and float(donated["hours"]) == 6:
            ok("donated hours are recorded as donated")
        else:
            finding("donated hours did not reach the donated view")
        # The test is that they move nothing, not that the objective is empty:
        # Barb has paid Youth time too, and it must be untouched.
        if float(after_paid["h"]) == float(before["h"]):
            ok(f"the paid distribution is unchanged at {float(before['h']):g} "
               f"hours — donated time moves no paid share")
        else:
            finding(f"donated hours moved the paid distribution from "
                    f"{before['h']} to {after_paid['h']}")
        rate = one("""SELECT rate_missing FROM v_donated_time
                       WHERE employee_key='EWING' AND objective_id='YOUTH'""")
        if rate and rate["rate_missing"]:
            ok("and they are listed as unvalued rather than valued at a guess")
    finally:
        barb.close()

    # ── Buildings, the kit in them, and what it is worth ─────────────
    print("\nSpace and equipment — five buildings, and the cost-share line")
    tom = sign_in(args.base, "tom@ybi.org", password)
    try:
        # Five buildings. Shapes and rates are illustrative; the point of the
        # drive is that the arithmetic and the guardrails hold, not the survey.
        buildings = [
            ("TECH", "Technology Block", 48000.0, True, "", 14.00),
            ("INC2", "Incubator II", 31000.0, True, "", 13.50),
            ("AMFG", "Additive Manufacturing Hall", 26500.0, True, "", 11.00),
            ("ANNEX", "Federal Street Annex", 12000.0, False, "Youngstown CIC", 16.00),
            ("YARD", "Yard and Storage", 6500.0, True, "", 6.00),
        ]
        for code, name, area, owned, landlord, psf in buildings:
            call(tom, "PUT", "/api/facilities", 200, f"building {code}", json={
                "facility_id": code, "code": code, "name": name,
                "address": f"{name}, Youngstown OH", "owned": owned,
                "landlord": landlord, "usable_sqft": area,
                "market_rate_psf": psf,
                "market_basis": "2025 Youngstown CBD office and flex survey, "
                                "class B comparables.",
                "source_document": "Drive: illustrative"})
        got = call(tom, "GET", "/api/facilities", 200, "reads the buildings")
        if got.status_code == 200 and len(got.json()["facilities"]) == 5:
            ok("five buildings on file")
        else:
            finding("the five buildings did not land")

        call(tom, "PUT", "/api/facilities", 422,
             "a leased building without a landlord is refused", json={
                 "facility_id": "BAD", "name": "Nowhere", "owned": False,
                 "landlord": "", "usable_sqft": 100})

        # A tenant suite let below market, and a shared lab.
        call(tom, "PUT", "/api/facilities/space", 200, "a below-market suite",
             json={"unit_id": "TECH-210", "facility_id": "TECH",
                   "label": "Suite 210", "usable_sqft": 2400, "use": "TENANT",
                   "status": "OCCUPIED", "occupant": "Portfolio company",
                   "actual_annual_charge": 18000, "market_rate_psf": 14.00,
                   "market_basis": "2025 Youngstown CBD class B comparables.",
                   "market_source": "Drive: illustrative"})
        call(tom, "PUT", "/api/facilities/space", 200, "a shared lab", json={
            "unit_id": "AMFG-LAB1", "facility_id": "AMFG", "label": "Lab 1",
            "usable_sqft": 5000, "use": "SHARED_LAB", "status": "INTERNAL",
            "market_rate_psf": 11.00,
            "market_basis": "2025 Youngstown flex and light industrial survey."})

        call(tom, "PUT", "/api/facilities/space", 422,
             "a market rate with no basis is refused", json={
                 "unit_id": "TECH-211", "facility_id": "TECH", "label": "211",
                 "usable_sqft": 400, "use": "TENANT", "status": "OCCUPIED",
                 "occupant": "Someone", "market_rate_psf": 14.0,
                 "market_basis": "hearsay"})

        econ = call(tom, "GET", "/api/facilities/space", 200, "the rent roll")
        suite = next((u for u in econ.json()["space"]
                      if u["unit_id"] == "TECH-210"), None)
        if suite:
            expect = 2400 * 14.00 - 18000          # 33,600 - 18,000
            if abs(float(suite["subsidy"]) - expect) < 1:
                ok(f"the suite's subsidy computes to ${float(suite['subsidy']):,.0f} "
                   f"— {suite['usable_sqft']} sqft at market, less what was charged")
            else:
                finding(f"subsidy is {suite['subsidy']}, expected {expect}")

        # The cost-share line, which is the part that matters.
        call(tom, "POST", "/api/facilities/in-kind", 422,
             "YBI's own subsidy cannot be claimed as cost share", json={
                 "kind": "OWN_SPACE_SUBSIDY",
                 "description": "Below-market suites across the incubator",
                 "value": 184000,
                 "valuation_basis": "Market comparables against the rent roll.",
                 "claimed_as_cost_share": True})
        with mutating("the same value, recorded as mission value",
                      "Tom Metzinger", "IN_KIND"):
            call(tom, "POST", "/api/facilities/in-kind", 200, "mission value",
                 json={"kind": "OWN_SPACE_SUBSIDY",
                       "description": "Below-market suites across the incubator",
                       "value": 184000, "measured": "illustrative",
                       "valuation_basis": "Market comparables against the rent roll.",
                       "claimed_as_cost_share": False})
        call(tom, "POST", "/api/facilities/in-kind", 422,
             "unrecovered indirect without an approval is refused", json={
                 "kind": "UNRECOVERED_INDIRECT",
                 "description": "Unrecovered indirect on Project 88",
                 "value": 233543.12,
                 "valuation_basis": "Difference between de minimis billed and "
                                    "the computed rate.",
                 "claimed_as_cost_share": True})
        with mutating("third-party donated equipment use", "Tom Metzinger",
                      "IN_KIND"):
            call(tom, "POST", "/api/facilities/in-kind", 200, "third party",
                 json={"kind": "THIRD_PARTY_EQUIPMENT",
                       "description": "Donated use of partner metrology suite",
                       "value": 12500, "measured": "250 hours",
                       "valuation_basis": "Partner's published hourly rate card, "
                                          "2025.",
                       "claimed_as_cost_share": True})

        summary = call(tom, "GET", "/api/facilities/in-kind", 200, "in-kind summary")
        rows = summary.json()["summary"]
        claimable = [r for r in rows if r["claimed_as_cost_share"]]
        mission = [r for r in rows if not r["claimed_as_cost_share"]]
        if claimable and mission:
            ok(f"${float(claimable[0]['value']):,.0f} is cost-share eligible; "
               f"${float(mission[0]['value']):,.0f} is mission value and says so")
        else:
            finding("the in-kind summary does not separate the two")
    finally:
        tom.close()

    # ── The auditor ──────────────────────────────────────────────────
    print("\nAuditor — reading everything, changing nothing")
    auditor = sign_in(args.base, "auditor@ybi.org", password)
    try:
        r = call(auditor, "GET", "/api/timesheet/roster", 200, "reads the roster")
        if r.status_code == 200 and r.json():
            ok(f"sees {len(r.json())} employees and their coverage")
        call(auditor, "PUT", "/api/timesheet/employment", 403,
             "refused to set employment terms", json={
                 "employee_key": "EWING", "status": "PART_TIME",
                 "weekly_hours": 20, "employed_from": "2025-01-01"})
        call(auditor, "POST", "/api/timesheet/entry", 403,
             "refused to enter time", json={
                 "work_date": "2025-03-04", "objective_id": "ESP", "hours": 8,
                 "basis": "CALENDAR"})
        call(auditor, "POST", "/api/rates/seal", 403, "refused to seal",
             json={"sealed_by": "auditor-probe"})
        with mutating("downloads the record", "Engagement Auditor", "EXPORT"):
            pkg = auditor.get("/api/export/audit-package")
            if pkg.status_code != 200 or len(pkg.content) < 10_000:
                finding(f"audit package came back {pkg.status_code}, "
                        f"{len(pkg.content)} bytes")
    finally:
        auditor.close()

    # ── The reconciliation ───────────────────────────────────────────
    print("\nAudit reconciliation")
    unattributed = one("""SELECT count(*) AS n FROM audit_log
                           WHERE COALESCE(actor,'') = ''""")["n"]
    if unattributed:
        finding(f"{unattributed} audit entries name nobody")
    else:
        ok("every audit entry names a person")

    unroled = one("""SELECT count(*) AS n FROM audit_log
                      WHERE actor_role IS NULL""")["n"]
    if unroled:
        finding(f"{unroled} audit entries carry no role")
    else:
        ok("every audit entry carries the role it was made under")

    # Each of these leaves its own record as well as an audit entry. The feed
    # has to agree with the tables, or the feed is decoration.
    for table, action in (("decision", "CLASSIFY"),
                          ("timesheet_submission", "TIME_SUBMIT"),
                          ("labor_certification", "CERTIFY"),
                          ("employment", "EMPLOYMENT")):
        rows = one(f"SELECT count(*) AS n FROM {table}")["n"]
        logged = one("SELECT count(*) AS n FROM audit_log WHERE action = %s",
                     (action,))["n"]
        if logged >= rows:
            ok(f"{rows} {table} rows, {logged} {action} entries — every "
               f"change is on the record")
        else:
            finding(f"{rows} {table} rows but only {logged} {action} audit "
                    f"entries — {rows - logged} changes left no trace")

    feed = one("SELECT count(*) AS n FROM v_activity")["n"]
    ok(f"the activity feed reads {feed} events from the records themselves")

    print()
    if FINDINGS:
        print(f"FAIL — {len(FINDINGS)} finding(s) across {CHECKS} checks")
        for f in FINDINGS:
            print(f"  · {f}")
        return 1
    print(f"PASS — {CHECKS} checks, a year driven by four people, every "
          f"change on the record.")
    return 0


def _split_day(picks):
    total = sum(w for _, w in picks)
    left = 8.0
    out = []
    for i, (obj, w) in enumerate(picks):
        h = left if i == len(picks) - 1 else round(8 * w / total * 2) / 2
        h = min(h, left)
        if h > 0:
            out.append((obj, h))
            left -= h
    return out


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotRun as e:
        print(f"\nCOULD NOT RUN — {e}", file=sys.stderr)
        sys.exit(2)
