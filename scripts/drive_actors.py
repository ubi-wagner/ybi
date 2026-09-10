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
    if r.json().get("role") != "ADMIN":
        raise CannotRun(f"{admin_email} is not an ADMIN; cannot read the roster.")

    roster = c.get("/api/auth/actors")
    if roster.status_code != 200:
        raise CannotRun(f"could not read the actor roster ({roster.status_code}).")

    by_role: dict[str, dict] = {}
    for a in roster.json():
        by_role.setdefault(a["role"], a)
    for needed in ("CONTROLLER", "AUDITOR", "EMPLOYEE"):
        if needed not in by_role:
            raise CannotRun(f"no {needed} actor exists; nothing to drive.")
    return by_role


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
    finally:
        auditor.close()

    # ---------------------------------------------------- employee
    print("\nEmployee")
    employee = sign_in(args.base, actors["EMPLOYEE"]["email"], password)
    try:
        for path in ("/api/classify/queue", "/api/classify/coverage"):
            code = employee.get(path).status_code
            if code == 403:
                ok(f"{path} -> 403")
            else:
                finding(f"employee read {path} ({code}); an employee certifies "
                        f"their own hours and does not see the ledger")
        me = employee.get("/api/auth/me").json()
        if me.get("employee_key"):
            ok(f"carries an employee key — {me['employee_key']}")
        else:
            finding("employee actor has no employee_key; it cannot certify anything")
    finally:
        employee.close()

    # ---------------------------------------------------- controller
    print("\nController")
    controller = sign_in(args.base, actors["CONTROLLER"]["email"], password)
    try:
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
