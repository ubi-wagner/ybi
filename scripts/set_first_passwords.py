#!/usr/bin/env python3
"""Set a first-login password on named accounts, out of band.

    railway run python3 scripts/set_first_passwords.py --check
    railway run python3 scripts/set_first_passwords.py --apply

Reads the passwords from `scripts/first_passwords.json` — a file that is
**gitignored and never committed** — so this script invents nothing and ships
nothing. `--check` reads the record and says what would change; `--apply`
writes.

Out of band on purpose, the same way `scripts/seed_actors.py` is. The API has
`POST /auth/actors/{id}/password`, which is the right door for a reset and
should be used where it can be — but it cannot start this. Rank runs downward
and only downward: nobody outranks `SYSTEM_ADMIN`, so no route can set that
account's password except its own owner, who needs a password to sign in with
to do it. A bootstrap is exactly the case the ladder cannot reach.

**Every account it touches is marked `ADMIN`, never `SELF`.** That is the
whole point: `refuse_issued_password` then refuses every write from the
account — no classification, no timesheet, no certification, no seal — until
its owner replaces the password. The one exit is changing it. So a password
from this sheet gets somebody *in*, and nothing they record carries their
name until it is theirs alone.

It also closes every session those accounts have open, because a reset whose
purpose is to hand an account to its owner cannot leave somebody else's
session alive inside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import MIN_PASSWORD, hash_password  # noqa: E402
from app.db import execute, one, open_pool, query  # noqa: E402

SHEET = Path(__file__).resolve().parent / "first_passwords.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true",
                   help="read the record and say what would change")
    g.add_argument("--apply", action="store_true", help="write it")
    ap.add_argument("--sheet", default=str(SHEET))
    args = ap.parse_args()

    sheet = Path(args.sheet)
    if not sheet.exists():
        print(f"No password sheet at {sheet}.\n\n"
              f"It is deliberately not in the repository. Write it as\n"
              f'  {{"tom@ybi.org": "...", "bewing@ybi.org": "..."}}\n'
              f"and delete it once the five people have signed in.",
              file=sys.stderr)
        return 2

    wanted: dict[str, str] = json.loads(sheet.read_text())
    short = [e for e, p in wanted.items() if len(p) < MIN_PASSWORD]
    if short:
        # The floor is the schema's, not this script's. A bootstrap that
        # lowered it would be setting passwords no route will accept as a
        # replacement, and the person would meet the refusal on the screen
        # that exists to get them past it.
        print(f"These are under the {MIN_PASSWORD}-character minimum the API "
              f"enforces: {', '.join(short)}", file=sys.stderr)
        return 2

    open_pool()
    rows = {r["email"]: r for r in query(
        """SELECT actor_id, email, display_name, role::text AS role,
                  is_active, password_set_by::text AS origin, last_login_at
             FROM actor WHERE email = ANY(%s)""", (list(wanted),))}

    missing = [e for e in wanted if e not in rows]
    if missing:
        # Never invent an account here. Creating one needs a role, an
        # employee key and a place on the ladder, all of which are judgments.
        print(f"No account for: {', '.join(missing)}. Open accounts on the "
              f"People screen first — this script only sets passwords.",
              file=sys.stderr)
        return 2

    print(f"{'account':<26} {'role':<14} {'now':<8} {'signed in before':<18} "
          f"{'->'}")
    for email in wanted:
        r = rows[email]
        seen = (f"{r['last_login_at']:%d %b %H:%M}" if r["last_login_at"]
                else "never")
        state = "inactive" if not r["is_active"] else r["origin"]
        print(f"  {email:<24} {r['role']:<14} {state:<8} {seen:<18} "
              f"ADMIN, must set their own")

    if args.check:
        print(f"\n--check only. Nothing was written. "
              f"{len(wanted)} account(s) would be set.")
        return 0

    for email, password in wanted.items():
        r = rows[email]
        execute("""UPDATE actor
                      SET password_hash = %s, password_set_by = 'ADMIN',
                          password_set_at = now()
                    WHERE actor_id = %s""", (hash_password(password),
                                             r["actor_id"]))
        closed = query("""UPDATE actor_session SET revoked_at = now()
                           WHERE actor_id = %s AND revoked_at IS NULL
                       RETURNING session_id""", (r["actor_id"],))
        # audit_log means "this changed", and a password set outside the API
        # is still a change to who can act as that person. `actor` is a name
        # rather than a session because a bootstrap has no session — which is
        # itself the fact worth recording.
        execute("""INSERT INTO audit_log (actor, action, entity, entity_id,
                                          after_state, reason)
                   VALUES (%s, 'PASSWORD_RESET', 'actor', %s, %s, %s)""",
                ("set_first_passwords.py (out of band)", str(r["actor_id"]),
                 json.dumps({"email": email, "origin": "ADMIN",
                             "sessions_closed": len(closed)}),
                 "first-login password set out of band; the owner must "
                 "replace it before the account can record anything"))
        print(f"  set      {email:<24} {len(closed)} session(s) closed")

    print(f"\n{len(wanted)} account(s) set. Each person must choose their own "
          f"password on first sign-in before they can record anything.\n"
          f"Delete {sheet} once they have.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
