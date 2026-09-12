#!/usr/bin/env python3
"""The rate build-up, and everything that moves it.

    YBI_SEED_PASSWORD=... python3 scripts/drive_buildup.py [--base URL]

`drive_propagation` asks what one reclassification moves. This asks the
question underneath it: **as the controller works the queue, does the rate
build up completely** — does every figure between a judgment and a number on
a workpaper move, and do the ones that must not hold still?

The chain, and every hop is checked rather than assumed:

    classify a group        ->  coverage moves by that group's dollars
    classify into a pool    ->  that pool's gross and allocable move
                            ->  its rate moves, and no other pool's does
    classify DIRECT         ->  the MTDC base moves, so the indirect rate does
                            ->  and the wage-based fringe base does not
    compute                 ->  carve-outs are recorded beside the rate
                            ->  every objective's allocation lands
    at every step           ->  rate.pool_amount = v_pool_balance.allocable

That last line is the one that matters most and it is new. For the life of
the system the rate carried a $932,254.78 facilities carve-out that
`v_pool_balance` knew nothing about, in adjacent columns on the same screen,
because **nothing compared them**. `v_rate_buildup.ties` is that comparison;
this drive is what proves it can fail.

Leaves the record as it found it, against a census taken before it started.

Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run.
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
NOTES: list[str] = []
MARK = "Build-up drive"


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  --       {msg}", flush=True)


def step(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=300)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    return c


def coverage(period: str) -> dict:
    return one("""SELECT classified, unclassified, scope_dollars,
                         pct_dollars_covered, groups_total
                    FROM v_classification_coverage WHERE period = %s""",
               (period,))


def buildup(period: str) -> dict[str, dict]:
    return {r["kind"]: r for r in query("""
        SELECT kind, pool_amount, base_amount, rate, pool_gross, pool_carved,
               pool_allocable, carve_outs, pool_variance, pool_state, ties
          FROM v_rate_buildup WHERE period = %s""", (period,))}


def d(v) -> Decimal:
    return Decimal(str(v or 0))


def check_ties(b: dict[str, dict], when: str) -> None:
    """The control. Every live rate against the pool underneath it.

    Three states, not two. A pool nobody has classified into is NO DATA while
    the queue is open — `0 = 0` is not a tie — and reporting that as a
    failure would be the same overstatement in the other direction. Only OPEN
    is a finding.
    """
    if not b:
        finding(f"no rate on file {when}")
        return
    open_ = [f"{k} off by {r['pool_variance']}" for k, r in b.items()
             if r["pool_state"] == "OPEN"]
    empty = sorted(k for k, r in b.items() if r["pool_state"] == "NO DATA")
    if open_:
        finding(f"the build-up does not tie {when}: {'; '.join(open_)}")
        return
    tied = sorted(k for k, r in b.items() if r["pool_state"] == "TIES")
    ok(f"every pool with cost in it ties {when} — "
       + ", ".join(f"{k} {b[k]['pool_amount']}" for k in tied))
    if empty:
        note(f"{', '.join(empty)} hold nothing yet, so they read NO DATA "
             f"rather than tying at zero — the tie points anchor when the "
             f"queue is empty, and it is not")


def seal_and_compute(tom, period: str, why: str) -> bool:
    s = tom.post("/api/rates/seal", json={"note": f"{MARK}: {why}"})
    if s.status_code != 200:
        finding(f"could not seal ({why}): {s.status_code} {s.text[:120]}")
        return False
    r = tom.post("/api/rates/compute", params={"period": period},
                 json={"note": f"{MARK}: {why}"})
    if r.status_code != 200:
        finding(f"could not compute ({why}): {r.status_code} {r.text[:200]}")
        return False
    return True


def judge(tom, groups: list[dict], pool: str, fn: str, objective=None) -> bool:
    r = tom.post("/api/classify/decide", json={
        "group_keys": [g["group_key"] for g in groups], "pool": pool,
        "function_990": fn, "federal": "ALLOWABLE",
        "objective_id": objective, "grade": "TEST_ASSUMPTION",
        "rationale": f"{MARK}: {pool}. Reversed at the end of this run."})
    if r.status_code != 200:
        finding(f"could not classify to {pool}: {r.status_code} {r.text[:200]}")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is not set.", file=sys.stderr)
        return 2
    open_pool()
    period = args.period
    tom = sign_in(args.base, "tom@ybi.org", pw)

    before_cov = coverage(period)
    if not before_cov:
        print("\nCOULD NOT RUN — no ledger in this period.", file=sys.stderr)
        return 2

    step("What the queue is asking a person to judge")
    # The scope is cost, not the P&L. Income was 242 of 999 groups and 40% of
    # the dollars, with four revenue rows at the top by size and no answer to
    # any of them.
    income = one("""SELECT count(*) AS n FROM v_cost_line
                     WHERE period = %s AND section = 'Income'""", (period,))
    if income["n"] == 0:
        ok("no income line is in the classification scope — a cost pool is "
           "for cost, and grant income has no answer in one")
    else:
        finding(f"{income['n']} income line(s) are still being offered as "
                f"cost to classify")

    top = tom.get("/api/classify/queue",
                  params={"status": "undecided", "limit": 5}).json()
    revenue = [g for g in top if str(g["account"]).startswith(("3", "4"))]
    if revenue:
        finding("the largest things in the queue include revenue: "
                + ", ".join(g["account"][:40] for g in revenue))
    else:
        ok(f"the five largest open groups are all cost — "
           f"{top[0]['account'][:44] if top else 'queue empty'}")

    step("A judgment moves coverage, and moves it by its own amount")
    # Nothing is sealed or computed before this point, deliberately. On a
    # proof from an empty database `drive_concurrency` runs just before this
    # and reverses every judgment it made, so the decision set can be
    # genuinely empty here — the first version of this drive sealed at a
    # "baseline" it had not earned and met NOTHING_TO_SEAL. A drive that
    # needs a starting position makes its own.
    # Open the set if somebody left it sealed. The drive makes its own
    # starting position rather than assuming one — the first version sealed a
    # baseline it had not earned, and this is the same assumption from the
    # other side. A 404 here means it was already open, which is the state
    # wanted.
    u = tom.post("/api/rates/unseal",
                 params={"reason": f"{MARK}: opening the set to judge into "
                                   f"it. Walked back at the end of this run."})
    if u.status_code not in (200, 404):
        print(f"\nCOULD NOT RUN — could not open the set: {u.status_code} "
              f"{u.text[:160]}", file=sys.stderr)
        return 2

    q = tom.get("/api/classify/queue",
                params={"status": "undecided", "limit": 40}).json()
    wages = [g for g in q if "Payroll" in g["account"]][:2]
    if not wages:
        print("\nCOULD NOT RUN — no open payroll group to put in FRINGE.",
              file=sys.stderr)
        return 2
    # And something into OVERHEAD, because the two checks that matter most
    # depend on there being an indirect pool at all: the 200.465 carve-out is
    # sized as a share of overhead gross and is skipped when that is zero,
    # and there is nothing to allocate to an objective without an indirect
    # rate. A drive that cannot reach its own control is not a drive.
    overhead = [g for g in q if g not in wages][:3]
    if not overhead:
        print("\nCOULD NOT RUN — nothing open to put in OVERHEAD.",
              file=sys.stderr)
        return 2
    moved = sum(d(g["abs_amount"]) for g in wages + overhead)
    if not judge(tom, wages, "FRINGE", "NOT_APPLICABLE"):
        return 1
    if not judge(tom, overhead, "OVERHEAD", "MANAGEMENT_AND_GENERAL"):
        return 1
    after = coverage(period)
    grew = d(after["classified"]) - d(before_cov["classified"])
    if grew == moved:
        ok(f"coverage grew by exactly what was judged — {grew}")
    else:
        finding(f"coverage grew by {grew}, but {moved} was judged")
    if d(after["scope_dollars"]) == d(before_cov["scope_dollars"]):
        ok("and the scope held still — no judgment changes how much there "
           "is to judge")
    else:
        finding(f"the scope moved from {before_cov['scope_dollars']} to "
                f"{after['scope_dollars']}, which no judgment may do")

    step("And it reaches the pool, the rate and the workpaper")
    if not seal_and_compute(tom, period, "after the fringe judgment"):
        return 1
    b2 = buildup(period)
    check_ties(b2, "over the judgments made so far")
    if "FRINGE" in b2 and d(b2["FRINGE"]["pool_amount"]) > 0:
        ok(f"FRINGE carries {b2['FRINGE']['pool_amount']} at "
           f"{b2['FRINGE']['rate']}, and its gross and allocable agree with "
           f"the rate that was computed from them")
    else:
        finding("classifying into FRINGE did not move the FRINGE pool")
    carves = one("""SELECT count(*) AS n, COALESCE(sum(amount), 0) AS amt
                      FROM carve_out WHERE period = %s""", (period,))
    if carves["n"]:
        ok(f"{carves['n']} carve-out(s) recorded beside the rate, "
           f"{carves['amt']} — applied to the pool *and* on the workpaper, "
           f"which for the life of the system it was not")
    else:
        note("no carve-out applies on this record, so there is none to "
             "record — v_facility_occupancy has nothing to exclude")

    step("Direct cost moves the base, and the base moves the rate")
    tom.post("/api/rates/unseal",
             params={"reason": f"{MARK}: reopening to judge direct cost."})
    q = tom.get("/api/classify/queue",
                params={"status": "undecided", "limit": 20}).json()
    obj = one("""SELECT objective_id FROM cost_objective
                  WHERE is_final ORDER BY objective_id LIMIT 1""")
    if not q or not obj:
        note("nothing open to judge as direct, or no final objective")
    else:
        if judge(tom, q[:1], "DIRECT", "PROGRAM", obj["objective_id"]):
            if seal_and_compute(tom, period, "after the direct judgment"):
                b3 = buildup(period)
                check_ties(b3, "after classifying direct cost")
                mtdc_before = d(b2.get("INDIRECT_COMBINED", {}).get("base_amount"))
                mtdc_after = d(b3.get("INDIRECT_COMBINED", {}).get("base_amount"))
                if mtdc_after != mtdc_before:
                    ok(f"the MTDC base moved {mtdc_before} -> {mtdc_after}, "
                       f"and the rate with it "
                       f"{b2.get('INDIRECT_COMBINED', {}).get('rate')} -> "
                       f"{b3.get('INDIRECT_COMBINED', {}).get('rate')}")
                else:
                    finding("direct cost was classified and the MTDC base "
                            "did not move — the rate cannot be right")
                fb, fa = (d(b2.get("FRINGE", {}).get("base_amount")),
                          d(b3.get("FRINGE", {}).get("base_amount")))
                if fb == fa:
                    ok("and the fringe base held still, because it is wages "
                       "rather than modified total direct cost — two bases, "
                       "moving on different things")
                else:
                    finding(f"the wage base moved on a direct judgment: "
                            f"{fb} -> {fa}")
                allocated = one("""SELECT count(*) AS n,
                                          COALESCE(sum(allocated), 0) AS amt
                                     FROM allocation a JOIN rate r USING (rate_id)
                                    WHERE r.status <> 'SUPERSEDED'""")
                combined = d(b3.get("INDIRECT_COMBINED", {}).get("pool_amount"))
                if allocated["n"]:
                    ok(f"and it lands: {allocated['n']} objective(s) carry "
                       f"{allocated['amt']} of indirect")
                elif combined == 0:
                    # Not a fault. Nothing has been judged into overhead or
                    # G&A, so there is no indirect to spread, and spreading
                    # nothing over seventeen objectives is not a finding.
                    note("no indirect pool on this record, so there is "
                         "nothing to allocate")
                else:
                    finding(f"an indirect pool of {combined} was computed and "
                            f"no objective carries any of it")

    step("What the rate as a whole is anchored to")
    for a in query("""SELECT control, description, expected, actual,
                             variance, state, classification_complete
                        FROM v_rate_anchor WHERE period = %s ORDER BY seq""",
                   (period,)):
        if a["state"] == "TIES":
            ok(f"{a['control']} — {a['description'].lower()}: "
               f"{a['expected']} both sides"
               + ("" if a["classification_complete"]
                  else ", over a queue that is not finished"))
        elif a["state"] == "NO DATA":
            note(f"{a['control']} cannot be evaluated yet — {a['description']}")
        else:
            finding(f"{a['control']} does not tie: {a['description']} — "
                    f"{a['expected']} against {a['actual']}, off by "
                    f"{a['variance']}")

    step("The control can fail, which is the only reason to trust it")
    # Take the carve-outs away underneath the rate and read the view. This is
    # the exact state the system was in for its whole life.
    saved = query("""SELECT pool::text AS pool, period, name, citation, amount,
                            driver, grade::text AS grade, created_by
                       FROM carve_out WHERE period = %s""", (period,))
    if not saved:
        note("no carve-out on this record to remove, so the failing side of "
             "the tie control cannot be shown here")
    else:
        query("DELETE FROM carve_out WHERE period = %s", (period,))
        broken = buildup(period)
        off = [k for k, r in broken.items() if not r["ties"]]
        if off:
            ok(f"with the carve-outs removed the build-up reports {len(off)} "
               f"rate(s) not tying, by "
               f"{broken[off[0]]['pool_variance']} — the defect that survived "
               f"the life of the system, now a control")
        else:
            finding("the carve-outs were removed and every rate still "
                    "reported tying, so the control cannot fail")
        for c in saved:
            query("""INSERT INTO carve_out (pool, period, name, citation,
                                            amount, driver, grade, created_by)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (c["pool"], c["period"], c["name"], c["citation"],
                   c["amount"], c["driver"], c["grade"], c["created_by"]))
        # `pool_state == OPEN`, not `not ties`. An empty pool reads NO DATA
        # while the queue is open and `ties` is false on it — correctly — so
        # a check written as `all(ties)` calls a pool nobody has classified
        # into a broken control. Same assumption `check_ties` was just fixed
        # for, one function away, which is the argument for going back
        # through a file once you have found one in it.
        still_open = [k for k, r in buildup(period).items()
                      if r["pool_state"] == "OPEN"]
        if not still_open:
            ok("and it ties again once they are put back")
        else:
            finding(f"the carve-outs were restored and {', '.join(still_open)} "
                    f"still does not tie")

    return walk_back(tom, period, before_cov)


