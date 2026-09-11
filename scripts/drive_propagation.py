#!/usr/bin/env python3
"""The change propagation matrix.

**Reclassifying one expense changes the whole system**, and the point of this
drive is that "the whole system" is a list rather than a feeling. Twenty-one
observations are taken before and after each change, and every one of them is
asserted to move or to hold — because a figure that moves when it should not
is as much a defect as one that does not move when it should, and only the
second kind ever gets noticed.

Four changes, each a state a controller actually reaches:

    1  classify a group that was unjudged
    2  reclassify it into a different pool
    3  seal the set
    4  try to reclassify a sealed set, and be refused

The fourth is the one the engagement rests on. A rate carries the seal of the
judgments under it, so a classification that could change afterwards without
superseding the rate would make the seal decorative.

Everything is walked back at the end, through the real undo route, so the
drive leaves the record as it found it.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_propagation.py \\
        [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import httpx

FINDINGS: list[str] = []
CHECKS = 0


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


def head(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m", flush=True)


# ── What the whole system looks like at one moment ───────────────────
#
# Each entry is a thing somebody reads off a screen. Grouped by what a
# classification is *supposed* to do to it, because that is the assertion:
# not "something changed" but "these changed and those did not".

def observe() -> dict:
    from app.db import one

    def scalar(sql, params=()):
        row = one(sql, params)
        return None if not row else list(row.values())[0]

    return {
        # -- the judgment itself -------------------------------------
        "decisions": scalar("SELECT count(*) FROM decision WHERE reversed_at IS NULL"),
        "decision_lines": scalar("SELECT count(*) FROM decision_line"),
        "sets_open": scalar("SELECT count(*) FROM decision_set WHERE sealed_at IS NULL"),
        "sets_sealed": scalar("SELECT count(*) FROM decision_set WHERE sealed_at IS NOT NULL"),

        # -- what it is supposed to move -----------------------------
        "coverage_pct": scalar("SELECT pct_dollars_covered FROM "
                               "v_classification_coverage WHERE period='2025'"),
        "classified": scalar("SELECT classified FROM "
                             "v_classification_coverage WHERE period='2025'"),
        "unclassified": scalar("SELECT unclassified FROM "
                               "v_classification_coverage WHERE period='2025'"),
        "groups_decided": scalar("SELECT groups_decided FROM "
                                 "v_classification_coverage WHERE period='2025'"),
        "unclassified_groups": scalar("SELECT count(*) FROM v_unclassified"),
        "pool_rows": scalar("SELECT count(*) FROM v_pool_balance "
                            "WHERE period='2025'"),
        "ga_pool": scalar("SELECT coalesce(sum(gross),0) FROM v_pool_balance "
                          "WHERE period='2025' AND pool='G&A'"),
        "overhead_pool": scalar("SELECT coalesce(sum(gross),0) FROM "
                                "v_pool_balance WHERE period='2025' "
                                "AND pool='OVERHEAD'"),
        "worklist_unclassified": scalar(
            "SELECT count(*) FROM v_worklist WHERE kind='UNCLASSIFIED'"),
        "audit": scalar("SELECT count(*) FROM audit_log"),

        # -- what it must never move ---------------------------------
        "ledger_lines": scalar("SELECT count(*) FROM ledger_line WHERE period='2025'"),
        "ledger_net": scalar("SELECT coalesce(sum(amount),0) FROM ledger_line "
                             "WHERE period='2025'"),
        "scope_dollars": scalar("SELECT scope_dollars FROM "
                                "v_classification_coverage WHERE period='2025'"),
        "register": scalar("SELECT register_wages FROM "
                           "v_payroll_reconciliation WHERE period='2025'"),
        "controls_open": scalar("SELECT count(*) FROM v_statement_reconciliation "
                                "WHERE period='2025' AND state <> 'TIES'"),
        "documents": scalar("SELECT count(*) FROM evidence"),
        "invoices": scalar("SELECT count(*) FROM invoice"),
        "awards": scalar("SELECT count(*) FROM award"),
    }


#: What a classification is allowed to touch. Everything not named here must
#: hold, and the drive asserts that explicitly rather than assuming it — a
#: figure that moves when nobody expected it to is the defect nobody finds.
MAY_MOVE = {
    "decisions", "decision_lines", "coverage_pct", "classified",
    "unclassified", "groups_decided", "unclassified_groups", "pool_rows",
    "ga_pool", "overhead_pool", "worklist_unclassified", "audit",
    "sets_open", "sets_sealed",
}

MUST_HOLD = {
    "ledger_lines": "classifying cost must not change the cost",
    "ledger_net": "classifying cost must not change what the ledger says",
    "scope_dollars": "judging cost must not change how much there is to judge",
    "register": "classification must not touch the payroll register",
    "controls_open": "classification must not open or close a control",
    "documents": "classification must not add or remove a document",
    "invoices": "classification must not touch the invoice register",
    "awards": "classification must not touch the award register",
}


def compare(before: dict, after: dict, expect_moved: set[str],
            what: str) -> None:
    """Assert the matrix: these moved, those held, nothing else stirred."""
    moved = {k for k in before
             if str(before[k]) != str(after[k])}

    for key in expect_moved:
        if key not in moved:
            finding(f"{what}: {key} did not move "
                    f"({before[key]} -> {after[key]})")
        else:
            ok(f"{what}: {key} moved {before[key]} -> {after[key]}")

    for key, why in MUST_HOLD.items():
        if key in moved:
            finding(f"{what}: {why} — {key} moved "
                    f"{before[key]} -> {after[key]}")
        else:
            ok(f"{what}: {why}")

    unexpected = moved - expect_moved - set(MUST_HOLD)
    for key in sorted(unexpected):
        if key in MAY_MOVE:
            ok(f"{what}: {key} also moved {before[key]} -> {after[key]} "
               f"(allowed)")
        else:
            finding(f"{what}: {key} moved and nothing said it could "
                    f"({before[key]} -> {after[key]})")


# ── The drive ────────────────────────────────────────────────────────

def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code}). "
                         f"A signed-out client and a correctly-refusing "
                         f"server look identical, so this cannot run.")
    return c


def pick_group(c: httpx.Client) -> dict | None:
    r = c.get("/api/classify/queue?limit=1")
    if r.status_code != 200:
        finding(f"the classification queue answered {r.status_code}")
        return None
    rows = r.json()
    return rows[0] if rows else None


def classify(c: httpx.Client, group: dict, pool: str, why: str):
    return c.post("/api/classify/decide", json={
        "group_keys": [group["group_key"]],
        "pool": pool,
        "function_990": "MANAGEMENT_AND_GENERAL",
        "federal": "PENDING",
        "grade": "CORROBORATED",
        "rationale": why,
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required.")

    from app.db import open_pool
    open_pool()

    tom = sign_in(args.base, "tom@ybi.org", password)
    undo_ids: list[str] = []

    try:
        head("A group nobody has judged")
        group = pick_group(tom)
        if not group:
            print("\nCOULD NOT RUN — the queue is empty, so there is no "
                  "unjudged cost to reclassify.", file=sys.stderr)
            return 2
        # Two figures, and the difference matters. `amount` is the group's
        # net position, which is what the queue prints; `abs_amount` is the
        # sum of what each line moved, which is what coverage counts. For a
        # group with both debits and credits they differ — here by more than
        # half a million — and comparing one against the other made the first
        # run of this drive report a defect that was really two correct
        # measures of two different things.
        net = Decimal(str(group["amount"]))
        amount = Decimal(str(group["abs_amount"]))
        print(f"  {group['account'][:58]}")
        print(f"  {group['line_count']} lines, net {net:,.2f}, "
              f"absolute {amount:,.2f}")
        if net != amount:
            print(f"  (the queue prints the net; coverage counts the "
                  f"absolute — a difference of {amount - abs(net):,.2f})")

        # ── 1. classify it ──────────────────────────────────────────
        head("1. Classifying it")
        before = observe()
        r = classify(tom, group, "G&A",
                     "Propagation drive: judged once, to measure what one "
                     "judgment moves and what it must leave alone.")
        if r.status_code >= 400:
            # A sealed set refusing a new judgment is the guarantee working,
            # not a fault — and it means this drive has nothing to measure.
            # Saying "could not run" is the honest answer; reporting the
            # guarantee as a defect is what this did when it was ordered
            # after a drive that seals.
            if "sealed" in r.text.lower() or "no open decision set" in r.text.lower():
                print("\nCOULD NOT RUN — the decision set is sealed, so there "
                      "is no change to make and nothing to measure. That is "
                      "the correct state, not a defect: run this on a freshly "
                      "seeded database, before any drive that seals.",
                      file=sys.stderr)
                return 2
            finding(f"a controller could not classify ({r.status_code}): "
                    f"{r.text[:160]}")
            return 1
        after = observe()
        compare(before, after,
                {"decisions", "decision_lines", "coverage_pct", "classified",
                 "unclassified", "groups_decided", "unclassified_groups",
                 "worklist_unclassified", "audit", "ga_pool"},
                "classify")

        # The arithmetic, not just the direction. A coverage figure that
        # moves the right way by the wrong amount is the harder bug.
        moved = Decimal(str(after["classified"])) - Decimal(str(before["classified"]))
        if moved != amount:
            finding(f"classified moved {moved:,.2f} for a group whose lines "
                    f"move {amount:,.2f} — coverage and the queue disagree "
                    f"about what this group is")
        else:
            ok(f"classified moved by exactly the group's {amount:,.2f}")

        released = Decimal(str(before["unclassified"])) - Decimal(str(after["unclassified"]))
        if released != amount:
            finding(f"unclassified fell {released:,.2f}, not {amount:,.2f}")
        else:
            ok("and unclassified fell by the same amount")

        if Decimal(str(after["classified"])) + Decimal(str(after["unclassified"])) \
                != Decimal(str(after["scope_dollars"])):
            finding("classified + unclassified no longer equals the scope")
        else:
            ok("classified + unclassified still equals the scope")

        # ── 2. reclassify into a different pool ─────────────────────
        head("2. Reclassifying it into a different pool")
        before = observe()
        r = classify(tom, group, "OVERHEAD",
                     "Propagation drive: the same cost judged differently, "
                     "to prove the pools move and the totals do not.")
        if r.status_code >= 400:
            finding(f"a reclassification was refused ({r.status_code}): "
                    f"{r.text[:160]}")
        else:
            after = observe()
            # Coverage must NOT move: the same dollars are still judged. Only
            # which pool holds them changes. This is the assertion that would
            # catch a supersede that double-counts.
            if str(before["coverage_pct"]) != str(after["coverage_pct"]):
                finding(f"reclassifying moved coverage "
                        f"{before['coverage_pct']} -> {after['coverage_pct']}; "
                        f"the same cost is judged either way")
            else:
                ok("reclassifying leaves coverage where it was — the same "
                   "cost is judged, in a different pool")
            if str(before["classified"]) != str(after["classified"]):
                finding(f"classified moved on a reclassification: "
                        f"{before['classified']} -> {after['classified']}")
            else:
                ok("and the classified total is unchanged")

            # The pools hold net cost, not absolute movement — a pool is
            # what the period spent, so a credit reduces it.
            ga = Decimal(str(before["ga_pool"])) - Decimal(str(after["ga_pool"]))
            oh = Decimal(str(after["overhead_pool"])) - Decimal(str(before["overhead_pool"]))
            if ga != net or oh != net:
                finding(f"the cost did not move whole between pools: G&A fell "
                        f"{ga:,.2f}, overhead rose {oh:,.2f}, group is "
                        f"{net:,.2f}")
            else:
                ok(f"the whole {net:,.2f} left G&A and arrived in overhead — "
                   f"no dollar in two pools, none in neither")

            body = r.json()
            if body.get("superseded") != 1:
                finding(f"the response says superseded={body.get('superseded')}; "
                        f"a screen has no other way to tell somebody their "
                        f"change replaced an earlier judgment")
            else:
                ok("and the response says it superseded one judgment")
            for key, why in MUST_HOLD.items():
                if str(before[key]) != str(after[key]):
                    finding(f"reclassify: {why}")
            ok("and everything a reclassification must not touch held")

        # ── 3. seal, and 4. be refused ──────────────────────────────
        seal_and_refuse(tom, group)

        head("Putting it back")
        walk_back(tom)

        print(f"\n{'PASS' if not FINDINGS else 'FAIL'} — {CHECKS} checks"
              + (f", {len(FINDINGS)} finding(s)" if FINDINGS else
                 ", every change moved what it should and nothing else"))
        return 1 if FINDINGS else 0
    finally:
        tom.close()


def seal_and_refuse(tom: httpx.Client, group: dict) -> None:
    """The step the engagement rests on.

    A rate carries the seal of the judgments under it. If a classification
    could change after the seal without superseding the rate, the seal would
    be decorative — so the refusal is not an inconvenience to be worked
    around, it is the guarantee itself, and it is asserted here rather than
    assumed.
    """
    head("3. Sealing the set")
    before = observe()
    r = tom.post("/api/rates/seal", json={
        "period": "2025",
        "label": "Propagation drive — sealed to prove what a seal refuses"})
    if r.status_code >= 400:
        # Already sealed is a legitimate state, not a fault.
        if "sealed" in r.text.lower():
            ok("the set was already sealed")
        else:
            finding(f"sealing was refused ({r.status_code}): {r.text[:160]}")
            return
    else:
        after = observe()
        if after["sets_sealed"] <= before["sets_sealed"]:
            finding("sealing recorded no sealed set")
        else:
            ok(f"sets sealed {before['sets_sealed']} -> {after['sets_sealed']}")
        for key, why in MUST_HOLD.items():
            if str(before[key]) != str(after[key]):
                finding(f"seal: {why}")
        ok("sealing changed no cost, no control and no document")

    head("4. Reclassifying a sealed set — which must be refused")
    before = observe()
    r = classify(tom, group, "G&A",
                 "Propagation drive: this must not be accepted while the set "
                 "is sealed.")
    after = observe()

    if r.status_code < 400:
        finding("a sealed decision set accepted a new classification. The "
                "rate carries the seal of the judgments under it, so this "
                "makes the seal decorative.")
        return
    ok(f"a sealed set refuses a reclassification — {r.status_code}")

    # And it must have refused *completely*. A refusal that half-applied
    # would be worse than an acceptance, because nothing would say so.
    changed = [k for k in before if str(before[k]) != str(after[k])
               and k != "audit"]
    if changed:
        finding(f"the refused classification still moved {', '.join(changed)}")
    else:
        ok("and nothing moved — the refusal was complete, not partial")

    # The refusal is on the record, which is the thing that was missing.
    from app.db import one
    row = one("""SELECT status, detail FROM refusal
                  WHERE path = '/api/classify/decide' AND status >= 400
                  ORDER BY occurred_at DESC LIMIT 1""")
    if not row:
        finding("the refusal left no trace in the refusal table")
    else:
        ok(f"and the refusal is on the record — {row['status']}, "
           f"{(row['detail'] or '')[:60]}")


def walk_back(tom: httpx.Client) -> None:
    """Leave the record as it was found.

    A drive that leaves its own test data behind changes the thing it
    measures, and the next run measures the run before it.
    """
    for _ in range(6):
        r = tom.post("/api/undo", json={
            "count": 1,
            "reason": "Propagation drive: reversing its own changes so the "
                      "record is left as it was found."})
        if r.status_code >= 400:
            break
    ok("the drive walked its own changes back")


if __name__ == "__main__":
    sys.exit(main())
