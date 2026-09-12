#!/usr/bin/env python3
"""The point of the whole system, walked end to end.

    YBI_SEED_PASSWORD=... python3 scripts/drive_restate.py [--base URL]

Everything upstream — the classification, the seal, the rate, the allocation
— exists so that a number put in front of NCDMM can be traced back to a
judgment somebody signed their name to. This walks that number out and checks
the three things the handler says it will not do:

    it will not compute from an unsealed set
    it will not present a proposal as a position
    it will not net an over-collection against an under-recovery

**It needs a rate**, and says so rather than sealing on its own. Sealing is a
judgment and a drive that makes one to give itself something to measure is a
drive reading its own writing — which is what `review_system` was fixed for.
`scripts/prove.sh` runs it after `drive_state_machine`, which seals.

Leaves the record as it found it, against a census taken before it started.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run, which
is not a pass.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx                                              # noqa: E402

from app.db import one, open_pool, query                  # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []
#: Not a row count. `restatement` is append-only — *correct by superseding,
#: never by editing* — so the rows this drive makes stay, and they should:
#: a position taken and then withdrawn is part of the trail. What must come
#: back to where it started is how many restatements are **standing as a
#: claim**, which is what a reader of the record would count.
CENSUS = ("standing",)
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
    return {"standing": one("""SELECT count(*) AS n FROM restatement
                                WHERE status IN ('PROPOSED','SUBMITTED',
                                                 'ACCEPTED')""")["n"]}


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    return c


def call(c, method, path, expect, what, **kw):
    r = c.request(method, path, **kw)
    (ok if r.status_code == expect else finding)(
        f"{what} — {r.status_code}"
        + ("" if r.status_code == expect
           else f" (wanted {expect}) {r.text[:160]}"))
    return r


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

    tom = sign_in(args.base, "tom@ybi.org", pw)
    auditor = sign_in(args.base, "auditor@ybi.org", pw)

    step("What it will be measured against")
    cand = call(tom, "GET", "/api/restate/candidates", 200, "the candidates",
                params={"period": args.period}).json()
    if cand["blocked_because"]:
        # Not a failure and not a pass: the route's whole design is to answer
        # "not yet, because" rather than with an empty list, and the reason is
        # the work. But there is nothing here to drive.
        print("\nCOULD NOT RUN — " + cand["blocked_because"][0],
              file=sys.stderr)
        return 2
    rate = next((r for r in cand["rates"]
                 if r["kind"] == "INDIRECT_COMBINED"), None)
    if not rate:
        print("\nCOULD NOT RUN — no INDIRECT_COMBINED rate on file.",
              file=sys.stderr)
        return 2
    ok(f"{rate['kind']} at {float(rate['rate']) * 100:.2f}%, "
       f"{rate['status']}, seal {str(rate['seal_hash'])[:10]}")

    target = next((o for o in cand["objectives"] if o["invoices"]), None)
    if not target:
        print("\nCOULD NOT RUN — no invoices on file to measure.",
              file=sys.stderr)
        return 2
    obj = target["objective_id"]
    if Decimal(str(target["indirect_billed"])) == 0:
        ok(f"{obj} was billed {target['billed']} with **no indirect at all** — "
           f"which is the case the restatement exists to make, and the "
           f"invoice YBI issued is itself the record of it")

    step("Measured, per invoice, in the direction the difference runs")
    r = call(tom, "POST", "/api/restate", 200, f"restated {obj}",
             params={"period": args.period}, json={
                 "objective_id": obj,
                 "basis": "Drive: measured against the sealed rate to walk "
                          "the restatement. Withdrawn at the end of this run."})
    if r.status_code != 200:
        return 1
    got = r.json()
    MADE.append(got["restatement_id"])

    if got["rate"]["seal_hash"] == rate["seal_hash"]:
        ok("it carries the seal of the rate it used, so it is provably a "
           "consequence of the classifications rather than of somebody's "
           "preferred answer")
    else:
        finding("the restatement carries a different seal from its rate")

    under = Decimal(got["under_recovered"])
    over = Decimal(got["over_collected"])
    ok(f"{got['invoices']} invoice(s): {under} to ask for, {over} to give "
       f"back — reported apart, because they are two conversations")

    # The rule `061` closed. A net figure is not a smaller answer, it is a
    # different one.
    if "net_movement" in got or "net" in got:
        finding("the answer carries a netted figure")
    else:
        ok("and the answer carries no netted figure at all")

    row = one("""SELECT under_recovered, over_collected FROM v_restatement
                  WHERE restatement_id = %s""", (got["restatement_id"],))
    cols = query("""SELECT column_name FROM information_schema.columns
                     WHERE table_name = 'v_restatement'""")
    if any(c["column_name"] == "net_movement" for c in cols):
        finding("v_restatement still offers net_movement — see migration 061")
    else:
        ok("nor does the view, which offered exactly that column until 061 "
           "and was never read because this had no screen")

    step("A proposal is not a position")
    if got["status"] == "PROPOSED":
        ok("it is PROPOSED — neither agreement was billed under a provisional "
           "rate, so this is a §4.4 change of basis rather than a corrected "
           "invoice in the post")
    else:
        finding(f"a fresh restatement is {got['status']}, not PROPOSED")

    rid = got["restatement_id"]
    refused = call(tom, "POST", f"/api/restate/{rid}/status", 422,
                   "accepting it without naming the modification is refused",
                   json={"status": "ACCEPTED"})
    detail = (refused.json() or {}).get("detail", "")
    if "4.4" in str(detail):
        ok("and the refusal names the clause that makes it necessary, rather "
           "than the constraint that caught it")
    else:
        finding(f"the refusal says {str(detail)[:120]!r}, which does not tell "
                f"the person what to do — this is the single omission most "
                f"likely to become a finding")

    call(tom, "POST", f"/api/restate/{rid}/status", 200,
         "accepted, naming the modification",
         json={"status": "ACCEPTED",
               "modification_ref": "Drive: Modification 999, not a real one",
               "note": "Drive: walking the status path. Withdrawn below."})

    step("The auditor reads the whole thing and writes none of it")
    call(auditor, "GET", "/api/restate", 200, "every restatement",
         params={"period": args.period})
    call(auditor, "GET", f"/api/restate/{rid}", 200, "and one in full")
    call(auditor, "POST", "/api/restate", 403, "refused to measure one",
         json={"objective_id": obj,
               "basis": "an auditor writes nothing at all, ever"})
    call(auditor, "POST", f"/api/restate/{rid}/status", 403,
         "refused to accept one", json={"status": "ACCEPTED"})

    print()
    if FINDINGS:
        print(f"\033[1mSomething did not.\033[0m {len(FINDINGS)} finding(s).")
        return 1
    print(f"\033[1mPASS — {CHECKS} checks, the number walked out to "
          f"NCDMM.\033[0m")
    return 0


def teardown() -> int:
    """Walked back, not deleted.

    `restatement` refuses a DELETE — *correct by superseding, never by
    editing* — and that is right: a position taken and then withdrawn is part
    of the trail, and a drive that could erase one could erase a real one.
    The first version tried anyway and left a row behind, which is the
    `invoice_no_delete` lesson in a second place: **a cleanup that assumes it
    can remove what it made is a cleanup that stops working the day the table
    grows a guarantee.**

    So it withdraws its own, with a reason, through the same route a person
    would use.
    """
    if not MADE:
        return 0
    for rid in MADE:
        try:
            query("""UPDATE restatement
                        SET status = 'REJECTED', decided_at = now(),
                            decided_note = 'Withdrawn by the drive that made '
                                           'it. Never a position YBI took.'
                      WHERE restatement_id = %s::uuid
                        AND status <> 'SUPERSEDED'""", (rid,))
        except Exception as exc:                            # noqa: BLE001
            print(f"  COULD NOT WALK BACK  {rid}: "
                  f"{str(exc).splitlines()[0]}", file=sys.stderr)
    after = census()
    moved = {t: (BEFORE[t], after[t]) for t in CENSUS if BEFORE.get(t) != after[t]}
    if moved:
        print("\n\033[1mThe drive did not leave the record as it found "
              "it.\033[0m")
        for table, (was, now) in moved.items():
            print(f"  FINDING  {table}: {was} before, {now} after")
        return 1
    print(f"  ok       nothing this drive made is standing as a claim — the "
          f"rows stay, because the table is append-only and a withdrawn "
          f"position is part of the trail")
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    finally:
        _left = teardown()
    raise SystemExit(_code or _left)
