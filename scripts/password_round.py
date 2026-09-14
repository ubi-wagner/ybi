#!/usr/bin/env python3
"""Put accounts back on the organisation's password, and end their sessions.

    PYTHONPATH=. python3 scripts/password_round.py --list
    PYTHONPATH=. python3 scripts/password_round.py --all --yes
    PYTHONPATH=. python3 scripts/password_round.py --email hruby@ybi.org --yes

Opening a round means everybody signs in on one value the organisation
holds and replaces it with their own before they can record anything. A
deployment that has just been rebuilt is already there — every account the
boot opened is on `SEED` — and this is for the other case: accounts that
survived on passwords their owners chose, and the person who has forgotten
theirs.

**This takes an account away from the person using it**, which is the one
thing every other path in this system refuses to do, so three things are
true of it:

- it is never automatic. The boot bootstrap opens missing accounts and will
  not touch one that exists; this is the deliberate act, run by a person,
  behind `--yes`.
- it revokes every live session. Leaving them open would mean somebody
  carries on writing on a credential that has been withdrawn, which is the
  opposite of the point.
- it writes an audit row per account naming who ran it, so "why am I being
  asked for a password again" has an answer on the record rather than in
  somebody's memory.

It does **not** invent or store a password. `YBI_INITIAL_PASSWORD` is the
way in and it stays a setting: the row gets the random hash nobody holds,
exactly as `unusable_password_hash` describes. With no organisational
password configured this refuses outright, because putting six accounts on
a credential that does not exist is locking six people out.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import shared_initial_password, unusable_password_hash  # noqa: E402
from app.db import execute, one, open_pool, query, transaction  # noqa: E402


def roster() -> list[dict]:
    return query("""SELECT a.actor_id, a.email, a.display_name,
                           a.role::text AS role,
                           a.password_set_by::text AS origin,
                           a.is_active,
                           (SELECT count(*) FROM actor_session s
                             WHERE s.actor_id = a.actor_id
                               AND s.revoked_at IS NULL
                               AND s.expires_at > now()) AS live_sessions
                      FROM actor a
                     ORDER BY a.role, a.email""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true",
                    help="show who is on what, and change nothing")
    ap.add_argument("--all", action="store_true",
                    help="every active account")
    ap.add_argument("--email", action="append", default=[],
                    help="one address; repeatable")
    ap.add_argument("--yes", action="store_true",
                    help="required: this ends sessions and withdraws the "
                         "passwords people chose")
    ap.add_argument("--by", default="",
                    help="who is doing this; defaults to the shell user")
    args = ap.parse_args()

    open_pool()
    people = roster()

    if args.list or not (args.all or args.email):
        shared = shared_initial_password()
        print(f"the organisation's password is "
              f"{'set' if shared else 'NOT SET — nobody could sign in'}\n")
        print(f"  {'address':30s} {'role':13s} {'password':9s} sessions")
        for p in people:
            print(f"  {p['email']:30s} {p['role']:13s} "
                  f"{('theirs' if p['origin'] == 'SELF' else p['origin'].lower()):9s} "
                  f"{p['live_sessions']}"
                  f"{'' if p['is_active'] else '   (inactive)'}")
        if not args.list:
            print("\nNothing was changed. Pass --all or --email, with --yes.")
        return 0

    if not shared_initial_password():
        print("YBI_INITIAL_PASSWORD is not set, or is under twelve "
              "characters. Putting accounts on a credential that does not "
              "exist locks their owners out. Set it and run this again.",
              file=sys.stderr)
        return 2

    wanted = {e.strip().lower() for e in args.email}
    targets = [p for p in people
               if p["is_active"] and (args.all or p["email"] in wanted)]
    missing = wanted - {p["email"] for p in people}
    for m in sorted(missing):
        print(f"  no such account   {m}", file=sys.stderr)

    already = [p for p in targets if p["origin"] == "SEED"]
    moving = [p for p in targets if p["origin"] != "SEED"]

    for p in already:
        print(f"  already on it     {p['email']}")
    if not moving:
        print("\nNothing to do — everybody named is already on the "
              "organisation's password.")
        return 1 if missing else 0

    print(f"\nThis will withdraw the password {len(moving)} "
          f"{'person' if len(moving) == 1 else 'people'} chose, end "
          f"{sum(p['live_sessions'] for p in moving)} live session(s), and "
          f"require each of them to sign in on the organisation's password "
          f"and choose a new one:\n")
    for p in moving:
        print(f"  {p['email']:30s} {p['display_name']}")

    if not args.yes:
        print("\nRe-run with --yes to do it.", file=sys.stderr)
        return 2

    by = args.by or getpass.getuser()
    for p in moving:
        # One transaction per account: the hash, the sessions and the audit
        # row are one act, and a half-applied one would leave somebody
        # signed out of an account whose password had not moved.
        with transaction() as cur:
            cur.execute("""UPDATE actor
                              SET password_hash = %s, password_set_by = 'SEED',
                                  password_set_at = now()
                            WHERE actor_id = %s""",
                        (unusable_password_hash(), p["actor_id"]))
            cur.execute("""UPDATE actor_session SET revoked_at = now()
                            WHERE actor_id = %s AND revoked_at IS NULL""",
                        (p["actor_id"],))
            cur.execute("""INSERT INTO audit_log (actor, action, entity,
                                                  entity_id, reason)
                           VALUES (%s, 'PASSWORD_CHANGE', 'actor', %s, %s)""",
                        (f"password round by {by}", p["email"],
                         "put back on the organisation's first-login "
                         "password; every session ended. They choose their "
                         "own again at next sign-in."))
        print(f"  moved             {p['email']}")

    print(f"\n{len(moving)} account(s) are on the organisation's password. "
          f"Tell them to sign in with it and choose their own.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
