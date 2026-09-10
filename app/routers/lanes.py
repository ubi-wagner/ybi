"""Testing lanes.

Assumption variants are free. Classification overrides are counted, reasoned
and disclosed. Both are legitimate; only one needs a paper trail.
"""

from fastapi import Depends, APIRouter
from pydantic import BaseModel

from app.auth import require_controller, require_reader
from app.db import execute, one, query

router = APIRouter(prefix="/lanes", tags=["lanes"],
                   dependencies=[Depends(require_reader)])


class LaneIn(BaseModel):
    name: str
    purpose: str
    parent_lane: str | None = None
    created_by: str


@router.get("")
def list_lanes(period: str = "2025") -> list[dict]:
    return query("SELECT * FROM v_lane_disclosure WHERE period=%s ORDER BY created_at", (period,))


@router.post("",
              dependencies=[Depends(require_controller)])
def create_lane(body: LaneIn, period: str = "2025") -> dict:
    st = one("""SELECT set_id FROM decision_set WHERE period=%s ORDER BY set_id LIMIT 1""",
             (period,))
    row = one("""INSERT INTO lane (period,name,kind,parent_lane,set_id,purpose,created_by)
                 VALUES (%s,%s,'SANDBOX',%s,%s,%s,%s) RETURNING lane_id""",
              (period, body.name, body.parent_lane, st["set_id"], body.purpose, body.created_by))
    return {"lane_id": str(row["lane_id"]), "kind": "SANDBOX"}


@router.get("/{lane_id}/buildup")
def buildup(lane_id: str) -> list[dict]:
    """Read-only: what these classifications do to the pools. No rate."""
    return query("SELECT * FROM v_lane_buildup WHERE lane_id=%s ORDER BY pool", (lane_id,))


@router.post("/{lane_id}/promote",
              dependencies=[Depends(require_controller)])
def promote(lane_id: str, to_kind: str, rationale: str, approved_by: str) -> dict:
    cur = one("SELECT kind FROM lane WHERE lane_id=%s", (lane_id,))
    execute("""INSERT INTO lane_promotion (lane_id,from_kind,to_kind,rationale,approved_by)
               VALUES (%s,%s,%s,%s,%s)""",
            (lane_id, cur["kind"], to_kind, rationale, approved_by))
    execute("UPDATE lane SET kind=%s WHERE lane_id=%s", (to_kind, lane_id))
    return {"lane_id": lane_id, "kind": to_kind}


@router.get("/compare")
def compare(a: str, b: str) -> dict:
    left = {r["pool"]: r for r in query("SELECT * FROM v_lane_buildup WHERE lane_id=%s", (a,))}
    right = {r["pool"]: r for r in query("SELECT * FROM v_lane_buildup WHERE lane_id=%s", (b,))}
    pools = sorted(set(left) | set(right))
    return {"pools": [{"pool": p,
                       "a": float(left.get(p, {}).get("amount") or 0),
                       "b": float(right.get(p, {}).get("amount") or 0),
                       "delta": float((right.get(p, {}).get("amount") or 0)
                                      - (left.get(p, {}).get("amount") or 0))}
                      for p in pools]}