def walk_back(tom, period: str, before_cov: dict) -> int:
    step("Walking it back")
    tom.post("/api/rates/unseal",
             params={"reason": f"{MARK}: finished; leaving the set open as "
                               f"it was found."})
    query("""UPDATE decision SET reversed_at = now(),
                    reversal_reason = %s
              WHERE reversed_at IS NULL AND rationale LIKE %s""",
          (f"{MARK}, walked back.", f"{MARK}%"))
    left = one("""SELECT count(*) AS n FROM decision
                   WHERE reversed_at IS NULL AND rationale LIKE %s""",
               (f"{MARK}%",))
    if left["n"] == 0:
        ok("every judgment this drive made is reversed")
    else:
        finding(f"{left['n']} of this drive's judgments are still live")

    after = coverage(period)
    if d(after["classified"]) == d(before_cov["classified"]):
        ok(f"and coverage is back where it started — "
           f"{after['classified']} ({after['pct_dollars_covered']}%)")
    else:
        finding(f"coverage started at {before_cov['classified']} and ended "
                f"at {after['classified']}")

    print()
    for f in FINDINGS:
        print(f"    - {f}")
    for n in NOTES:
        print(f"    ~ {n}")
    if FINDINGS:
        print(f"\033[1mSomething did not.\033[0m {len(FINDINGS)} finding(s).")
        return 1
    print(f"\033[1mPASS — {CHECKS} checks, the build-up moves with every "
          f"judgment and ties at each step.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
