#!/usr/bin/env python3
"""Heidi measures, Tom verifies, and the carve-out fires for the first time.

    YBI_SEED_PASSWORD=... python3 scripts/drive_partitions.py [--base URL]

Two partitions have reported NO DATA for the life of the system: **no building
carries square footage**, so the 2 CFR 200.465 facilities carve-out — the
single largest adjustment in the rate model — cannot fire at all and every
dollar of tenant and vacant occupancy cost sits in the federal pool; and **no
asset carries a funding source**, so 200.436(b) cannot be answered on $850,383
of depreciation.

Heidi holds FACILITIES and INVENTORY and is who goes and measures. Tom signs
the rate those measurements feed. So this walks the loop `084` built:

    Heidi proposes a building, and the rooms in it, in one sitting
    every rule the register enforces is enforced on the proposal
    Tom sees them on one list, a building above the rooms inside it
    Tom accepts                 -> the rows are written through the real routes
    the space accounts for itself, the walk's SPACE step moves off NO DATA
    recompute                   -> the carve-out fires, and the rate moves

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

from app.db import execute, one, open_pool, query                 # noqa: E402
from app.foundation import EMAIL                                  # noqa: E402

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
    """Sign in, choosing an own password where the account is still on the
    organisation's — `refuse_issued_password` stops an issued credential
    writing anything, so a drive that skipped this would report every write as
    a 403 and look like a permissions defect."""
    c = httpx.Client(base_url=base, timeout=300)
    own = password.rstrip("!") + "-own!"
    for candidate in (own, password):
        r = c.post("/api/auth/login", json={"email": email, "password": candidate})
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
            print(f"{email} could not set an own password: {ch.status_code}",
                  file=sys.stderr)
            raise SystemExit(2)
        c.post("/api/auth/login", json={"email": email, "password": own})
    return c


def rates(period: str) -> dict[str, Decimal]:
    return {r["kind"]: Decimal(str(r["rate"]))
            for r in query("""SELECT kind, rate FROM rate
                               WHERE period = %s AND status <> 'SUPERSEDED'""",
                           (period,))}


def admin_basis(period: str) -> str:
    """The basis the rate on file was computed under.

    Hard-coding POOL here restored a record that was on OBJECTIVE as
    43.99% — nine points of combined rate, chosen by a drive rather than
    by anybody, and invisible on a reference record that happened to be on
    POOL already. `read the record, never recall it`, pointed at a policy
    this drive has no business choosing. Where there is no rate yet the
    default is the schema's.
    """
    r = one("""SELECT admin_labour_basis FROM rate
                WHERE period = %s AND status <> 'SUPERSEDED'
                ORDER BY computed_at DESC LIMIT 1""", (period,))
    return r["admin_labour_basis"] if r else "OBJECTIVE"


def walk_state(period: str, key: str) -> str:
    r = one("SELECT state FROM v_audit_walk WHERE period = %s AND key = %s",
            (period, key))
    return r["state"] if r else "—"


FACILITY = "DRIVE-TB"
UNITS = [
    ("DRIVE-TB-1", "Tenant suites", 2000, "TENANT", "OCCUPIED", "", "A tenant"),
    ("DRIVE-TB-2", "Shared lab", 1400, "SHARED_LAB", "INTERNAL", "", ""),
    ("DRIVE-TB-3", "Offices", 1000, "ADMINISTRATIVE", "INTERNAL", "", ""),
    ("DRIVE-TB-4", "Vacant floor", 1000, "VACANT", "VACANT", "", ""),
]
WHY = ("Measured off the floor plan the drive carries; this row exists to be "
       "taken down again at the end of the run.")


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
    period, base = args.period, args.base
    tom = sign_in(base, EMAIL["tom"], pw)
    heidi = sign_in(base, "hruby@ybi.org", pw)
    P = {"period": period}

    if one("SELECT 1 FROM facility WHERE facility_id = %s", (FACILITY,)):
        note("clearing what an earlier run left behind")
        execute("DELETE FROM space_unit WHERE facility_id = %s", (FACILITY,))
        execute("DELETE FROM facility WHERE facility_id = %s", (FACILITY,))
    execute("DELETE FROM recommendation WHERE subject_id LIKE 'DRIVE-TB%'")

    before_rates = rates(period)
    before_basis = admin_basis(period)
    before_space = walk_state(period, "SPACE")
    buildings_before = one("SELECT count(*) AS n FROM facility "
                           "WHERE period = %s", (period,))["n"]

    # ── every rule the register has, on the way in ───────────────────────
    head("What a proposal is refused for")
    for label, body, expect in [
        ("a building with no square footage",
         {"subject": "FACILITY", "subject_id": "DRIVE-X",
          "proposal": {"name": "Unmeasured"}, "note": WHY}, "carve-out"),
        ("federal money with no award named",
         {"subject": "ASSET_FUNDING", "subject_id": "DRIVE-A",
          "proposal": {"kind": "FEDERAL", "amount": 1000}, "note": WHY},
         "200.313"),
        ("a space use the register does not have",
         {"subject": "SPACE_UNIT", "subject_id": "DRIVE-X-1",
          "proposal": {"facility_id": FACILITY, "label": "X", "usable_sqft": 10,
                       "use": "BASEMENT", "status": "VACANT"}, "note": WHY},
         "is not a space use"),
    ]:
        r = heidi.post("/api/positions/recommend", params=P, json=body)
        text = r.text.lower()
        if r.status_code in (409, 422) and expect.lower() in text:
            ok(f"{label} — refused, and the refusal names the rule")
        elif r.status_code == 500:
            bad(f"{label} answered 500: a refusal reaching a person as a fault")
        else:
            bad(f"{label} answered {r.status_code}: {r.text[:120]}")

    # ── the building and its rooms, in one sitting ───────────────────────
    head("Heidi measures")
    r = heidi.post("/api/positions/recommend", params=P, json={
        "subject": "FACILITY", "subject_id": FACILITY,
        "proposal": {"name": "Drive Tech Block", "usable_sqft": 5400,
                     "owned": True},
        "note": WHY})
    if r.status_code != 200:
        bad(f"proposing a building answered {r.status_code}: {r.text[:140]}")
        return 1
    if r.json()["is_new"]:
        ok("a building nobody has recorded — the proposal says it is new")
    else:
        bad("a building that is not on the record did not read as new")

    made = 0
    for uid, label, sq, use, status, obj, occ in UNITS:
        rr = heidi.post("/api/positions/recommend", params=P, json={
            "subject": "SPACE_UNIT", "subject_id": uid,
            "proposal": {"facility_id": FACILITY, "label": label,
                         "usable_sqft": sq, "use": use, "status": status,
                         "objective_id": obj, "occupant": occ},
            "note": WHY})
        made += rr.status_code == 200
    if made == len(UNITS):
        ok("and the rooms in it, against a building only proposed so far")
    else:
        bad(f"{made} of {len(UNITS)} spaces were accepted onto the list")

    if rates(period) == before_rates:
        ok("nothing on the record has moved — a recommendation writes nothing")
    else:
        bad("the rate moved when somebody proposed a measurement")
    if one("SELECT count(*) AS n FROM facility WHERE period = %s",
           (period,))["n"] == buildings_before:
        ok("and no building was created by proposing one")
    else:
        bad("proposing a building created one")

    # ── Tom's list ───────────────────────────────────────────────────────
    head("Tom verifies")
    rv = tom.get("/api/positions/review", params=P).json()
    mine = [x for x in rv["recommendations"]
            if x["subject_id"] == FACILITY or x["subject_id"].startswith("DRIVE-TB-")]
    if len(mine) == 5:
        ok("all five are on the controller's one list")
    else:
        bad(f"{len(mine)} of 5 reached the controller's list")
    if mine and mine[0]["subject"] == "FACILITY":
        ok("the building sorts above the rooms in it, which is the order they "
           "have to be accepted in")
    else:
        bad("the list offers a room before the building it is in")
    if all(x["is_new"] for x in mine):
        ok("every one reads as not on the record — which is the normal case "
           "here, not an edge")
    else:
        bad("a proposal for a row that does not exist did not say so")

    for rec in mine:
        rr = tom.post(f"/api/positions/recommendations/{rec['item_id']}/accept",
                      params=P, json={"rationale": WHY})
        if rr.status_code != 200:
            bad(f"accepting {rec['subject_id']} answered {rr.status_code}: "
                f"{rr.text[:120]}")
            return 1
    ok("accepted, each through the route that owns its register")

    ctl = one("""SELECT ties, variance, units FROM v_space_unit_control
                  WHERE facility_id = %s""", (FACILITY,))
    if ctl and ctl["ties"] and ctl["units"] == len(UNITS):
        ok(f"the space accounts for itself — {ctl['units']} units, variance "
           f"{ctl['variance']}")
    else:
        bad(f"the building does not add up: {ctl}")

    if walk_state(period, "SPACE") == "DONE" and before_space == "NO DATA":
        ok("the walk's SPACE step moves NO DATA -> DONE")
    else:
        note(f"the walk's SPACE step reads {walk_state(period, 'SPACE')} "
             f"(it was {before_space})")

    # ── the other partition ──────────────────────────────────────────────
    head("And who paid for each asset")
    reg = one("""SELECT count(*) AS assets,
                        count(*) FILTER (WHERE NOT EXISTS (
                            SELECT 1 FROM asset_funding f
                             WHERE f.asset_id = a.asset_id)) AS unanswered
                   FROM asset a WHERE a.period = %s""", (period,))
    if reg["assets"] == 0:
        note("the asset register is empty, so there is nothing to answer for. "
             "`scripts/load_assets.py` loads it from the schedule YBI already "
             "holds; the funding column is what this half is about.")
    else:
        ok(f"{reg['assets']} assets on the register, {reg['unanswered']} with "
           f"no funding source — 200.313(d)(1) unanswered")
        part = one("""SELECT covered, whole, parts_done, parts, needs
                        FROM v_partition_coverage
                       WHERE period = %s AND partition = 'ASSETS'""", (period,))
        # The partition read `gross_cost - funding_unknown` — dollars minus a
        # count — so a loaded register reported 100% answered over a register
        # where nothing was. It cannot exceed the cost of what is answered.
        answered_cost = one("""SELECT COALESCE(sum(a.gross_cost), 0) AS c
                                 FROM asset a
                                WHERE a.period = %s
                                  AND EXISTS (SELECT 1 FROM asset_funding f
                                               WHERE f.asset_id = a.asset_id)""",
                            (period,))["c"]
        if Decimal(str(part["covered"])) == Decimal(str(answered_cost)):
            ok("the partition counts the cost of the assets somebody has "
               "answered for, in dollars")
        else:
            bad(f"the partition reports {part['covered']} covered where the "
                f"answered assets cost {answered_cost}")
        if part["parts_done"] < part["parts"] and (part["needs"] or "").strip():
            ok("and OPEN says what it needs")
        elif part["parts_done"] < part["parts"]:
            bad("the asset partition is OPEN and does not say what it needs")

        target = one("""SELECT a.asset_id, a.description, a.gross_cost
                          FROM asset a WHERE a.period = %s
                           AND NOT EXISTS (SELECT 1 FROM asset_funding f
                                            WHERE f.asset_id = a.asset_id)
                         ORDER BY a.gross_cost DESC LIMIT 1""", (period,))
        rr = heidi.post("/api/positions/recommend", params=P, json={
            "subject": "ASSET_FUNDING", "subject_id": target["asset_id"],
            "proposal": {"kind": "FEDERAL",
                         "amount": float(target["gross_cost"]),
                         "award_reference": "DRIVE-AWARD-1",
                         "funder": "A federal agency"},
            "note": WHY})
        if rr.status_code == 200:
            ok(f"Heidi answers the funding on {target['description'][:32]}")
            rec_id = rr.json()["rec_id"]
            ac = tom.post(f"/api/positions/recommendations/{rec_id}/accept",
                          params=P, json={"rationale": WHY})
            if ac.status_code == 200:
                ok("Tom accepts it, through the route that owns the register")
            else:
                bad(f"accepting the funding answered {ac.status_code}: "
                    f"{ac.text[:120]}")
            allow = one("""SELECT allowable_depreciation, depreciation
                             FROM v_asset_allowability WHERE asset_id = %s""",
                        (target["asset_id"],))
            if allow and Decimal(str(allow["allowable_depreciation"])) == 0 \
                    and Decimal(str(allow["depreciation"])) > 0:
                ok(f"and 200.436(b) fires: {allow['depreciation']} of "
                   f"depreciation, {allow['allowable_depreciation']} allowable")
            else:
                bad(f"a wholly federally funded asset still allows "
                    f"{allow['allowable_depreciation'] if allow else '—'}")
            execute("DELETE FROM asset_funding WHERE asset_id = %s",
                    (target["asset_id"],))
            execute("DELETE FROM recommendation WHERE rec_id = %s", (rec_id,))
        else:
            bad(f"proposing a funding source answered {rr.status_code}: "
                f"{rr.text[:140]}")

    # ── and the carve-out, which has never fired ─────────────────────────
    head("The carve-out")
    occ = one("SELECT tenant_sqft, vacant_sqft FROM v_facility_occupancy "
              "WHERE facility_id = %s", (FACILITY,))
    if occ:
        ok(f"v_facility_occupancy returns a row — {occ['tenant_sqft']} tenant "
           f"and {occ['vacant_sqft']} vacant square feet to carve")
    else:
        bad("no occupancy row, so the carve-out still cannot fire")

    r = tom.post("/api/rates/compute", params=P, json={"admin_labour": before_basis})
    if r.status_code != 200:
        note(f"the rate could not be recomputed ({r.status_code}); the "
             f"carve-out is proved by the occupancy row above")
    else:
        carved = one("SELECT COALESCE(sum(amount), 0) AS a FROM carve_out")["a"]
        after = rates(period)
        if Decimal(str(carved)) > 0:
            ok(f"a 200.465 carve-out is recorded: {carved}")
        else:
            bad("the rate recomputed and carved nothing out")
        if after.get("INDIRECT_COMBINED") != before_rates.get("INDIRECT_COMBINED"):
            ok(f"and the combined rate moves "
               f"{before_rates.get('INDIRECT_COMBINED')} -> "
               f"{after.get('INDIRECT_COMBINED')}")
        else:
            bad("the combined rate did not move on a carve-out")
        open_ties = query("""SELECT kind FROM v_rate_buildup
                              WHERE period = %s AND NOT ties""", (period,))
        if not open_ties:
            ok("every pool still ties to the ledger underneath it")
        else:
            bad(f"pools not tying after the carve-out: "
                f"{[x['kind'] for x in open_ties]}")

    # ── put it back ──────────────────────────────────────────────────────
    head("Leaving the record as it was found")
    for sql, arg in (("DELETE FROM space_unit WHERE facility_id = %s", FACILITY),
                     ("DELETE FROM facility WHERE facility_id = %s", FACILITY),
                     ("DELETE FROM recommendation WHERE subject_id LIKE %s",
                      "DRIVE-TB%")):
        try:
            execute(sql, (arg,))
        except Exception as e:                                # noqa: BLE001
            note(f"could not clean up: {e}")
    if one("SELECT count(*) AS n FROM facility WHERE period = %s",
           (period,))["n"] == buildings_before:
        ok("the building and its rooms are gone")
    else:
        bad("the drive left a building behind")

    # And the rate comes back, because **computing is arithmetic and sealing
    # is a judgment** — this drive may recompute over a set it did not seal.
    #
    # The first version left the carved rate standing and called that
    # deference. It is not: a second run then read 26.42% as its baseline,
    # added the same building, produced the same 26.42%, and reported *the
    # combined rate did not move on a carve-out* — a drive measuring its own
    # leftover and finding a fault in working code. `review_system` was fixed
    # for exactly this and I wrote it again one file away.
    r = tom.post("/api/rates/compute", params=P, json={"admin_labour": before_basis})
    if r.status_code == 200 and rates(period) == before_rates:
        ok("and the rate is back where it was found, over the same sealed set")
    elif r.status_code != 200:
        bad(f"the rate could not be restored ({r.status_code}): {r.text[:120]}")
    else:
        bad(f"the rate did not come back: {before_rates} -> {rates(period)}")

    head(f"{CHECKS} checks, {len(FINDINGS)} finding(s)")
    for f in FINDINGS:
        print(f"  - {f}")
    return 1 if FINDINGS else 0


if __name__ == "__main__":
    raise SystemExit(main())
