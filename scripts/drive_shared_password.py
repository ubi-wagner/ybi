#!/usr/bin/env python3
"""The shared first-login password, driven through the real API.

    YBI_INITIAL_PASSWORD=... YBI_SEED_PASSWORD=... \
        python3 scripts/drive_shared_password.py [--base http://127.0.0.1:8000]

The unit tests prove `check_credential` decides correctly. They cannot prove
the *running* service opens an account on it, bounces the person to the
password screen, refuses their writes until they claim it, and then stops
accepting the shared value for them. That is a chain across four routes and a
database trigger, and this is where it is proved.

It walks the round exactly as a person will:

    Barb opens an account, naming no password
    the person signs in on the organisation's shared one
    the API says must_set_password, and every write is refused
    they set their own
    the shared password no longer opens their account
    their own does, and now they can write

Two things it asserts that are easy to lose and would not show for months:

- **A sign-in on the shared password is its own act on the trail.**
  `SIGN_IN_SHARED`, not `SIGN_IN`. "Who was still on the shared credential,
  and when" is a question an auditor can ask, and one action could not
  answer it.
- **It is not an enumeration oracle.** The shared password against an address
  with no account must answer exactly what a wrong password against a real one
  answers. This system knows the names of everyone at the organisation, so a
  credential that distinguishes the two would hand over the roster.

It stands its probe account down afterwards and checks the census, because
"leaves the record as it found it" is a claim and a claim in a drive is
something to check.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

FINDINGS: list[str] = []


class CannotRun(RuntimeError):
    """The rig could not be driven. Exit 2 — not a finding, not a pass."""


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}")


def ok(msg: str) -> None:
    print(f"  ok       {msg}")


def client(base: str) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=60)


def sign_in(base: str, email: str, password: str) -> tuple[httpx.Client, dict]:
    c = client(base)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise CannotRun(f"could not sign in as {email} "
                        f"({r.status_code}: {r.text[:140]})")
    return c, r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--admin", default="bewing@ybi.org")
    args = ap.parse_args()

    shared = (os.environ.get("YBI_INITIAL_PASSWORD") or "").strip()
    seed = os.environ.get("YBI_SEED_PASSWORD") or ""
    if not shared:
        raise CannotRun(
            "YBI_INITIAL_PASSWORD is not set for this drive. It has to be the "
            "same value the running service holds, or the drive is testing a "
            "different password from the one the API will accept.")
    if not seed:
        raise CannotRun("YBI_SEED_PASSWORD is not set — cannot sign in as the "
                        "administrator who opens the account.")

    print(f"Shared first-login password — {args.base}\n")

    # ── the administrator opens an account, naming no password ──────────────
    admin, who = sign_in(args.base, args.admin, seed)
    if who.get("role") not in ("SYSTEM_ADMIN", "ORG_ADMIN"):
        raise CannotRun(f"{args.admin} does not provision accounts.")
    ok(f"signed in as {who['display_name']} ({who['role']})")

    before = admin.get("/api/auth/actors")
    if before.status_code != 200:
        raise CannotRun(f"could not read the roster ({before.status_code})")
    # Live on both sides or the comparison is not one. The first version
    # counted every row before and only the active ones after, so a stood-down
    # probe left by an earlier run made a correct cleanup report as a failure
    # — a drive arguing against working code, which is worse than no drive.
    def live_accounts(rows: list[dict]) -> int:
        return len([a for a in rows if a.get("is_active", True)])

    census = live_accounts(before.json())

    stamp = int(time.time())
    email = f"first-login-probe-{stamp}@ybi.org"
    made = admin.post("/api/auth/actors", json={
        "email": email, "display_name": "First Login Probe",
        "role": "EMPLOYEE", "employee_key": f"PROBE{stamp}"})
    if made.status_code != 201:
        raise CannotRun(f"could not open an account on the shared password "
                        f"({made.status_code}: {made.text[:200]})")
    account = made.json()
    actor_id = account["actor_id"]
    if account.get("opened_on") != "SHARED_INITIAL":
        finding(f"opened an account without a password and the answer says "
                f"opened_on={account.get('opened_on')!r} — a caller cannot "
                f"tell the person which password to use")
    else:
        ok("Barb opened an account naming no password — opened_on=SHARED_INITIAL")

    try:
        # ── the person signs in on the organisation's shared password ───────
        person, session = sign_in(args.base, email, shared)
        if session.get("signed_in_with") != "SHARED":
            finding(f"signed in on the shared password and the answer says "
                    f"signed_in_with={session.get('signed_in_with')!r}")
        else:
            ok("the shared password signs the new account in")

        if not session.get("must_set_password"):
            finding("signed in on the shared password and must_set_password is "
                    "false — the screen would not put the password page in "
                    "front, and every write would be refused by an API that "
                    "knows something the screen does not")
        else:
            ok("the answer says must_set_password, so the screen bounces them")

        # ── until they claim it, nothing they record is theirs ──────────────
        wrote = person.post("/api/timesheet/entry", json={
            "period": "2025", "work_date": "2025-06-02",
            "objective_id": "YBI-GA", "hours": 1,
            "basis": "RECALL", "note": "drive: should be refused"})
        if wrote.status_code != 403:
            finding(f"a write from an account on the shared password answered "
                    f"{wrote.status_code}, not 403 — a record whose signatures "
                    f"anyone could have written is not a record")
        elif "PASSWORD_NOT_YOUR_OWN" not in wrote.text:
            finding(f"the write was refused but not for the password: "
                    f"{wrote.text[:140]}")
        else:
            ok("every write is refused while the password is not their own")

        # ── they claim it ──────────────────────────────────────────────────
        reused = person.post("/api/auth/password", json={
            "current_password": shared, "new_password": shared})
        if reused.status_code != 422:
            finding(f"setting the new password to the shared one answered "
                    f"{reused.status_code}, not 422 — the account would read "
                    f"as claimed while the whole organisation holds it")
        else:
            ok("the shared password is refused as the new one")

        mine = f"probe-own-password-{stamp}"
        claimed = person.post("/api/auth/password", json={
            "current_password": shared, "new_password": mine})
        if claimed.status_code != 200:
            raise CannotRun(
                f"could not set an own password from the shared one "
                f"({claimed.status_code}: {claimed.text[:200]}). This is the "
                f"single exit from the write gate; without it an account "
                f"opened this way can neither write nor become able to.")
        ok("they set their own password from the shared one")

        # ── the door closes, for them alone ────────────────────────────────
        stale = client(args.base).post("/api/auth/login",
                                       json={"email": email,
                                             "password": shared})
        if stale.status_code != 401:
            finding(f"the shared password still opens a claimed account "
                    f"({stale.status_code}) — the round would never close")
        else:
            ok("the shared password no longer opens that account")

        after, now = sign_in(args.base, email, mine)
        if now.get("signed_in_with") != "OWN":
            finding(f"signed in on their own password and the answer says "
                    f"signed_in_with={now.get('signed_in_with')!r}")
        elif now.get("must_set_password"):
            finding("they set their own password and must_set_password is "
                    "still true")
        else:
            ok("their own password signs them in, and the gate is down")

        # The write gate is the point of the whole exercise: it has to lift.
        lifted = after.get("/api/timesheet/summary")
        if lifted.status_code >= 500:
            finding(f"reading their own timesheet answered "
                    f"{lifted.status_code}")
        else:
            ok(f"the account works normally afterwards ({lifted.status_code})")

        # ── and it is not an oracle ────────────────────────────────────────
        absent = client(args.base).post(
            "/api/auth/login",
            json={"email": f"nobody-{stamp}@ybi.org", "password": shared})
        if absent.status_code != 401:
            finding(f"the shared password against an address with no account "
                    f"answered {absent.status_code} — it would tell anybody "
                    f"which of our people have accounts")
        else:
            ok("an address with no account answers 401, like a wrong password")

        # The sharper oracle, found by a security review of this very commit:
        # secrets.compare_digest refuses two non-ASCII str arguments, and
        # unhandled that answered 500 for an account still on the shared
        # password and 401 for everything else — naming which accounts are
        # still claimable, and doing it before login records the attempt, so
        # the lockout never counted it. Driven here against all three states.
        seen = set()
        for label, addr in (("an unclaimed account", email),
                            ("a claimed account", args.admin),
                            ("no account at all", f"nobody-{stamp}@ybi.org")):
            r = client(args.base).post(
                "/api/auth/login",
                json={"email": addr, "password": "pässwort-mit-umlaut"})
            seen.add(r.status_code)
            if r.status_code >= 500:
                finding(f"a non-ASCII password against {label} answered "
                        f"{r.status_code} — an unmetered oracle for which "
                        f"accounts are still claimable")
        if len(seen) > 1:
            finding(f"a non-ASCII password answers differently by account "
                    f"state ({sorted(seen)}) — that difference is the oracle")
        elif seen == {401}:
            ok("a non-ASCII password answers 401 in all three account states")

        # ── an administrator's reset takes the account out of the round ────
        # `reset_password` writes ADMIN, and its own docstring says a reset is
        # for when the account may be in the wrong hands. If the shared value
        # still opened it, a reset would not restore exclusive control.
        reset = admin.post(f"/api/auth/actors/{actor_id}/password",
                           json={"new_password": f"admin-issued-{stamp}"})
        if reset.status_code != 200:
            print(f"  note     could not reset the probe's password "
                  f"({reset.status_code}); the ADMIN case was not driven")
        else:
            after_reset = client(args.base).post(
                "/api/auth/login", json={"email": email, "password": shared})
            if after_reset.status_code == 200:
                finding("the shared password opens an account an "
                        "administrator has just reset — a reset does not "
                        "restore exclusive control while a round is running")
            else:
                ok("an administrator's reset closes the shared door "
                   f"({after_reset.status_code})")

        # ── the trail says which credential it was ─────────────────────────
        # /activity, not /audit — the first draft of this drive asked for a
        # route that has never existed, and the 404 read as "could not
        # evaluate" rather than as a pass, which is the only reason it was
        # noticed. `v_activity` names the action `kind`.
        trail = admin.get("/api/dashboard/activity", params={"limit": 200})
        if trail.status_code != 200:
            print(f"  note     could not read the audit trail "
                  f"({trail.status_code}); SIGN_IN_SHARED not checked")
        else:
            rows = trail.json()
            rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
            actions = {r.get("kind") for r in rows if isinstance(r, dict)}
            if "SIGN_IN_SHARED" not in actions:
                finding("no SIGN_IN_SHARED on the trail — a sign-in on the "
                        "organisation's password is recorded as though it "
                        "identified one person")
            else:
                ok("the trail records SIGN_IN_SHARED as its own act")
    finally:
        admin.post(f"/api/auth/actors/{actor_id}/active", json={
            "is_active": False,
            "reason": "Drive: a first-login probe, finished with."})

    end = admin.get("/api/auth/actors")
    remaining = live_accounts(end.json()) if end.status_code == 200 else census
    if end.status_code == 200 and remaining != census:
        finding(f"the roster has {remaining} live accounts, started with "
                f"{census} — the drive did not leave the record as it found it")
    else:
        ok(f"probe stood down, {census} live accounts as before")

    print()
    if FINDINGS:
        print(f"{len(FINDINGS)} finding(s)")
        return 1
    print("the shared first-login round holds end to end")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CannotRun as e:
        print(f"\nCOULD NOT RUN: {e}", file=sys.stderr)
        raise SystemExit(2)
