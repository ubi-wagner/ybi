#!/usr/bin/env python3
"""File an invoice under the year it is dated, when a loader filed it wrong.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/reperiod_invoices.py \\
        --check [--base http://127.0.0.1:8000]
    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/reperiod_invoices.py --apply

`load_invoices.py` wrote `period` as the literal `'2025'` while its three
invoices are dated April 2026, so every 2025 figure taken off the register
compared thirteen months to twelve — 19,145.79 of Drive AM ODCs on its own.
The invoice itself is untouched: the date, the amount, the lines and the
status all stand. Only the fiscal period it is filed under moves, and it moves
to the one its own date names.

**It signs in first, and that is the whole point of the file.** The first
version of this correction was a direct INSERT into `audit_log` naming the
script, and `drive_everyone` caught it within the hour: *3 audit entries have
no actor or no session*. Before it, every entry on the record named an account
and the session it was made in — one of the cleaner invariants here, and one
a convenient `psql` breaks silently. `app/audit.py` opens by saying the actor
is never a parameter, and a script writing its own name into that column is
that rule broken from outside.

There is no route that re-periods an invoice and there should not be: it
corrects a loader, not a business event. So this stays out of band — but out
of band is about *where the statement runs*, never about whether a person
stands behind it. A real person signs in, and the row carries their actor id
and their session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.db import one, open_pool, query, transaction  # noqa: E402
from app.foundation import EMAIL  # noqa: E402


def sign_in(base: str, email: str, password: str) -> dict:
    """The actor and the live session behind them, or nothing."""
    c = httpx.Client(base_url=base, timeout=60)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code}: "
                         f"{r.text[:160]})")
    actor_id = r.json()["actor_id"]
    session = one("""SELECT session_id FROM actor_session
                      WHERE actor_id = %s AND revoked_at IS NULL
                      ORDER BY issued_at DESC LIMIT 1""", (actor_id,))
    if not session:
        raise SystemExit("signed in and no live session is on the record — "
                         "the audit row would have nothing to point at")
    return dict(actor_id=actor_id, session_id=session["session_id"],
                name=r.json()["display_name"], role=r.json()["role"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--actor", default=EMAIL["tom"])
    args = ap.parse_args()

    open_pool()
    wrong = query("""
        SELECT invoice_id, invoice_number, invoice_date, period, objective_id,
               total, to_char(invoice_date, 'YYYY') AS should_be
          FROM invoice
         WHERE period <> to_char(invoice_date, 'YYYY')
         ORDER BY invoice_number""")

    if not wrong:
        print("Every invoice is filed under the year it is dated.")
        return 0

    print(f"{'invoice':>9} {'dated':<12} {'objective':<13} {'total':>13}  "
          f"{'filed':<7} -> {'should be'}")
    for w in wrong:
        print(f"  {w['invoice_number']:>7} {str(w['invoice_date']):<12} "
              f"{str(w['objective_id']):<13} {w['total']:>13,.2f}  "
              f"{w['period']:<7} -> {w['should_be']}")

    missing = {w["should_be"] for w in wrong} - {
        r["period"] for r in query("SELECT period FROM fiscal_period")}
    if missing:
        raise SystemExit(f"no fiscal period on the record for {sorted(missing)} "
                         f"— open it before filing anything into it")

    if args.check:
        print(f"\n--check only, nothing written. {len(wrong)} to re-file.")
        return 0

    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required — the correction is "
                         "recorded against a person, so it needs one to sign "
                         "in as.")
    who = sign_in(args.base, args.actor, password)
    print(f"\nrecorded as {who['name']} ({who['role']})")

    with transaction() as cur:
        for w in wrong:
            cur.execute("UPDATE invoice SET period = %s WHERE invoice_id = %s",
                        (w["should_be"], w["invoice_id"]))
            cur.execute("""
                INSERT INTO audit_log (actor, actor_id, session_id, action,
                                       entity, entity_id, before_state,
                                       after_state, reason)
                VALUES (%s,%s,%s,'INVOICE_REPERIOD','invoice',%s,%s,%s,%s)""",
                (who["name"], who["actor_id"], who["session_id"],
                 str(w["invoice_id"]),
                 json.dumps({"period": w["period"]}),
                 json.dumps({"period": w["should_be"]}),
                 f"Filed under {w['period']} by a constant in the loader; the "
                 f"invoice is dated {w['invoice_date']}. The invoice is "
                 f"unchanged — only the period it is filed under."))
            print(f"  re-filed {w['invoice_number']} into {w['should_be']}")
    print(f"\n{len(wrong)} invoice(s) re-filed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
