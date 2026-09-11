"""Testing lanes.

Assumption variants are free. Classification overrides are counted, reasoned
and disclosed. Both are legitimate; only one needs a paper trail.

**A lane never touches the sealed set.** That is the whole reason the
machinery exists rather than a second classification queue: an override lives
in `lane_decision_override` and covers specific ledger lines, and
`v_lane_buildup` reads the pool as `COALESCE(override.pool, decision.pool)`.
The decision the controller sealed is not edited, superseded or unsealed by
trying something, and the rate that carries that seal is unaffected. A lane
is a question; the sealed set is the answer on the record.

Which is why a BASELINE lane takes no overrides at all. The baseline is *the
classifications and assumptions that will be submitted* — changing that goes
through the queue and the seal, in front of the trigger that refuses a rate
whose seal does not match. A lane override on the baseline would be a way
round the one guarantee this system is built on.

`lane_decision_override`, `lane_override_line` and `lane_assumption` were
created in the first migrations and **nothing wrote any of them** for as long
as they existed, so every lane's build-up was identical to the baseline's by
construction and `GET /lanes/compare` could only ever answer with zeroes. The
ninth, tenth and eleventh columns-or-tables in this schema that looked usable
and were filled by nothing. Building the side-by-side screen over that API
first would have produced a screen that cannot say anything — which is the
`FACILITY_UNPARTITIONED` mistake: worse than no screen, because it teaches
the reader that the comparison is broken.
"""

from decimal import Decimal

from psycopg.errors import UniqueViolation

from fastapi import Depends, APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import execute, one, query, transaction
from app.domain.core import money
from app.settings import settings
from app.statelock import turn
from app.vocab import (EvidenceGrade, FederalTreatment, Function990, LaneKind,
                       Pool)

router = APIRouter(prefix="/lanes", tags=["lanes"],
                   dependencies=[Depends(require_reader)])


class LaneIn(BaseModel):
    name: str
    purpose: str
    parent_lane: str | None = None
    created_by: str = ""


class PromoteIn(BaseModel):
    to_kind: LaneKind
    rationale: str


@router.get("")
def list_lanes(period: str = "2025") -> list[dict]:
    return query("SELECT * FROM v_lane_disclosure WHERE period=%s ORDER BY created_at", (period,))


@router.post("")
def create_lane(body: LaneIn, period: str = "2025",
                actor: Actor = Depends(require_controller)) -> dict:
    st = one("""SELECT set_id FROM decision_set WHERE period=%s ORDER BY set_id LIMIT 1""",
             (period,))
    if not st:
        raise HTTPException(404, f"No decision set for {period}.")
    created_by = actor.display_name or body.created_by
    row = one("""INSERT INTO lane (period,name,kind,parent_lane,set_id,purpose,created_by)
                 VALUES (%s,%s,'SANDBOX',%s,%s,%s,%s) RETURNING lane_id""",
              (period, body.name, body.parent_lane, st["set_id"], body.purpose,
               created_by))
    record(actor, "LANE_CREATE", "lane", str(row["lane_id"]),
           after={"name": body.name, "kind": "SANDBOX",
                  "parent_lane": body.parent_lane},
           reason=body.purpose)
    return {"lane_id": str(row["lane_id"]), "kind": "SANDBOX"}


@router.get("/{lane_id}/buildup")
def buildup(lane_id: str) -> list[dict]:
    """Read-only: what these classifications do to the pools. No rate."""
    return query("SELECT * FROM v_lane_buildup WHERE lane_id=%s ORDER BY pool", (lane_id,))


