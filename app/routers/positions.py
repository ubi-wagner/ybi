"""Working positions: adopting one, writing against one, recommending against
one.

The 757 judgments on the 2025 record were written by
`scripts/classification_log.py --apply` through the real API signed in as the
controller — which is the right way for a script to write, and which leaves
every one of them reading `decided_by = 'Tom Metzinger'` across six seconds.
`083` gave the schema a word for what kind of act that was. These are the
doors onto it, and there are three of them because there are three acts:

  * **adopting** — the controller reading a working position and making it his
    own judgment. It moves no figure, by construction: the confirmation is a
    row in its own table and touches no judgment, so adopting under a seal
    leaves the seal reproducing and the rate exactly where it was. That is the property `POST
    /api/timesheet/adopt` has one level down, and it is the reason the
    exercise is honest — if adopting moved the rate, the rate would depend on
    who had got round to reviewing.

  * **noting** — anybody who may read the cost record writing down what they
    see. Two kinds, and the kind is the visibility: a RECORD note is part of
    the record and travels in the audit package; a WORKING note is
    deliberative and does not. **Its count is disclosed to every reader
    regardless.** Undisclosed is a position anybody can take; concealed is not
    one, and a switch that can be flipped after somebody asks for the file is
    the difference.

  * **recommending** — somebody who is not the controller saying *this is
    classified wrong, here is what it should be, here is why*. It is never a
    decision and never becomes one: accepting it records a fresh judgment
    through `classify.decide`, under the controller's name, citing this row.
    There is one door onto the cost record and this is not a second one.

Recommending and noting take `require_reader` rather than a portfolio, which
departs from `062` on purpose. That migration offered its Recommend button
only to portfolio holders because a worklist item is work to *do* and the
auditor does none of it. This is the opposite case: an auditor requiring a new
classification out of a sealed account is the whole exercise, and a system
where the auditor cannot record the ask has put it back in an email.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import (Actor, Portfolio, Role, current_actor,
                      require_controller, require_reader)
from app.db import one, query, transaction
from app.statelock import turn
from app.vocab import FederalTreatment, Function990, Pool
from app.routers.classify import DecideIn, decide

router = APIRouter(prefix="/positions", tags=["positions"],
                   dependencies=[Depends(require_reader)])


def reads_working_notes(actor: Actor) -> bool:
    """Whether this reader is shown the body of a deliberative note.

    The organisation's own decision-makers — whoever holds CONTROLLER, and the
    administrator — plus the person who wrote it. Deliberately not everybody
    who may read the cost record: the auditor reads the record and is the
    party a working note is *not* addressed to, and a visibility setting that
    the auditor can see through is not one.

    The count is a different question and is answered to everybody, in
    `v_classification_standing`.
    """
    return actor.holds(Portfolio.CONTROLLER) or actor.role is Role.ORG_ADMIN


# ------------------------------------------------------------- reading ------

@router.get("")
def positions(period: str = "2025",
              state: str = Query("all", pattern="^(all|unadopted|adopted)$"),
              decision_id: str | None = None,
              limit: int = 200, offset: int = 0) -> dict:
    """Where every group stands. `total` is read off the same view the rows
    come from rather than counted on the screen, so paging cannot make the
    count disagree with itself.

    `decision_id` narrows it to one group, which is what the notes panel asks
    for. The panel loads the position rather than being handed whichever
    fields its parent happened to have: a first draft passed a partial object
    through and printed a heading with nothing under it, because the
    recommendation list carries the recommender's note and not the rationale.
    """
    where = "period = %s"
    args: list = [period]
    if decision_id:
        where += " AND decision_id = %s"
        args.append(decision_id)
    if state == "unadopted":
        where += " AND is_working_position AND NOT adopted"
    elif state == "adopted":
        where += " AND adopted"
    total = one(f"SELECT count(*) AS n FROM v_classification_standing "
                f"WHERE {where}", tuple(args))["n"]
    rows = query(f"""SELECT * FROM v_classification_standing WHERE {where}
                     ORDER BY adopted, account, payee
                     LIMIT %s OFFSET %s""", tuple(args) + (limit, offset))
    return {"period": period, "total": total, "shown": len(rows),
            "positions": [dict(r) for r in rows]}


@router.get("/review")
def review(period: str = "2025") -> dict:
    """The controller's list. Recommendations first — somebody is waiting on
    each of those — then the working positions nobody has adopted."""
    rows = query("""SELECT * FROM v_controller_review WHERE period = %s
                     ORDER BY item DESC, raised_at""", (period,))
    items = [dict(r) for r in rows]
    return {
        "period": period,
        "recommendations": [i for i in items if i["item"] == "RECOMMENDATION"],
        "unconfirmed": [i for i in items if i["item"] == "UNCONFIRMED"],
    }


# ------------------------------------------------------------- adopting -----

class ConfirmIn(BaseModel):
    decision_ids: list[str] = Field(..., min_length=1)
    note: str = ""


@router.post("/confirm")
def confirm(body: ConfirmIn, period: str = "2025",
            actor: Actor = Depends(require_controller)) -> dict:
    """Adopt one or more working positions as the controller's own judgment.

    Nothing about the cost moves. The seal is untouched, so a rate computed
    from the set before this call reproduces after it — which is checked by
    `tests/test_restaging.py` rather than asserted here.
    """
    confirmed, already, missing = 0, 0, 0
    with turn(period) as cur:
        for did in body.decision_ids:
            cur.execute("""SELECT decision_id, origin, adopted, scope
                             FROM v_classification_standing
                            WHERE decision_id = %s AND period = %s""",
                        (did, period))
            st = cur.fetchone()
            if st is None:
                missing += 1
                continue
            if st["adopted"]:
                already += 1
                continue
            cur.execute("""INSERT INTO position_confirmation
                             (decision_id, confirmed_by, note)
                           VALUES (%s,%s,%s)""",
                        (did, actor.actor_id, body.note))
            record(actor, "POSITION_CONFIRM", "decision", did,
                   after={"scope": st["scope"]}, reason=body.note, cursor=cur)
            confirmed += 1
    if confirmed == 0:
        # A write that landed on nothing is never reported in the tone used
        # for success. The screen has the counts; the status says which case.
        raise HTTPException(409, {
            "error": "NOTHING_CONFIRMED",
            "already": already, "missing": missing,
            "message": (f"Nothing was adopted — {already} of those were "
                        f"already adopted and {missing} are not working "
                        f"positions on {period}. Reload and try again.")})
    return {"confirmed": confirmed, "already": already, "missing": missing}


class WithdrawIn(BaseModel):
    decision_id: str
    reason: str


@router.post("/confirm/withdraw")
def withdraw_confirmation(body: WithdrawIn, period: str = "2025",
                          actor: Actor = Depends(require_controller)) -> dict:
    """Take a signature back off a working position, with a reason.

    `rate_certification`'s shape, for the same reason: a position adopted and
    then unadopted is part of the trail, not an edit.
    """
    if len(body.reason.strip()) < 12:
        raise HTTPException(422, "Say why the signature is coming off. A "
                                 "withdrawal with no reason is the position "
                                 "changing with nobody accountable for it.")
    with turn(period) as cur:
        cur.execute("""SELECT confirmation_id FROM v_position_confirmed
                        WHERE decision_id = %s AND live""", (body.decision_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(409, "No signature stands on that position.")
        cur.execute("""UPDATE position_confirmation
                          SET withdrawn_at = now(), withdrawn_by = %s,
                              withdrawn_reason = %s
                        WHERE confirmation_id = %s""",
                    (actor.actor_id, body.reason, row["confirmation_id"]))
        record(actor, "POSITION_CONFIRM_WITHDRAW", "decision", body.decision_id,
               reason=body.reason, cursor=cur)
    return {"withdrawn": True, "decision_id": body.decision_id}


# --------------------------------------------------------------- notes ------

class NoteIn(BaseModel):
    scope: str | None = None
    decision_id: str | None = None
    kind: str = Field("RECORD", pattern="^(RECORD|WORKING)$")
    body: str


def _scope_of(cur, decision_id: str, period: str) -> str:
    cur.execute("""SELECT scope FROM v_classification_standing
                    WHERE decision_id = %s AND period = %s""",
                (decision_id, period))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(404, "No live classification with that id on "
                                 f"{period}.")
    return row["scope"]


@router.get("/notes")
def notes(scope: str | None = None, decision_id: str | None = None,
          period: str = "2025",
          actor: Actor = Depends(current_actor)) -> dict:
    """The notes on a group.

    A WORKING note the caller may not read comes back with its body withheld
    and everything else intact — who wrote it and when. Dropping the row would
    make three notes look like one, which is concealment; this is disclosure
    without the contents.
    """
    if not scope and not decision_id:
        raise HTTPException(422, "Name a group: scope or decision_id.")
    with transaction() as cur:
        if not scope:
            scope = _scope_of(cur, decision_id, period)
        cur.execute("""SELECT n.note_id, n.kind, n.body, n.written_at,
                              n.written_by, a.display_name AS author,
                              n.redesignated_at, n.redesignated_reason,
                              w.display_name AS redesignated_by
                         FROM classification_note n
                         JOIN actor a ON a.actor_id = n.written_by
                         LEFT JOIN actor w ON w.actor_id = n.redesignated_by
                        WHERE n.period = %s AND n.scope = %s
                        ORDER BY n.written_at""", (period, scope))
        rows = [dict(r) for r in cur.fetchall()]
    may = reads_working_notes(actor)
    out = []
    for r in rows:
        mine = str(r["written_by"]) == str(actor.actor_id)
        readable = r["kind"] == "RECORD" or may or mine
        out.append({**{k: v for k, v in r.items() if k != "written_by"},
                    "body": r["body"] if readable else None,
                    "withheld": not readable})
    return {"scope": scope, "period": period, "notes": out,
            "withheld": sum(1 for r in out if r["withheld"])}


@router.post("/notes")
def write_note(body: NoteIn, period: str = "2025",
               actor: Actor = Depends(require_reader)) -> dict:
    """Write a note against a group. Anybody who may read the cost record may
    write one — including the auditor, whose observations are the reason this
    register exists."""
    if len(body.body.strip()) < 12:
        raise HTTPException(422, "A note under twelve characters is not one. "
                                 "Say what you saw.")
    with turn(period) as cur:
        scope = body.scope
        about = body.decision_id
        if not scope:
            if not about:
                raise HTTPException(422, "Name a group: scope or decision_id.")
            scope = _scope_of(cur, about, period)
        cur.execute("""INSERT INTO classification_note
                         (period, scope, kind, body, written_by, about_decision)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING note_id""",
                    (period, scope, body.kind, body.body, actor.actor_id, about))
        note_id = cur.fetchone()["note_id"]
        record(actor, "CLASSIFICATION_NOTE", "decision", about or scope,
               after={"note_id": str(note_id), "kind": body.kind,
                      "scope": scope},
               reason=body.body[:500], cursor=cur)
    return {"note_id": str(note_id), "scope": scope, "kind": body.kind}


class RedesignateIn(BaseModel):
    kind: str = Field(..., pattern="^(RECORD|WORKING)$")
    reason: str


@router.patch("/notes/{note_id}")
def redesignate(note_id: str, body: RedesignateIn, period: str = "2025",
                actor: Actor = Depends(require_reader)) -> dict:
    """Change what a note discloses.

    The setting the record needs and the one place it could go wrong. It is
    never silent: the reason is required, the row keeps who changed it and
    when, and `audit_log` holds every change rather than only the last. A
    visibility switch somebody can flip the day after an auditor asks for the
    file, leaving no trace, is worse than having no note at all.
    """
    if len(body.reason.strip()) < 12:
        raise HTTPException(422, "Say why this is changing what it discloses.")
    with turn(period) as cur:
        cur.execute("""SELECT note_id, kind, scope, written_by
                         FROM classification_note WHERE note_id = %s""",
                    (note_id,))
        n = cur.fetchone()
        if n is None:
            raise HTTPException(404, "No note with that id.")
        mine = str(n["written_by"]) == str(actor.actor_id)
        if not mine and not actor.holds(Portfolio.CONTROLLER):
            raise HTTPException(403, "A note is somebody's own words. Its "
                                     "author or the controller decides what "
                                     "it discloses.")
        if n["kind"] == body.kind:
            raise HTTPException(409, f"That note is already {body.kind}.")
        cur.execute("""UPDATE classification_note
                          SET kind = %s, redesignated_at = now(),
                              redesignated_by = %s, redesignated_reason = %s
                        WHERE note_id = %s""",
                    (body.kind, actor.actor_id, body.reason, note_id))
        record(actor, "CLASSIFICATION_NOTE_REDESIGNATE", "decision", n["scope"],
               before={"kind": n["kind"]}, after={"kind": body.kind,
                                                  "note_id": note_id},
               reason=body.reason, cursor=cur)
    return {"note_id": note_id, "kind": body.kind}


# ----------------------------------------------------- recommendations ------

class RecommendIn(BaseModel):
    decision_id: str
    pool: Pool
    function_990: Function990
    federal: FederalTreatment
    objective_id: str | None = None
    note: str


@router.post("/recommend")
def recommend(body: RecommendIn, period: str = "2025",
              actor: Actor = Depends(require_reader)) -> dict:
    """Recommend a different classification for a group.

    It writes nothing to the cost record — not a decision, not a pool, not a
    dollar. `062` refused to express a helper's suggestion as a `PROPOSED`
    decision row because `PROPOSED` already means *YBI has put this to a
    sponsor and they have not answered*; this is its own register for the same
    reason.

    `saw_decision` is the position it was written against, so a recommendation
    that has been overtaken says so on the controller's list rather than being
    applied to whatever is there now.

    A controller may recommend, which is worth saying because the first draft
    refused it: Heidi and Stephanie both hold CONTROLLER and could simply
    reclassify, and a rule that forced them to would turn *flag this for Tom*
    into *overrule Tom*. What the record actually needs is the narrower rule,
    and it is in the schema: nobody disposes of their own recommendation.
    """
    if (body.pool == Pool.DIRECT) != bool(body.objective_id):
        raise HTTPException(422, "Direct cost names a cost objective; pooled "
                                 "cost must not carry one. The queue would "
                                 "refuse this, so it is refused here.")
    with turn(period) as cur:
        scope = _scope_of(cur, body.decision_id, period)
        cur.execute("""SELECT 1 FROM reclass_recommendation
                        WHERE period = %s AND scope = %s
                          AND recommended_by = %s AND disposition = 'OPEN'""",
                    (period, scope, actor.actor_id))
        if cur.fetchone():
            raise HTTPException(409, "You already have an open recommendation "
                                     "on that group. Withdraw it and make the "
                                     "one you mean; two from one person reads "
                                     "as two people having looked.")
        cur.execute("""INSERT INTO reclass_recommendation
                         (period, scope, pool, function_990, federal,
                          objective_id, note, recommended_by, saw_decision)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING rec_id""",
                    (period, scope, body.pool.value, body.function_990.value,
                     body.federal.value, body.objective_id, body.note,
                     actor.actor_id, body.decision_id))
        rec_id = cur.fetchone()["rec_id"]
        record(actor, "RECLASS_RECOMMEND", "decision", body.decision_id,
               after={"rec_id": str(rec_id), "pool": body.pool.value,
                      "function_990": body.function_990.value,
                      "federal": body.federal.value,
                      "objective_id": body.objective_id, "scope": scope},
               reason=body.note[:500], cursor=cur)
    return {"rec_id": str(rec_id), "scope": scope, "disposition": "OPEN"}


class DisposeIn(BaseModel):
    reason: str = ""
    #: The rationale the resulting judgment carries. Accepting writes a real
    #: decision and a decision states its own reasons; without this the
    #: judgment would inherit the recommender's words under the controller's
    #: name, which is not what either of them said.
    rationale: str = ""
    citation: str | None = None
    grade: str = "CORROBORATED"


def _rec(cur, rec_id: str, period: str) -> dict:
    cur.execute("""SELECT * FROM reclass_recommendation
                    WHERE rec_id = %s AND period = %s""", (rec_id, period))
    r = cur.fetchone()
    if r is None:
        raise HTTPException(404, "No recommendation with that id.")
    if r["disposition"] != "OPEN":
        raise HTTPException(409, f"That recommendation is already "
                                 f"{r['disposition'].lower()}.")
    return dict(r)


@router.post("/recommendations/{rec_id}/decline")
def decline(rec_id: str, body: DisposeIn, period: str = "2025",
            actor: Actor = Depends(require_controller)) -> dict:
    """Decline a recommendation, with a reason.

    The reason is required and accepting's is not, because accepting says why
    by producing a judgment that carries its own rationale. A declined
    recommendation is the only one of the two where the record would otherwise
    hold the ask and not the answer.
    """
    if len(body.reason.strip()) < 12:
        raise HTTPException(422, "Say why. Somebody went and looked at this, "
                                 "and a refusal with no reason is the ask "
                                 "disappearing.")
    with turn(period) as cur:
        r = _rec(cur, rec_id, period)
        cur.execute("""UPDATE reclass_recommendation
                          SET disposition = 'DECLINED', disposed_by = %s,
                              disposed_at = now(), disposition_reason = %s
                        WHERE rec_id = %s""", (actor.actor_id, body.reason,
                                               rec_id))
        record(actor, "RECLASS_DECLINE", "reclass_recommendation", rec_id,
               before={"scope": r["scope"], "pool": r["pool"]},
               reason=body.reason, cursor=cur)
    return {"rec_id": rec_id, "disposition": "DECLINED"}


@router.post("/recommendations/{rec_id}/withdraw")
def withdraw_recommendation(rec_id: str, body: DisposeIn, period: str = "2025",
                            actor: Actor = Depends(require_reader)) -> dict:
    """The person who made a recommendation taking it back. Only them — for
    anybody else the act is declining it, which is a different thing and says
    so on the record."""
    with turn(period) as cur:
        r = _rec(cur, rec_id, period)
        if str(r["recommended_by"]) != str(actor.actor_id):
            raise HTTPException(403, "Only the person who made a "
                                     "recommendation withdraws it.")
        cur.execute("""UPDATE reclass_recommendation
                          SET disposition = 'WITHDRAWN', disposed_by = %s,
                              disposed_at = now(), disposition_reason = %s
                        WHERE rec_id = %s""",
                    (actor.actor_id, body.reason or None, rec_id))
        record(actor, "RECLASS_WITHDRAW", "reclass_recommendation", rec_id,
               reason=body.reason, cursor=cur)
    return {"rec_id": rec_id, "disposition": "WITHDRAWN"}


@router.post("/recommendations/{rec_id}/accept")
def accept(rec_id: str, body: DisposeIn, period: str = "2025",
           actor: Actor = Depends(require_controller)) -> dict:
    """Accept a recommendation: record the judgment it proposes.

    It goes through `classify.decide` rather than writing a decision here.
    That route holds the seal check, the stale-screen check, the supersession,
    the line-level fan-out and the proof that the lines landed — and a second
    path to the cost record is a second place all of that can be missing. One
    door.

    So this is refused under a seal, and refused *by the seal*, in the words
    the seal uses. Unsealing is a deliberate act with a reason, which is the
    whole point of the guarantee: the auditor's ask does not get to move a
    sealed judgment quietly.
    """
    with transaction() as cur:
        r = _rec(cur, rec_id, period)
        cur.execute("""SELECT account, payee, decision_id
                         FROM v_classification_standing
                        WHERE period = %s AND scope = %s""",
                    (period, r["scope"]))
        st = cur.fetchone()
        if st is None:
            raise HTTPException(409, "That group no longer carries a live "
                                     "judgment. Nothing was recorded.")
        if r["saw_decision"] and str(r["saw_decision"]) != str(st["decision_id"]):
            raise HTTPException(409, {
                "error": "POSITION_MOVED",
                "message": ("The classification has changed since this was "
                            "recommended, so accepting it would apply a "
                            "proposal to something it was never about. "
                            "Decline it and ask for a fresh one.")})
        group_key = f"{st['account']}\x1f{st['payee'] or ''}"
        live_id = str(st["decision_id"])

    out = decide(DecideIn(
        group_keys=[group_key],
        pool=Pool(r["pool"]),
        function_990=Function990(r["function_990"]),
        federal=FederalTreatment(r["federal"]),
        objective_id=r["objective_id"],
        grade=body.grade,
        rationale=(body.rationale.strip()
                   or f"Accepted the recommendation of {r['recommended_at']:%d %b %Y}: "
                      f"{r['note']}")[:2000],
        citation=body.citation,
        based_on={group_key: live_id},
    ), period=period, actor=actor)

    with transaction() as cur:
        # The judgment this ask produced, named on the row that asked for it.
        # A recommendation that says it was accepted and does not say what
        # came of it is the citation-with-no-document shape — and the reader
        # who wants it is the person who raised it.
        cur.execute("""SELECT decision_id FROM v_classification_standing
                        WHERE period = %s AND scope = %s""",
                    (period, r["scope"]))
        made = cur.fetchone()
        cur.execute("""UPDATE reclass_recommendation
                          SET disposition = 'ACCEPTED', disposed_by = %s,
                              disposed_at = now(), disposition_reason = %s,
                              resulting_decision = %s
                        WHERE rec_id = %s AND disposition = 'OPEN'""",
                    (actor.actor_id, body.reason or None,
                     made["decision_id"] if made else None, rec_id))
        record(actor, "RECLASS_ACCEPT", "reclass_recommendation", rec_id,
               after={"scope": r["scope"], "pool": r["pool"]},
               reason=body.reason, cursor=cur)
    return {"rec_id": rec_id, "disposition": "ACCEPTED", "decision": out}
