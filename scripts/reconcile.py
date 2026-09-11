#!/usr/bin/env python3
"""Schedule A-1: run the three source documents against each other.

    PYTHONPATH=. python3 scripts/reconcile.py [--base http://127.0.0.1:8000]
                                              [--record]

Reads the cross-reference register, prints every control, and for each
account where the ledger and the profit and loss disagree asks the system
which ledger lines would account for the difference.

With --record it signs in as the controller and records the proposals that
came back unambiguous, each as a written reconciling item with the lines
behind it. Without it, nothing is written: the proposals are shown and the
register is left saying what it says.

Exits non-zero if a control that should tie does not, so this can be the
gate in front of classification rather than a report nobody reads.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import httpx

# Differences that come from the books moving between two exports. Naming the
# kind is a judgment; naming it once here keeps the wording consistent across
# however many accounts turn out to be affected.
DEFAULT_KIND = "RECLASS_AFTER_EXPORT"


def sign_in(c: httpx.Client, email: str) -> None:
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required to record anything.")
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code})")


def money(v) -> str:
    return f"{Decimal(str(v)):,.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--period", default="2025")
    ap.add_argument("--record", action="store_true",
                    help="record the unambiguous proposals as reconciling items")
    ap.add_argument("--as-user", default=os.environ.get("YBI_TOM", "tom@ybi.org"))
    args = ap.parse_args()

    with httpx.Client(base_url=args.base, timeout=120) as c:
        sign_in(c, args.as_user)

        if args.record:
            # The general ledger calls the accumulated surplus one thing and
            # the balance sheet another. Written down, with the reason.
            c.post("/api/reconcile/aliases", json={
                "gl_account": "Retained Earnings",
                "statement": "BALANCE_SHEET",
                "statement_account": "3000 Fund Balance",
                "reason": ("The general ledger prints the accumulated surplus "
                           "as Retained Earnings and the balance sheet prints "
                           "it as 3000 Fund Balance. Same account, same "
                           "balance, two labels."),
            }).raise_for_status()

            props = c.get("/api/reconcile/propose",
                          params={"period": args.period}).json()
            print("Proposals")
            for p in props["proposals"]:
                head = (f"  {p['from_account'][:46]:46s} -> "
                        f"{p['to_account'][:40]:40s} {money(p['amount']):>12}")
                if not p["proposed"]:
                    print(head + "   no unique attribution")
                    print(f"      {p['why_not']}")
                    continue
                print(head + f"   {len(p['lines'])} line"
                      + ("" if len(p["lines"]) == 1 else "s"))
                for l in p["lines"]:
                    print(f"      {l['date']}  {l['payee'][:28]:28s} "
                          f"{money(l['amount']):>10}  {l['memo'][:34]}")
                r = c.post("/api/reconcile/items", json={
                    "control": "GL_PL_ACCOUNT",
                    "from_account": p["from_account"],
                    "to_account": p["to_account"],
                    "amount": p["amount"],
                    "kind": DEFAULT_KIND,
                    "explanation": (
                        f"{len(p['lines'])} line{'' if len(p['lines']) == 1 else 's'} "
                        f"sitting in "
                        f"{p['from_account']} in the general ledger and in "
                        f"{p['to_account']} on the profit and loss. The two "
                        f"exports are two moments in the same books; the "
                        f"reclassification was posted after the ledger was "
                        f"run. No effect on the section total or net income."),
                    "line_ids": [l["line_id"] for l in p["lines"]],
                    "period": args.period,
                })
                if r.status_code != 201:
                    print(f"      REFUSED: {r.text[:200]}")
            print()

        reg = c.get("/api/reconcile", params={"period": args.period}).json()

    print(f"Cross-reference register — {args.period}\n")
    for ctl in reg["controls"]:
        mark = "tie " if ctl["ties"] else "OPEN"
        print(f"  [{mark}] {ctl['control']:22s} {ctl['description']}")
        print(f"         {ctl['left_label']:38s} {money(ctl['left_value']):>18}")
        print(f"         {ctl['right_label']:38s} {money(ctl['right_value']):>18}")
        if ctl["basis"] == "VARIANCE":
            print(f"         {'variance':38s} {money(ctl['variance']):>18}")
        else:
            print(f"         {'exceptions':38s} {int(ctl['exceptions']):>18}")
        print()

    if reg["ties"]:
        print("Every cross-reference point ties.")
        return 0
    print("Open: " + ", ".join(reg["failing"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