@router.post("/{lane_id}/promote")
def promote(lane_id: str, body: PromoteIn,
            actor: Actor = Depends(require_controller)) -> dict:
    """Move a lane up. Promoting a scenario into the working set is a decision
    about what the engagement stands behind, so it is recorded as one."""
    cur = one("SELECT kind, name FROM lane WHERE lane_id=%s", (lane_id,))
    if not cur:
        raise HTTPException(404, "No such lane.")
    if not body.rationale.strip():
        raise HTTPException(422, "Promoting a lane needs a rationale.")
    with transaction() as tx:
        tx.execute("""INSERT INTO lane_promotion
                        (lane_id,from_kind,to_kind,rationale,approved_by)
                      VALUES (%s,%s,%s,%s,%s)""",
                   (lane_id, cur["kind"], body.to_kind, body.rationale.strip(),
                    actor.display_name))
        tx.execute("UPDATE lane SET kind=%s WHERE lane_id=%s", (body.to_kind, lane_id))
        record(actor, "LANE_PROMOTE", "lane", lane_id,
               before={"kind": cur["kind"]}, after={"kind": body.to_kind},
               reason=body.rationale.strip(), cursor=tx)
    return {"lane_id": lane_id, "kind": body.to_kind}


class OverrideIn(BaseModel):
    """One reading of a group of lines, tried inside a lane.

    The same four things a decision records, because an override answers the
    same question — and `direct_needs_objective_ovr` in the schema enforces
    the same rule about DIRECT carrying an objective, so a lane cannot try
    something the sealed set could not have said.
    """
    pool: Pool
    function_990: Function990 = Function990.NOT_APPLICABLE
    federal: FederalTreatment = FederalTreatment.PENDING
    objective_id: str | None = None
    grade: EvidenceGrade = EvidenceGrade.UNSUPPORTED
    #: Why this reading is worth trying. The CHECK refuses an empty one; a
    #: lane whose overrides carry no reason is a set of numbers nobody can
    #: defend, and a promoted lane's overrides are what gets disclosed.
    reason: str = Field(min_length=1)
    #: The lines it covers. Given as a group — account and payee, the way the
    #: queue works — or as explicit line ids.
    account: str = ""
    payee: str = ""
    line_ids: list[str] = []


class AssumptionIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    value: Decimal
    basis: str = ""
    grade: EvidenceGrade = EvidenceGrade.UNSUPPORTED


def _lane(lane_id: str) -> dict:
    row = one("""SELECT lane_id, period, name, kind::text AS kind
                   FROM lane WHERE lane_id = %s""", (lane_id,))
    if not row:
        raise HTTPException(404, f"No lane {lane_id}.")
    return row


def _not_the_baseline(lane: dict) -> None:
    if lane["kind"] == "BASELINE":
        raise HTTPException(
            409,
            f"{lane['name']} is the baseline — the classifications and "
            f"assumptions that will be submitted. Changing those goes through "
            f"the queue and the seal, in front of the trigger that refuses a "
            f"rate whose seal does not match. Try it in a sandbox lane and "
            f"promote it if it holds.")


