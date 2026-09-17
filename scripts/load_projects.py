#!/usr/bin/env python3
"""The three America Makes projects, set up on the contracts they work under.

    PYTHONPATH=. python3 scripts/load_projects.py --base http://127.0.0.1:8000

Recorded through the real endpoint, so the trail shows a person setting a
project up rather than a migration asserting one.

**Signed in as the controller, not as the manager.** The first draft ran as
Stephanie and was refused three times — *"Nobody puts themselves on a charge
code"* — which is the rule working exactly as intended. An assignment is a
statement by one person about another, and one made by its own beneficiary
says nothing. So Tom names her, which is also what "set Stephanie as the
manager" has to mean if the record is to be worth anything.

**Facts only.** Every part of this is already on the record somewhere and is
being tied together rather than invented:

    the project      a charge code that already exists, and the award it
                     works under, matched on `award.objective_id`
    the manager      Stephanie Gaffney, who held the project-manager role
                     across 2025 as a helper to the controller
    the team         whoever the 2025 payroll distribution actually put on
                     the objective — `labor_allocation`, not a guess
    the first job    one todo per project, naming what is genuinely
                     outstanding on it and read from the record

**And no claim is approved here.** A claim is the manager saying a span of
work is right, which is a judgment with her name on it. The seed inventing
one would be the thing `CLAUDE.md` argues against on every other page — so
what the seed leaves behind is the *job of making it*, which is the honest
first state and also the demonstration: the loop starts with somebody having
to do something.

`scripts/drive_projects.py` walks the loop as the real people and leaves the
record as it found it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx                                              # noqa: E402

from app.db import one, open_pool, query                  # noqa: E402
from app.foundation import EMAIL  # noqa: E402

#: Who ran the projects in 2025. The project-manager role here was a helper
#: to the controller rather than a separate job, which is why Stephanie holds
#: CONTROLLER as well — and why the manager is recorded as a *role on the
#: grant* rather than as a rank.
MANAGER = "GAFFNEY"

#: What is genuinely outstanding on each, read off the record rather than
#: made up. Each of these is answerable and none of them is busywork.
FIRST_JOBS = {
    "DRIVE-AM": (
        "Approve the 2025 work so it can be tied to invoice 10018",
        "Invoice 10018 was issued for $37,593.90 and nothing on the record "
        "says which work it settles. Approving the 2025 span links the "
        "people, the hours, the documents and the money to each other for "
        "the first time."),
    "HYBRID-II": (
        "Approve the 2025 work so it can be tied to invoice 10023",
        "Invoice 10023 was issued for $1,374.00. Same thread: nothing "
        "connects it to the work underneath it."),
    "LTM": (
        "Approve the 2025 work so it can be tied to invoice 10039",
        "Invoice 10039 was issued for $18,993.52. Last Tactical Mile is also "
        "the only one of the four awards that budgets a real indirect figure "
        "— $81,772.76 — so what it claims matters more than the others."),
}


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    if r.json().get("must_set_password"):
        raise SystemExit(f"{email} is on a password somebody else chose, so "
                         f"nothing can be recorded under it.")
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--period", default="2025")
    ap.add_argument("--who", default=EMAIL["tom"])
    ap.add_argument("--password", default="")
    args = ap.parse_args()
    password = (args.password or os.environ.get("YBI_SEED_PASSWORD")
                or getpass.getpass(f"password for {args.who}: "))
    open_pool()
    c = sign_in(args.base, args.who, password)

    # The awards with an invoice on file — which is what "active now" means
    # for a project that has to be tied to money. The fourth, Digital
    # Engineering, has an award and no invoice, so there is nothing yet to
    # thread back to and it is named rather than quietly skipped.
    awards = query("""SELECT a.award_id, a.objective_id, a.sponsor,
                             a.period_start, a.period_end, o.label,
                             o.is_federal,
                             (SELECT count(*) FROM invoice i
                               WHERE i.objective_id = a.objective_id) AS invoices
                        FROM award a
                        JOIN cost_objective o ON o.objective_id = a.objective_id
                       ORDER BY a.award_id""")

    made = skipped = 0
    for aw in awards:
        if not aw["invoices"]:
            print(f"  NO INVOICE  {aw['award_id']} — nothing to thread a "
                  f"claim back to yet, so no project opened",
                  file=sys.stderr)
            skipped += 1
            continue
        if one("SELECT 1 FROM project WHERE objective_id = %s",
               (aw["objective_id"],)):
            print(f"  exists      {aw['objective_id']}")
            continue

        # The team, read off the payroll distribution rather than chosen.
        people = query("""SELECT DISTINCT employee_key
                            FROM labor_allocation
                           WHERE period = %s AND objective_id = %s
                           ORDER BY employee_key""",
                       (args.period, aw["objective_id"]))
        team = [{"employee_key": MANAGER, "role_on_project": "MANAGER",
                 "reason": "Project manager across 2025, as a helper to the "
                           "controller. Recorded as a role on the grant "
                           "because that is where a person's role on a code "
                           "already lives."}]
        for p in people:
            if p["employee_key"] == MANAGER:
                continue
            team.append({
                "employee_key": p["employee_key"],
                "role_on_project": "",
                "reason": f"On the 2025 payroll distribution for "
                          f"{aw['objective_id']} — read off the register "
                          f"rather than assigned by hand."})

        title, detail = FIRST_JOBS.get(
            aw["objective_id"],
            ("Approve the 2025 work", "Tie the invoice to what is under it."))
        r = c.post("/api/projects", params={"period": args.period}, json={
            "objective_id": aw["objective_id"],
            "name": f"{aw['label']} — {aw['sponsor']}",
            "summary": f"{aw['award_id']}. Cost reimbursement, invoiced "
                       f"monthly. Performance {aw['period_start']} to "
                       f"{aw['period_end']}.",
            "award_id": aw["award_id"],
            "starts_on": str(aw["period_start"]),
            "ends_on": str(aw["period_end"]),
            "people": team,
            "todos": [{"title": title, "detail": detail,
                       "due_on": str(dt.date.today() + dt.timedelta(days=30))}],
            "reason": f"Setting {aw['label']} up so the 2025 work, the people "
                      f"on it and the invoice already issued against it hang "
                      f"together.",
        })
        if r.status_code >= 400:
            print(f"  FAILED      {aw['objective_id']} — {r.status_code} "
                  f"{r.text[:160]}", file=sys.stderr)
            skipped += 1
            continue
        got = r.json()
        print(f"  {aw['objective_id']:12} {aw['award_id']:15} "
              f"{len(got['people'])} on it, manager {MANAGER}, "
              f"{got['todos']} job to do"
              + ("" if got["gate_live"] else "  ← nobody assigned, gate off"))
        made += 1

    print(f"\n  {made} project(s) set up"
          + (f", {skipped} not" if skipped else "")
          + ".\n  No claim approved — that is the manager's judgment, and "
            "each project carries the job of making it.")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
