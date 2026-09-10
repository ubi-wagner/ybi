"""Rates and allocation.

Sealing is the gate. A rate cannot be computed from an unsealed decision set,
in this handler or anywhere else — a database trigger enforces it too, so the
guarantee survives a bug here.
"""

from fastapi import Depends, APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import require_controller, require_reader
from app.audit import record
from app.auth import Actor
from app.db import execute, one, query

router = APIRouter(prefix="/rates", tags=["rates"],
                   dependencies=[Depends(require_reader)])


class SealIn(BaseModel):
    sealed_by: str = ""
    note: str = ""


@router.post("/seal")
def seal(body: SealIn, period: str = "2025",
         actor: Actor = Depends(require_controller)) -> dict:
    """Hash every live classification and freeze the set. After this the rate
    phase unlocks and classifications can only change by unsealing, with a
    reason, which supersedes any rate already computed.

    The seal is the moment the whole guarantee rests on, so it is recorded as
    the signed-in controller and body.sealed_by is only a label. An identity
    the client supplies is not evidence of who did this.
    """
    st = one("""SELECT set_id FROM decision_set WHERE period=%s AND seal_hash IS NULL
                 ORDER BY set_id LIMIT 1""", (period,))
    if not st:
        raise HTTPException(409, "No open decision set — this period is already sealed.")
    h = one("""
        SELECT encode(digest(string_agg(fp,'' ORDER BY fp),'sha256'),'hex') AS seal
          FROM (SELECT encode(digest(
                   d.decision_id::text || d.pool::text || d.function_990::text ||
                   d.federal::text || coalesce(d.objective_id,'') || d.grade::text,
                   'sha256'),'hex') AS fp
                  FROM decision d
                 WHERE d.set_id=%s AND d.reversed_at IS NULL) x
    """, (st["set_id"],))
    sealed_by = actor.display_name or body.sealed_by
    counts = one("""SELECT count(*) AS decisions,
                           count(*) FILTER (WHERE grade IN ('UNSUPPORTED','TEST_ASSUMPTION'))
                             AS weak
                      FROM decision
                     WHERE set_id = %s AND reversed_at IS NULL""", (st["set_id"],))
    execute("""UPDATE decision_set SET seal_hash=%s, sealed_at=now(), sealed_by=%s
                WHERE set_id=%s""", (h["seal"], sealed_by, st["set_id"]))
    record(actor, "SEAL", "decision_set", str(st["set_id"]),
           after={"seal_hash": h["seal"], "decisions": counts["decisions"],
                  "weakly_graded": counts["weak"]},
           reason=body.note.strip() or "decision set sealed")
    return {"set_id": str(st["set_id"]), "seal_hash": h["seal"],
            "decisions": counts["decisions"]}


@router.post("/unseal")
def unseal(reason: str, period: str = "2025",
           actor: Actor = Depends(require_controller)) -> dict:
    if not reason.strip():
        raise HTTPException(422, "Unsealing requires a reason for the audit trail.")
    st = one("""SELECT set_id FROM decision_set WHERE period=%s AND seal_hash IS NOT NULL
                 ORDER BY sealed_at DESC LIMIT 1""", (period,))
    if not st:
        raise HTTPException(404, "No sealed decision set for this period.")
    execute("""UPDATE decision_set SET seal_hash=NULL, sealed_at=NULL,
                      unsealed_reason=%s WHERE set_id=%s""", (reason, st["set_id"]))
    execute("""UPDATE rate SET status='SUPERSEDED' WHERE set_id=%s AND status<>'ACCEPTED'""",
            (st["set_id"],))
    record(actor, "UNSEAL", "decision_set", str(st["set_id"]), reason=reason)
    return {"set_id": str(st["set_id"]), "status": "unsealed"}


@router.get("/current")
def current(period: str = "2025") -> dict:
    rates = query("""SELECT kind, pool_amount, base_type, base_amount, rate, status,
                            seal_hash, computed_at
                       FROM rate WHERE period=%s AND status<>'SUPERSEDED'
                      ORDER BY computed_at DESC""", (period,))
    return {"period": period, "rates": rates}


@router.get("/allocation")
def allocation(rate_id: str) -> list[dict]:
    return query("""SELECT a.objective_id, o.label, o.is_federal,
                           a.base_amount, a.allocated, a.rounding_adj
                      FROM allocation a JOIN cost_objective o USING (objective_id)
                     WHERE a.rate_id=%s ORDER BY a.allocated DESC""", (rate_id,))
