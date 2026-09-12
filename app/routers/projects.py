"""Setting a piece of work up, and writing down who is doing what by when.

Read across from the RFP pipeline (`ubi-wagner/govwin`), which is the other
half of the same engagement: it wins the work, this system accounts for it.
Migration `059` says what was taken from its post-award module and — at more
length — what was deliberately not, because the register already exists here
under another name.

**Setting up is one act.** Opening a charge code, saying which contract it
works under, naming who may charge it and writing down the first things to do
were four separate calls in four places, and a code with nobody on it is a
code with the authority gate switched off. One call does all of it, inside
one `turn(period)`, through every rule the separate routes already enforce —
nobody assigns themselves, a federal code carries its CFDA, an assignment
names somebody who can book time.

The gate is `require_project`, which is what the charge-code routes take. A
project is the project manager's job and the controller's, and `CONTROLLER`
reaches everything by definition rather than by exception.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_project, require_reader
from app.db import one, query
from app.settings import settings
from app.statelock import turn

router = APIRouter(prefix="/projects", tags=["projects"],
                   dependencies=[Depends(require_reader)])


class PersonIn(BaseModel):
    employee_key: str = Field(min_length=1, max_length=60)
    role_on_project: str = ""
    reason: str = Field(min_length=1)
    opens_on: dt.date | None = None
    closes_on: dt.date | None = None


class TodoSeed(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = ""
    assignee: str | None = None
    due_on: dt.date | None = None


class ProjectIn(BaseModel):
    #: The charge code. It *is* the project — see `059`.
    objective_id: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    summary: str = ""
    award_id: str | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    #: Only used where the code does not exist yet.
    label: str = ""
    objective_type: str = "PROGRAM"
    is_federal: bool = False
    cfda: str | None = None
    people: list[PersonIn] = []
    todos: list[TodoSeed] = []
    reason: str = Field(min_length=1)


class StatusIn(BaseModel):
    status: str
    note: str = ""


class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = ""
    objective_id: str | None = None
    assignee: str | None = None
    due_on: dt.date | None = None
    worklist_kind: str | None = None
    worklist_entity_id: str | None = None
    verification_ref: str | None = None


class TodoPatch(BaseModel):
    """What may change about a todo, and nothing else.

    The title and what it is about are not here on purpose. A todo whose
    title can be rewritten is one nobody can be held to — the same reason a
    reply from a spreadsheet may never touch `display_name`.
    """
    assignee: str | None = None
    due_on: dt.date | None = None
    status: str | None = None
    blocked_reason: str | None = None
    detail: str | None = None


def _can_book_time(cur, employee_key: str) -> bool:
    """The same three registers `POST /contracts/.../authorise` reads."""
    for sql in ("SELECT 1 AS ok FROM labor_allocation WHERE employee_key = %s LIMIT 1",
                "SELECT 1 AS ok FROM employment WHERE employee_key = %s LIMIT 1",
                "SELECT 1 AS ok FROM actor WHERE employee_key = %s LIMIT 1"):
        cur.execute(sql, (employee_key,))
        if cur.fetchone():
            return True
    return False


@router.get("")
def list_projects(period: str | None = None) -> dict:
    period = period or settings.period
    return {"period": period,
            "projects": query("""SELECT * FROM v_project_overview
                                  ORDER BY status, name""")}


@router.post("", status_code=201)
def open_project(body: ProjectIn, period: str | None = None,
                 actor: Actor = Depends(require_project)) -> dict:
    """Open a charge code, hang it off its contract, put people on it and
    write down the first things to do — in one act, under one lock."""
    period = period or settings.period
    made_code = False
    assigned: list[str] = []
    todos = 0

    with turn(period) as cur:
        # Everything this depends on is read inside the turn, because another
        # project manager may be opening the same code at this instant.
        cur.execute("SELECT 1 FROM project WHERE objective_id = %s",
                    (body.objective_id,))
        if cur.fetchone():
            raise HTTPException(
                409, f"{body.objective_id} is already set up as a project.")

        cur.execute("""SELECT objective_id, is_federal, cfda
                         FROM cost_objective WHERE objective_id = %s""",
                    (body.objective_id,))
        code = cur.fetchone()
        if not code:
            if body.is_federal and not body.cfda:
                raise HTTPException(
                    422, "A federal charge code needs its CFDA number. "
                         "Without it the award cannot reach the SEFA, and the "
                         "Single Audit scope is decided by what is on the "
                         "SEFA.")
            cur.execute("""INSERT INTO cost_objective
                             (objective_id, period, label, objective_type,
                              is_federal, is_final, cfda)
                           VALUES (%s,%s,%s,%s,%s,true,%s)""",
                        (body.objective_id, period,
                         body.label or body.name, body.objective_type,
                         body.is_federal, body.cfda))
            record(actor, "CHARGE_CODE_OPEN", "cost_objective",
                   body.objective_id,
                   after={"label": body.label or body.name,
                          "is_federal": body.is_federal, "cfda": body.cfda},
                   reason=body.reason, cursor=cur)
            made_code = True

        if body.award_id:
            cur.execute("SELECT 1 FROM award WHERE award_id = %s",
                        (body.award_id,))
            if not cur.fetchone():
                raise HTTPException(404, f"No award {body.award_id}.")

        cur.execute("""INSERT INTO project (objective_id, award_id, name,
                                            summary, starts_on, ends_on,
                                            opened_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (body.objective_id, body.award_id, body.name, body.summary,
                     body.starts_on, body.ends_on, actor.display_name))
        record(actor, "PROJECT_OPEN", "project", body.objective_id,
               after={"name": body.name, "award_id": body.award_id,
                      "starts_on": str(body.starts_on) if body.starts_on else None,
                      "ends_on": str(body.ends_on) if body.ends_on else None},
               reason=body.reason, cursor=cur)

        for person in body.people:
            # Nobody assigns themselves — the rule the portfolios follow, and
            # it holds here for the same reason: an assignment is a statement
            # by one person about another, and one made by its own
            # beneficiary says nothing.
            if actor.employee_key and actor.employee_key == person.employee_key:
                raise HTTPException(
                    403, "Nobody puts themselves on a charge code. Ask the "
                         "project manager or the controller.")
            if not _can_book_time(cur, person.employee_key):
                raise HTTPException(
                    422, f"{person.employee_key} is on no payroll register "
                         f"and no account. A charge code is authorised to "
                         f"somebody who can book time to it.")
            cur.execute("""INSERT INTO charge_authority
                             (period, objective_id, employee_key,
                              role_on_project, granted_by, reason, opens_on,
                              closes_on)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (period, body.objective_id, person.employee_key,
                         person.role_on_project, actor.display_name,
                         person.reason, person.opens_on, person.closes_on))
            record(actor, "CHARGE_AUTHORISE", "cost_objective",
                   body.objective_id,
                   after={"employee_key": person.employee_key,
                          "role": person.role_on_project},
                   reason=person.reason, cursor=cur)
            assigned.append(person.employee_key)

        for seed in body.todos:
            cur.execute("""INSERT INTO todo (period, objective_id, title,
                                             detail, assignee, due_on,
                                             opened_by, sort_index)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (period, body.objective_id, seed.title, seed.detail,
                         seed.assignee, seed.due_on, actor.display_name, todos))
            todos += 1
        if todos:
            record(actor, "TODO_OPEN", "project", body.objective_id,
                   after={"todos": todos}, reason=body.reason, cursor=cur)

    return {"objective_id": body.objective_id, "charge_code_created": made_code,
            "people": assigned, "todos": todos,
            # Said plainly: an unmanned code has its gate switched off, which
            # is right for reconstructing 2025 and wrong for work starting now.
            "gate_live": bool(assigned)}


