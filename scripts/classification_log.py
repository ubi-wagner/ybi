#!/usr/bin/env python3
"""Walk 2025 a month at a time and write down a reasoned treatment for every
open group — then check the result against the figures that are already known.

    python3 scripts/classification_log.py                  # walk and report
    python3 scripts/classification_log.py --write          # + write the log
    python3 scripts/classification_log.py --apply --base … # + record them

**It proposes; it does not decide.** Without `--apply` nothing is written to
the cost record at all: the run reads live rows, reasons over them and prints.
With `--apply` it records the judgments *through the real API, signed in as a
real controller*, so every one carries that person's name and an audit row —
which is the only way they should ever reach the record. There is no path
here that writes a decision behind the API's back.

Why the walk is monthly. The classification unit is a group — an account and
a payee — and a group spans months, so a strictly monthly queue would deal
the same group twelve times. Instead each group is reached in **the month it
first appears**, and judged once. Every group is therefore reached exactly
once, in ledger order, and by December the year is covered. That gives the
thing a controller actually checks against: a month of the general ledger, and
what was decided while reading it.

Why it ends at the anchors. A walk that only reports what it did is a review
reading its own writing. The last section compares the result against figures
that were fixed before it ran — the eleven cross-reference controls, the P&L's
own fringe accounts at $401,783.60, the payroll register at $1,835,047.17 and
the 21.90% that falls out of the two — and reports a difference rather than
absorbing one.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.db import one, open_pool, query
from app.domain.classification_log import (
    OBJECTIVES_TO_OPEN, RECORDED, Group, disagreements, judge,
    judge_on_merits, summarise, walk)
from app.domain.core import money

BOLD, DIM, OK, WARN, FAIL, END = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")


def rows_for(period: str) -> list[Group]:
    """Every cost group, with the month it first appears.

    `v_cost_line` rather than `ledger_line`: the scope of what is cost to
    classify is defined once, in the schema, and a fifth copy of it here is
    exactly the shape that produced 13.0% and 2.2% at the same moment.
    """
    got = query("""
        SELECT l.account,
               coalesce(l.payee, '')                          AS payee,
               count(*)                                       AS lines,
               sum(l.amount)                                  AS net,
               sum(abs(l.amount))                             AS gross,
               sum(l.amount) FILTER (WHERE l.amount > 0)      AS debits,
               -sum(l.amount) FILTER (WHERE l.amount < 0)     AS credits,
               to_char(min(l.txn_date), 'YYYY-MM')            AS first_month,
               count(dl.line_id) FILTER (WHERE dl.live)       AS judged
          FROM v_cost_line l
          LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
         WHERE l.period = %s
         GROUP BY l.account, coalesce(l.payee, '')
    """, (period,))
    return [Group(account=r["account"], payee=r["payee"], lines=r["lines"],
                  net=money(r["net"]), gross=money(r["gross"]),
                  debits=money(r["debits"] or 0), credits=money(r["credits"] or 0),
                  first_month=r["first_month"], judged=r["judged"])
            for r in got]


def federal_objectives() -> frozenset[str]:
    """Which objectives carry federal money, read from the record.

    Not a constant in the domain module: `cost_objective.is_federal` is the
    answer and a second copy of it here would be the hand-kept map again —
    free to drift from the row the SEFA is built off.
    """
    return frozenset(r["objective_id"] for r in
                     query("SELECT objective_id FROM cost_objective "
                           "WHERE is_federal"))


def already_judged(period: str) -> dict:
    r = one("""SELECT count(DISTINCT l.account || coalesce(l.payee,'')) AS groups,
                      sum(abs(l.amount))                                AS gross
                 FROM v_cost_line l
                 JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
                WHERE l.period = %s""", (period,))
    return {"groups": r["groups"] or 0, "gross": money(r["gross"] or 0)}


# ----------------------------------------------------------------- the walk

def report(walked, done, period: str) -> dict:
    s = summarise(walked)
    print(f"\n{BOLD}Walking {period}, a month at a time{END}")
    print(f"{DIM}Each group is reached in the month it first appears and judged "
          f"once.{END}\n")
    print(f"  {'month':<9} {'groups':>7} {'on record':>10} {'proposed':>9} "
          f"{'open':>6} {'proposed $':>15} {'open $':>15}")
    print("  " + "-" * 76)
    run_j = run_b = money(0)
    for m in sorted(s["by_month"]):
        v = s["by_month"][m]
        run_j = money(run_j + v["judged_gross"])
        run_b = money(run_b + v["blocked_gross"])
        print(f"  {m:<9} {v['groups']:>7} {v['recorded']:>10} {v['judged']:>9} "
              f"{v['blocked']:>6} {v['judged_gross']:>15,.2f} "
              f"{v['blocked_gross']:>15,.2f}")
    print("  " + "-" * 76)
    print(f"  {'year':<9} {s['groups']:>7} {s['recorded']:>10} {s['judged']:>9} "
          f"{s['blocked']:>6} {run_j:>15,.2f} {run_b:>15,.2f}")

    print(f"\n{BOLD}What it recommends{END}")
    for pool, v in sorted(s["by_pool"].items(), key=lambda x: -x[1]["gross"]):
        print(f"  {pool:<16} {v['groups']:>4} group(s)  "
              f"gross {v['gross']:>14,.2f}   net {v['net']:>14,.2f}")

    print(f"\n{BOLD}What it will not judge, and what each is waiting for{END}")
    print(f"{DIM}A group that cannot be judged stays in the queue saying why. "
          f"Defaulting it into a pool to improve a percentage is the one thing "
          f"this system is built to refuse.{END}")
    for on, v in sorted(s["by_block"].items(), key=lambda x: -x[1]["gross"]):
        print(f"  {WARN}{v['gross']:>14,.2f}{END} gross  "
              f"{v['net']:>14,.2f} net  {v['groups']:>4} group(s)  {on}")

    scope = one("""SELECT scope_dollars, classified, unclassified, pct_dollars_covered
                     FROM v_classification_coverage WHERE period = %s""",
                (period,))
    reach = money(s["recorded_gross"] + s["judged_gross"])
    print(f"\n{BOLD}Coverage if every recommendation here were accepted{END}")
    print(f"  already on record   {s['recorded_gross']:>15,.2f}   "
          f"{s['recorded']:>4} group(s)")
    print(f"  recommended here   {s['judged_gross']:>15,.2f}   "
          f"{s['judged']:>4} group(s)")
    print(f"  {BOLD}would reach{END}         {reach:>15,.2f}   "
          f"of {scope['scope_dollars']:,.2f}  "
          f"= {BOLD}{reach / scope['scope_dollars'] * 100:.1f}%{END}"
          f"  {DIM}(today {scope['pct_dollars_covered']:.1f}%){END}")
    s["reach"] = reach
    s["scope"] = money(scope["scope_dollars"])
    return s


# ------------------------------------------------------------- the anchors

def anchors(period: str) -> list[tuple[str, bool | None, str]]:
    """Check the result against figures fixed before this ran.

    Three states, not two. A control that cannot be evaluated has not passed,
    so an anchor with nothing behind it reports as such rather than as green.
    """
    out: list[tuple[str, bool | None, str]] = []

    controls = query("""SELECT control, state, left_value, right_value, variance
                          FROM v_statement_reconciliation
                         WHERE period = %s ORDER BY seq""", (period,))
    open_ = [c for c in controls if c["state"] == "OPEN"]
    nodata = [c for c in controls if c["state"] == "NO DATA"]
    out.append((
        f"the eleven cross-reference controls",
        not open_ and not nodata,
        f"{len(controls) - len(open_) - len(nodata)} tie, {len(open_)} open, "
        f"{len(nodata)} cannot be evaluated"))

    pr = one("""SELECT fringe_pool, register_wages, ledger_wages,
                       gross_difference, unexplained
                  FROM v_payroll_reconciliation WHERE period = %s""", (period,))
    if pr:
        pool, reg, led = (money(pr["fringe_pool"]), money(pr["register_wages"]),
                          money(pr["ledger_wages"]))
        out.append(("the P&L's six fringe accounts = $401,783.60",
                    pool == Decimal("401783.60"), f"${pool:,.2f}"))
        out.append(("the payroll register's wages = $1,835,047.17",
                    reg == Decimal("1835047.17"), f"${reg:,.2f}"))
        out.append(("the donor credit between the two = $45,053.23",
                    money(reg - led) == Decimal("45053.23"),
                    f"${money(reg - led):,.2f}"))
        rate = (pool / reg).quantize(Decimal("0.0001")) if reg else None
        alt = (pool / led).quantize(Decimal("0.0001")) if led else None
        out.append(("fringe on the register = 21.90%",
                    rate == Decimal("0.2190"),
                    f"{rate:.4f} — and {alt:.4f} on the ledger's wage "
                    f"accounts, which is the same pool over the wrong "
                    f"denominator"))
        out.append(("nothing in the register is unexplained",
                    money(pr["unexplained"]) == 0,
                    f"${money(pr['unexplained']):,.2f}"))

    cov = one("""SELECT scope_dollars, classified, unclassified
                   FROM v_classification_coverage WHERE period = %s""", (period,))
    out.append(("coverage reproduces from its own row",
                money(cov["classified"] + cov["unclassified"])
                == money(cov["scope_dollars"]),
                f"{cov['classified']:,.2f} + {cov['unclassified']:,.2f} "
                f"= {money(cov['classified'] + cov['unclassified']):,.2f}"))

    # The 200.465 carve-out, and whether it was in a position to fire.
    #
    # On a freshly seeded record `facility` and `space_unit` are both empty,
    # `v_facility_occupancy` inner-joins to its space totals and returns
    # nothing, and **no carve-out is computed at all** — silently. The pool
    # then ties to itself perfectly, `pool_carved` reads 0.00, and nothing on
    # the build-up distinguishes "there is no tenant space" from "nobody has
    # measured any". That is `029`'s lesson in the one adjustment this file
    # calls the largest in the rate model: an empty set matching an empty set.
    #
    # It is not raised on the worklist either. `SPACE_UNMEASURED` fires per
    # building, and a record with no buildings has none to fire on.
    space = one("""SELECT (SELECT count(*) FROM facility)    AS facilities,
                          (SELECT count(*) FROM space_unit)  AS units""")
    carved = one("""SELECT count(*) AS n, COALESCE(sum(amount), 0) AS amount
                      FROM carve_out WHERE period = %s""", (period,))
    if not space["facilities"]:
        out.append(("the 200.465 facilities carve-out", None,
                    "not evaluable — no building is on the record, so "
                    "v_facility_occupancy is empty and no carve-out was "
                    "computed. Every dollar of tenant and vacant occupancy "
                    "cost is in the federal pool"))
    elif not space["units"]:
        out.append(("the 200.465 facilities carve-out", None,
                    f"not evaluable — {space['facilities']} building(s) and "
                    f"no square footage against any of them "
                    f"(SPACE_UNMEASURED)"))
    else:
        out.append(("the 200.465 facilities carve-out", bool(carved["n"]),
                    f"{carved['n']} recorded, ${carved['amount']:,.2f}"))

    build = query("""SELECT kind, pool_amount, pool_allocable, pool_variance,
                            pool_state FROM v_rate_buildup WHERE period = %s""",
                  (period,))
    if not build:
        out.append(("the build-up ties to the pool underneath it", None,
                    "no rate on file — the set is open, and computing one "
                    "over an open set is what the seal exists to refuse"))
    else:
        bad = [b for b in build if b["pool_state"] == "OPEN"]
        nd = [b for b in build if b["pool_state"] == "NO DATA"]
        out.append(("the build-up ties to the pool underneath it",
                    None if nd and not bad else not bad,
                    "; ".join(f"{b['kind']} {b['pool_state']}"
                              + (f" by {b['pool_variance']:,.2f}"
                                 if b["pool_variance"] else "")
                              for b in build)))
    return out


def show_anchors(period: str) -> int:
    print(f"\n{BOLD}Against the anchors{END}")
    print(f"{DIM}Figures fixed before this ran. A difference is reported, "
          f"never absorbed.{END}\n")
    faults = 0
    for name, state, detail in anchors(period):
        if state is True:
            mark = f"{OK}  ok  {END}"
        elif state is False:
            mark = f"{FAIL} FAIL {END}"
            faults += 1
        else:
            mark = f"{WARN}  --  {END}"
        print(f"  {mark} {name:<48} {detail}")
    return faults


# ----------------------------------------------------------------- the log

def write_log(walked, s, period: str, path: Path,
              federal: frozenset[str] = frozenset()) -> None:
    lines: list[str] = []
    w = lines.append
    w(f"# Classification log — {period}\n")
    w("Generated by `scripts/classification_log.py`. **Every line here is a\n"
      "recommendation, not a decision.** Nothing in this file has been\n"
      "recorded against the cost record; `--apply` does that, through the\n"
      "real API, signed in as the controller, so each judgment carries a\n"
      "person's name and an audit row.\n")
    w("Read it beside the general ledger a month at a time. Each group is\n"
      "reached in the month it first appears and judged once.\n")

    w("\n## What the walk found\n")
    w(f"- **{s['recorded']}** groups the controller has already judged, "
      f"${s['recorded_gross']:,.2f}")
    w(f"- **{s['judged']}** groups recommended here, "
      f"${s['judged_gross']:,.2f} of absolute movement")
    w(f"- **{s['blocked']}** groups left in the queue, "
      f"${s['blocked_gross']:,.2f}, each naming what it waits for")
    w(f"- coverage would reach **{s['reach'] / s['scope'] * 100:.1f}%** of "
      f"${s['scope']:,.2f} of cost\n")

    w("\n## Month by month\n")
    w("| month | groups | on record | recommended | left open | "
      "recommended $ | open $ |")
    w("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for m in sorted(s["by_month"]):
        v = s["by_month"][m]
        w(f"| {m} | {v['groups']} | {v['recorded']} | {v['judged']} | "
          f"{v['blocked']} | {v['judged_gross']:,.2f} | "
          f"{v['blocked_gross']:,.2f} |")

    w("\n## What is waiting, and on what\n")
    w("A group that cannot be judged is not judged. *Unclassified cost is\n"
      "never defaulted into a pool* — the rate reads high while this is open,\n"
      "which is the honest direction to err.\n")
    w("| gross | net | groups | waiting on |")
    w("| ---: | ---: | ---: | --- |")
    for on, v in sorted(s["by_block"].items(), key=lambda x: -x[1]["gross"]):
        w(f"| {v['gross']:,.2f} | {v['net']:,.2f} | {v['groups']} | {on} |")

    w("\n## Every group, in ledger order\n")
    w("| month | account | payee | lines | net | pool | 990 | federal | "
      "objective | basis | why |")
    w("| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |")
    for g, j in walked:
        # **A judged group still gets its reasoning.** `judge` refuses to
        # re-propose one — that would be this log taking credit for somebody
        # else's judgment — and returns the bare "already carries a live
        # decision". That is right for proposing and useless for reviewing,
        # which is what anybody opens this file to do once the judgments are
        # on the record. `judge_on_merits` answers from the group alone, so
        # the row shows what the treatment is *and* that it already stands.
        shown = j if j.basis != RECORDED else judge_on_merits(g, federal)
        basis = j.basis if j.basis != RECORDED else f"{RECORDED} · {shown.basis}"
        j = shown
        why = (j.rationale if j.blocked else f"{j.citation} — {j.rationale}")
        # `<vendor>` in a markdown cell renders as an HTML tag and vanishes.
        why = (why.replace("|", "\\|").replace("\n", " ")
                  .replace("<", "&lt;").replace(">", "&gt;"))
        w(f"| {g.first_month} | {g.account.replace('|', '')} | "
          f"{g.payee.replace('|', '') or '—'} | {g.lines} | {g.net:,.2f} | "
          f"{j.pool or '**open**'} | {j.function_990 or '—'} | "
          f"{j.federal or '—'} | {j.objective_id or '—'} | {basis} | {why} |")

    path.write_text("\n".join(lines) + "\n")
    print(f"\n  wrote {path} — {len(walked)} group(s)")


# --------------------------------------------------------------- recording

def apply(walked, base: str, email: str, password: str, period: str) -> int:
    """Record the recommendations through the real API, as a real person."""
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"{FAIL}could not sign in as {email}: {r.status_code}{END}")
        return 1
    # An objective the account names and the register has never had. Opening
    # it is transcription — the account already says the programme exists and
    # money was spent on it — and it has to happen first, because
    # `direct_needs_objective` refuses a DIRECT judgment naming a row that is
    # not there. Through the real route, so it carries an audit entry.
    for oid, label in OBJECTIVES_TO_OPEN.items():
        r = c.post("/api/contracts/charge-codes", json={
            "objective_id": oid, "label": label, "objective_type": "PROGRAM",
            "is_federal": False, "is_final": True, "cfda": None,
            "reason": f"Opened so {label} can be charged: the 2025 ledger "
                      f"carries cost under that name and the objective "
                      f"register has never had a row for it. Non-federal "
                      f"until an award is shown — a federal code needs a "
                      f"CFDA number and the Single Audit scope follows the "
                      f"SEFA."})
        if r.status_code == 201:
            print(f"  {OK}opened cost objective {oid}{END} — {label}")
        elif r.status_code != 409:
            print(f"  {FAIL}could not open {oid}: {r.status_code} "
                  f"{r.text[:120]}{END}")
            return 1

    todo = [(g, j) for g, j in walked if not j.blocked]
    print(f"\n{BOLD}Recording {len(todo)} judgment(s) as {email}{END}")
    ok = bad = 0
    # A refusal that applies to the whole run is reported once and stops the
    # run. The first version printed it 572 times — the same sentence per
    # group — which is the defect the evidence screen already learned: a
    # screen that prints one fact 572 times buries the three that differ.
    for g, j in todo:
        body = {"group_keys": [g.key], "pool": j.pool,
                "function_990": j.function_990, "federal": j.federal,
                "objective_id": j.objective_id, "grade": j.grade,
                "citation": j.citation, "period": period,
                "rationale": f"{j.rationale} [{j.basis}; "
                             f"scripts/classification_log.py]"}
        r = c.post("/api/classify/decide", json=body)
        if r.status_code == 200:
            ok += 1
        else:
            bad += 1
            detail = r.json().get("detail") if r.headers.get(
                "content-type", "").startswith("application/json") else r.text
            if isinstance(detail, dict) and detail.get("error") == "SET_IS_SEALED":
                print(f"  {FAIL}the set is sealed{END} — {detail['message']}")
                print(f"  {DIM}Nothing was recorded. Unsealing is the "
                      f"controller's judgment and needs a written reason; it "
                      f"supersedes any rate computed from the set.{END}")
                return 1
            print(f"  {FAIL}{r.status_code}{END} {g.account[:48]:<48} {detail}")
    print(f"  {OK}{ok} recorded{END}, {FAIL if bad else DIM}{bad} refused{END}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2025")
    ap.add_argument("--reverse", action="store_true",
                    help="walk December back to January instead")
    ap.add_argument("--write", action="store_true", help="write docs/CLASSIFICATION_LOG.md")
    ap.add_argument("--apply", action="store_true", help="record through the API")
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--email", default="tom@ybi.org")
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD", ""))
    a = ap.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.")
        return 2
    open_pool()

    groups = rows_for(a.period)
    done = already_judged(a.period)
    federal = federal_objectives()
    walked = walk(groups, reverse=a.reverse, federal_objectives=federal)

    # Both directions, every run. The check costs one more pass over a list
    # already in memory, and what it proves is the thing nobody would find by
    # reading either run alone: that the order of the books does not decide
    # the judgments. A difference here is a defect in `judge()`, not in the
    # ledger.
    other = walk(groups, reverse=not a.reverse, federal_objectives=federal)
    differ = disagreements(walked, other)
    print(f"\n{BOLD}Read {'December back to January' if a.reverse else 'January forward'}"
          f"{END}  {DIM}— and checked against the other direction{END}")
    if differ:
        print(f"  {FAIL}{len(differ)} group(s) judged differently depending on "
              f"the direction of the read:{END}")
        for line in differ[:20]:
            print(f"    {line}")
        return 1
    print(f"  {OK}all {len(walked)} group(s) judge the same read either way"
          f"{END}")

    s = report(walked, done, a.period)

    if a.write:
        write_log(walked, s, a.period,
                  Path(__file__).resolve().parent.parent / "docs"
                  / "CLASSIFICATION_LOG.md", federal)

    rc = 0
    if a.apply:
        rc |= apply(walked, a.base, a.email, a.password, a.period)

    faults = show_anchors(a.period)
    if faults:
        print(f"\n{FAIL}{BOLD}{faults} anchor(s) do not hold.{END}")
        return 1
    print(f"\n{BOLD}Every anchor that can be evaluated holds.{END}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