@router.post("/{lane_id}/overrides", status_code=201)
def add_override(lane_id: str, body: OverrideIn,
                 actor: Actor = Depends(require_controller)) -> dict:
    """Try a different reading of some lines, without touching the seal."""
    lane = _lane(lane_id)
    _not_the_baseline(lane)
    if (body.pool == Pool.DIRECT) != bool(body.objective_id):
        raise HTTPException(
            422, "A DIRECT reading names the objective the cost is direct to, "
                 "and nothing else may name one. The schema says the same.")

    with turn(lane["period"]) as cur:
        # Read the lines inside the turn, because what they are classified as
        # is what this override is departing from, and another controller may
        # be judging the same group right now.
        if body.line_ids:
            cur.execute("""SELECT line_id, amount FROM ledger_line
                            WHERE period = %s AND line_id = ANY(%s)""",
                        (lane["period"], body.line_ids))
        elif body.account:
            cur.execute("""SELECT line_id, amount FROM ledger_line
                            WHERE period = %s AND account = %s AND payee = %s""",
                        (lane["period"], body.account, body.payee))
        else:
            raise HTTPException(422, "An override covers lines: give either "
                                     "line_ids or an account and payee.")
        lines = cur.fetchall()
        if not lines:
            raise HTTPException(
                404, "No ledger line matches — an override covering nothing "
                     "would sit in the disclosure saying it changed something.")

        # What it is departing from, so the answer can say. A line with no
        # live decision is one the queue has not reached, and overriding it
        # is trying a reading rather than disagreeing with one.
        cur.execute("""SELECT count(DISTINCT dl.line_id) AS n
                         FROM decision_line dl
                         JOIN decision d ON d.decision_id = dl.decision_id
                        WHERE dl.live AND d.reversed_at IS NULL
                          AND d.set_id = (SELECT set_id FROM lane
                                           WHERE lane_id = %s)
                          AND dl.line_id = ANY(%s)""",
                    (lane_id, [r["line_id"] for r in lines]))
        departs_from = cur.fetchone()["n"]

        cur.execute("""INSERT INTO lane_decision_override
                         (lane_id, pool, function_990, federal, objective_id,
                          grade, reason, created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING override_id""",
                    (lane_id, body.pool, body.function_990, body.federal,
                     body.objective_id, body.grade, body.reason.strip(),
                     actor.display_name))
        override_id = str(cur.fetchone()["override_id"])
        # `one_override_per_line_per_lane` refuses a line already tried in
        # this lane — two readings of one line would count it twice in the
        # lane's own build-up, which is the supersession defect in a new
        # place. Named here rather than surfaced as a raw constraint
        # violation that says nothing.
        try:
            cur.executemany(
                """INSERT INTO lane_override_line (override_id, lane_id, line_id)
                   VALUES (%s,%s,%s)""",
                [(override_id, lane_id, r["line_id"]) for r in lines])
        except UniqueViolation:
            raise HTTPException(
                409, f"Some of these {len(lines)} lines are already given a "
                     f"different reading in {lane['name']}. A line carries one "
                     f"reading per lane; withdraw the other one first, or try "
                     f"this in a lane of its own.")
        covered = money(sum(r["amount"] for r in lines))
        record(actor, "LANE_OVERRIDE", "lane", lane_id,
               after={"override_id": override_id, "pool": str(body.pool),
                      "lines": len(lines), "amount": str(covered)},
               reason=body.reason.strip(), cursor=cur)
    return {"override_id": override_id, "lines": len(lines),
            "amount": str(covered), "departs_from": departs_from}


@router.delete("/{lane_id}/overrides/{override_id}")
def remove_override(lane_id: str, override_id: str,
                    actor: Actor = Depends(require_controller)) -> dict:
    """Untry it.

    A sandbox somebody cannot back out of is not a sandbox — the rule that
    nothing destructive happens without a way back. A promoted lane is
    different: its overrides are what the disclosure is *about*, so they are
    removed by demoting the lane rather than by quietly dropping a row.
    """
    lane = _lane(lane_id)
    _not_the_baseline(lane)
    row = one("""SELECT pool::text AS pool, reason FROM lane_decision_override
                  WHERE override_id = %s AND lane_id = %s""",
              (override_id, lane_id))
    if not row:
        raise HTTPException(404, "No such override on this lane.")
    with turn(lane["period"]) as cur:
        cur.execute("DELETE FROM lane_decision_override WHERE override_id = %s",
                    (override_id,))
        record(actor, "LANE_OVERRIDE_REMOVE", "lane", lane_id,
               before={"override_id": override_id, "pool": row["pool"]},
               reason=f"withdrew: {row['reason']}", cursor=cur)
    return {"removed": override_id}


@router.get("/{lane_id}/overrides")
def overrides(lane_id: str) -> list[dict]:
    _lane(lane_id)
    return query("""SELECT o.override_id, o.pool::text AS pool,
                           o.function_990::text AS function_990,
                           o.federal::text AS federal, o.objective_id,
                           o.grade::text AS grade, o.reason, o.created_by,
                           o.created_at,
                           count(l.line_id)                     AS lines,
                           COALESCE(sum(ll.amount), 0)          AS amount
                      FROM lane_decision_override o
                      LEFT JOIN lane_override_line l
                             ON l.override_id = o.override_id
                      LEFT JOIN ledger_line ll ON ll.line_id = l.line_id
                     WHERE o.lane_id = %s
                     GROUP BY o.override_id
                     ORDER BY o.created_at""", (lane_id,))


