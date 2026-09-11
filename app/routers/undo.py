"""Walking an action back.

A fat finger and a mass reclassification are the same accident at different
scales, and the answer to both is the same: put it back, and say so.

Undo here is a forward act. Nothing is erased — a classification is reversed,
a split is reversed, an entry is superseded by one carrying the old value, a
note is retracted. Each of those is a record in its own right, and the audit
entry the undo writes names the entry it walked back, so the log reads as a
statement and its answer rather than two unrelated events.

Who may walk back what follows from who could have done it in the first
place. Your own actions are yours. The controller may walk back the
classification side of the work, because that is their judgment to make and
remake. Nobody may walk back somebody else's certification or somebody else's
timesheet: a signature you did not give is not yours to withdraw.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, Role, current_actor, require_own_writes
from app.db import one, query, transaction

router = APIRouter(prefix="/undo", tags=["undo"])

#: Actions the controller may walk back whoever performed them — the shared
#: judgment about how cost is classified and what the record says about it.
CONTROLLER_SCOPE = {"CLASSIFY", "SEGMENT", "NOTE", "EMPLOYMENT",
                    "EVIDENCE_UPLOAD", "SEAL"}

#: Actions that are only ever the actor's own to undo. A certification is a
#: personal statement and a timesheet is a personal record; somebody else
#: withdrawing either would be forging a retraction.
PERSONAL = {"CERTIFY", "TIME_ENTRY", "TIME_REMOVE", "TIME_SUBMIT"}

REVERSIBLE = CONTROLLER_SCOPE | PERSONAL


class UndoIn(BaseModel):
    entry_ids: list[int] = Field(default_factory=list)
    count: int | None = Field(default=None, ge=1, le=200)
    reason: str


def _may_undo(actor: Actor, row: dict) -> str | None:
    """Why this actor cannot undo this entry, or None if they may."""
    if row["action"] not in REVERSIBLE:
        return f"a {row['action']} cannot be walked back"
    own = row["actor_id"] and str(row["actor_id"]) == actor.actor_id
    if own:
        return None
    if row["action"] in PERSONAL:
        return (f"{row['label'].lower()} belongs to {row['actor']} — a record "
                f"somebody else made is not yours to withdraw")
    if row["action"] in CONTROLLER_SCOPE and actor.may_seal:
        return None
    return "only the person who did this, or the controller, may walk it back"


@router.get("")
def recent(limit: int = Query(20, ge=1, le=100), mine: bool = True,
           actor: Actor = Depends(current_actor)) -> list[dict]:
    """The trail, newest first.

    ``mine`` is the default because the common case is somebody looking at
    what they just did. A controller can widen it to the whole engagement.
    """
    if mine or actor.role is Role.EMPLOYEE:
        rows = query("""SELECT * FROM v_undoable WHERE actor_id = %s
                         ORDER BY occurred_at DESC LIMIT %s""",
                     (actor.actor_id, limit))
    elif actor.can_read:
        rows = query("""SELECT * FROM v_undoable
                         ORDER BY occurred_at DESC LIMIT %s""", (limit,))
    else:
        rows = []
    out = []
    for r in rows:
        blocked = _may_undo(actor, r)
        out.append({**r,
                    "entry_id": r["entry_id"],
                    "can_undo": bool(r["reversible_action"]) and not r["already_undone"]
                                and blocked is None,
                    "blocked_because": (
                        "already walked back" if r["already_undone"] else blocked)})
    return out


def _undo_one(cur, actor: Actor, row: dict, reason: str) -> str:
    """Reverse one entry through the same path a person would use by hand.

    Returns a sentence describing what happened, or raises HTTPException when
    the world has moved on since the entry was written.
    """
    action, target = row["action"], row["entity_id"]

    if action == "CLASSIFY":
        cur.execute("""UPDATE decision
                          SET reversed_at = now(), reversal_reason = %s
                        WHERE decision_id = %s AND reversed_at IS NULL
                        RETURNING scope""", (reason, target))
        got = cur.fetchone()
        if not got:
            raise HTTPException(409, "That classification has already been "
                                     "reversed or superseded.")
        return f"classification of {got['scope']} reversed"

    if action == "SEGMENT":
        cur.execute("""UPDATE ledger_segment
                          SET reversed_at = now(), reversed_by = %s,
                              reversal_reason = %s
                        WHERE batch_key = (SELECT after_state->>'batch_key'
                                             FROM audit_log WHERE entry_id = %s)
                          AND reversed_at IS NULL
                        RETURNING segment_id""",
                    (actor.display_name, reason, row["entry_id"]))
        n = len(cur.fetchall())
        if not n:
            raise HTTPException(409, "That split has already been reversed.")
        return f"{n} segments reversed"

    if action == "NOTE":
        cur.execute("""UPDATE note
                          SET retracted_at = now(), retracted_by = %s,
                              retraction_reason = %s
                        WHERE note_id = %s AND retracted_at IS NULL
                        RETURNING note_id""",
                    (actor.display_name, reason, target))
        if not cur.fetchone():
            raise HTTPException(409, "That note is already retracted.")
        return "note retracted"

    if action in ("TIME_ENTRY", "TIME_REMOVE"):
        return _undo_time(cur, actor, row, reason)

    if action == "TIME_SUBMIT":
        cur.execute("""UPDATE timesheet_submission
                          SET withdrawn_at = now(), withdrawn_reason = %s
                        WHERE submission_id = %s AND withdrawn_at IS NULL
                        RETURNING period""", (reason, target))
        if not cur.fetchone():
            raise HTTPException(409, "That submission is already withdrawn.")
        return "timesheet submission withdrawn"

    if action == "CERTIFY":
        cur.execute("""UPDATE labor_certification
                          SET superseded_at = now(), superseded_reason = %s
                        WHERE certification_id = %s AND superseded_at IS NULL
                        RETURNING employee_key""", (reason, target))
        if not cur.fetchone():
            raise HTTPException(409, "That certification is already superseded.")
        return "certification withdrawn — the effort is unattested again"

    if action == "EMPLOYMENT":
        cur.execute("""UPDATE employment
                          SET superseded_at = now(), superseded_reason = %s
                        WHERE employee_key = %s AND superseded_at IS NULL
                          AND recorded_at = (SELECT occurred_at FROM audit_log
                                              WHERE entry_id = %s)
                        RETURNING employment_id""",
                    (reason, target, row["entry_id"]))
        if not cur.fetchone():
            raise HTTPException(409, "Those employment terms have already been "
                                     "superseded.")
        return "employment span withdrawn"

    if action == "EVIDENCE_UPLOAD":
        cur.execute("""UPDATE attachment SET detached_at = now()
                        WHERE evidence_id = %s AND detached_at IS NULL
                        RETURNING attachment_id""", (target,))
        n = len(cur.fetchall())
        if not n:
            raise HTTPException(409, "That document is already detached.")
        return f"document detached from {n} line(s) — the file stays on file"

    if action == "SEAL":
        cur.execute("""UPDATE decision_set
                          SET seal_hash = NULL, sealed_at = NULL,
                              unsealed_reason = %s
                        WHERE set_id = %s AND seal_hash IS NOT NULL
                        RETURNING set_id""", (reason, target))
        if not cur.fetchone():
            raise HTTPException(409, "That set is not sealed.")
        cur.execute("""UPDATE rate SET status = 'SUPERSEDED'
                        WHERE set_id = %s AND status <> 'ACCEPTED'""", (target,))
        return "seal broken — any rate computed from it is superseded"

    raise HTTPException(422, f"A {action} cannot be walked back.")


def _undo_time(cur, actor: Actor, row: dict, reason: str) -> str:
    """Put a timesheet cell back the way it was.

    The audit entry names the row it created, so there is nothing to search
    for. Forward, like everything else: the current entry is superseded and
    the value it replaced is written again as a new row. The old rows stay
    exactly where they are, so the trail reads entry, correction, restoration
    rather than a value that quietly changed twice.
    """
    entry_id = row["entity_id"]
    cur.execute("""SELECT period, employee_key, work_date, objective_id, hours,
                          basis, note, superseded_at
                     FROM timesheet_entry WHERE entry_id = %s::bigint""",
                (entry_id,))
    target = cur.fetchone()
    if not target:
        raise HTTPException(404, "That entry is no longer on file.")

    if row["action"] == "TIME_REMOVE":
        # It was taken off the sheet; putting it back means writing it again.
        cur.execute("""SELECT 1 FROM timesheet_entry
                        WHERE period=%s AND employee_key=%s AND work_date=%s
                          AND objective_id=%s AND superseded_at IS NULL""",
                    (target["period"], target["employee_key"],
                     target["work_date"], target["objective_id"]))
        if cur.fetchone():
            raise HTTPException(409, "There is time recorded there again, so "
                                     "there is nothing to put back.")
        cur.execute("""INSERT INTO timesheet_entry
                         (period, employee_key, work_date, objective_id, hours,
                          basis, note, entered_by, entered_by_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (target["period"], target["employee_key"],
                     target["work_date"], target["objective_id"],
                     target["hours"], target["basis"],
                     f"Restored: {reason}"[:400], actor.actor_id,
                     actor.display_name))
        return (f"{target['objective_id']} on {target['work_date']} put back "
                f"at {target['hours']} hours")

    if target["superseded_at"] is not None:
        raise HTTPException(409, "That entry has already been changed or "
                                 "removed since.")

    # What it replaced, if anything: the row it superseded.
    cur.execute("""SELECT hours, basis, note FROM timesheet_entry
                    WHERE superseded_by = %s::bigint
                    ORDER BY entry_id DESC LIMIT 1""", (entry_id,))
    prior = cur.fetchone()

    cur.execute("""UPDATE timesheet_entry SET superseded_at = now()
                    WHERE entry_id = %s::bigint AND superseded_at IS NULL""",
                (entry_id,))

    if not prior:
        return (f"{target['objective_id']} on {target['work_date']} taken off "
                f"the sheet")

    cur.execute("""INSERT INTO timesheet_entry
                     (period, employee_key, work_date, objective_id, hours,
                      basis, note, entered_by, entered_by_name)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (target["period"], target["employee_key"], target["work_date"],
                 target["objective_id"], prior["hours"], prior["basis"],
                 f"Restored: {reason}"[:400], actor.actor_id,
                 actor.display_name))
    return (f"{target['objective_id']} on {target['work_date']} put back to "
            f"{prior['hours']} hours")


@router.post("")
def undo(body: UndoIn, actor: Actor = Depends(require_own_writes)) -> dict:
    """Walk back specific entries, or the last N of your own actions.

    Newest first, always: undoing out of order would put a value back that a
    later action had already moved on from.
    """
    if not body.reason.strip():
        raise HTTPException(422, "Walking an action back needs a reason. It "
                                 "is the part a reviewer reads.")
    if not body.entry_ids and not body.count:
        raise HTTPException(422, "Name the entries to walk back, or how many.")

    if body.entry_ids:
        rows = query("""SELECT * FROM v_undoable WHERE entry_id = ANY(%s)
                         ORDER BY occurred_at DESC""", (body.entry_ids,))
        if len(rows) != len(set(body.entry_ids)):
            raise HTTPException(404, "One of those entries is not on the "
                                     "record, or cannot be walked back.")
    else:
        rows = query("""SELECT * FROM v_undoable
                         WHERE actor_id = %s AND reversible_action
                           AND NOT already_undone
                         ORDER BY occurred_at DESC LIMIT %s""",
                     (actor.actor_id, body.count))
        if not rows:
            raise HTTPException(404, "Nothing of yours left to walk back.")

    done, refused = [], []
    for r in rows:
        blocked = _may_undo(actor, r)
        if blocked:
            refused.append({"entry_id": r["entry_id"], "why": blocked})
            continue
        if r["already_undone"]:
            refused.append({"entry_id": r["entry_id"],
                            "why": "already walked back"})
            continue
        # Each undo is its own transaction: one that cannot be reversed must
        # not roll back the ones that already were.
        try:
            with transaction() as cur:
                what = _undo_one(cur, actor, r, body.reason.strip())
                cur.execute("""INSERT INTO audit_log
                                 (actor, actor_id, session_id, actor_role,
                                  action, entity, entity_id, reason,
                                  before_state, undoes_entry_id)
                               VALUES (%s,%s,%s,%s,'UNDO',%s,%s,%s,%s,%s)""",
                            (actor.display_name, actor.actor_id,
                             actor.session_id, actor.role.value,
                             r["entity"], r["entity_id"],
                             body.reason.strip(),
                             json.dumps({"action": r["action"],
                                         "label": r["label"],
                                         "originally_by": r["actor"]}),
                             r["entry_id"]))
            done.append({"entry_id": r["entry_id"], "was": r["label"],
                         "result": what})
        except HTTPException as e:
            refused.append({"entry_id": r["entry_id"], "why": e.detail})

    return {"undone": done, "refused": refused,
            "count": len(done)}
