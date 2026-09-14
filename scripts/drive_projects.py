#!/usr/bin/env python3
"""The handoff, walked as the two people who do it.

    YBI_SEED_PASSWORD=... python3 scripts/drive_projects.py [--base URL]

Stephanie manages the projects and Tom does the invoicing, which for 2025 was
a helper arrangement rather than two departments — and it is exactly the
shape the loop needs, because every step is one person handing work to
another and the whole point is that neither has to remember.

    the manager approves a span   ->  the controller gets a job to invoice
    the controller sends it back  ->  the manager gets a job to answer
    the controller settles it     ->  the manager gets a job to chase the money

Every write is checked three ways, the same as `drive_everyone`: the call
answered the way the contract says, the database moved the way the call
claimed, and the change is on the audit record under the name of the person
who made it.

**And it leaves the record as it found it**, checked against a census taken
before it started. `drive_contracts` had been writing fiction onto real
awards for as long as it existed; a drive that cannot clean up after itself
is the thing that fixed.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run, which
is not a pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx                                              # noqa: E402

from app.db import one, open_pool, query                  # noqa: E402
from app.foundation import EMAIL  # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []
CENSUS = ("project", "project_claim", "todo", "charge_authority")
#: Todos this run raised that hang off no claim, so teardown can
#: find them: a recommendation points at a worklist item rather
#: than at a claim, so `from_claim` is NULL on every one.
MADE_TODOS: list[str] = []
BEFORE: dict[str, int] = {}
MADE: list[str] = []


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def step(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m", flush=True)


def census() -> dict[str, int]:
    return {t: one(f"SELECT count(*) AS n FROM {t}")["n"] for t in CENSUS}


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    return c


def call(c: httpx.Client, method: str, path: str, expect: int, what: str,
         **kw) -> httpx.Response:
    r = c.request(method, path, **kw)
    (ok if r.status_code == expect else finding)(
        f"{what} — {r.status_code}"
        + ("" if r.status_code == expect else f" (wanted {expect})"
           + f" {r.text[:140]}"))
    return r


def audit_says(action: str, email: str) -> bool:
    """Whether the newest entry for this action names that person.

    `audit_log.actor` holds a **display name**, not an email — which this
    checked for and was wrong about, reporting a fault against working code
    on its first run. So the name is read off the account rather than written
    down here in either spelling: a value recalled instead of read is the
    defect `scripts/schema.py` and `tests/test_sql_is_real.py` exist for, and
    it does not stop being one because it is in a drive.
    """
    who = one("SELECT display_name FROM actor WHERE email = %s", (email,))
    row = one("""SELECT actor FROM audit_log WHERE action = %s
                  ORDER BY occurred_at DESC LIMIT 1""", (action,))
    return bool(who) and bool(row) and row["actor"] == who["display_name"]


def main() -> int:
    global BEFORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is not set.", file=sys.stderr)
        return 2
    open_pool()
    BEFORE = census()
    # The registers that carry a figure. A recommendation must move none of
    # them — it raises work, and the whole design turns on the difference.
    REGISTERS = {t: one(f"SELECT count(*) AS n FROM {t}")["n"]
                 for t in ("restatement", "decision", "rate")}

    steph = sign_in(args.base, "sgaffney@ybi.org", pw)
    tom = sign_in(args.base, EMAIL["tom"], pw)
    auditor = sign_in(args.base, "auditor@ybi.org", pw)

    # A project the loader set up. If none exists the drive says so rather
    # than inventing one: `load_projects.py` is what puts them there and a
    # drive standing up its own would be proving its own scaffolding.
    proj = one("""SELECT objective_id, name FROM v_project_overview
                   WHERE manager IS NOT NULL AND status <> 'CLOSED'
                   ORDER BY objective_id LIMIT 1""")
    if not proj:
        print("\nCOULD NOT RUN — no project with a manager on it. Run "
              "scripts/load_projects.py first.", file=sys.stderr)
        return 2
    code = proj["objective_id"]

    step(f"What {proj['name']} holds, before anybody says anything about it")
    w = call(steph, "GET", f"/api/projects/{code}", 200, "the project",
             params={"period": args.period}).json()
    work = w["work"]
    ok(f"{work['timesheet_hours']} hours booked, "
       f"{work['classified_amount']} of cost classified, "
       f"{work['documents']} document(s) — and "
       f"{work['distributed_wages']} of wages distributed across "
       f"{work['people_distributed']} people, which is annual and named "
       f"separately because it is not span-scoped")
    if w["project"]["manager"]:
        ok(f"{w['project']['manager']} manages it, read off the role on the "
           f"grant rather than from a column of its own")
    else:
        finding("the project has no manager")

    step("The manager approves a span, and the controller gets a job")
    before_todos = one("SELECT count(*) AS n FROM todo")["n"]
    r = call(steph, "POST", f"/api/projects/{code}/claims", 201,
             "approved a span", params={"period": args.period}, json={
                 "covers_from": f"{args.period}-01-01",
                 "covers_to": f"{args.period}-12-31",
                 "hand_to": EMAIL["tom"],
                 "note": "Drive: the year as distributed, for the handoff to "
                         "be walked. Withdrawn at the end of this run."})
    if r.status_code != 201:
        return 1
    claim = r.json()["claim_id"]
    MADE.append(claim)

    if not audit_says("CLAIM_APPROVE", "sgaffney@ybi.org"):
        finding("the approval is not on the audit record under her name")
    else:
        ok("the approval is on the record under Stephanie's name")

    after_todos = one("SELECT count(*) AS n FROM todo")["n"]
    if after_todos == before_todos + 1:
        ok("one job was raised by it — an act by one person that creates "
           "work for another is one act, not two people remembering")
    else:
        finding(f"todos went {before_todos} to {after_todos} on one approval")

    mine = call(tom, "GET", "/api/todos", 200, "Tom's own list",
                params={"mine": "true", "period": args.period}).json()
    his = [t for t in mine["todos"] if t["from_claim"] == claim]
    if his:
        ok(f"and it is on his list: “{his[0]['title'][:60]}”, due "
           f"{his[0]['due_on']}")
    else:
        finding("the job did not reach Tom — which is the whole point of "
                "`060`: he holds CONTROLLER and is not on the payroll "
                "register, so an employee key could never have reached him")

    step("What the approval was of, and what happens when the record moves")
    got = one("""SELECT saw_hours, saw_amount, saw_documents, still_agrees
                   FROM v_project_claim WHERE claim_id = %s::uuid""", (claim,))
    if got["still_agrees"]:
        ok(f"it agrees with the record: approved against {got['saw_hours']} "
           f"hours, {got['saw_amount']} and {got['saw_documents']} document(s)")
    else:
        finding("a claim approved a moment ago already disagrees with the "
                "record")

    step("The controller sends it back — the other direction")
    r = call(tom, "POST", f"/api/claims/{claim}/query", 200, "queried it",
             json={"reason": "Drive: sending it back to prove the loop "
                             "closes both ways."})
    if r.status_code == 200:
        back = call(steph, "GET", "/api/todos", 200, "Stephanie's own list",
                    params={"mine": "true", "period": args.period}).json()
        hers = [t for t in back["todos"] if t["from_claim"] == claim]
        if hers:
            ok(f"it went back to her: “{hers[0]['title'][:58]}”")
        else:
            finding("the query did not reach the manager who approved it")
        still_open = one("""SELECT count(*) AS n FROM todo
                             WHERE from_claim = %s::uuid AND status <> 'DONE'""",
                         (claim,))["n"]
        if still_open == 1:
            ok("and the job it answered is closed — one live job per claim, "
               "or the list grows a row every time somebody looks at it")
        else:
            finding(f"{still_open} live jobs on one claim after a query")

    step("And settled against the invoice already on file")
    inv = one("""SELECT invoice_id, invoice_number FROM invoice
                  WHERE objective_id = %s ORDER BY invoice_date LIMIT 1""",
              (code,))
    if not inv:
        ok("no invoice on this objective, so there is nothing to settle "
           "against — said rather than skipped")
    else:
        r = call(tom, "POST", f"/api/claims/{claim}/invoiced", 200,
                 f"settled against {inv['invoice_number']}",
                 json={"invoice_id": str(inv["invoice_id"]),
                       "note": "Drive: linking rather than creating, because "
                               "no route here raises an invoice."})
        if r.status_code == 200:
            chase = one("""SELECT title FROM todo
                            WHERE from_claim = %s::uuid AND status <> 'DONE'
                            ORDER BY opened_at DESC LIMIT 1""", (claim,))
            if chase and "watch for the money" in chase["title"]:
                ok("and the manager is told it went out, with a job to watch "
                   "for the money — the loop only closes if it closes both "
                   "ways")
            else:
                finding("nothing went back to the manager when it was invoiced")

    step("A helper recommends, and the controller is the one who decides")
    # Something outstanding that nobody has picked up. Read from the live
    # record rather than named, because a drive that hard-codes an item is a
    # drive that starts failing the day the item is cleared — which is the
    # good outcome.
    item = one("""SELECT kind, entity_id, label, owner_portfolio
                    FROM v_worklist_covered
                   WHERE period = %s AND NOT taken
                   ORDER BY amount DESC NULLS LAST LIMIT 1""", (args.period,))
    if not item:
        ok("nothing is outstanding and unclaimed, so there is nothing to "
           "recommend — which is the good outcome, not a gap")
    else:
        reason = ("Drive: recommended to prove the helper-recommends path. "
                  "Withdrawn at the end of this run.")
        rec = call(steph, "POST", "/api/dashboard/worklist/recommend", 201,
                   f"Stephanie recommends {item['label'][:48]}",
                   params={"period": args.period},
                   json={"kind": item["kind"], "entity_id": item["entity_id"],
                         "reason": reason})
        if rec.status_code == 201:
            got = rec.json()
            MADE_TODOS.append(got["todo_id"])
            ok(f"and the answer says where it went — "
               f"{'to ' + got['to_whom'] if got['assigned'] else got['to_whom']}")

            # The whole point, in one row: who noticed is not who decides.
            row = one("""SELECT taken, assignee, opened_by
                           FROM v_worklist_covered
                          WHERE period = %s AND kind = %s AND entity_id = %s""",
                      (args.period, item["kind"], item["entity_id"]))
            if row and row["taken"] and row["opened_by"] == "Stephanie Gaffney":
                ok(f"the list now says who noticed it — opened by "
                   f"{row['opened_by']}, held by "
                   f"{row['assignee'] or 'nobody yet'}. audit_log has always "
                   f"said who decided and nothing said who spotted it")
            else:
                finding(f"the item does not read as recommended: {row}")

            call(steph, "POST", "/api/dashboard/worklist/recommend", 409,
                 "a second recommendation on the same item is refused — two "
                 "people each told to clear it is two each assuming the other "
                 "has", params={"period": args.period},
                 json={"kind": item["kind"], "entity_id": item["entity_id"],
                       "reason": reason})

        call(steph, "POST", "/api/dashboard/worklist/recommend", 404,
             "and an item that is not outstanding cannot be recommended",
             params={"period": args.period},
             json={"kind": item["kind"], "entity_id": "no-such-entity",
                   "reason": reason})

        # Nobody recommends to themselves. The rule provisioning, the
        # portfolios and charge authority already follow — handing yourself a
        # job is *taking* one, which reads differently on the record and is
        # the whole reason this act exists separately.
        spare = one("""SELECT kind, entity_id FROM v_worklist_covered
                        WHERE period = %s AND NOT taken
                          AND entity_id <> %s
                        ORDER BY amount DESC NULLS LAST LIMIT 1""",
                    (args.period, item["entity_id"]))
        if spare:
            call(steph, "POST", "/api/dashboard/worklist/recommend", 422,
                 "and nobody recommends to themselves — that is taking a job, "
                 "not asking for one", params={"period": args.period},
                 json={"kind": spare["kind"], "entity_id": spare["entity_id"],
                       "reason": reason, "hand_to": "sgaffney@ybi.org"})

    # A recommendation raises work and never a number, so nothing that carries
    # a figure may have moved. Checked rather than asserted in a comment.
    moved = [t for t in ("restatement", "decision", "rate")
             if one(f"SELECT count(*) AS n FROM {t}")["n"] != REGISTERS[t]]
    if moved:
        finding(f"recommending moved {', '.join(moved)} — it must raise work "
                f"and nothing else")
    else:
        ok("and no register moved: not a restatement, not a judgment, not a "
           "rate. A recommendation raises work, never a number")

    step("The auditor reads the whole thread and writes none of it")
    call(auditor, "GET", "/api/claims", 200, "every claim",
         params={"period": args.period})
    call(auditor, "POST", f"/api/projects/{code}/claims", 403,
         "refused to approve one",
         json={"covers_from": f"{args.period}-01-01",
               "covers_to": f"{args.period}-12-31",
               "note": "an auditor writes nothing"})
    call(auditor, "POST", f"/api/claims/{claim}/query", 403,
         "refused to query one", json={"reason": "an auditor writes nothing"})
    # No portfolio at all, so the refusal is the portfolio gate rather than a
    # rule about auditors — and the screen does not offer them the button.
    call(auditor, "POST", "/api/dashboard/worklist/recommend", 403,
         "and cannot recommend, holding no portfolio",
         params={"period": args.period},
         json={"kind": "UNCLASSIFIED", "entity_id": "anything",
               "reason": "an auditor writes nothing at all, ever"})

    step("A claim cannot be settled against another objective's invoice")
    other = one("""SELECT invoice_id, invoice_number, objective_id FROM invoice
                    WHERE objective_id IS NOT NULL AND objective_id <> %s
                    LIMIT 1""", (code,))
    if other:
        r2 = call(steph, "POST", f"/api/projects/{code}/claims", 201,
                  "a second claim, to try it on", json={
                      "covers_from": f"{args.period}-01-01",
                      "covers_to": f"{args.period}-06-30",
                      "note": "Drive: to prove the objective check. "
                              "Withdrawn at the end of this run."})
        if r2.status_code == 201:
            MADE.append(r2.json()["claim_id"])
            call(tom, "POST", f"/api/claims/{r2.json()['claim_id']}/invoiced",
                 409, f"refused {other['invoice_number']}, which is on "
                      f"{other['objective_id']}",
                 json={"invoice_id": str(other["invoice_id"])})

    print()
    if FINDINGS:
        print(f"\033[1mSomething did not.\033[0m {len(FINDINGS)} finding(s).")
        return 1
    print(f"\033[1mPASS — {CHECKS} checks, the handoff in both directions.\033[0m")
    return 0


def teardown() -> int:
    """Everything this run made, removed — and the record proved unchanged.

    Every statement is attempted even if one fails, because a cleanup that
    stops at the first refusal leaves worse residue than none.
    """
    if not (MADE or MADE_TODOS):
        return 0
    for sql, params in (
            ("DELETE FROM todo WHERE todo_id = ANY(%s::uuid[])", (MADE_TODOS,)),
            ("DELETE FROM todo WHERE from_claim = ANY(%s::uuid[])", (MADE,)),
            ("DELETE FROM project_claim WHERE claim_id = ANY(%s::uuid[])", (MADE,))):
        try:
            query(sql, params)
        except Exception as exc:                            # noqa: BLE001
            print(f"  COULD NOT CLEAN UP  {sql.split(' WHERE')[0]}: "
                  f"{str(exc).splitlines()[0]}", file=sys.stderr)
    after = census()
    moved = {t: (BEFORE[t], after[t]) for t in CENSUS if BEFORE.get(t) != after[t]}
    if moved:
        print("\n\033[1mThe drive did not leave the record as it found "
              "it.\033[0m")
        for table, (was, now) in moved.items():
            print(f"  FINDING  {table}: {was} before, {now} after")
        return 1
    print(f"  ok       the record is as it was found — "
          f"{', '.join(sorted(CENSUS))} all unchanged")
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    finally:
        _left = teardown()
    raise SystemExit(_code or _left)