@router.put("/{lane_id}/assumptions", status_code=201)
def set_assumption(lane_id: str, body: AssumptionIn,
                   actor: Actor = Depends(require_controller)) -> dict:
    """An assumption variant. Free, in the sense that it needs no paper trail
    of its own — but it still carries the grade of what it rests on, because
    a number somebody picked and a number read off a document are different
    kinds of number and the disclosure has to be able to say which."""
    lane = _lane(lane_id)
    _not_the_baseline(lane)
    with turn(lane["period"]) as cur:
        cur.execute("""INSERT INTO lane_assumption (lane_id, key, value,
                                                    basis, grade)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (lane_id, key) DO UPDATE
                         SET value = EXCLUDED.value, basis = EXCLUDED.basis,
                             grade = EXCLUDED.grade""",
                    (lane_id, body.key.strip(), body.value, body.basis.strip(),
                     body.grade))
        record(actor, "LANE_ASSUMPTION", "lane", lane_id,
               after={"key": body.key.strip(), "value": str(body.value),
                      "grade": str(body.grade)},
               reason=body.basis.strip() or f"assumption {body.key.strip()}",
               cursor=cur)
    return {"lane_id": lane_id, "key": body.key.strip()}


@router.get("/{lane_id}/assumptions")
def assumptions(lane_id: str) -> list[dict]:
    _lane(lane_id)
    return query("""SELECT key, value, basis, grade::text AS grade
                      FROM lane_assumption WHERE lane_id = %s ORDER BY key""",
                 (lane_id,))


@router.get("/compare")
def compare(lanes: str, period: str | None = None) -> dict:
    """Two or three readings side by side, against the first as the base.

    Money is a string, not a float. It used to be `float(...)` on all three
    columns, which is the one thing `domain/core.py::money()` exists to stop:
    a cost model that rounds in binary produces variances that take hours to
    chase, and a comparison screen is exactly where somebody would chase one.

    Nothing here is computed beyond the difference between two recorded
    figures. The rate under each reading is not divided out on the way past —
    a lane is not sealed, so it has no rate, and inventing one here would put
    a rate on a screen with no seal behind it.
    """
    period = period or settings.period
    ids = [x.strip() for x in lanes.split(",") if x.strip()]
    if not 2 <= len(ids) <= 4:
        raise HTTPException(422, "Compare two, three or four lanes: "
                                 "?lanes=<id>,<id>[,<id>]")
    heads = query("""SELECT * FROM v_lane_disclosure
                      WHERE lane_id = ANY(%s::uuid[]) AND period = %s""",
                  (ids, period))
    found = {str(h["lane_id"]): h for h in heads}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(404, f"No lane in {period}: {', '.join(missing)}")

    rows = query("""SELECT lane_id, pool::text AS pool, amount, lines
                      FROM v_lane_buildup WHERE lane_id = ANY(%s::uuid[])""",
                 (ids,))
    by_lane: dict[str, dict[str, dict]] = {i: {} for i in ids}
    for r in rows:
        by_lane[str(r["lane_id"])][r["pool"]] = r
    pools = sorted({r["pool"] for r in rows})

    base = ids[0]
    out = []
    for pool in pools:
        cells = []
        for i in ids:
            got = by_lane[i].get(pool)
            amount = money(got["amount"]) if got else money(0)
            against = by_lane[base].get(pool)
            base_amount = money(against["amount"]) if against else money(0)
            cells.append({"lane_id": i, "amount": str(amount),
                          "lines": (got or {}).get("lines", 0),
                          "delta": str(money(amount - base_amount))})
        out.append({"pool": pool, "cells": cells})

    # Said plainly rather than left to be inferred from a column of zeroes.
    # Every lane read identically for as long as nothing could write an
    # override, and a reader seeing that would reasonably assume the screen
    # was broken.
    identical = [i for i in ids[1:]
                 if all(c["delta"] == "0.00"
                        for row in out for c in row["cells"]
                        if c["lane_id"] == i)]
    return {"period": period, "base": base,
            "lanes": [{"lane_id": str(found[i]["lane_id"]),
                       "name": found[i]["name"],
                       "kind": found[i]["kind"],
                       "purpose": found[i]["purpose"],
                       "overrides": found[i]["classification_overrides"],
                       "assumptions": found[i]["assumption_variants"]}
                      for i in ids],
            "pools": out,
            "identical_to_base": identical}