@router.get("/{objective_id}")
def project(objective_id: str, period: str | None = None) -> dict:
    period = period or settings.period
    head = one("SELECT * FROM v_project_overview WHERE objective_id = %s",
               (objective_id,))
    if not head:
        raise HTTPException(404, f"No project on {objective_id}.")
    return {
        "period": period,
        "project": head,
        # Read from the registers that already hold these. A project screen
        # that kept its own copy of who may charge a code would be the second
        # register this whole design exists to avoid.
        "people": query("""SELECT employee_key, role_on_project, opens_on,
                                  closes_on, granted_by, granted_at, reason
                             FROM v_charge_authorised
                            WHERE period = %s AND objective_id = %s
                            ORDER BY employee_key""", (period, objective_id)),
        "todos": query("""SELECT * FROM v_todo_live WHERE objective_id = %s
                           ORDER BY (due_on IS NULL), due_on, sort_index""",
                       (objective_id,)),
        "done": query("""SELECT todo_id, title, assignee, done_at, done_by
                           FROM todo
                          WHERE objective_id = %s AND status = 'DONE'
                          ORDER BY done_at DESC LIMIT 20""", (objective_id,)),
        "terms": query("""SELECT t.term_key, t.term_value, t.citation,
                                 c.state AS citation_state
                            FROM award_term t
                            LEFT JOIN v_award_citation_check c
                                   ON c.award_id = t.award_id
                                  AND c.term_key = t.term_key
                           WHERE t.award_id = (SELECT award_id FROM project
                                                WHERE objective_id = %s)
                           ORDER BY t.term_key""", (objective_id,)),
    }


