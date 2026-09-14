#!/usr/bin/env python3
"""Set the organisation up, through the ladder rather than around it.

    PYTHONPATH=. python3 scripts/provision.py [--base http://127.0.0.1:8000]

The first system administrator cannot be created through the API, because
creating an account requires an account. That one is written directly, which
is what a bootstrap is. Everything after it goes through the real endpoints,
signed in as the person doing it — so the audit trail shows Eric setting up
Barb and Barb setting up everybody else, which is what actually happened.

The ladder is the point. A system administrator provisions the organisation's
administrator. The organisation's administrator provisions controllers and
employees. Neither can mint a peer, and the database says so as well as this
script does.

Each account gets its own one-time password, printed at the end on a sheet to
hand out. Nobody can record anything until they replace it: a judgment made on
a password two people know identifies two people.

    --sheet out.txt     write the handout to a file as well as the terminal
    --dry-run           show what would be created, create nothing
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

import httpx

# Readable rather than clever: these are read down a phone line and typed
# once, and a password with l/1/O/0 in it produces a support call instead of
# a login. Four words from thirty-two plus five digits is about thirty-six
# bits — which on its own would be thin, and against eight attempts per
# fifteen minutes is not reachable. It is also a password that must be
# replaced before the account can record anything.
WORDS = ("ledger", "rampart", "quarry", "meridian", "tallow", "bellwether",
         "furnace", "cobalt", "lantern", "sable", "kestrel", "mortar",
         "harrow", "verdigris", "tundra", "pewter", "juniper", "brigand",
         "cistern", "marlin", "thistle", "gantry", "vellum", "prairie",
         "drayage", "flagon", "spindle", "copper", "wharf", "tempest",
         "nutmeg", "bastion")


def one_time_password() -> str:
    return "-".join([secrets.choice(WORDS) for _ in range(4)]
                    + ["".join(secrets.choice("23456789") for _ in range(5))])


#: The roster, the reasons and the NDA grant live in `app/foundation.py`,
#: which is what the deployment itself reads on every boot. This script and
#: that module are two doors to the same room — the ladder walked by a person
#: against a running API, and the boot opening whatever is missing on the
#: organisation's password — and two copies of the six people is the defect
#: that module is named after.
#:
#: The shapes below are what this script has always used: tuples, not the
#: `Person` records, because the rest of the file reads them positionally.
from app.foundation import (ALL_PORTFOLIOS as ALL, BARB_REASON, NDA_REASON,
                            ORG_ADMIN as _ORG_ADMIN, STAFF as _STAFF,
                            SYSTEM_ADMIN as _SYSTEM_ADMIN)

STAFF = [(p.email, p.display_name, p.role, p.employee_key,
          list(p.portfolios), p.why) for p in _STAFF]

ORG_ADMIN = (_ORG_ADMIN.email, _ORG_ADMIN.display_name,
             _ORG_ADMIN.employee_key)
SYSTEM_ADMIN = (_SYSTEM_ADMIN.email, _SYSTEM_ADMIN.display_name)


def sign_in(c: httpx.Client, email: str, password: str) -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} "
                         f"({r.status_code}): {r.text[:200]}")
    return r.json()


def set_own_password(c: httpx.Client, current: str, new: str, who: str) -> None:
    """An administrator cannot provision anybody while still on a password
    somebody else chose. Their first act is replacing it — which is the same
    rule everyone else gets, applied to the people who hand it out."""
    r = c.post("/api/auth/password",
               json={"current_password": current, "new_password": new})
    if r.status_code != 200:
        raise SystemExit(f"{who} could not set their own password "
                         f"({r.status_code}): {r.text[:200]}")


def bootstrap_system_admin(password: str, supplied: bool = False) -> str:
    """Write the root account directly. The one step that cannot go through
    the API, because there is nobody yet to authorise it."""
    from app.auth import hash_password
    from app.db import execute, one, open_pool
    open_pool()
    email, name = SYSTEM_ADMIN
    row = one("SELECT actor_id, password_set_by::text AS o FROM actor "
              "WHERE email=%s", (email,))
    if row:
        # Re-runnable: put the known bootstrap password back so the rest of
        # the script can proceed, unless this account is already in use by a
        # person who has set their own.
        if row["o"] == "SELF":
            # Somebody real is using this account. Signing in as them with a
            # password they chose is fine; silently replacing it is not.
            if supplied:
                return "in use"
            raise SystemExit(
                f"{email} has set their own password. Run this with "
                f"YBI_ROOT_PASSWORD set to it, or reset it out of band.")
        execute("""UPDATE actor SET password_hash=%s, role='SYSTEM_ADMIN',
                                    password_set_by='SEED'
                    WHERE email=%s""", (hash_password(password), email))
        return "reset"
    execute("""INSERT INTO actor (email, display_name, role, password_hash,
                                  password_set_by)
               VALUES (%s,%s,'SYSTEM_ADMIN',%s,'SEED')""",
            (email, name, hash_password(password)))
    return "created"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--sheet", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--staff-password", default="",
                    help="seed an account for every person on the 2025 payroll "
                         "with this shared password, each forced to replace it "
                         "at first sign-in")
    ap.add_argument("--dev-password", default="",
                    help="development only: give every account this password, "
                         "marked self-chosen, so the drive scripts can sign in")
    args = ap.parse_args()

    if args.dry_run:
        print("Would provision:")
        print(f"  SYSTEM_ADMIN  {SYSTEM_ADMIN[0]}  (written directly)")
        print(f"  ORG_ADMIN     {ORG_ADMIN[0]}  provisioned by {SYSTEM_ADMIN[0]}")
        for email, name, role, key, pf, _ in STAFF:
            print(f"  {role:12s}  {email:24s} provisioned by {ORG_ADMIN[0]}"
                  f"  {', '.join(pf) or 'no portfolio'}")
        return 0

    issued: list[tuple[str, str, str, str]] = []   # name, email, role, password

    # ── The root, out of band ────────────────────────────────────────
    supplied = bool(os.environ.get("YBI_ROOT_PASSWORD"))
    boot = os.environ.get("YBI_ROOT_PASSWORD") or one_time_password()
    what = bootstrap_system_admin(boot, supplied=supplied)
    eric_pw = boot if what == "in use" else one_time_password()
    print(f"System administrator {what}: {SYSTEM_ADMIN[0]}")

    with httpx.Client(base_url=args.base, timeout=120) as c:
        sign_in(c, SYSTEM_ADMIN[0], boot)
        if what != "in use":
            set_own_password(c, boot, eric_pw, "the system administrator")
            issued.append((SYSTEM_ADMIN[1], SYSTEM_ADMIN[0], "SYSTEM_ADMIN",
                           eric_pw))

        # ── Eric sets up Barb, and stops ─────────────────────────────
        barb_pw = one_time_password()
        email, name, key = ORG_ADMIN
        r = c.post("/api/auth/actors", json={
            "email": email, "display_name": name, "role": "ORG_ADMIN",
            "password": barb_pw, "employee_key": key,
            "portfolios": [], "grant_reason": BARB_REASON})
        if r.status_code == 409:
            print(f"  exists    {email}")
            barb_pw = os.environ.get("YBI_ORG_ADMIN_PASSWORD", "")
            barb_in_use = bool(barb_pw)
            if not barb_pw:
                # The account may have been opened by the deployment itself.
                # `app/foundation.py` opens the six on the organisation's
                # password when the record comes back without them, and the
                # two doors have to compose rather than collide: this script
                # ran, reset the root account and then stopped here, on a
                # deployment where the answer was a variable already set.
                #
                # Only on SEED. An account on ADMIN or SELF holds a password
                # somebody chose for one named person, and signing in as
                # them with the organisation's value is precisely what
                # `check_credential` refuses.
                from app.auth import shared_initial_password
                from app.db import one, open_pool
                open_pool()
                row = one("SELECT password_set_by::text AS o FROM actor "
                          "WHERE email=%s", (email,))
                if row and row["o"] == "SEED" and shared_initial_password():
                    barb_pw = shared_initial_password()
                    print(f"  on the organisation's password  {email}")
            if not barb_pw:
                raise SystemExit(
                    f"{email} already exists. Set YBI_ORG_ADMIN_PASSWORD to "
                    f"their current password to continue, or set "
                    f"YBI_INITIAL_PASSWORD if the deployment opened the "
                    f"account, or reset it out of band.")
        elif r.status_code != 201:
            raise SystemExit(f"could not provision {email}: {r.text[:300]}")
        else:
            print(f"  ORG_ADMIN {email}  provisioned by Eric Wagner")
            issued.append((name, email, "ORG_ADMIN", barb_pw))
            barb_in_use = False

        # The ladder refuses upward. Proving it here means the rule is
        # exercised on every run rather than asserted in a comment.
        probe = c.post("/api/auth/actors", json={
            "email": "peer@ybi.org", "display_name": "Peer Admin",
            "role": "SYSTEM_ADMIN", "password": one_time_password()})
        assert probe.status_code == 403, \
            f"a system administrator minted a peer ({probe.status_code})"
        print("  refused    a system administrator creating another one — 403")

    # ── Barb sets up the finance accounts ────────────────────────────
    with httpx.Client(base_url=args.base, timeout=120) as c:
        sign_in(c, ORG_ADMIN[0], barb_pw)
        me = c.get("/api/auth/me").json()
        if me.get("must_set_password"):
            new = one_time_password()
            set_own_password(c, barb_pw, new, "the organisation's administrator")
            for i, row in enumerate(issued):
                if row[1] == ORG_ADMIN[0]:
                    issued[i] = (row[0], row[1], row[2], new)
            barb_pw = new          # every later step signs in with this one
            sign_in(c, ORG_ADMIN[0], new)

        # An organisation administrator cannot mint a peer either.
        probe = c.post("/api/auth/actors", json={
            "email": "peer2@ybi.org", "display_name": "Peer",
            "role": "ORG_ADMIN", "password": one_time_password()})
        assert probe.status_code == 403, \
            f"an org admin provisioned a peer ({probe.status_code})"
        print("  refused    an organisation administrator creating another — 403")

        for email, name, role, key, portfolios, why in STAFF:
            pw = one_time_password()
            r = c.post("/api/auth/actors", json={
                "email": email, "display_name": name, "role": role,
                "password": pw, "employee_key": key,
                "portfolios": portfolios, "grant_reason": why})
            if r.status_code == 409:
                print(f"  exists    {email}")
                continue
            if r.status_code != 201:
                print(f"  FAILED    {email}: {r.text[:200]}", file=sys.stderr)
                continue
            print(f"  {role:12s} {email:24s} "
                  f"{', '.join(portfolios) or 'no portfolio'}")
            issued.append((name, email, role, pw))

        # ── The rest of the payroll ──────────────────────────────
        #
        # One password for everybody, which is what a bootstrap is, and every
        # one of them must be replaced before the account can record
        # anything. The addresses come from the naming convention the known
        # accounts use — they are a starting point, not a lookup, so each
        # account is marked with its address unconfirmed until somebody who
        # knows it says otherwise. An account nobody can sign into is a
        # better outcome than an account somebody else can.
        gaps = c.get("/api/auth/roster-gaps")
        seeded = 0
        if gaps.status_code == 200 and args.staff_password:
            if len(args.staff_password) < 12:
                raise SystemExit("--staff-password must be at least 12 characters.")
            for person in gaps.json()["people"]:
                key = person["employee_key"]
                r = c.post("/api/auth/actors", json={
                    "email": person["suggested_email"],
                    "display_name": person["employee_name"] or key,
                    "role": "EMPLOYEE", "employee_key": key,
                    "password": args.staff_password,
                    "portfolios": [], "grant_reason": ""})
                if r.status_code == 201:
                    seeded += 1
                elif r.status_code != 409:
                    print(f"  FAILED    {key}: {r.text[:140]}", file=sys.stderr)
            if seeded:
                mark_unconfirmed([p["suggested_email"]
                                  for p in gaps.json()["people"]])
                print(f"  EMPLOYEE     {seeded} account(s) seeded from the 2025 "
                      f"payroll, all on one password, all addresses derived")

        gaps = c.get("/api/auth/roster-gaps")
        if gaps.status_code == 200:
            n = gaps.json()["without_account"]
            if n:
                print(f"\n  {n} people on the 2025 payroll still have no "
                      f"account. They are listed on the People screen.")

    # ── The consultant's access to the client's books ────────────────
    #
    # Granted by YBI's own administrator, to the account above her in rank.
    # That is backwards for provisioning and exactly right here: the data is
    # theirs, so they are who lets somebody read it. An auditor asking who
    # authorised an outside consultant to see the payroll finds this row.
    with httpx.Client(base_url=args.base, timeout=120) as c:
        sign_in(c, ORG_ADMIN[0], barb_pw)
        roster = {a["email"]: a for a in c.get("/api/auth/actors").json()}
        eric_id = roster[SYSTEM_ADMIN[0]]["actor_id"]
        r = c.post(f"/api/auth/actors/{eric_id}/record-access", json={
            "granted": True, "reason": NDA_REASON})
        if r.status_code == 200:
            print(f"  granted    {SYSTEM_ADMIN[1]} access to the cost record, "
                  f"by {ORG_ADMIN[1]}")
        else:
            print(f"  FAILED     record access for {SYSTEM_ADMIN[0]}: "
                  f"{r.text[:200]}", file=sys.stderr)

    # The two administrators had to hold a working password for this script
    # to act as them at all. That password was chosen by a script, not by
    # them — so it is marked as issued rather than self-chosen, and the gate
    # will ask each of them for their own before they can record anything.
    # Claiming otherwise would put a signature in the file that nobody chose.
    # Only the ones this run chose a password for. An account already in use
    # by a person keeps the password that person set.
    mark_issued([e for _, e, _, _ in issued
                 if e in (SYSTEM_ADMIN[0], ORG_ADMIN[0])])

    if args.dev_password:
        n = dev_passwords(args.dev_password)
        print(f"\n  DEVELOPMENT: {n} account(s) set to a shared password so "
              f"the drive scripts can sign in. This is refused outside a "
              f"development environment, and the sheet below does not apply.")
        return 0

    sheet = render_sheet(issued)
    print("\n" + sheet)
    if args.sheet:
        Path(args.sheet).write_text(sheet)
        Path(args.sheet).chmod(0o600)
        print(f"(also written to {args.sheet})")
    return 0


def dev_passwords(password: str) -> int:
    """Give every account one known password, marked self-chosen.

    Only for a sandbox. The drive scripts sign in as four different people
    and cannot each be handed a printed slip, and the write gate quite
    correctly refuses an account still on a password somebody else picked.

    Refused anywhere that is not development, because a shared password
    marked as self-chosen is exactly the lie the gate exists to prevent.
    """
    from app.settings import settings
    if settings.env != "dev":
        raise SystemExit(
            f"--dev-password refused: YBI_ENV is {settings.env!r}. A shared "
            f"password recorded as self-chosen would put signatures in the "
            f"file that nobody chose.")
    if len(password) < 12:
        raise SystemExit("--dev-password must be at least 12 characters.")
    from app.auth import hash_password
    from app.db import query
    rows = query("""UPDATE actor SET password_hash = %s,
                                     password_set_by = 'SELF',
                                     password_set_at = now()
                     RETURNING email""", (hash_password(password),))
    return len(rows)


def mark_unconfirmed(emails: list[str]) -> None:
    """Say which addresses were derived rather than known.

    The convention is a good guess and a guess is not a fact. An account
    flagged here shows on the roster as unable to sign in until somebody who
    knows the address corrects it, which is a shorter list to work than
    forty accounts that all look fine.
    """
    from app.db import execute
    for email in emails:
        execute("""UPDATE actor SET email_confirmed = false
                    WHERE email = %s AND password_set_by = 'ADMIN'""", (email,))


def mark_issued(emails: list[str]) -> None:
    from app.db import execute
    for email in emails:
        execute("""UPDATE actor SET password_set_by = 'ADMIN'
                    WHERE email = %s AND password_set_by = 'SELF'""", (email,))


def render_sheet(issued: list[tuple[str, str, str, str]]) -> str:
    if not issued:
        return "No new accounts — nothing to hand out."
    w = max(len(n) for n, _, _, _ in issued)
    lines = [
        "=" * 72,
        "  YBI Cost Allocation — first sign-in",
        "=" * 72,
        "",
        "  Hand each person their own line, and no more than their own line.",
        "  These passwords work once for signing in; the system will not let",
        "  anyone record anything until they have replaced theirs with one",
        "  only they know.",
        "",
    ]
    for name, email, role, pw in issued:
        lines.append(f"  {name:<{w}}  {email:<26} {role}")
        lines.append(f"  {'':<{w}}  password: {pw}")
        lines.append("")
    lines += [
        "  Sign in at the address in the invitation, choose your own",
        "  password when asked, and you will land on your own screen.",
        "",
        "  Destroy this sheet once the passwords have been handed out.",
        "=" * 72,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
