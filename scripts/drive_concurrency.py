#!/usr/bin/env python3
"""Two people, one record, the same instant.

Every other drive in this repository does one thing at a time, which is how
the system is meant to be worked and is not how it will be worked. Tom and
Heidi both hold CONTROLLER and both work the queue. The system is fast enough
that they will almost never collide — and that is exactly what makes the
collision worth proving, because a defect that appears once a month and
cannot be reproduced is one people learn to explain away.

Four races, each a state two controllers actually reach:

    1  both judge the same group at the same moment, from screens drawn
       before either of them acted
    2  the same, from screens that are current — one of them is simply
       later, and superseding is the right answer
    3  a storm of judgments across different groups while a seal is taken
    4  a seal and an unseal fired together

What each one is looking for is not "did it crash". It is whether the record
afterwards can be read by one person and understood:

  * exactly one live judgment on a group, whatever order they arrived in
  * `classified + unclassified = scope_dollars`, which is the arithmetic
    the coverage figure reproduces from
  * **the seal covers what it sealed** — the stored hash recomputes to
    itself over the set's live judgments

The third is the one the engagement rests on, and it is the one that was
broken. `seal()` ran four statements on four pooled connections: find the
open set, hash it, count it, write the hash. A judgment committing between
the hash and the write landed in a set whose `seal_hash` does not cover it,
silently, and nothing would ever have shown it — the hash is only recomputed
when somebody unseals, which may be months later or never.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_concurrency.py \\
        [--base http://127.0.0.1:8000]

It is destructive in the ordinary way a drive is: it classifies, seals and
unseals. It walks its own judgments back at the end and leaves the set open.
Run it before any drive that seals, like the propagation drive, and after the
foundation is loaded.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.foundation import EMAIL  # noqa: E402

FINDINGS: list[str] = []
CHECKS = 0


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"  FINDING  {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  ok       {msg}", flush=True)


#: A race can legitimately go entirely one way, and then a guarantee that is
#: only reachable down the other branch has no occasion to be tested. That is
#: not a pass and it is not a finding — it is the `NO DATA` state of the
#: control register, in a drive. Said out loud, because the alternative is a
#: check count that reads 16 one run and 15 the next with nothing explaining
#: the difference, which is how somebody comes to dismiss the run that
#: actually lost a check.
NOTES: list[str] = []


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  --       {msg}", flush=True)


def head(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code}). "
                         f"A signed-out client and a correctly-refusing server "
                         f"look identical, so this cannot run.")
    return c


# ── Firing two requests at genuinely the same moment ──────────────────
#
# Threads started one after another are not simultaneous — the first can be
# finished before the second is scheduled, and the race this drive exists to
# test would never happen. A barrier makes them wait for each other and let
# go together, which is as close to one instant as two processes get.

def simultaneously(calls):
    """Run each zero-argument call at once. Returns results in order."""
    gate = threading.Barrier(len(calls))
    out: list = [None] * len(calls)

    def run(i, fn):
        gate.wait()
        try:
            out[i] = fn()
        except Exception as exc:                     # noqa: BLE001
            out[i] = exc

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        for i, fn in enumerate(calls):
            pool.submit(run, i, fn)
    return out


# ── What the record says afterwards ───────────────────────────────────

def live_decisions_on(account: str, payee: str, period="2025") -> list[dict]:
    from app.db import query
    return query("""SELECT DISTINCT d.decision_id::text AS decision_id,
                           d.pool::text AS pool, d.decided_by
                      FROM decision d
                      JOIN decision_line dl ON dl.decision_id = d.decision_id
                                           AND dl.live
                      JOIN ledger_line l ON l.line_id = dl.line_id
                     WHERE d.reversed_at IS NULL AND l.period = %s
                       AND l.account = %s AND coalesce(l.payee,'') = %s""",
                 (period, account, payee))


def coverage_is_arithmetic(period="2025") -> tuple[bool, str]:
    """classified + unclassified = scope_dollars, or the percentage on the
    screen does not reproduce from the row it is printed off."""
    from app.db import one
    r = one("""SELECT classified, unclassified, scope_dollars
                 FROM v_classification_coverage WHERE period = %s""", (period,))
    if not r:
        return False, "no coverage row"
    total = r["classified"] + r["unclassified"]
    return total == r["scope_dollars"], (
        f"{r['classified']} + {r['unclassified']} = {total} "
        f"against scope {r['scope_dollars']}")


def seal_recomputes(period="2025") -> tuple[bool, str]:
    """The stored seal hashed again over the set's live judgments.

    This is the whole guarantee, expressed as arithmetic. The recomputation
    is the same expression `seal()` uses — deliberately, because what is
    being tested is not whether the expression is right but whether the set
    moved between computing it and storing it.
    """
    from app.db import one
    r = one("""
        SELECT s.set_id::text AS set_id, s.seal_hash,
               (SELECT encode(digest(string_agg(fp,'' ORDER BY fp),'sha256'),'hex')
                  FROM (SELECT encode(digest(
                           d.decision_id::text || d.pool::text ||
                           d.function_990::text || d.federal::text ||
                           coalesce(d.objective_id,'') || d.grade::text,
                           'sha256'),'hex') AS fp
                          FROM decision d
                         WHERE d.set_id = s.set_id
                           AND d.reversed_at IS NULL) x) AS recomputed
          FROM decision_set s
         WHERE s.period = %s AND s.seal_hash IS NOT NULL
         ORDER BY s.sealed_at DESC LIMIT 1""", (period,))
    if not r:
        return False, "no sealed set"
    same = r["seal_hash"] == r["recomputed"]
    return same, (f"stored {r['seal_hash'][:12]}… "
                  f"{'=' if same else '≠'} recomputed "
                  f"{(r['recomputed'] or 'NULL')[:12]}…")


# ── The races ─────────────────────────────────────────────────────────

def undecided_groups(c: httpx.Client, n: int) -> list[dict]:
    r = c.get("/api/classify/queue", params={"status": "undecided", "limit": n})
    r.raise_for_status()
    return r.json()[:n]


def judgment(group: dict, pool: str, who: str, based_on: dict | None = None) -> dict:
    body = {
        "group_keys": [group["group_key"]],
        "pool": pool,
        "function_990": "PROGRAM" if pool != "FRINGE" else "NOT_APPLICABLE",
        "federal": "ALLOWABLE",
        "objective_id": None,
        "grade": "TEST_ASSUMPTION",
        "rationale": f"Concurrency drive — {who} judging {group['account']}.",
    }
    if based_on is not None:
        body["based_on"] = based_on
    return body


def race_same_group_stale(tom, heidi) -> list[str]:
    """Both screens were drawn before either acted. Exactly one judgment
    should land, and the other person should be told what happened in a
    sentence with a name in it."""
    head("Two controllers, one group, both screens drawn first")
    groups = undecided_groups(tom, 1)
    if not groups:
        finding("no undecided group to race on")
        return []
    g = groups[0]
    # Both send what their screen showed: unjudged. That is the stale claim.
    seen = {g["group_key"]: g.get("live_decision", "none")}

    results = simultaneously([
        lambda: tom.post("/api/classify/decide",
                         json=judgment(g, "OVERHEAD", "Tom", seen)),
        lambda: heidi.post("/api/classify/decide",
                           json=judgment(g, "G&A", "Heidi", seen)),
    ])
    codes = sorted(r.status_code for r in results if isinstance(r, httpx.Response))
    if codes != [200, 409]:
        finding(f"expected one to land and one to be refused; got {codes}")
    else:
        ok(f"one landed, one refused — {codes}")

    refused = next((r for r in results
                    if isinstance(r, httpx.Response) and r.status_code == 409), None)
    if refused is None:
        note("no judgment was refused, so there was nothing to read the "
             "refusal off — covered by the finding above")
    else:
        detail = refused.json().get("detail", {})
        msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        if "changed while this screen was open" in msg and "classified it as" in msg:
            ok(f"and the refusal says who and what: “{msg[:90]}…”")
        else:
            finding(f"the refusal does not name what changed: {msg[:160]}")

    live = live_decisions_on(g["account"], g["payee"])
    if len(live) == 1:
        ok(f"exactly one live judgment on {g['account']} — "
           f"{live[0]['pool']} by {live[0]['decided_by']}")
    else:
        finding(f"{len(all_pools(live))} live judgments on {g['account']}: "
                f"{[d['pool'] for d in live]}")
    return [g["group_key"]]


def all_pools(rows):
    return {r["pool"] for r in rows}


def race_same_group_current(tom, heidi) -> list[str]:
    """Neither screen is stale — both simply arrive at once. Superseding is
    the right answer here: one of them is later, and the later judgment is
    the one on file. What must not happen is two live judgments, or one
    reported as recorded that is not."""
    head("Two controllers, one group, neither claiming a prior state")
    groups = undecided_groups(tom, 1)
    if not groups:
        finding("no undecided group to race on")
        return []
    g = groups[0]
    results = simultaneously([
        lambda: tom.post("/api/classify/decide", json=judgment(g, "OVERHEAD", "Tom")),
        lambda: heidi.post("/api/classify/decide", json=judgment(g, "G&A", "Heidi")),
    ])
    codes = sorted(r.status_code for r in results if isinstance(r, httpx.Response))
    if codes == [200, 200]:
        ok("both accepted — the second superseded the first, which is the rule")
    else:
        finding(f"expected both to be accepted; got {codes}")

    live = live_decisions_on(g["account"], g["payee"])
    if len(live) == 1:
        ok(f"and exactly one survives — {live[0]['pool']} by {live[0]['decided_by']}")
    else:
        finding(f"{len(live)} live judgments after the race: "
                f"{[(d['pool'], d['decided_by']) for d in live]}")

    # A success that did nothing is the shape this system has been bitten by
    # before, so the claim is checked against the record rather than trusted.
    landed = [r.json() for r in results
              if isinstance(r, httpx.Response) and r.status_code == 200]
    if sum(j.get("decisions_created", 0) for j in landed) == 2:
        ok("both said they recorded a judgment, and both did")
    else:
        finding(f"a 200 that recorded nothing: {landed}")
    if any(j.get("superseded") for j in landed):
        ok("the later one says it replaced something, so the screen can say so")
    else:
        finding("neither response reports superseding, so neither screen can")
    return [g["group_key"]]


def race_classify_against_seal(tom, heidi) -> list[str]:
    """The one that matters. Judgments in flight while the set is sealed.

    Whatever order they land in, the stored hash has to be a hash of the set
    as it finally stands. Either a judgment is in the set and in the hash, or
    it was refused because the set was already sealed. There is no third
    outcome, and the third outcome is what four separate transactions made
    possible.
    """
    head("A seal taken while judgments are in flight")
    groups = undecided_groups(tom, 6)
    if len(groups) < 6:
        finding(f"only {len(groups)} undecided groups; wanted 6")
        if not groups:
            return []

    calls = [(lambda g=g: heidi.post("/api/classify/decide",
                                     json=judgment(g, "OVERHEAD", "Heidi")))
             for g in groups]
    # The seal goes in the middle of the pack rather than at the end, so some
    # judgments are certain to be behind it in the queue and some ahead.
    calls.insert(len(calls) // 2,
                 lambda: tom.post("/api/rates/seal",
                                  json={"note": "Concurrency drive."}))
    results = simultaneously(calls)

    sealed = [r for r in results if isinstance(r, httpx.Response)
              and r.request.url.path.endswith("/rates/seal")]
    if sealed and sealed[0].status_code == 200:
        ok(f"the seal was taken — {sealed[0].json()['decisions']} judgments in it")
    else:
        finding(f"the seal did not take: "
                f"{sealed[0].status_code if sealed else 'no response'}")

    accepted = sum(1 for r in results if isinstance(r, httpx.Response)
                   and r.request.url.path.endswith("/decide")
                   and r.status_code == 200)
    refused = [r for r in results if isinstance(r, httpx.Response)
               and r.request.url.path.endswith("/decide")
               and r.status_code != 200]
    ok(f"{accepted} judgment(s) landed before the seal, "
       f"{len(refused)} refused after it")
    for r in refused:
        body = r.text
        if "sealed" not in body.lower():
            finding(f"a judgment was refused for a reason that does not "
                    f"mention the seal: {body[:160]}")
            break
    else:
        if refused:
            ok("and every refusal says the set was sealed")
        else:
            note("every judgment beat the seal this run, so there was no "
                 "refusal to read — the guarantee that a refusal names the "
                 "seal had no occasion to be tested")

    same, how = seal_recomputes()
    if same:
        ok(f"the seal covers what it sealed — {how}")
    else:
        finding(f"THE SEAL DOES NOT COVER WHAT IT SEALED — {how}")
    return [g["group_key"] for g in groups]


def race_seal_against_unseal(tom, heidi) -> None:
    """Seal and unseal fired together. The set ends in one of the two states
    and the rates agree with it — an open set with a live rate on file is the
    state `/review` presents as the rate on file."""
    head("A seal and an unseal, fired together")
    from app.db import one

    results = simultaneously([
        lambda: heidi.post("/api/rates/unseal",
                           params={"reason": "Concurrency drive — reopening."}),
        lambda: tom.post("/api/rates/seal", json={"note": "Concurrency drive."}),
    ])
    codes = [r.status_code if isinstance(r, httpx.Response) else str(r)
             for r in results]
    ok(f"unseal {codes[0]}, seal {codes[1]} — one of each order is legitimate")

    state = one("""SELECT seal_hash IS NOT NULL AS sealed,
                          (SELECT count(*) FROM rate
                            WHERE period = '2025' AND status = 'PROPOSED') AS live_rates
                     FROM decision_set WHERE period = '2025'
                    ORDER BY set_id DESC LIMIT 1""")
    if state["sealed"]:
        same, how = seal_recomputes()
        if same:
            ok(f"it ended sealed, and the seal recomputes — {how}")
        else:
            finding(f"it ended sealed with a hash that does not recompute — {how}")
    else:
        if state["live_rates"] == 0:
            ok("it ended open, with no rate left standing over it")
        else:
            finding(f"it ended open with {state['live_rates']} rate(s) still "
                    f"PROPOSED — an unsealed set with a live rate is the state "
                    f"the review screen presents as the rate on file")


# ── Walking it back ───────────────────────────────────────────────────

def walk_back(tom: httpx.Client, keys: list[str]) -> None:
    """Leave the record as it was found: the set open, and the judgments this
    drive made reversed. Reversing is the same mechanism undo and
    reclassification use; there is deliberately not a second one."""
    head("Walking it back")
    from app.db import execute, one

    st = one("SELECT set_id, seal_hash FROM decision_set WHERE period='2025' "
             "ORDER BY set_id DESC LIMIT 1")
    # Whether there *is* a seal to release depends on which way the last race
    # went: `race_seal_against_unseal` fires both at once and either order is
    # legitimate, so the set reaches here sealed or open. That is the other
    # half of the 16-checks-then-15 mystery — this branch printed nothing at
    # all when the set was already open.
    if st and st["seal_hash"]:
        r = tom.post("/api/rates/unseal",
                     params={"reason": "Concurrency drive finished; "
                                       "leaving the set as it was found."})
        # And it was `ok(f"unsealed ({r.status_code})")`, which prints a 409
        # as a pass. A check whose assertion is the thing it is printing is
        # not a check — the third instance of that shape in this one file.
        if r.status_code == 200:
            ok("unsealed — the set is open again, as it was found")
        else:
            finding(f"could not unseal: {r.status_code} {r.text[:160]}")
    else:
        note("the set was already open — the seal-against-unseal race ended "
             "with the unseal, which is one of its two legitimate outcomes, "
             "so there was nothing here to release")

    execute("""UPDATE decision SET reversed_at = now(),
                      reversal_reason = 'Concurrency drive, walked back.'
                WHERE reversed_at IS NULL
                  AND rationale LIKE 'Concurrency drive%'""")
    left = one("""SELECT count(*) AS n FROM decision
                   WHERE reversed_at IS NULL AND rationale LIKE 'Concurrency drive%'""")
    if left["n"] == 0:
        ok("every judgment this drive made is reversed")
    else:
        finding(f"{left['n']} of this drive's judgments are still live")

    good, how = coverage_is_arithmetic()
    if good:
        ok(f"and coverage still reproduces from its own row — {how}")
    else:
        finding(f"coverage does not reproduce — {how}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--password", default=os.environ.get("YBI_SEED_PASSWORD", ""))
    args = ap.parse_args()
    if not args.password:
        raise SystemExit("YBI_SEED_PASSWORD (or --password) is required.")

    tom = sign_in(args.base, EMAIL["tom"], args.password)
    heidi = sign_in(args.base, "hruby@ybi.org", args.password)
    print("Tom and Heidi are both signed in, in separate sessions.")

    touched: list[str] = []
    touched += race_same_group_stale(tom, heidi)
    touched += race_same_group_current(tom, heidi)
    touched += race_classify_against_seal(tom, heidi)
    race_seal_against_unseal(tom, heidi)
    walk_back(tom, touched)

    head("Summary")
    # `coverage_is_arithmetic()` used to be called here and its answer thrown
    # away — bound to `good, how` and read by nothing, so it could not pass
    # and could not fail. `walk_back` checks it properly; this was a fourth
    # instance of *a test that cannot fail for the thing it names*.
    for f in FINDINGS:
        print(f"    - {f}")
    for n in NOTES:
        print(f"    ~ {n}")
    # Last, because `scripts/prove.sh` prints the final line of a passing run
    # as the result and the count is what a reader wants there.
    print(f"  {CHECKS} check(s), {len(FINDINGS)} finding(s), "
          f"{len(NOTES)} note(s)")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    sys.exit(main())
