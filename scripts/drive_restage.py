#!/usr/bin/env python3
"""Restaging 2025: a working position, a note, a recommendation, an adoption.

    YBI_SEED_PASSWORD=... python3 scripts/drive_restage.py [--base URL]

The 757 judgments on the 2025 record were written by
`scripts/classification_log.py --apply` in six seconds under the controller's
credentials. `083` gave the schema a word for that — MACHINE_PROPOSAL — and
this drives the loop that word exists for, as the four people who walk it:

    the auditor reads the record, writes a note, recommends a reclassification
    Heidi writes a working note, which the auditor is not shown and is told of
    Tom sees both on his review list, with the proposal beside what is there
    Tom adopts a working position          -> and the rate does not move
    Tom declines a recommendation          -> with a reason, on the record
    Tom accepts one                        -> refused by the seal, in its words

Nine properties are asserted, and three are the ones this could plausibly get
wrong:

  * **adopting moves nothing.** A confirmation is a row in its own table
    and touches no judgment, so 757 adoptions leave the seal reproducing
    and the rate exactly where it was. If that were false the rate would
    depend on who had got round to reviewing.
  * **a working note is undisclosed and never concealed.** The auditor does
    not get the body and *does* get the count, on the same answer.
  * **accepting a recommendation goes through the one door.** Under a seal it
    is refused by the seal, in the seal's own words, because there is no
    second path to the cost record for an auditor's ask to travel down.

Leaves the record as it found it, against a census taken before it starts.
Exit 0 is a pass. Exit 1 is a finding. Exit 2 means it could not run.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, one, open_pool, query             # noqa: E402
from app.foundation import EMAIL                              # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []


def ok(what: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  \033[32mok\033[0m       {what}", flush=True)


def bad(what: str) -> None:
    global CHECKS
    CHECKS += 1
    FINDINGS.append(what)
    print(f"  \033[31mFINDING\033[0m  {what}", flush=True)


def note(what: str) -> None:
    print(f"  \033[33m·\033[0m        {what}", flush=True)


def head(what: str) -> None:
    print(f"\n\033[1m{what}\033[0m", flush=True)


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    """Sign in, and choose an own password where the account is still on one
    somebody else issued.

    Not a convenience. `refuse_issued_password` stops an account on an issued
    credential writing anything at all, so a drive that skipped this would
    report every write in it as a 403 and look like a permissions defect. The
    one exit from that state is changing your own password, which is what a
    real person does on their first morning.
    """
    c = httpx.Client(base_url=base, timeout=300)
    own = password.rstrip("!") + "-own!"
    # The own password first, because a second run of this drive meets the
    # accounts it left behind. A drive that only worked the first time is one
    # nobody can re-run on the day something breaks.
    for candidate in (own, password):
        r = c.post("/api/auth/login",
                   json={"email": email, "password": candidate})
        if r.status_code == 200:
            break
    else:
        print(f"could not sign in as {email}: {r.status_code} {r.text[:160]}",
              file=sys.stderr)
        raise SystemExit(2)
    if r.json().get("must_set_password"):
        ch = c.post("/api/auth/password",
                    json={"current_password": candidate, "new_password": own})
        if ch.status_code != 200:
            print(f"{email} could not set an own password: {ch.status_code} "
                  f"{ch.text[:160]}", file=sys.stderr)
            raise SystemExit(2)
        c.post("/api/auth/login", json={"email": email, "password": own})
    return c


def rates(period: str) -> dict[str, Decimal]:
    return {r["kind"]: Decimal(str(r["rate"]))
            for r in query("""SELECT kind, rate FROM rate
                               WHERE period = %s AND status <> 'SUPERSEDED'""",
                           (period,))}


def seal_of(period: str) -> str | None:
    r = one("""SELECT seal_hash FROM decision_set
                WHERE period = %s AND seal_hash IS NOT NULL
                ORDER BY sealed_at DESC LIMIT 1""", (period,))
    return r["seal_hash"] if r else None


def census(period: str) -> dict:
    return {
        "notes": one("SELECT count(*) AS n FROM classification_note")["n"],
        "recs": one("SELECT count(*) AS n FROM reclass_recommendation")["n"],
        "confs": one("SELECT count(*) AS n FROM position_confirmation")["n"],
        "decisions": one("SELECT count(*) AS n FROM decision "
                         "WHERE reversed_at IS NULL")["n"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("YBI_BASE",
                                                "http://127.0.0.1:8000"))
    ap.add_argument("--period", default="2025")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is required.", file=sys.stderr)
        return 2

    open_pool()
    period = args.period
    base = args.base
    tom = sign_in(base, EMAIL["tom"], pw)
    auditor = sign_in(base, "auditor@ybi.org", pw)
    heidi = sign_in(base, "hruby@ybi.org", pw)

    # Anything this drive left behind on a previous run is cleared first, and
    # said out loud. A drive that only works once is one nobody re-runs on the
    # day something breaks — and silently tolerating its own residue is how a
    # drive stops measuring the system and starts measuring its own state.
    stale = one("""SELECT count(*) AS n FROM reclass_recommendation
                    WHERE disposition = 'OPEN'""")["n"]
    if stale:
        execute("DELETE FROM reclass_recommendation WHERE disposition = 'OPEN'")
        print(f"  cleared {stale} open recommendation(s) from an earlier run")

    before = census(period)
    rates_before = rates(period)
    seal_before = seal_of(period)

    # ── where the year stands ────────────────────────────────────────────
    head("The year, as restaged")
    r = tom.get("/api/positions", params={"period": period, "state": "unadopted",
                                          "limit": 1})
    if r.status_code != 200:
        bad(f"/api/positions answered {r.status_code}")
        return 1
    unadopted = r.json()["total"]
    total = tom.get("/api/positions",
                    params={"period": period, "limit": 1}).json()["total"]
    if unadopted == 0:
        note("nothing is a working position — this drive has nothing to walk. "
             "It runs against a record the classification log has written.")
        return 2
    ok(f"{unadopted} of {total} groups are working positions nobody has adopted")

    w = one("""SELECT state, detail FROM v_audit_walk
                WHERE period = %s AND key = 'CLASSIFY'""", (period,))
    if w["state"] == "OPEN" and "not yet a judgment" in w["detail"]:
        ok("the walk's CLASSIFY step reads OPEN and says why")
    else:
        bad(f"the walk calls CLASSIFY {w['state']}: {w['detail'][:90]}")

    # a group to work on: the first unadopted one, read from the record
    pos = tom.get("/api/positions", params={"period": period,
                                            "state": "unadopted",
                                            "limit": 1}).json()["positions"][0]
    did = pos["decision_id"]
    note(f"working on {pos['account'][:60]} — currently {pos['pool']}")
    _n = one("""SELECT record_notes, working_notes
                  FROM v_classification_standing WHERE decision_id = %s""",
             (did,))
    notes_before = (_n["record_notes"], _n["working_notes"])

    # ── the auditor reads, notes and recommends ──────────────────────────
    head("The auditor, who holds no portfolio")
    r = auditor.post("/api/positions/notes", params={"period": period},
                     json={"decision_id": did, "kind": "RECORD",
                           "body": "Reviewed against the general ledger. The "
                                   "supporting schedule was not in the file."})
    if r.status_code == 200:
        ok("the auditor may write a note on the cost record")
    else:
        bad(f"the auditor's note answered {r.status_code}: {r.text[:120]}")

    proposed = "G&A" if pos["pool"] != "G&A" else "OVERHEAD"
    r = auditor.post("/api/positions/recommend", params={"period": period},
                     json={"decision_id": did, "pool": proposed,
                           "function_990": "MANAGEMENT_AND_GENERAL",
                           "federal": "ALLOWABLE",
                           "note": "This reads as general administration "
                                   "rather than the pool it sits in."})
    if r.status_code != 200:
        bad(f"the auditor's recommendation answered {r.status_code}: "
            f"{r.text[:140]}")
        return 1
    rec_id = r.json()["rec_id"]
    ok(f"the auditor recommends {proposed}, and nothing on the record moved")

    if rates(period) == rates_before:
        ok("a recommendation raises work and never a number")
    else:
        bad("the rate moved when somebody recommended something")

    # the same person, the same group, twice
    r = auditor.post("/api/positions/recommend", params={"period": period},
                     json={"decision_id": did, "pool": proposed,
                           "function_990": "MANAGEMENT_AND_GENERAL",
                           "federal": "ALLOWABLE",
                           "note": "Saying the same thing a second time."})
    if r.status_code == 409:
        ok("one open recommendation per person per group")
    else:
        bad(f"a second recommendation from the same person answered "
            f"{r.status_code}")

    # ── a working note, and what the auditor is told about it ────────────
    head("A working note")
    r = heidi.post("/api/positions/notes", params={"period": period},
                   json={"decision_id": did, "kind": "WORKING",
                         "body": "Ask Tom whether the 2019 memo still governs "
                                 "this before we answer the auditor."})
    if r.status_code != 200:
        bad(f"Heidi's working note answered {r.status_code}: {r.text[:120]}")
        return 1
    ok("Heidi writes a deliberative note")

    seen = auditor.get("/api/positions/notes",
                       params={"period": period,
                               "decision_id": did}).json()
    working = [n for n in seen["notes"] if n["kind"] == "WORKING"]
    # Measured as a delta, not an absolute: a note cannot be deleted, so a
    # second run of this drive meets the notes the first one left. A check
    # that only passes on a virgin record is one nobody runs twice.
    if working and all(n["body"] is None and n["withheld"] for n in working) \
            and seen["withheld"] == len(working):
        ok(f"the auditor is told {len(working)} working note(s) exist and is "
           f"shown none of them")
    else:
        bad(f"the auditor saw {len(working)} working note(s), withheld="
            f"{seen['withheld']}, body={working[0]['body'] if working else '—'}")

    mine = heidi.get("/api/positions/notes",
                     params={"period": period, "decision_id": did}).json()
    if all(n["body"] for n in mine["notes"]):
        ok("Heidi reads her own note and the auditor's")
    else:
        bad("Heidi cannot read a note she wrote")

    st = one("""SELECT record_notes, working_notes FROM v_classification_standing
                 WHERE decision_id = %s""", (did,))
    if (st["record_notes"] - notes_before[0],
            st["working_notes"] - notes_before[1]) == (1, 1):
        ok("the count of each kind is on the standing view, for every reader")
    else:
        bad(f"the standing view counts {st['record_notes']} record and "
            f"{st['working_notes']} working notes, against "
            f"{notes_before} before")

    # ── Tom's list ───────────────────────────────────────────────────────
    head("Tom's review list")
    rv = tom.get("/api/positions/review", params={"period": period}).json()
    mine_rec = [x for x in rv["recommendations"] if x["item_id"] == rec_id]
    if len(mine_rec) == 1:
        rec = mine_rec[0]
        if rec["proposed_pool"] == proposed and rec["current_pool"] == pos["pool"] \
                and rec["raised_by"] == "Engagement Auditor" and rec["still_agrees"]:
            ok("the proposal, what is there now, and who raised it, on one row")
        else:
            bad(f"the review row reads {rec['proposed_pool']} over "
                f"{rec['current_pool']} raised by {rec['raised_by']}")
    else:
        bad("the recommendation is not on the controller's list")

    if len(rv["unconfirmed"]) == unadopted:
        ok(f"and {len(rv['unconfirmed'])} working positions to adopt")
    else:
        bad(f"the list shows {len(rv['unconfirmed'])} unconfirmed, the view "
            f"says {unadopted}")

    # ── adopting moves nothing ───────────────────────────────────────────
    head("Adopting a working position")
    other = [p for p in tom.get("/api/positions",
                                params={"period": period, "state": "unadopted",
                                        "limit": 3}).json()["positions"]
             if p["decision_id"] != did][0]
    r = tom.post("/api/positions/confirm", params={"period": period},
                 json={"decision_ids": [other["decision_id"]],
                       "note": "Read the lines. This is mine."})
    if r.status_code == 200 and r.json()["confirmed"] == 1:
        ok("Tom adopts a working position, inside a sealed set")
    else:
        bad(f"adopting answered {r.status_code}: {r.text[:140]}")

    if seal_of(period) == seal_before:
        ok("the seal is untouched — adopting is outside what it hashes")
    else:
        bad("the seal moved when a position was adopted")
    if rates(period) == rates_before:
        ok("and the rate is exactly where it was")
    else:
        bad(f"the rate moved: {rates_before} -> {rates(period)}")

    st2 = one("""SELECT adopted, confirmed_by, origin
                   FROM v_classification_standing WHERE decision_id = %s""",
              (other["decision_id"],))
    if st2["adopted"] and st2["confirmed_by"] == "Tom Metzinger" \
            and st2["origin"] == "MACHINE_PROPOSAL":
        ok("it reads adopted, by name — and still says a script proposed it")
    else:
        bad(f"adopted={st2['adopted']} by={st2['confirmed_by']} "
            f"origin={st2['origin']}")

    r = tom.post("/api/positions/confirm", params={"period": period},
                 json={"decision_ids": [other["decision_id"]], "note": ""})
    if r.status_code == 409:
        ok("adopting it twice is a refusal, not a second signature")
    else:
        bad(f"a second adoption answered {r.status_code}")

    # ── accepting, under a seal ──────────────────────────────────────────
    head("Accepting the auditor's recommendation")
    r = tom.post(f"/api/positions/recommendations/{rec_id}/accept",
                 params={"period": period},
                 json={"rationale": "The auditor is right; this is "
                                    "administration.", "reason": ""})
    body = r.text.lower()
    if r.status_code in (409, 422) and "seal" in body:
        ok("refused by the seal, in the seal's words — there is one door")
    elif r.status_code == 200:
        bad("a sealed judgment was replaced without anybody unsealing")
    else:
        bad(f"accepting answered {r.status_code}: {r.text[:160]}")

    still = one("""SELECT disposition FROM reclass_recommendation
                    WHERE rec_id = %s""", (rec_id,))["disposition"]
    if still == "OPEN":
        ok("and the recommendation is still open, so nobody has to remember it")
    else:
        bad(f"the refused recommendation is {still}")

    # ── declining says why ───────────────────────────────────────────────
    head("Declining")
    r = tom.post(f"/api/positions/recommendations/{rec_id}/decline",
                 params={"period": period}, json={"reason": "short"})
    if r.status_code == 422:
        ok("a refusal with no reason is refused")
    else:
        bad(f"a twelve-character floor let 'short' through: {r.status_code}")

    r = tom.post(f"/api/positions/recommendations/{rec_id}/decline",
                 params={"period": period},
                 json={"reason": "Occupancy cost. The carve-out takes the "
                                 "tenant share at rate time, not here."})
    if r.status_code == 200:
        ok("declined, with the reason on the record")
    else:
        bad(f"declining answered {r.status_code}: {r.text[:140]}")

    for action in ("RECLASS_RECOMMEND", "RECLASS_DECLINE",
                   "POSITION_CONFIRM", "CLASSIFICATION_NOTE"):
        n = one("""SELECT count(*) AS n FROM audit_log
                    WHERE action = %s AND actor_id IS NOT NULL
                      AND session_id IS NOT NULL""", (action,))["n"]
        if n:
            ok(f"{action} names an account and a session")
        else:
            bad(f"{action} is on no audit row with an account and a session")

    # ── put it back ──────────────────────────────────────────────────────
    head("Leaving the record as it was found")
    tom.post("/api/positions/confirm/withdraw", params={"period": period},
             json={"decision_id": other["decision_id"],
                   "reason": "Drive cleanup; this adoption was not Tom's."})
    # Every statement is attempted and a failure is printed rather than
    # raised: a cleanup that stops at the first refusal leaves more behind
    # than one that never ran. `drive_contracts` learned that against
    # `invoice_no_delete`.
    for sql, arg in (
            ("DELETE FROM position_confirmation WHERE decision_id = %s",
             other["decision_id"]),
            ("DELETE FROM reclass_recommendation WHERE rec_id = %s", rec_id)):
        try:
            execute(sql, (arg,))
        except Exception as e:                                # noqa: BLE001
            note(f"could not clean up: {e}")
    # A note is never deleted — the trigger says so and it is right. The drive
    # says what it left rather than working round its own guarantee, which is
    # `invoice_no_delete`'s lesson in a third place.
    after = census(period)
    residue = {k: after[k] - before[k] for k in after if after[k] != before[k]}
    note(f"{residue.get('notes', 0)} note(s) left on the record: a note is not "
         f"deletable, by design, and a drive that routed round that would be "
         f"testing a system it had just disabled")
    stray = {k: v for k, v in residue.items() if k != "notes"}
    if stray:
        bad(f"left behind: {stray}")
    else:
        ok("nothing else is left behind — confirmations and recommendations "
           "are gone")
    if after["decisions"] == before["decisions"]:
        ok("no judgment was created or reversed by any of this")
    else:
        bad(f"live decisions went {before['decisions']} -> {after['decisions']}")
    if rates(period) == rates_before and seal_of(period) == seal_before:
        ok("the rate and the seal are as they were found")
    else:
        bad("the rate or the seal moved across the whole drive")

    head(f"{CHECKS} checks, {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"  - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
