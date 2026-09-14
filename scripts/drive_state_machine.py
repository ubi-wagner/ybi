#!/usr/bin/env python3
"""The system as a state machine, driven one turn at a time.

This is not a review and it does not sample. It performs real actions through
the real API, in sequence, and after **every single one** it re-reads the
whole system and checks every invariant again — because the defect that
matters here is not an action that fails, it is an action that succeeds and
quietly moves something three screens away that nobody connected to it.

Three rules it is built on:

**Serial.** One action, fully committed, then observe. Nothing is batched and
nothing overlaps, so when a figure moves there is exactly one thing that could
have moved it.

**Every invariant, every turn.** Not the ones related to the action — all of
them. A chain reaction that goes wrong two turns downstream is invisible to a
check that only looks at what it expected to change. This is how the coverage
double-count was found: the *scope* grew on a reclassification, and no
judgment anybody makes can change how much there is to judge.

**The edges, not just the nodes.** After each turn the drive attempts things
that must be refused *in this state* and confirms they are. A state machine
is its transitions; a drive that only checks the states it visits proves half
of it.

Then it walks the whole thing back and compares the final state to the first,
field by field. Where the system is deliberately not reversible — a computed
rate supersedes, it does not vanish — the drive says so rather than failing,
because "you cannot un-compute a rate" is a design decision and not a defect.

    PYTHONPATH=. YBI_SEED_PASSWORD=... python3 scripts/drive_state_machine.py \\
        [--base http://127.0.0.1:8000]

Exit 0 when every turn moved what it should and the reset landed where it
started; 1 on a finding; 2 when it could not run at all.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import httpx

from app.foundation import EMAIL  # noqa: E402

FINDINGS: list[str] = []
CHECKS = 0
TURN = 0


def finding(msg: str) -> None:
    FINDINGS.append(msg)
    print(f"       FINDING  {msg}", file=sys.stderr, flush=True)


def ok(msg: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"       ok       {msg}", flush=True)


def note(msg: str) -> None:
    print(f"       —        {msg}", flush=True)


# ── The whole state, read fresh every turn ───────────────────────────

def snapshot() -> dict:
    from app.db import one

    def v(sql, params=()):
        row = one(sql, params)
        return None if not row else list(row.values())[0]

    return {
        # the ledger and what it says — none of this may ever move
        "ledger_lines": v("SELECT count(*) FROM ledger_line WHERE period='2025'"),
        "ledger_net": v("SELECT coalesce(sum(amount),0) FROM ledger_line WHERE period='2025'"),
        "scope_dollars": v("SELECT scope_dollars FROM v_classification_coverage WHERE period='2025'"),
        "register": v("SELECT register_wages FROM v_payroll_reconciliation WHERE period='2025'"),
        "controls_open": v("SELECT count(*) FROM v_statement_reconciliation WHERE period='2025' AND state<>'TIES'"),

        # judgment
        "decisions_live": v("SELECT count(*) FROM decision WHERE reversed_at IS NULL"),
        "decisions_all": v("SELECT count(*) FROM decision"),
        "decision_lines_live": v("SELECT count(*) FROM decision_line WHERE live"),
        "classified": v("SELECT classified FROM v_classification_coverage WHERE period='2025'"),
        "unclassified": v("SELECT unclassified FROM v_classification_coverage WHERE period='2025'"),
        "coverage_pct": v("SELECT pct_dollars_covered FROM v_classification_coverage WHERE period='2025'"),
        "groups_decided": v("SELECT groups_decided FROM v_classification_coverage WHERE period='2025'"),
        "pools": v("SELECT count(*) FROM v_pool_balance WHERE period='2025'"),
        "pool_gross": v("SELECT coalesce(sum(gross),0) FROM v_pool_balance WHERE period='2025'"),

        # the seal, and what hangs off it
        "sets_open": v("SELECT count(*) FROM decision_set WHERE sealed_at IS NULL"),
        "sets_sealed": v("SELECT count(*) FROM decision_set WHERE sealed_at IS NOT NULL"),
        "rates_live": v("SELECT count(*) FROM rate WHERE status<>'SUPERSEDED'"),
        "rates_all": v("SELECT count(*) FROM rate"),
        "allocations": v("SELECT count(*) FROM allocation"),
        "restatements": v("SELECT count(*) FROM restatement"),

        # labour
        "time_entries": v("SELECT count(*) FROM timesheet_entry WHERE superseded_at IS NULL"),
        "submissions": v("SELECT count(*) FROM timesheet_submission WHERE withdrawn_at IS NULL"),
        "certifications": v("SELECT count(*) FROM labor_certification"),

        # the record of it all
        "audit": v("SELECT count(*) FROM audit_log"),
        "refusals": v("SELECT count(*) FROM refusal"),
        "documents": v("SELECT count(*) FROM evidence"),
        "invoices": v("SELECT count(*) FROM invoice"),
        "awards": v("SELECT count(*) FROM award"),
    }


#: Never moves, whatever anybody does. The ledger is what happened; every
#: action in this system is a judgment *about* it.
IMMUTABLE = {
    "ledger_lines": "the ledger's line count",
    "ledger_net": "what the ledger says was spent",
    "scope_dollars": "how much there is to judge",
    "register": "the payroll register",
    "invoices": "the invoice register",
    "awards": "the award register",
}


# ── Invariants, checked after every single turn ──────────────────────
#
# Each is (name, sql, what it must return). They are written to return the
# number of *violations*, so zero is always the passing answer and a new one
# can be added without thinking about direction.

INVARIANTS = [
    ("a line never carries two live decisions",
     """SELECT count(*) FROM (SELECT line_id FROM decision_line WHERE live
                               GROUP BY line_id, coalesce(segment_id,'')
                              HAVING count(*) > 1) x"""),

    # The defect the propagation drive found: a live decision attached to
    # nothing, created when a reclassification's lines were swallowed.
    ("a live decision always covers at least one line",
     """SELECT count(*) FROM decision d
         WHERE d.reversed_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM decision_line dl
                            WHERE dl.decision_id = d.decision_id AND dl.live)"""),

    ("a reversed decision holds no live lines",
     """SELECT count(*) FROM decision d JOIN decision_line dl USING (decision_id)
         WHERE d.reversed_at IS NOT NULL AND dl.live"""),

    ("classified plus unclassified equals the scope",
     """SELECT count(*) FROM v_classification_coverage
         WHERE period='2025' AND classified + unclassified <> scope_dollars"""),

    ("every pool's gross is the sum of the lines judged into it",
     """SELECT count(*) FROM (
          SELECT d.pool, sum(l.amount) AS from_lines,
                 (SELECT gross FROM v_pool_balance b
                   WHERE b.pool = d.pool AND b.period = l.period) AS from_view
            FROM decision d
            JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
            JOIN ledger_line l USING (line_id)
           WHERE d.reversed_at IS NULL
           GROUP BY d.pool, l.period
        ) x WHERE from_lines <> from_view"""),

    ("a rate always belongs to a decision set",
     """SELECT count(*) FROM rate r
         WHERE NOT EXISTS (SELECT 1 FROM decision_set s
                            WHERE s.set_id = r.set_id)"""),

    # The guarantee the engagement rests on, as a standing check rather than
    # a thing tested once: a live rate must carry the hash of a set that is
    # sealed, and sealed with that same hash.
    ("every live rate carries the seal of a sealed set",
     """SELECT count(*) FROM rate r
         JOIN decision_set s USING (set_id)
         WHERE r.status <> 'SUPERSEDED'
           AND (s.seal_hash IS NULL OR r.seal_hash IS DISTINCT FROM s.seal_hash)"""),

    ("an allocation always belongs to a rate",
     """SELECT count(*) FROM allocation a
         WHERE NOT EXISTS (SELECT 1 FROM rate r WHERE r.rate_id = a.rate_id)"""),

    ("a restatement always carries a seal",
     """SELECT count(*) FROM restatement
         WHERE coalesce(seal_hash,'') = ''"""),

    ("every audit entry names an account and a session",
     """SELECT count(*) FROM audit_log
         WHERE actor_id IS NULL OR session_id IS NULL"""),

    ("a decision set is sealed or open, never half",
     """SELECT count(*) FROM decision_set
         WHERE (seal_hash IS NULL) <> (sealed_at IS NULL)"""),

    ("no timesheet entry is live twice for a day and objective",
     """SELECT count(*) FROM (SELECT employee_key, work_date, objective_id
                               FROM timesheet_entry WHERE superseded_at IS NULL
                              GROUP BY 1,2,3 HAVING count(*) > 1) x"""),

    ("every document indexed has a path recorded",
     "SELECT count(*) FROM evidence WHERE coalesce(uri,'') = ''"),
]


def check_invariants(where: str) -> int:
    from app.db import one
    broken = 0
    for name, sql in INVARIANTS:
        try:
            n = list(one(sql).values())[0]
        except Exception as exc:                            # noqa: BLE001
            finding(f"{where}: invariant '{name}' could not be evaluated — "
                    f"{str(exc)[:120]}")
            broken += 1
            continue
        if n:
            finding(f"{where}: {n} violation(s) — {name}")
            broken += 1
    return broken


# ── One turn ─────────────────────────────────────────────────────────

def turn(label: str, who: str, act, *, may_move: set[str],
         expect: dict | None = None) -> dict:
    """Perform one action, fully, then re-read everything.

    `may_move` is the whole point. Anything outside it that moved is reported,
    because a figure nobody predicted would change is the defect that does not
    get noticed — it looks like the system working.
    """
    global TURN
    TURN += 1
    from app.db import one

    before = snapshot()
    print(f"\n\033[1mTurn {TURN}. {who}: {label}\033[0m", flush=True)

    result = act()
    status = getattr(result, "status_code", 200)
    if status >= 400:
        finding(f"turn {TURN} ({label}) was refused with {status}: "
                f"{getattr(result, 'text', '')[:200]}")
        return before

    after = snapshot()
    moved = {k for k in before if str(before[k]) != str(after[k])}

    for key in sorted(moved):
        arrow = f"{before[key]} -> {after[key]}"
        if key in IMMUTABLE:
            finding(f"turn {TURN}: {IMMUTABLE[key]} moved — {arrow}")
        elif key in may_move:
            ok(f"{key} {arrow}")
        else:
            finding(f"turn {TURN}: {key} moved and nothing said it could "
                    f"— {arrow}")

    for key in sorted(may_move - moved):
        # Not automatically wrong — an action can legitimately leave a figure
        # where it was — so this is stated rather than reported.
        note(f"{key} unchanged at {before[key]}")

    for key, expected in (expect or {}).items():
        if str(after.get(key)) != str(expected):
            finding(f"turn {TURN}: {key} is {after.get(key)}, expected "
                    f"{expected}")
        else:
            ok(f"{key} is exactly {expected}")

    if check_invariants(f"after turn {TURN}") == 0:
        ok(f"all {len(INVARIANTS)} invariants hold")
    return after


def refused(c: httpx.Client, method: str, path: str, why: str, **kw) -> None:
    """An edge of the state machine: something that must not be possible here.

    Attempting it is safe precisely because it must fail, and a state machine
    that only checks the states it visits proves half of itself.
    """
    r = c.request(method, path, **kw)
    if r.status_code < 400:
        finding(f"{why} — it was allowed ({r.status_code})")
    else:
        ok(f"{why} — refused {r.status_code}")


# ── The sequence ─────────────────────────────────────────────────────

def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=180)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email} ({r.status_code}). A "
                         f"signed-out client and a correctly-refusing server "
                         f"look identical, so this cannot run.")
    return c


def heading(text: str) -> None:
    print(f"\n\033[1m{'─' * 68}\n{text}\n{'─' * 68}\033[0m", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    password = os.environ.get("YBI_SEED_PASSWORD", "")
    if not password:
        raise SystemExit("YBI_SEED_PASSWORD is required.")

    from app.db import one, open_pool
    open_pool()

    tom = sign_in(args.base, EMAIL["tom"], password)
    heidi = sign_in(args.base, "hruby@ybi.org", password)
    auditor = sign_in(args.base, "auditor@ybi.org", password)

    try:
        heading("The state it starts in")
        initial = snapshot()
        for k in sorted(initial):
            print(f"  {k:22} {initial[k]}")
        if check_invariants("at rest") == 0:
            ok(f"all {len(INVARIANTS)} invariants hold before anything happens")

        # A state machine driven from an unknown state proves nothing. The
        # first run of this reported two findings that were really the second
        # run reading the first run's leavings — every count was cumulative
        # and every expectation was measured from the wrong zero.
        # Live state only. `decisions_all`, `rates_all` and the audit trail
        # are append-only, so they are non-zero after anything has ever
        # happened — including a drive that made one judgment and walked it
        # back. Testing those refused to run over a record that was, for
        # every purpose here, at rest.
        dirty = {k: initial[k] for k in
                 ("decisions_live", "decision_lines_live", "classified",
                  "pool_gross", "rates_live", "sets_sealed")
                 if initial[k]}
        if dirty:
            print("\nCOULD NOT RUN — the record is not at rest: "
                  + ", ".join(f"{k}={v}" for k, v in sorted(dirty.items()))
                  + ".\nEvery expectation here is an absolute count from a "
                    "known start, so a second run over the first run's "
                    "leavings measures from the wrong zero. Seed a fresh "
                    "database and run this before anything that classifies "
                    "or seals.", file=sys.stderr)
            return 2

        heading("What must not be possible yet")
        # The rate phase is locked until the set is sealed. This is the
        # guarantee, stated as an edge before the first action rather than
        # discovered later.
        refused(tom, "POST", "/api/rates/compute",
                "a rate before anything is classified or sealed", json={})
        refused(tom, "POST", "/api/rates/unseal?reason=nothing+is+sealed",
                "unsealing a set that was never sealed")
        refused(auditor, "POST", "/api/classify/decide",
                "the auditor classifying anything",
                json={"group_keys": ["x"], "pool": "G&A",
                      "function_990": "PROGRAM", "federal": "PENDING"})

        # ---- turns ------------------------------------------------
        heading("One action at a time")

        # Everything this drive does sits above here. The reset walks back
        # its own turns and stops — a loop that ran to exhaustion would
        # carry on into the seed and start reversing the eighteen
        # foundational documents, which is not a reset, it is demolition.
        floor = one("SELECT coalesce(max(entry_id), 0) AS n "
                    "FROM audit_log")["n"]
        note(f"every action from here carries an audit id above {floor}")

        q = tom.get("/api/classify/queue?limit=2")
        groups = q.json() if q.status_code == 200 else []
        if len(groups) < 2:
            print("\nCOULD NOT RUN — fewer than two unjudged groups.",
                  file=sys.stderr)
            return 2
        a, b = groups[0], groups[1]
        a_abs = Decimal(str(a["abs_amount"]))
        a_net = Decimal(str(a["amount"]))

        def classify(group, pool, why):
            return lambda: tom.post("/api/classify/decide", json={
                "group_keys": [group["group_key"]], "pool": pool,
                "function_990": "MANAGEMENT_AND_GENERAL", "federal": "PENDING",
                "grade": "CORROBORATED", "rationale": why})

        s = turn("classify the largest group into G&A", "Tom",
                 classify(a, "G&A", "State machine: the first judgment."),
                 may_move={"decisions_live", "decisions_all",
                           "decision_lines_live", "classified", "unclassified",
                           "coverage_pct", "groups_decided", "pools",
                           "pool_gross", "audit"},
                 expect={"decisions_live": 1,
                         "classified": a_abs,
                         "pool_gross": a_net})

        s = turn("reclassify the same group into OVERHEAD", "Tom",
                 classify(a, "OVERHEAD", "State machine: the same cost, judged "
                                         "differently."),
                 # The judgment count rises (append-only) and one is reversed,
                 # so live stays at one. Coverage must not move at all: the
                 # same dollars are judged either way.
                 may_move={"decisions_all", "audit"},
                 expect={"decisions_live": 1,
                         "classified": a_abs,
                         "pool_gross": a_net,
                         "coverage_pct": s["coverage_pct"]})

        s = turn("classify a second group into G&A", "Tom",
                 classify(b, "G&A", "State machine: a second judgment, so the "
                                    "set has more than one thing in it."),
                 may_move={"decisions_live", "decisions_all",
                           "decision_lines_live", "classified", "unclassified",
                           "coverage_pct", "groups_decided", "pools",
                           "pool_gross", "audit"},
                 expect={"decisions_live": 2})

        heading("Still not possible, two judgments in")
        refused(tom, "POST", "/api/rates/compute",
                "a rate over an unsealed set, however much is classified",
                json={})

        s = turn("seal the decision set", "Tom",
                 lambda: tom.post("/api/rates/seal", json={
                     "sealed_by": "Tom Metzinger",
                     "note": "State machine: sealed so the rate phase can be "
                             "driven, and so the refusals after it can be."}),
                 may_move={"sets_open", "sets_sealed", "audit"},
                 expect={"sets_sealed": 1, "sets_open": 0})

        heading("What the seal changed about what is possible")
        refused(tom, "POST", "/api/classify/decide",
                "classifying into a sealed set",
                json={"group_keys": [a["group_key"]], "pool": "G&A",
                      "function_990": "PROGRAM", "federal": "PENDING",
                      "grade": "CORROBORATED", "rationale": "must be refused"})
        refused(tom, "POST", "/api/rates/seal",
                "sealing a set that is already sealed",
                json={"sealed_by": "Tom", "note": "again"})
        return after_the_seal(tom, heidi, auditor, initial, a, b, floor)
    finally:
        for c in (tom, heidi, auditor):
            c.close()


def after_the_seal(tom, heidi, auditor, initial: dict, a: dict, b: dict,
                   floor: int) -> int:
    """The half of the machine that only exists once a set is sealed."""
    from app.db import one

    heading("The rate phase, which the seal unlocked")

    s = turn("compute the rate", "Tom",
             lambda: tom.post("/api/rates/compute", json={
                 "note": "State machine: computed over the sealed set."}),
             may_move={"rates_live", "rates_all", "allocations", "audit"})

    if s["rates_live"]:
        ok(f"{s['rates_live']} rate(s) on file, each carrying the seal")
    else:
        note("no rate was produced — the pools may not reconcile, which is a "
             "409 rather than a rate and is the system working")

    heading("Unsealing, and what it takes with it")

    s = turn("unseal, with a reason", "Tom",
             lambda: tom.post("/api/rates/unseal?reason=State+machine:+"
                              "unsealed+to+prove+the+rate+is+superseded+"
                              "rather+than+left+standing"),
             may_move={"sets_open", "sets_sealed", "rates_live", "audit"},
             expect={"sets_sealed": 0, "sets_open": 1})

    # The point of unsealing: a rate computed over judgments that can now
    # change must not still be presented as the rate on file.
    if s["rates_all"] and s["rates_live"]:
        finding("unsealing left a rate live. A rate carries the seal of the "
                "judgments under it; if those can now change, the rate is "
                "superseded or the seal means nothing.")
    elif s["rates_all"]:
        ok("unsealing superseded every rate — none is presented as current")
    else:
        note("there was no rate to supersede")

    if s["rates_all"] != initial["rates_all"] and s["rates_all"] > 0:
        ok(f"and the superseded rate is still on the record "
           f"({s['rates_all']} in total) — supersede, never delete")

    heading("What unsealing put back within reach")
    s = turn("reclassify now that the set is open again", "Tom",
             lambda: tom.post("/api/classify/decide", json={
                 "group_keys": [a["group_key"]], "pool": "FRINGE",
                 "function_990": "MANAGEMENT_AND_GENERAL", "federal": "PENDING",
                 "grade": "CORROBORATED",
                 "rationale": "State machine: the judgment unsealing allows."}),
             may_move={"decisions_all", "pools", "pool_gross", "audit"},
             expect={"decisions_live": 2})

    heading("Walking the whole thing back")
    return reset(tom, initial, floor)


def reset(tom, initial: dict, floor: int) -> int:
    """Undo everything, then compare to where it started, field by field.

    Not everything is reversible, and that is a design decision rather than a
    gap: a computed rate supersedes, it does not vanish, because a workpaper
    that cited it has to keep resolving. So the comparison names what is
    deliberately one-way instead of failing on it.
    """
    from app.db import one

    from app.db import query

    walked, stuck = 0, []
    for _ in range(60):
        rows = query("""SELECT entry_id, label FROM v_undoable
                         WHERE entry_id > %s AND reversible_action
                           AND NOT already_undone
                         ORDER BY occurred_at DESC LIMIT 1""", (floor,))
        if not rows:
            break
        entry = rows[0]
        r = tom.post("/api/undo", json={
            "entry_ids": [entry["entry_id"]],
            "reason": "State machine: walking the sequence back to prove the "
                      "system returns to where it started."})
        if r.status_code >= 400:
            # An undo that walks nothing back answers 409 now. It used to
            # answer 200 with an empty list, which is how a loop counted
            # forty successes over one actual undo.
            stuck.append(f"{entry['label']} ({entry['entry_id']}): "
                         f"{r.text[:110]}")
            break
        walked += 1

    left = query("""SELECT count(*) AS n FROM v_undoable
                     WHERE entry_id > %s AND reversible_action
                       AND NOT already_undone""", (floor,))[0]["n"]
    settled = query("""SELECT count(*) AS n FROM v_undoable
                        WHERE entry_id > %s AND reversible_action
                          AND already_undone""", (floor,))[0]["n"]

    ok(f"walked back {walked} action(s) through the real undo route")
    note(f"{settled} entry/entries needed no walking back — already settled "
         f"by another route")
    if stuck:
        for why in stuck:
            finding(f"the undo trail jammed on {why}")
    elif left:
        finding(f"{left} reversible action(s) left unwalked with no refusal")
    else:
        ok("nothing of this drive's own actions remains to be walked back")

    final = snapshot()
    if check_invariants("after the reset") == 0:
        ok(f"all {len(INVARIANTS)} invariants still hold")

    #: Append-only by design. A trail that shrank when somebody undid
    #: something would be a trail you could erase, which is the opposite of
    #: what it is for.
    ONE_WAY = {
        "audit": "the audit trail is append-only — an undo is another entry",
        "refusals": "refusals are a record of what was tried, not of state",
        "decisions_all": "decisions are appended and reversed, never removed",
        "rates_all": "a rate supersedes, it does not vanish — a workpaper "
                     "that cited it has to keep resolving",
        "restatements": "a restatement is superseded, not deleted",
        "allocations": "an allocation belongs to a rate and supersedes with "
                       "it — deleting one would break a workpaper that cited "
                       "the rate",
    }

    heading("Where it landed, against where it started")
    drifted = []
    for key in sorted(initial):
        if str(initial[key]) == str(final[key]):
            continue
        if key in ONE_WAY:
            note(f"{key}: {initial[key]} -> {final[key]} — {ONE_WAY[key]}")
            continue
        drifted.append(key)
        finding(f"{key} did not come back: {initial[key]} -> {final[key]}")

    restored = [k for k in initial if str(initial[k]) == str(final[k])]
    if not drifted:
        ok(f"{len(restored)} of {len(initial)} observations are exactly where "
           f"they started; the rest are append-only by design")

    # "One-way by design" is a claim, so it is checked rather than asserted.
    # Every allocation left behind must belong to a rate that is superseded;
    # one hanging off a live rate would be a stale figure presented as
    # current, which is the trap v_rate_buildup already fell into once.
    from app.db import one as _one
    stale = _one("""SELECT count(*) AS n FROM allocation a
                      JOIN rate r USING (rate_id)
                     WHERE r.status <> 'SUPERSEDED'""")["n"]
    if final["allocations"] and stale:
        finding(f"{stale} allocation(s) belong to a rate that is not "
                f"superseded, after every rate was superseded")
    elif final["allocations"]:
        ok(f"all {final['allocations']} allocation(s) left behind belong to "
           f"superseded rates — none is presented as current")

    # The figures that matter most, stated rather than left to the loop.
    for key in ("classified", "unclassified", "coverage_pct", "pool_gross",
                "decisions_live", "decision_lines_live", "sets_sealed",
                "rates_live"):
        if str(initial[key]) == str(final[key]):
            ok(f"{key} is back to {initial[key]}")
        else:
            finding(f"{key} is {final[key]}, started at {initial[key]}")

    print(f"\n{'PASS' if not FINDINGS else 'FAIL'} — {TURN} turns, "
          f"{CHECKS} checks"
          + (f", {len(FINDINGS)} finding(s)" if FINDINGS else
             ", every turn moved what it should and the reset landed home"))
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    sys.exit(main())