@router.post("/{objective_id}/status")
def set_status(objective_id: str, body: StatusIn,
               actor: Actor = Depends(require_project)) -> dict:
    """Move a project along. Closing needs a sentence, like every other
    judgment recorded here."""
    if body.status not in ("PLANNING", "ACTIVE", "CLOSING", "CLOSED"):
        raise HTTPException(422, "A project is PLANNING, ACTIVE, CLOSING or "
                                 "CLOSED.")
    period = settings.period
    with turn(period) as cur:
        cur.execute("""SELECT status, name FROM project
                        WHERE objective_id = %s""", (objective_id,))
        was = cur.fetchone()
        if not was:
            raise HTTPException(404, f"No project on {objective_id}.")
        if body.status == "CLOSED":
            if len(body.note.strip()) < 10:
                raise HTTPException(
                    422, "Closing a project says what it delivered and what "
                         "is left — in a sentence, not a word. The schema "
                         "asks for ten characters and a reader asks for more.")
            cur.execute("""SELECT count(*) AS n FROM todo
                            WHERE objective_id = %s AND status <> 'DONE'""",
                        (objective_id,))
            outstanding = cur.fetchone()["n"]
            if outstanding:
                raise HTTPException(
                    409, f"{outstanding} thing(s) on this project are still "
                         f"open. Finish them or say in the closeout why they "
                         f"are being left — a project closed over an open "
                         f"list is a list nobody will look at again.")
            cur.execute("""UPDATE project SET status = 'CLOSED',
                                  closed_at = now(), closed_by = %s,
                                  closeout_note = %s
                            WHERE objective_id = %s""",
                        (actor.display_name, body.note.strip(), objective_id))
        else:
            cur.execute("""UPDATE project SET status = %s, closed_at = NULL,
                                  closed_by = NULL
                            WHERE objective_id = %s""",
                        (body.status, objective_id))
        record(actor, "PROJECT_STATUS", "project", objective_id,
               before={"status": was["status"]}, after={"status": body.status},
               reason=body.note.strip() or f"moved to {body.status}",
               cursor=cur)
    return {"objective_id": objective_id, "status": body.status}


# ── The list a person can actually write ──────────────────────────────

todos = APIRouter(prefix="/todos", tags=["todos"],
                  dependencies=[Depends(require_reader)])


@todos.get("")
def list_todos(period: str | None = None, assignee: str | None = None,
               mine: bool = False, actor: Actor = Depends(require_reader)) -> dict:
    period = period or settings.period
    who = actor.employee_key if mine else assignee
    rows = query("""SELECT * FROM v_todo_live
                     WHERE period = %s
                       AND (%s::text IS NULL OR assignee = %s)
                     ORDER BY overdue DESC, (due_on IS NULL), due_on,
                              sort_index""", (period, who, who))
    return {"period": period, "assignee": who, "todos": rows,
            "overdue": sum(1 for r in rows if r["overdue"]),
            "unassigned": sum(1 for r in rows if not r["assignee"])}


