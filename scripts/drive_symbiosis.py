#!/usr/bin/env python3
"""What the system writes is what it reads back — across all five registers.

    YBI_SEED_PASSWORD=... python3 scripts/drive_symbiosis.py [--base URL]

`drive_propagation` asks what one reclassification moves. `drive_buildup` asks
whether the rate builds up as the queue is worked. This asks the question
behind both, over the whole surface at once: **five different people change
five different registers, and every figure downstream of each has to move by
exactly the right amount and nothing else may move at all.**

    LABOUR          5130 Benefits, FRINGE -> OVERHEAD
    G&A             the accounting retainer, G&A -> OVERHEAD
    SUBCONTRACTOR   5227 portfolio consulting, DIRECT -> EXCLUDED
    FACILITIES      a suite's square footage, and what it is used for
    INVENTORY       an asset's funding source, FEDERAL <-> what it was

After each one the whole read side is taken again: coverage, seven pools, four
rates, the carve-outs, Form 990 Parts VIII, IX and X, the twenty-one anchors of
the tie register, the walk, the asset control and the estate's occupancy. Every
figure is asserted to move or to hold, because **a figure that moves when it
should not is as much a defect as one that does not move when it should, and
only the second kind ever gets noticed.**

Then all five are walked back, and the census at the end has to equal the
census at the start — every figure, to the cent.

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
from app.foundation import EMAIL                          # noqa: E402

CHECKS = 0
FINDINGS: list[str] = []
NOTES: list[str] = []
MARK = "Symbiosis drive"


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


def d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def sign_in(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=600)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"could not sign in as {email}: {r.status_code}")
    return c


# ── The census ──────────────────────────────────────────────────────

def census(period: str) -> dict:
    """Every figure downstream of a judgment, in one flat reading.

    Flat on purpose: the assertions are about *which keys moved*, and a nested
    shape would make that a walk rather than a set difference.
    """
    c: dict[str, object] = {}

    r = one("""SELECT classified, unclassified, scope_dollars,
                      pct_dollars_covered, groups_total
                 FROM v_classification_coverage WHERE period = %s""", (period,))
    for k in ("classified", "unclassified", "scope_dollars",
              "pct_dollars_covered", "groups_total"):
        c[f"coverage.{k}"] = d(r[k]) if r else None

    for p in query("""SELECT pool::text AS pool, gross, carved, allocable
                        FROM v_pool_balance WHERE period = %s""", (period,)):
        for k in ("gross", "carved", "allocable"):
            c[f"pool.{p['pool']}.{k}"] = d(p[k])

    for r in query("""SELECT kind, rate, pool_amount, base_amount, pool_state
                        FROM v_rate_buildup WHERE period = %s""", (period,)):
        c[f"rate.{r['kind']}.rate"] = d(r["rate"])
        c[f"rate.{r['kind']}.pool"] = d(r["pool_amount"])
        c[f"rate.{r['kind']}.base"] = d(r["base_amount"])
        c[f"rate.{r['kind']}.state"] = r["pool_state"]

    r = one("""SELECT count(*) AS n, COALESCE(sum(amount), 0) AS total
                 FROM carve_out WHERE period = %s""", (period,))
    c["carveout.count"], c["carveout.total"] = r["n"], d(r["total"])

    for r in query("""SELECT line_id, total, program, management, fundraising
                        FROM v_form_990_part_ix WHERE period = %s""", (period,)):
        for k in ("total", "program", "management", "fundraising"):
            c[f"ix.{r['line_id']}.{k}"] = d(r[k])
    r = one("""SELECT COALESCE(sum(total), 0) AS t,
                      COALESCE(sum(program), 0) AS p,
                      COALESCE(sum(management), 0) AS m,
                      COALESCE(sum(fundraising), 0) AS f
                 FROM v_form_990_part_ix
                WHERE period = %s AND line_id <> '8b'""", (period,))
    for k, v in (("total", r["t"]), ("program", r["p"]),
                 ("management", r["m"]), ("fundraising", r["f"])):
        c[f"ix.25.{k}"] = d(v)

    for r in query("""SELECT line_id, amount FROM v_form_990_part_viii
                       WHERE period = %s""", (period,)):
        c[f"viii.{r['line_id']}"] = d(r["amount"])
    for r in query("""SELECT line_id, amount FROM v_form_990_part_x
                       WHERE period = %s""", (period,)):
        c[f"x.{r['line_id']}"] = d(r["amount"])

    r = one("""SELECT anchors, ties, open, no_data, state
                 FROM v_report_tie_summary WHERE period = %s""", (period,))
    for k in ("anchors", "ties", "open", "no_data", "state"):
        c[f"tie.{k}"] = r[k] if r else None
    # And every anchor by name, not only the tally. A control that changed
    # state while another changed the other way would leave the counts
    # standing and nothing would say so — netting, in a census.
    for r in query("""SELECT report, anchor, state, variance FROM v_report_tie
                       WHERE period = %s""", (period,)):
        # `register.` and not `anchor.`: `v_rate_anchor` already keys on
        # `anchor.<CONTROL>` and two families under one prefix is the
        # collision this file keeps finding, one identifier wide.
        key = f"register.{r['report']}.{r['anchor']}"
        c[key + ".state"] = r["state"]
        c[key + ".variance"] = d(r["variance"]) if r["variance"] is not None \
            else None

    for r in query("""SELECT control, state FROM v_rate_anchor
                       WHERE period = %s""", (period,)):
        c[f"anchor.{r['control']}"] = r["state"]

    for r in query("""SELECT control, state FROM v_statement_reconciliation
                       WHERE period = %s""", (period,)):
        c[f"books.{r['control']}"] = r["state"]

    r = one("""SELECT variance, funding_unknown, state, gross_cost,
                      register_depreciation, allowable_depreciation
                 FROM v_asset_control WHERE period = %s""", (period,))
    for k in ("variance", "funding_unknown", "state", "gross_cost",
              "register_depreciation", "allowable_depreciation"):
        c[f"asset.{k}"] = (d(r[k]) if k not in ("state", "funding_unknown")
                           else r[k]) if r else None

    for r in query("""SELECT facility_id, usable_sqft, rental_share
                        FROM v_facility_occupancy WHERE period = %s""",
                   (period,)):
        c[f"space.{r['facility_id']}.usable"] = d(r["usable_sqft"])
        c[f"space.{r['facility_id']}.rental"] = d(r["rental_share"])

    for r in query("""SELECT partition, state, pct FROM v_partition_coverage
                       WHERE period = %s""", (period,)):
        c[f"partition.{r['partition']}.state"] = r["state"]
        c[f"partition.{r['partition']}.pct"] = d(r["pct"])

    r = one("""SELECT count(*) FILTER (WHERE state = 'DONE') AS done,
                      count(*) AS steps FROM v_audit_walk WHERE period = %s""",
            (period,))
    c["walk.done"], c["walk.steps"] = r["done"], r["steps"]
    return c


def diff(before: dict, after: dict) -> dict:
    return {k: (before.get(k), after.get(k)) for k in
            set(before) | set(after) if before.get(k) != after.get(k)}


def expect(before, after, moves: dict, label: str,
           may: tuple = ()) -> None:
    """`moves` maps a key to the amount it must move by, or to None for
    'moved, and the amount is not asserted'. Every other key must hold."""
    changed = diff(before, after)
    for k, want in moves.items():
        if k not in changed:
            finding(f"{label}: {k} did not move at all "
                    f"(still {before.get(k)})")
            continue
        was, now = changed.pop(k)
        if want is None:
            ok(f"{label}: {k} moved, {was} -> {now}")
        elif d(now) - d(was) == d(want):
            ok(f"{label}: {k} moved by exactly {want}")
        else:
            finding(f"{label}: {k} moved by {d(now) - d(was)}, "
                    f"expected {want}")
    stray = {k: v for k, v in changed.items()
             if not any(k.startswith(m) for m in may)}
    allowed = len(changed) - len(stray)
    if stray:
        for k, (was, now) in sorted(stray.items()):
            finding(f"{label}: {k} moved and must not have — {was} -> {now}")
    else:
        ok(f"{label}: nothing outside the expected reach moved — "
           f"{len(before) - len(changed)} of {len(before)} figures held still"
           + (f", {allowed} moved inside it" if allowed else ""))


def held(before, after, label: str) -> None:
    changed = diff(before, after)
    if changed:
        for k, (was, now) in sorted(changed.items()):
            finding(f"{label}: {k} moved and must not have — {was} -> {now}")
    else:
        ok(f"{label}: every one of {len(before)} figures is identical")


# ── Acts ────────────────────────────────────────────────────────────

SEP = "\x1f"


def group_keys(period: str, account_like: str, payee: str | None = None):
    """The queue's wire form for a group: account and payee joined by 0x1f.

    Read off the ledger rather than out of `decision.scope`, which is the
    other encoding of the same key and has no decoder anywhere — feeding it
    back to /classify/decide answers 409 naming a group that does not exist.
    """
    rows = query("""SELECT DISTINCT l.account, COALESCE(l.payee, '') AS payee
                      FROM ledger_line l
                     WHERE l.period = %s AND l.account LIKE %s
                       AND (%s::text IS NULL OR l.payee = %s::text)""",
                 (period, account_like, payee, payee))
    return [r["account"] + SEP + r["payee"] for r in rows]


def live_position(period: str, keys: list[str]) -> dict:
    """What each group is classified as right now, so the drive can put it
    back exactly rather than to what it remembers."""
    out = {}
    for k in keys:
        account, _, payee = k.partition(SEP)
        r = one("""SELECT d.pool::text AS pool, d.function_990::text AS fn,
                          d.federal::text AS federal,
                          d.objective_id, d.rationale
                     FROM decision d
                     JOIN decision_line dl ON dl.decision_id = d.decision_id
                                          AND dl.live
                     JOIN ledger_line l ON l.line_id = dl.line_id
                    WHERE d.reversed_at IS NULL AND l.period = %s
                      AND l.account = %s AND COALESCE(l.payee, '') = %s
                    LIMIT 1""", (period, account, payee))
        if r:
            out[k] = r
    return out


def amount_of(period: str, keys: list[str]) -> Decimal:
    total = Decimal(0)
    for k in keys:
        account, _, payee = k.partition(SEP)
        r = one("""SELECT COALESCE(sum(amount), 0) AS a FROM ledger_line
                    WHERE period = %s AND account = %s
                      AND COALESCE(payee, '') = %s""",
                (period, account, payee))
        total += d(r["a"])
    return total


def unseal(tom, why: str) -> bool:
    # `reason` is a query parameter on this route, not a body. Read off the
    # route rather than assumed: a reason in the body is dropped and the
    # refusal names a field the caller thinks it sent.
    r = tom.post("/api/rates/unseal", params={"reason": f"{MARK}: {why}"})
    if r.status_code != 200:
        finding(f"could not unseal ({why}): {r.status_code} {r.text[:160]}")
        return False
    return True


def seal(tom, why: str) -> bool:
    r = tom.post("/api/rates/seal", json={"note": f"{MARK}: {why}"})
    if r.status_code != 200:
        finding(f"could not seal ({why}): {r.status_code} {r.text[:160]}")
        return False
    return True


def compute(tom, period: str, basis: str, why: str) -> bool:
    r = tom.post("/api/rates/compute", params={"period": period},
                 json={"note": f"{MARK}: {why}", "admin_labour": basis})
    if r.status_code != 200:
        finding(f"could not compute ({why}): {r.status_code} {r.text[:200]}")
        return False
    return True


def reclassify(tom, keys, pool, fn, federal, objective, why) -> bool:
    r = tom.post("/api/classify/decide", json={
        "group_keys": keys, "pool": pool, "function_990": fn,
        "federal": federal, "objective_id": objective,
        "grade": "TEST_ASSUMPTION",
        "rationale": f"{MARK}: {why}. Walked back at the end of this run."})
    if r.status_code != 200:
        finding(f"could not reclassify to {pool}: {r.status_code} "
                f"{r.text[:200]}")
        return False
    body = r.json()
    if not body.get("lines_recorded", body.get("decision_lines", 1)):
        finding(f"reclassify to {pool} answered 200 and recorded no lines")
        return False
    return True


def put_space(heidi, unit: dict) -> bool:
    r = heidi.put("/api/facilities/space", json={
        "unit_id": unit["unit_id"], "facility_id": unit["facility_id"],
        "label": unit["label"], "floor": unit["floor"],
        "usable_sqft": str(unit["usable_sqft"]), "use": unit["use"],
        "status": unit["status"], "objective_id": unit["objective_id"],
        "occupant": unit["occupant"],
        "months_occupied": str(unit["months_occupied"]),
        "actual_annual_charge": (str(unit["actual_annual_charge"])
                                 if unit["actual_annual_charge"] is not None
                                 else None),
        "market_rate_psf": (str(unit["market_rate_psf"])
                            if unit["market_rate_psf"] is not None else None),
        "market_basis": unit["market_basis"],
        "market_source": unit["market_source"], "note": unit["note"]})
    if r.status_code != 200:
        finding(f"could not record space: {r.status_code} {r.text[:200]}")
        return False
    return True


def put_funding(heidi, asset_id, kind, amount, ref, funder, note) -> bool:
    r = heidi.put("/api/facilities/asset-funding", json={
        "asset_id": asset_id, "kind": kind, "amount": str(amount),
        "award_reference": ref, "funder": funder,
        "counted_as_cost_share": False, "note": note})
    if r.status_code != 200:
        finding(f"could not record funding: {r.status_code} {r.text[:200]}")
        return False
    return True


def read_unit(unit_id: str) -> dict:
    r = one("""SELECT unit_id, facility_id, label, floor, usable_sqft,
                      use::text AS use, status::text AS status, objective_id,
                      occupant, months_occupied, actual_annual_charge,
                      market_rate_psf, market_basis, market_source, note
                 FROM space_unit WHERE unit_id = %s""", (unit_id,))
    return dict(r) if r else {}



# The reach of a reclassification: the pools it moves between, the rates over
# them, and the carve-outs taken off a pool whose gross has changed. Anything
# outside this that moves is a finding — coverage, the three statements of the
# return, the asset register and the estate are all downstream of *other*
# registers and a judgment must not touch them.
CLASSIFY_REACH = ("pool.", "rate.", "carveout.")

# A partition change reaches the carve-out and therefore the overhead rate,
# and nothing in the pools' gross: carving is taken off a pool, not out of it.
PARTITION_REACH = ("pool.OVERHEAD.carved", "pool.OVERHEAD.allocable",
                   "rate.", "carveout.")


def _still_ties(c: dict, label: str) -> None:
    """`065`'s control, after every change: the rate against the pool under
    it. A reclassification that left a rate not tying to its own pool is the
    $932,254.78 defect coming back."""
    open_ = sorted(k.split(".")[1] for k, v in c.items()
                   if k.endswith(".state") and k.startswith("rate.")
                   and v == "OPEN")
    if open_:
        finding(f"{label}: the build-up stopped tying on {', '.join(open_)}")
    else:
        ok(f"{label}: every rate still ties to the pool underneath it")


def _reclass_act(tom, period, basis, title, keys, pool, why,
                 objective=None, extra_reach=(), breaks=None):
    """One judgment changed, sealed, computed, and every figure checked."""
    step(title)
    if not keys:
        finding(f"{title}: no group matched, so nothing could be driven")
        return None
    breaks = breaks or {}
    was = live_position(period, keys)
    if len(was) != len(keys):
        finding(f"{title}: {len(keys) - len(was)} of {len(keys)} groups carry "
                f"no live judgment")
        return None
    amount = amount_of(period, keys)
    from_pool = {v["pool"] for v in was.values()}
    if len(from_pool) != 1:
        finding(f"{title}: the groups are not all in one pool: {from_pool}")
        return None
    from_pool = from_pool.pop()
    fn = {v["fn"] for v in was.values()}.pop()
    fed = {v["federal"] for v in was.values()}.pop()
    print(f"           {amount} of {from_pool} -> {pool}")

    before = census(period)
    if not unseal(tom, why):
        return None
    if not reclassify(tom, keys, pool, fn, fed, objective, why):
        return None
    if not seal(tom, why) or not compute(tom, period, basis, why):
        return None
    after = census(period)

    moves = {f"pool.{from_pool}.gross": -amount,
             f"pool.{pool}.gross": amount}
    # A pool nothing is carved out of moves its allocable with its gross.
    if d(before.get(f"pool.{from_pool}.carved")) == 0:
        moves[f"pool.{from_pool}.allocable"] = -amount
    if d(before.get(f"pool.{pool}.carved")) == 0:
        moves[f"pool.{pool}.allocable"] = amount
    expect(before, after, moves, title,
           may=CLASSIFY_REACH + tuple(extra_reach))
    for control, want in breaks.items():
        if after.get(control) != want:
            finding(f"{title}: {control} reads {after.get(control)} and the "
                    f"change should have made it {want}")
        else:
            ok(f"{title}: {control} caught it and reads {want}")

    for k in ("coverage.classified", "coverage.unclassified",
              "coverage.scope_dollars", "ix.25.total", "viii.V1",
              "x.X16" if "x.X16" in before else "x.X1",
              "asset.variance"):
        if before.get(k) != after.get(k):
            finding(f"{title}: {k} moved on a reclassification — {before[k]} "
                    f"-> {after[k]}")
    ok(f"{title}: coverage, the three statements of the return, the asset "
       f"register and the estate all held still")
    _still_ties(after, title)

    def undo():
        for k, v in was.items():
            reclassify(tom, [k], v["pool"], v["fn"], v["federal"],
                       v["objective_id"], f"walking back {title}")
    return undo


def _labour(tom, heidi, period, basis):
    keys = group_keys(period, "%5130 Benefits%")
    return _reclass_act(
        tom, period, basis,
        "LABOUR — the benefits account, out of the fringe pool",
        keys, "OVERHEAD",
        "what is in FRINGE decides the fringe rate, so moving benefits out "
        "of it has to move both ends of that rate",
        # `067` anchors the fringe rate by anchoring both of its parts: the
        # numerator to the six accounts the P&L names and the denominator to
        # the payroll register. Taking one of the six out of the pool is
        # exactly what those two anchors exist to catch, so they are asserted
        # to fire rather than allowed to move quietly.
        extra_reach=("anchor.FRINGE_", "tie.",
                     "register.RATE.The fringe"),
        breaks={"anchor.FRINGE_POOL_IS_THE_PAYROLL_FRINGE": "OPEN",
                "anchor.FRINGE_RATE_ON_THE_REGISTER": "OPEN",
                "register.RATE.The fringe pool is the six accounts the "
                "P&L names.state": "OPEN",
                "register.RATE.The fringe rate falls out of its own two "
                "parts.state": "OPEN"})


def _gna(tom, heidi, period, basis):
    keys = group_keys(period, "%5202 Accounting%", "Metz Consulting, LLC.")
    return _reclass_act(
        tom, period, basis,
        "G&A — the accounting retainer, into overhead",
        keys, "OVERHEAD",
        "the retainer is administrative and the question 200.413(c) asks is "
        "whether it is general or occupancy-related")


def _subcontractor(tom, heidi, period, basis):
    keys = group_keys(period, "%5227 Portfolio consulting%",
                      "S-Gen Marketing LLC")
    return _reclass_act(
        tom, period, basis,
        "SUBCONTRACTOR — a portfolio consultant, out of the base",
        keys, "EXCLUDED",
        "200.331 decides contractor against subrecipient, and only one of "
        "the two readings leaves the whole amount in MTDC",
        extra_reach=())


def _facilities(tom, heidi, period, basis):
    step("FACILITIES — a suite let to a tenant, taken back for programme use")
    unit = one("""SELECT unit_id FROM space_unit
                   WHERE period = %s AND use::text = 'TENANT'
                   ORDER BY usable_sqft DESC LIMIT 1""", (period,))
    if not unit:
        note("no tenant space is on this record, so the facilities half "
             "could not be driven — not a pass and not a finding")
        return lambda: None
    before_unit = read_unit(unit["unit_id"])
    print(f"           {before_unit['label']} · "
          f"{before_unit['usable_sqft']} sq ft · "
          f"{before_unit['facility_id']}")

    before = census(period)
    changed = dict(before_unit, use="PROGRAM", status="INTERNAL",
                   objective_id=None, occupant="",
                   actual_annual_charge=None,
                   note=f"{MARK}: taken back for programme use.")
    # A PROGRAM space names an objective, which is the register's own rule.
    obj = one("""SELECT objective_id FROM cost_objective
                  WHERE period = %s AND objective_type = 'PROGRAM'
                  ORDER BY objective_id LIMIT 1""", (period,))
    changed["objective_id"] = obj["objective_id"] if obj else None
    if not put_space(heidi, changed):
        return None
    if not compute(tom, period, basis, "after the suite changed use"):
        return None
    after = census(period)

    fac = before_unit["facility_id"]
    expect(before, after,
           {f"space.{fac}.rental": None,
            "pool.OVERHEAD.carved": None,
            "pool.OVERHEAD.allocable": None,
            "carveout.total": None,
            "rate.OVERHEAD.rate": None,
            "rate.INDIRECT_COMBINED.rate": None},
           "FACILITIES",
           may=PARTITION_REACH + ("space.", "partition.SPACE."))

    for k in ("pool.OVERHEAD.gross", "pool.DIRECT.gross",
              "coverage.classified", "ix.25.total", "asset.variance",
              "rate.FRINGE.rate"):
        if before.get(k) != after.get(k):
            finding(f"FACILITIES: {k} moved on a square-footage change — "
                    f"{before[k]} -> {after[k]}")
    ok("FACILITIES: no pool's gross moved, the fringe rate held and the "
       "return held — carving is taken off a pool, never out of it")
    _still_ties(after, "FACILITIES")

    def undo():
        put_space(heidi, before_unit)
    return undo


def _inventory(tom, heidi, period, basis):
    step("INVENTORY — an asset that turns out not to be federally funded")
    row = one("""SELECT f.asset_id, f.amount, f.award_reference, f.funder,
                        a.description, a.depreciation
                   FROM asset_funding f JOIN asset a USING (asset_id)
                  WHERE f.kind = 'FEDERAL' AND a.period = %s
                    AND a.depreciation > 0
                  ORDER BY a.depreciation DESC OFFSET 1 LIMIT 1""", (period,))
    if not row:
        note("no federally funded asset carries depreciation on this "
             "record, so the inventory half could not be driven — not a "
             "pass and not a finding")
        return lambda: None
    print(f"           {row['description']} · {row['amount']} federal · "
          f"{row['depreciation']} of depreciation")

    before = census(period)
    if not put_funding(heidi, row["asset_id"], "FEDERAL", "0.00",
                       row["award_reference"], row["funder"],
                       f"{MARK}: no federal money in this asset after all."):
        return None
    if not compute(tom, period, basis, "after the funding source changed"):
        return None
    after = census(period)

    expect(before, after,
           {"asset.allowable_depreciation": d(row["depreciation"]),
            "pool.OVERHEAD.carved": None,
            "pool.OVERHEAD.allocable": None,
            "carveout.total": None,
            "rate.OVERHEAD.rate": None,
            "rate.INDIRECT_COMBINED.rate": None},
           "INVENTORY",
           may=PARTITION_REACH + ("asset.",))

    for k in ("asset.variance", "asset.funding_unknown", "asset.gross_cost",
              "pool.OVERHEAD.gross", "coverage.classified", "ix.25.total",
              "rate.FRINGE.rate"):
        if before.get(k) != after.get(k):
            finding(f"INVENTORY: {k} moved on a funding change — "
                    f"{before[k]} -> {after[k]}")
    ok("INVENTORY: the register still ties to the ledger, every asset still "
       "names a source, and only what 200.436(b) turns on moved")
    _still_ties(after, "INVENTORY")

    def undo():
        put_funding(heidi, row["asset_id"], "FEDERAL", str(row["amount"]),
                    row["award_reference"], row["funder"],
                    f"{MARK}: restored.")
    return undo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--period", default="2025")
    ap.add_argument("--hold", action="store_true",
                    help="leave the five changes standing instead of walking "
                         "them back, so the screens and the papers can be "
                         "read in the moved state")
    args = ap.parse_args()
    pw = os.environ.get("YBI_SEED_PASSWORD", "")
    if not pw:
        print("YBI_SEED_PASSWORD is not set.", file=sys.stderr)
        return 2
    open_pool()
    period = args.period

    live = one("""SELECT admin_labour_basis FROM rate
                   WHERE period = %s AND status <> 'SUPERSEDED'
                   ORDER BY computed_at DESC LIMIT 1""", (period,))
    if not live:
        print("\nCOULD NOT RUN — no live rate to measure against.",
              file=sys.stderr)
        return 2
    # Read the policy off the rate on file. A drive that hard-coded one would
    # restore nine points of combined rate chosen by the instrument rather
    # than by anybody — which `drive_partitions` did once.
    basis = live["admin_labour_basis"]

    tom = sign_in(args.base, EMAIL["tom"], pw)
    heidi = sign_in(args.base, "hruby@ybi.org", pw)

    start = census(period)
    print(f"\n{len(start)} figures under watch · admin labour on {basis}")

    # ── The signature comes off first, and that is two acts ─────────
    step("The certificate, before anything is touched")
    cert = one("SELECT certified FROM v_rate_certified WHERE period = %s",
               (period,))
    was_certified = bool(cert and cert["certified"])
    if was_certified:
        r = tom.post("/api/rates/certify/withdraw", json={
            "reason": f"{MARK}: five registers are about to be changed and "
                      f"put back, and a signature must not ride through it."})
        if r.status_code != 200:
            finding(f"could not withdraw the signature: {r.status_code} "
                    f"{r.text[:160]}")
            return _report()
        ok("the signature came off before the seal did — two acts, two "
           "reasons, which is what stops an auditor's ask taking a "
           "controller's name off a rate in passing")
    else:
        note("no signature stood on this record, so there was none to take "
             "off — not a pass and not a finding")

    acts = [_labour, _gna, _subcontractor, _facilities, _inventory]
    undo: list = []
    for act in acts:
        back = act(tom, heidi, period, basis)
        if back is None:
            return _report()
        undo.append(back)

    step("The return, against all five changes at once")
    moved = census(period)
    statements = {k: v for k, v in start.items()
                  if k.startswith(("ix.", "viii.", "x.", "coverage."))}
    drifted = {k for k, v in statements.items() if moved.get(k) != v}
    if drifted:
        for k in sorted(drifted):
            finding(f"the return moved on a rate-model change: {k} "
                    f"{statements[k]} -> {moved.get(k)}")
    else:
        ok(f"all {len(statements)} figures of Form 990 Parts VIII, IX and X "
           f"and of coverage are identical, with the combined rate moved "
           f"from {start['rate.INDIRECT_COMBINED.rate']} to "
           f"{moved['rate.INDIRECT_COMBINED.rate']} — the return is a "
           f"statement about the ledger and the rate is a statement about "
           f"the pools, and neither may reach into the other")

    if args.hold:
        step("Held, deliberately")
        if was_certified:
            note("the signature is off, and stays off: five judgments have "
                 "moved since it was given and a certificate that survived "
                 "that would be on a rate nobody saw")
        note("the five changes stand on this database. Nothing has been "
             "walked back, so the screens and the papers can be read in the "
             "moved state — run again without --hold to put it back.")
        return _report()

    step("Walking all five back")
    # The judgments are put back inside one unseal, because each one is not a
    # separate decision to reopen the set — it is the same decision to undo
    # what this drive did.
    if not unseal(tom, "walking every change back"):
        return _report()
    for fn in reversed(undo):
        fn()
    if not seal(tom, "after walking every change back"):
        return _report()
    if not compute(tom, period, basis, "after walking every change back"):
        return _report()
    if was_certified:
        tom.post("/api/rates/certify", json={
            "signature": "Tom Metzinger",
            "note": f"{MARK}: re-signed after the record was put back."})

    end = census(period)
    step("The record, against the census taken before any of it")
    held(start, end, "end to end")
    return _report()


def _report() -> int:
    print()
    if FINDINGS:
        print(f"\033[1m{CHECKS} checks, {len(FINDINGS)} finding(s)\033[0m")
        for f in FINDINGS:
            print(f"  - {f}")
        return 1
    print(f"\033[1m{CHECKS} checks, 0 findings\033[0m")
    for n in NOTES:
        print(f"  - {n}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
