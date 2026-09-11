#!/usr/bin/env python3
"""Multi-actor permission drive, through the real API.

Unit tests prove the role predicates. They cannot prove that the *running*
service enforces them, because the enforcement lives in dependencies wired to
routes and in a session resolved from the database. That is what this drives.

Three rules, carried over from the govwin drive estate where they were learned
the hard way.

**Resolve, never pin.** Actors come from the database. A pinned email is
correct until the next re-seed, then it is a script asserting things about
somebody who does not exist.

**Prove authentication before measuring anything.** A logged-out client and a
correctly-denying server produce identical output — 401s and empty lists — and
only one of them is a finding. A drive that cannot log in must die saying
exactly that, with an exit code meaning *could not run*, never a pass and never
a finding. That is what `CannotRun` and exit 2 are for.

**The positive control is load-bearing.** "The auditor saw no writes" passes
trivially against an empty database. So the drive first proves the auditor can
*read real rows*, and refuses to run at all if there are none to read. Without
that, a green result means nothing.

    python3 scripts/drive_actors.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

FINDINGS: list[str] = []


class CannotRun(RuntimeError):
    """The rig could not be driven. Exit 2 — not a finding, not a pass."""


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}")


def ok(msg: str) -> None:
    print(f"  ok       {msg}")


def resolve_actors(c: httpx.Client, admin_email: str, password: str) -> dict:
    """Sign in as the admin and read the actor roster from the service."""
    r = c.post("/api/auth/login", json={"email": admin_email, "password": password})
    if r.status_code != 200:
        raise CannotRun(
            f"could not sign in as {admin_email} ({r.status_code}). "
            f"Seed actors first: YBI_SEED_PASSWORD=... python3 scripts/seed_actors.py")
    # The login response carries rank; is_admin comes from /me. Rank is what
    # decides whether the roster is readable.
    if r.json().get("role") not in ("SYSTEM_ADMIN", "ORG_ADMIN"):
        raise CannotRun(f"{admin_email} does not provision accounts, so cannot "
                        f"read the roster.")

    roster = c.get("/api/auth/actors")
    if roster.status_code != 200:
        raise CannotRun(f"could not read the actor roster ({roster.status_code}).")

    rows = [a for a in roster.json() if a["is_active"]]
    by_role: dict[str, dict] = {}
    for a in rows:
        by_role.setdefault(a["role"], a)

    # "Employee" here means a person who keeps a timesheet, which since the
    # access model changed is most of the organisation rather than one role —
    # a controller is on the payroll too. What the section actually needs is
    # somebody with real payroll behind them, so pick the staff account with
    # the least authority: closest to a plain employee, and with an effort
    # distribution to read.
    staff = [a for a in rows if a["employee_key"]]
    staff.sort(key=lambda a: (len(a["portfolios"] or []), a["display_name"]))
    if staff:
        by_role["STAFF"] = staff[0]

    # A plain employee: a timesheet and nothing else. The boundary checks
    # below need one, because what they prove is that somebody with no
    # standing in the cost record cannot read it — and an executive who keeps
    # a timesheet is not that person.
    plain = [a for a in rows
             if a["role"] == "EMPLOYEE" and not (a["portfolios"] or [])
             and a["email"] not in SKIP_EMAILS]
    if plain:
        by_role["PLAIN_EMPLOYEE"] = plain[0]

    # And somebody who is emphatically not on the payroll, to prove that a
    # controller cannot open a timesheet they have no business in.
    off_payroll = [a for a in rows
                   if not a["employee_key"] and "CONTROLLER" in (a["portfolios"] or [])]
    if off_payroll:
        by_role["OFF_PAYROLL_CONTROLLER"] = off_payroll[0]

    for needed in ("CONTROLLER", "AUDITOR", "STAFF"):
        if needed not in by_role:
            raise CannotRun(f"no {needed} actor exists; nothing to drive.")
    return by_role


#: Accounts other drives create and stand down. They hold passwords only
#: those drives know, so they cannot be signed in as here.
SKIP_EMAILS: set[str] = set()


def ensure_plain_employee(c: httpx.Client, password: str) -> dict | None:
    """Make one if the roster has none.

    On a deployment where everybody carries a portfolio — which is every
    deployment before the payroll is seeded — there is no plain employee to
    prove the boundary against, and a drive that skips the check proves
    nothing. So it makes one, uses it, and stands it down afterwards. The
    boundary is a property of the system, not of who happens to be on the
    roster this week.
    """
    import time
    stamp = int(time.time())
    email = f"boundary-probe-{stamp}@ybi.org"
    r = c.post("/api/auth/actors", json={
        "email": email, "display_name": "Boundary Probe", "role": "EMPLOYEE",
        "employee_key": f"PROBE{stamp}", "password": password})
    if r.status_code != 201:
        return None
    return {"actor_id": r.json()["actor_id"], "email": email,
            "made_for_this_run": True}


def stand_down(c: httpx.Client, actor_id: str) -> None:
    c.post(f"/api/auth/actors/{actor_id}/active", json={
        "is_active": False,
        "reason": "Drive: a probe account, finished with."})


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise CannotRun(f"could not sign in as {email} ({r.status_code}: {r.text[:120]})")
    me = c.get("/api/auth/me")
    if me.status_code != 200:
        raise CannotRun(f"signed in as {email} but /me answered {me.status_code}")
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise CannotRun("YBI_SEED_PASSWORD is required to drive the actors.")

    admin_email = os.environ.get("YBI_ADMIN_EMAIL", "eric.c.wagner@gmail.com")

    with httpx.Client(base_url=args.base, timeout=60) as probe:
        # A transport error is "could not run", not a finding. Letting
        # httpx.ConnectError escape would exit 1 and read as a permission
        # failure against a service that was never up.
        try:
            health = probe.get("/api/health")
        except httpx.HTTPError as exc:
            raise CannotRun(f"nothing serving at {args.base}: {exc}") from exc
        if health.status_code != 200:
            raise CannotRun(f"{args.base} answered {health.status_code} at /api/health")
        actors = resolve_actors(probe, admin_email, password)

    roster = ", ".join(f"{r}={a['email']}" for r, a in sorted(actors.items()))
    print(f"\nActors resolved from the service: {roster}")

    # ---------------------------------------------------- anonymous
    print("\nAnonymous")
    with httpx.Client(base_url=args.base, timeout=60) as anon:
        for path in ("/api/classify/queue", "/api/classify/coverage",
                     "/api/auth/me", "/api/auth/actors"):
            code = anon.get(path).status_code
            if code == 401:
                ok(f"{path} -> 401")
            else:
                finding(f"{path} answered {code} to an anonymous caller, not 401")

    # ---------------------------------------------------- auditor
    print("\nAuditor")
    auditor = sign_in(args.base, actors["AUDITOR"]["email"], password)
    try:
        # POSITIVE CONTROL. "Saw no writes" is free against an empty database,
        # so prove first that there are real rows to see.
        cov = auditor.get("/api/classify/coverage")
        if cov.status_code != 200:
            raise CannotRun(f"auditor cannot read coverage ({cov.status_code}); "
                            f"a read-only role that reads nothing proves nothing.")
        lines = cov.json().get("total_lines", 0)
        if not lines:
            raise CannotRun("the ledger is empty; a no-write drive would pass "
                            "trivially. Load 2025 first: scripts/load_2025.py")
        ok(f"reads the ledger — {lines} lines in scope (positive control)")

        q = auditor.get("/api/classify/queue", params={"limit": 5})
        if q.status_code == 200 and isinstance(q.json(), list) and q.json():
            ok(f"reads the classification queue — {len(q.json())} groups")
        else:
            finding(f"auditor could not read the queue ({q.status_code}); "
                    f"read access is not working")

        # Now the negative: the reviewer must not be able to alter the record.
        w = auditor.post("/api/classify/decide", json={
            "group_keys": ["probe\x1f"], "pool": "G&A",
            "function_990": "MANAGEMENT_AND_GENERAL", "federal": "ALLOWABLE",
            "grade": "CORROBORATED", "rationale": "drive probe",
            "evidence_ids": [], "decided_by": "auditor-probe"})
        if w.status_code == 403:
            ok("refused a classification with 403")
        else:
            finding(f"auditor classification answered {w.status_code}, not 403 — "
                    f"a reviewer who can alter the record cannot attest to it")

        s = auditor.post("/api/rates/seal", json={"period": "2025",
                                                  "sealed_by": "auditor-probe"})
        if s.status_code == 403:
            ok("refused to seal with 403")
        else:
            finding(f"auditor seal answered {s.status_code}, not 403")

        a = auditor.get("/api/auth/actors")
        if a.status_code == 403:
            ok("refused the actor roster with 403")
        else:
            finding(f"auditor read the actor roster ({a.status_code}), not 403")

        # Taking the record away is the reviewer's side of the guarantee: a
        # reviewer who has to ask the controller for a copy has the person
        # being reviewed standing between them and the evidence.
        pkg = auditor.get("/api/export/audit-package", params={"period": "2025"})
        if pkg.status_code == 200 and len(pkg.content) > 10_000:
            ok(f"downloaded the audit package — {len(pkg.content):,} bytes")
        else:
            finding(f"auditor could not download the audit package "
                    f"({pkg.status_code}, {len(pkg.content)} bytes)")

        reg = auditor.get("/api/evidence", params={"period": "2025"})
        if reg.status_code != 200:
            finding(f"auditor could not read the document register "
                    f"({reg.status_code})")
        elif not reg.json():
            # An empty register is not a refusal, and calling it one would be
            # a finding against a system that did nothing wrong. It does mean
            # the retrieval check below cannot run, and saying so is the
            # honest answer rather than passing on an empty set.
            raise CannotRun("no documents on file, so retrieval cannot be "
                            "proved. Run scripts/tom_session.py first.")
        else:
            first = reg.json()[0]["evidence_id"]
            ok(f"reads the document register — {len(reg.json())} documents")
            doc = auditor.get(f"/api/evidence/{first}/file")
            if doc.status_code == 200 and doc.content:
                ok(f"retrieved a document itself — {first}, {len(doc.content):,} bytes")
            else:
                finding(f"auditor could not retrieve {first} ({doc.status_code}); "
                        f"a register that cannot produce the document is a claim, "
                        f"not evidence")

        up = auditor.post("/api/evidence/note",
                          json={"target_type": "LEDGER_GROUP", "target_id": "probe",
                                "body": "drive probe", "author": "auditor-probe"})
        if up.status_code == 403:
            ok("refused to write a note with 403")
        else:
            finding(f"auditor note answered {up.status_code}, not 403")

        seg = auditor.post("/api/classify/segment",
                           json={"group_key": "probe\x1f", "created_by": "auditor-probe",
                                 "parts": [{"label": "a", "share": "0.5",
                                            "rationale": "probe"},
                                           {"label": "b", "share": "0.5",
                                            "rationale": "probe"}]})
        if seg.status_code == 403:
            ok("refused to split a group with 403")
        else:
            finding(f"auditor segmentation answered {seg.status_code}, not 403")
    finally:
        auditor.close()

    # ---------------------------------------------------- employee
    print("\nEmployee")
    plain = actors.get("PLAIN_EMPLOYEE")
    made_one = False
    if not plain:
        admin = sign_in(args.base, actors["ORG_ADMIN"]["email"], password)
        try:
            plain = ensure_plain_employee(admin, password)
            made_one = bool(plain)
            if made_one:
                ok("no plain employee on the roster, so one was made for the "
                   "boundary — it is a property of the system, not of who "
                   "happens to be on the roster")
        finally:
            admin.close()
    if plain:
        outsider = sign_in(args.base, plain["email"], password)
        try:
            # The library belongs on this list rather than only on the
            # access drive: it is the cost record in document form, and
            # somebody with a timesheet and nothing else has no more standing
            # in the papers than in the ledger they support.
            for path in ("/api/classify/queue", "/api/classify/coverage",
                         "/api/export/audit-package",
                         "/api/documents/library"):
                r = outsider.get(path)
                (ok if r.status_code == 403 else finding)(
                    f"a plain employee is refused {path} — {r.status_code}"
                    if r.status_code == 403 else
                    f"a plain employee read {path} ({r.status_code}); somebody "
                    f"who keeps a timesheet and nothing else has no standing "
                    f"in the ledger")
        finally:
            outsider.close()
            if made_one:
                admin = sign_in(args.base, actors["ORG_ADMIN"]["email"], password)
                try:
                    stand_down(admin, plain["actor_id"])
                finally:
                    admin.close()
    else:
        finding("no plain employee account exists and one could not be made, "
                "so the boundary was not proved")

    employee = sign_in(args.base, actors["STAFF"]["email"], password)
    try:
        me = employee.get("/api/auth/me").json()
        if me.get("employee_key"):
            ok(f"carries an employee key — {me['employee_key']}")
        else:
            finding("employee actor has no employee_key; it cannot certify anything")

        mine = employee.get("/api/certify/mine")
        if mine.status_code == 200 and mine.json().get("distribution"):
            n = len(mine.json()["distribution"])
            ok(f"sees their own distribution — {n} activities")
        else:
            finding(f"employee cannot see their own effort ({mine.status_code}); "
                    f"nobody can certify what they cannot read")

        # Certification is personal. Signing for someone else is the one thing
        # 200.430(i) exists to prevent.
        other = employee.post("/api/certify/sign",
                              json={"employee_key": "GAFFNEY", "period": "2025",
                                    "acknowledged": True})
        if other.status_code in (403, 404):
            ok(f"refused to sign for another employee with {other.status_code}")
        else:
            finding(f"employee signed for GAFFNEY ({other.status_code}); a "
                    f"certification that is not the person's own supports nothing")

        pkg = employee.get("/api/export/audit-package")
        if me.get("can_read"):
            (ok if pkg.status_code == 200 else finding)(
                f"reads the audit package, as somebody who may read the "
                f"record — {pkg.status_code}")
        elif pkg.status_code == 403:
            ok("refused the audit package with 403")
        else:
            finding(f"an account with no standing in the record downloaded "
                    f"the audit package ({pkg.status_code})")

        # Reading somebody else's timesheet is review, and review belongs to
        # whoever may read the record. Writing into one never does — that is
        # the boundary the certification rests on, and it is proved in the
        # controller section below.
        other = employee.get("/api/timesheet/entries",
                             params={"employee_key": "GAFFNEY"})
        if me.get("can_read"):
            (ok if other.status_code == 200 else finding)(
                f"reads another person's timesheet, which is review — "
                f"{other.status_code}")
        elif other.status_code == 403:
            ok("refused another employee's timesheet with 403")
        else:
            finding(f"employee read GAFFNEY's timesheet ({other.status_code})")

    finally:
        employee.close()

    # ---------------------------------------------------- controller
    print("\nController")
    controller = sign_in(args.base, actors["CONTROLLER"]["email"], password)
    try:
        # Everybody on the payroll keeps their own timesheet, controllers
        # included — so the rule is not "a controller may not enter time", it
        # is "nobody enters time on an account that is not on the payroll".
        # An account with no employee key has no timesheet to write into, and
        # that is what stops a controller filling one in for somebody else.
        off = actors.get("OFF_PAYROLL_CONTROLLER")
        if off:
            other = sign_in(args.base, off["email"], password)
            try:
                t = other.post("/api/timesheet/entry",
                               json={"work_date": "2025-03-04",
                                     "objective_id": "DRIVE-AM", "hours": 8,
                                     "basis": "CALENDAR"})
                if t.status_code == 403:
                    ok("a controller who is not on the payroll has no "
                       "timesheet to write into — 403")
                else:
                    finding(f"an account with no employee key recorded time "
                            f"({t.status_code}); a timesheet filled in by "
                            f"somebody else is what a certification exists to "
                            f"rule out")
            finally:
                other.close()
        else:
            ok("every controller is on the payroll, so there is no "
               "off-payroll account to test that boundary with")

        r = controller.get("/api/timesheet/entries",
                           params={"employee_key": "EWING"})
        if r.status_code == 200:
            ok("controller reads an employee's timesheet — review is their job")
        else:
            finding(f"controller cannot review a timesheet ({r.status_code})")
        q = controller.get("/api/classify/queue", params={"limit": 3})
        if q.status_code == 200 and q.json():
            ok(f"reads the queue — {len(q.json())} groups")
        else:
            finding(f"controller cannot read the queue ({q.status_code})")
        a = controller.get("/api/auth/actors")
        if a.status_code == 403:
            ok("refused the actor roster with 403 — administration is a separate job")
        else:
            finding(f"controller read the actor roster ({a.status_code}), not 403")
    finally:
        controller.close()

    print()
    if FINDINGS:
        print(f"FAIL — {len(FINDINGS)} finding(s)")
        return 1
    print("PASS — every boundary held, against a ledger with real rows in it.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotRun as exc:
        print(f"\nCOULD NOT RUN — {exc}", file=sys.stderr)
        sys.exit(2)