@todos.post("", status_code=201)
def open_todo(body: TodoIn, period: str | None = None,
              actor: Actor = Depends(require_project)) -> dict:
    period = period or settings.period
    if (body.worklist_kind is None) != (body.worklist_entity_id is None):
        raise HTTPException(422, "Naming a worklist item takes both its kind "
                                 "and its entity. The schema says the same.")
    with turn(period) as cur:
        if body.objective_id:
            cur.execute("SELECT 1 FROM project WHERE objective_id = %s",
                        (body.objective_id,))
            if not cur.fetchone():
                raise HTTPException(
                    404, f"No project on {body.objective_id}. A todo about "
                         f"the engagement rather than a project carries no "
                         f"charge code at all.")
        cur.execute("""INSERT INTO todo (period, objective_id, title, detail,
                                         assignee, due_on, worklist_kind,
                                         worklist_entity_id, verification_ref,
                                         opened_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING todo_id""",
                    (period, body.objective_id, body.title, body.detail,
                     body.assignee, body.due_on, body.worklist_kind,
                     body.worklist_entity_id, body.verification_ref,
                     actor.display_name))
        todo_id = str(cur.fetchone()["todo_id"])
        record(actor, "TODO_OPEN", "todo", todo_id,
               after={"title": body.title, "assignee": body.assignee,
                      "due_on": str(body.due_on) if body.due_on else None,
                      "objective_id": body.objective_id,
                      "worklist_kind": body.worklist_kind},
               reason=body.detail or body.title, cursor=cur)
    return {"todo_id": todo_id}


@todos.patch("/{todo_id}")
def change_todo(todo_id: str, body: TodoPatch,
                actor: Actor = Depends(require_project)) -> dict:
    """Assign it, date it, finish it, or say what is blocking it."""
    period = settings.period
    with turn(period) as cur:
        cur.execute("""SELECT status, assignee, due_on, title
                         FROM todo WHERE todo_id = %s::uuid""", (todo_id,))
        was = cur.fetchone()
        if not was:
            raise HTTPException(404, "No such todo.")
        if was["status"] == "DONE" and body.status != "OPEN":
            raise HTTPException(
                409, "That is already finished. Reopen it first if it turned "
                     "out not to be — a finished thing quietly becoming "
                     "unfinished is how a list stops being believed.")

        status = body.status or was["status"]
        if status not in ("OPEN", "DONE", "BLOCKED"):
            raise HTTPException(422, "A todo is OPEN, DONE or BLOCKED.")
        if status == "BLOCKED" and not (body.blocked_reason or "").strip():
            raise HTTPException(
                422, "Blocked on what? A blocked item with no reason is an "
                     "item nobody can unblock.")

        cur.execute("""UPDATE todo
                          SET assignee = COALESCE(%s, assignee),
                              due_on = COALESCE(%s, due_on),
                              detail = COALESCE(%s, detail),
                              status = %s,
                              blocked_reason = CASE WHEN %s = 'BLOCKED'
                                   THEN %s ELSE NULL END,
                              done_at = CASE WHEN %s = 'DONE'
                                   THEN COALESCE(done_at, now()) END,
                              done_by = CASE WHEN %s = 'DONE'
                                   THEN COALESCE(done_by, %s) END
                        WHERE todo_id = %s::uuid""",
                    (body.assignee, body.due_on, body.detail, status,
                     status, (body.blocked_reason or "").strip() or None,
                     status, status, actor.display_name, todo_id))
        record(actor, "TODO_CHANGE", "todo", todo_id,
               before={"status": was["status"], "assignee": was["assignee"]},
               after={"status": status, "assignee": body.assignee or was["assignee"],
                      "due_on": str(body.due_on) if body.due_on else None},
               reason=(body.blocked_reason or "").strip() or was["title"],
               cursor=cur)
    return {"todo_id": todo_id, "status": status}


@todos.get("/covering")
def covering(period: str | None = None) -> dict:
    """Of everything the system says is outstanding, what has anybody taken.

    `v_worklist` has always known what is outstanding and `v_worklist_owned`
    added which portfolio can act on it. Neither could say **who** or **by
    when**, because nothing could write that down. This is that answer.
    """
    period = period or settings.period
    rows = query("""SELECT * FROM v_worklist_covered WHERE period = %s
                     ORDER BY taken, severity, kind""", (period,))
    return {"period": period, "items": rows,
            "outstanding": len(rows),
            "taken": sum(1 for r in rows if r["taken"]),
            "nobody_has_it": sum(1 for r in rows if not r["taken"])}
