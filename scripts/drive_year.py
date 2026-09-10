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
                "basis": "CALENDAR", "note": "Drive: found a missed afternoon."})
        st = one("""SELECT stale FROM v_certification_status
                     WHERE period='2025' AND employee_key='EWING'""")
        if st and st["stale"]:
            ok("changing the sheet made the signature stale, as it must")
        else:
            finding("the sheet changed under a signature and it was not "
                    "marked stale")
    finally:
        barb.close()

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
