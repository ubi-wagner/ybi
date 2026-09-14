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
from app.auth import (Actor, require_controller, require_project,
                      require_reader)
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
    #: An account, not a payroll key — see `060`. Tom holds CONTROLLER and is
    #: not on the payroll register, so a todo keyed to an employee could
    #: never have reached the one person the handoff exists to reach.
    assignee_actor: str | None = None
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
    assignee_actor: str | None = None
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
    assignee_actor: str | None = None
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
                                             detail, assignee_actor, due_on,
                                             opened_by, sort_index)
                           VALUES (%s,%s,%s,%s,%s::uuid,%s,%s,%s)""",
                        (period, body.objective_id, seed.title, seed.detail,
                         seed.assignee_actor, seed.due_on,
                         actor.display_name, todos))
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
        "done": query("""SELECT t.todo_id, t.title, who.display_name AS assignee,
                                t.done_at, t.done_by
                           FROM todo t
                           LEFT JOIN actor who ON who.actor_id = t.assignee_actor
                          WHERE t.objective_id = %s AND t.status = 'DONE'
                          ORDER BY t.done_at DESC LIMIT 20""", (objective_id,)),
        # The invoices already on file for this objective — what a claim is
        # settled *against*. No route in this system raises one.
        "invoices": query("""SELECT invoice_id, invoice_number, invoice_date,
                                    total, status
                               FROM invoice
                              WHERE objective_id = %s
                              ORDER BY invoice_date, seq""", (objective_id,)),
        "claims": query("""SELECT * FROM v_project_claim
                            WHERE objective_id = %s
                            ORDER BY approved_at DESC""", (objective_id,)),
        "work": one("SELECT * FROM v_project_work WHERE objective_id = %s",
                    (objective_id,)),
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


# ── The handoff ───────────────────────────────────────────────────────
#
# The manager approves a span of work and the controller gets a job to do
# about it — as one act, not two people remembering. And the other way: the
# controller queries it and it goes back with a reason.


class ClaimIn(BaseModel):
    covers_from: dt.date
    covers_to: dt.date
    note: str = Field(min_length=10)
    due_in_days: int = Field(default=14, ge=1, le=365)
    #: Who is going to invoice it. Optional, and when it is left out the
    #: route picks the sole holder of CONTROLLER or hands it to nobody with
    #: the reason on it — see `_hand_to`. A *person* naming a person is
    #: better than a rule guessing between two, which is why this exists at
    #: all: the manager knows who does the invoicing and the system does not.
    hand_to: str | None = None


class QueryIn(BaseModel):
    reason: str = Field(min_length=10)
    due_in_days: int = Field(default=7, ge=1, le=365)


class InvoicedIn(BaseModel):
    invoice_id: str
    note: str = ""


def _hand_to(cur, actor: Actor, portfolio: str) -> tuple[str | None, str]:
    """Who to give this to, and what to say when that is not one person.

    More than one candidate means no candidate — the rule
    `/api/reconcile/propose` and the evidence matcher both follow, for the
    same reason: an attribution that could equally have been somebody else is
    not an attribution. So an unassigned todo with the reason on it beats a
    todo on whoever happened to sort first.
    """
    cur.execute("""SELECT a.actor_id, a.display_name
                     FROM actor a
                     JOIN actor_portfolio p ON p.actor_id = a.actor_id
                    WHERE p.portfolio = %s AND p.revoked_at IS NULL
                      AND a.is_active AND a.actor_id <> %s
                    ORDER BY a.display_name""", (portfolio, actor.actor_id))
    holders = cur.fetchall()
    if len(holders) == 1:
        return str(holders[0]["actor_id"]), holders[0]["display_name"]
    if not holders:
        return None, (f"nobody else holds {portfolio}, so this is on the list "
                      f"and unassigned")
    return None, (f"{len(holders)} people hold {portfolio} — "
                  + ", ".join(h["display_name"] for h in holders)
                  + " — so it is unassigned rather than given to whichever "
                    "of them sorted first")


def _raise_todo(cur, actor: Actor, *, period: str, objective_id: str,
                title: str, detail: str, assignee: str | None,
                due_on: dt.date, claim_id: str) -> str:
    cur.execute("""INSERT INTO todo (period, objective_id, title, detail,
                                     assignee_actor, due_on, opened_by,
                                     from_claim)
                   VALUES (%s,%s,%s,%s,%s::uuid,%s,%s,%s::uuid)
                   RETURNING todo_id""",
                (period, objective_id, title, detail, assignee, due_on,
                 actor.display_name, claim_id))
    return str(cur.fetchone()["todo_id"])


@router.post("/{objective_id}/claims", status_code=201)
def approve_claim(objective_id: str, body: ClaimIn, period: str | None = None,
                  actor: Actor = Depends(require_project)) -> dict:
    """The manager says a span of work is right and ready to invoice.

    Nothing about the work is copied here. What the span contains is read
    from `v_project_work` — hours from timesheets, cost from the live
    decisions over the ledger, documents from `attachment` — and the four
    figures recorded on the claim are **what the manager was looking at**, in
    the sense a seal records what it covered. If the record moves afterwards,
    `v_project_claim.still_agrees` says so instead of the approval silently
    coming to cover something else.
    """
    period = period or settings.period
    with turn(period) as cur:
        cur.execute("""SELECT p.name, p.status,
                              (SELECT c.employee_key FROM charge_authority c
                                WHERE c.objective_id = p.objective_id
                                  AND c.role_on_project = 'MANAGER'
                                  AND c.revoked_at IS NULL LIMIT 1) AS manager
                         FROM project p WHERE p.objective_id = %s""",
                    (objective_id,))
        proj = cur.fetchone()
        if not proj:
            raise HTTPException(404, f"No project on {objective_id}.")
        if proj["status"] == "CLOSED":
            raise HTTPException(
                409, f"{proj['name']} is closed. Reopen it before claiming "
                     f"against it — a claim on a closed project is work "
                     f"nobody is watching for.")

        # Read what is there inside the turn, because it is what the approval
        # is going to be *of*. Read outside it and another controller's
        # judgment could land between the reading and the recording.
        cur.execute("""SELECT timesheet_hours, classified_amount,
                              classified_lines, documents, distributed_wages
                         FROM v_project_work WHERE objective_id = %s""",
                    (objective_id,))
        work = cur.fetchone()

        cur.execute("""INSERT INTO project_claim
                         (objective_id, period, covers_from, covers_to,
                          approved_by, note, saw_hours, saw_amount,
                          saw_lines, saw_documents)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING claim_id""",
                    (objective_id, period, body.covers_from, body.covers_to,
                     actor.actor_id, body.note.strip(),
                     work["timesheet_hours"], work["classified_amount"],
                     work["classified_lines"], work["documents"]))
        claim_id = str(cur.fetchone()["claim_id"])

        if body.hand_to:
            cur.execute("""SELECT a.actor_id, a.display_name FROM actor a
                             JOIN actor_portfolio p ON p.actor_id = a.actor_id
                            WHERE (a.actor_id::text = %s OR a.email = %s)
                              AND p.portfolio = 'CONTROLLER'
                              AND p.revoked_at IS NULL AND a.is_active""",
                        (body.hand_to, body.hand_to))
            named = cur.fetchone()
            if not named:
                raise HTTPException(
                    422, f"{body.hand_to} does not hold CONTROLLER, and "
                         f"invoicing against an award is the controller's "
                         f"job. Leave it out to hand it to whoever does.")
            to, why = str(named["actor_id"]), named["display_name"]
        else:
            to, why = _hand_to(cur, actor, "CONTROLLER")
        due = dt.date.today() + dt.timedelta(days=body.due_in_days)
        todo_id = _raise_todo(
            cur, actor, period=period, objective_id=objective_id,
            title=f"Invoice {proj['name']} for "
                  f"{body.covers_from} to {body.covers_to}",
            detail=(f"{actor.display_name} approved it: {body.note.strip()} "
                    f"— {work['timesheet_hours']} hours booked, "
                    f"{work['classified_amount']} of cost classified to the "
                    f"objective, {work['documents']} document(s) on file."
                    + ("" if to else f" Unassigned: {why}.")),
            assignee=to, due_on=due, claim_id=claim_id)

        record(actor, "CLAIM_APPROVE", "project_claim", claim_id,
               after={"objective_id": objective_id,
                      "covers_from": str(body.covers_from),
                      "covers_to": str(body.covers_to),
                      "saw_hours": str(work["timesheet_hours"]),
                      "saw_amount": str(work["classified_amount"]),
                      "handed_to": to},
               reason=body.note.strip(), cursor=cur)

    return {"claim_id": claim_id, "todo_id": todo_id,
            "handed_to": to, "why_unassigned": None if to else why,
            "due_on": str(due),
            "saw": {"hours": str(work["timesheet_hours"]),
                    "amount": str(work["classified_amount"]),
                    "lines": work["classified_lines"],
                    "documents": work["documents"],
                    "distributed_wages": str(work["distributed_wages"])}}


claims = APIRouter(prefix="/claims", tags=["claims"],
                   dependencies=[Depends(require_reader)])


@claims.get("")
def list_claims(period: str | None = None,
                objective_id: str | None = None) -> dict:
    period = period or settings.period
    rows = query("""SELECT * FROM v_project_claim
                     WHERE period = %s
                       AND (%s::text IS NULL OR objective_id = %s)
                     ORDER BY approved_at DESC""",
                 (period, objective_id, objective_id))
    return {"period": period, "claims": rows,
            "to_invoice": sum(1 for r in rows if r["state"] == "APPROVED"),
            "moved_since_approval":
                sum(1 for r in rows if not r["still_agrees"])}


@claims.post("/{claim_id}/query")
def query_claim(claim_id: str, body: QueryIn,
                actor: Actor = Depends(require_controller)) -> dict:
    """The other direction. Send it back with what is wrong with it.

    Takes `CONTROLLER` rather than `PROJECT`: querying a claim is the person
    who would have to issue the invoice saying they cannot, and that is the
    controller's judgment. The manager's answer comes back as an approval.
    """
    period = settings.period
    with turn(period) as cur:
        cur.execute("""SELECT c.state, c.objective_id, c.covers_from,
                              c.covers_to, p.name,
                              (SELECT a.actor_id FROM actor a
                                WHERE a.actor_id = c.approved_by) AS manager
                         FROM project_claim c
                         JOIN project p ON p.objective_id = c.objective_id
                        WHERE c.claim_id = %s::uuid""", (claim_id,))
        claim = cur.fetchone()
        if not claim:
            raise HTTPException(404, "No such claim.")
        if claim["state"] == "INVOICED":
            raise HTTPException(
                409, "That is already invoiced. A query after the invoice has "
                     "gone is a credit or a restatement, not a query — "
                     "POST /api/restate is the route for it.")

        cur.execute("""UPDATE project_claim
                          SET state = 'QUERIED', queried_reason = %s,
                              queried_at = now(), queried_by = %s
                        WHERE claim_id = %s::uuid""",
                    (body.reason.strip(), actor.actor_id, claim_id))

        # The todo this raised goes back to whoever approved it, because they
        # are the one person who can answer — not to whoever holds PROJECT.
        due = dt.date.today() + dt.timedelta(days=body.due_in_days)
        todo_id = _raise_todo(
            cur, actor, period=period, objective_id=claim["objective_id"],
            title=f"Answer the query on {claim['name']} "
                  f"{claim['covers_from']} to {claim['covers_to']}",
            detail=f"{actor.display_name} could not invoice it: "
                   f"{body.reason.strip()}",
            assignee=str(claim["manager"]), due_on=due, claim_id=claim_id)

        # And the job it was raised from is answered, whichever way this goes.
        cur.execute("""UPDATE todo SET status = 'DONE', done_at = now(),
                              done_by = %s
                        WHERE from_claim = %s::uuid AND status <> 'DONE'
                          AND todo_id <> %s::uuid""",
                    (actor.display_name, claim_id, todo_id))

        record(actor, "CLAIM_QUERY", "project_claim", claim_id,
               before={"state": claim["state"]}, after={"state": "QUERIED"},
               reason=body.reason.strip(), cursor=cur)
    return {"claim_id": claim_id, "state": "QUERIED", "todo_id": todo_id,
            "went_back_to": str(claim["manager"])}


@claims.post("/{claim_id}/invoiced")
def claim_invoiced(claim_id: str, body: InvoicedIn,
                   actor: Actor = Depends(require_controller)) -> dict:
    """Settle it against the invoice on file.

    This links rather than creates. No route in this system raises an
    invoice and `invoice` is append-only — which for 2025 is exactly right:
    the invoice already exists, it is one of the three NCDMM issued, and what
    has been missing is the thread from it back to the work, the people and
    the documents underneath.
    """
    period = settings.period
    with turn(period) as cur:
        cur.execute("""SELECT c.state, c.objective_id, c.covers_from,
                              c.covers_to, c.approved_by, p.name
                         FROM project_claim c
                         JOIN project p ON p.objective_id = c.objective_id
                        WHERE c.claim_id = %s::uuid""", (claim_id,))
        claim = cur.fetchone()
        if not claim:
            raise HTTPException(404, "No such claim.")
        if claim["state"] == "INVOICED":
            raise HTTPException(409, "That is already settled.")

        cur.execute("""SELECT invoice_number, objective_id, total
                         FROM invoice WHERE invoice_id = %s::uuid""",
                    (body.invoice_id,))
        inv = cur.fetchone()
        if not inv:
            raise HTTPException(404, f"No invoice {body.invoice_id}.")
        if inv["objective_id"] and inv["objective_id"] != claim["objective_id"]:
            raise HTTPException(
                409, f"Invoice {inv['invoice_number']} is on "
                     f"{inv['objective_id']} and this claim is on "
                     f"{claim['objective_id']}. Settling a claim against "
                     f"another objective's invoice is how cost ends up "
                     f"charged to the wrong award.")

        cur.execute("""UPDATE project_claim
                          SET state = 'INVOICED', invoice_id = %s::uuid,
                              invoiced_at = now(), invoiced_by = %s,
                              queried_reason = NULL, queried_at = NULL,
                              queried_by = NULL
                        WHERE claim_id = %s::uuid""",
                    (body.invoice_id, actor.actor_id, claim_id))
        cur.execute("""UPDATE todo SET status = 'DONE', done_at = now(),
                              done_by = %s
                        WHERE from_claim = %s::uuid AND status <> 'DONE'""",
                    (actor.display_name, claim_id))

        # And back the other way, so the manager learns it went out rather
        # than having to go and look. This is the "and vice versa" half: the
        # loop is only a loop if it closes in both directions.
        due = dt.date.today() + dt.timedelta(days=30)
        todo_id = _raise_todo(
            cur, actor, period=period, objective_id=claim["objective_id"],
            title=f"Invoice {inv['invoice_number']} is out on "
                  f"{claim['name']} — watch for the money",
            detail=(f"{actor.display_name} settled "
                    f"{claim['covers_from']} to {claim['covers_to']} against "
                    f"invoice {inv['invoice_number']}"
                    + (f" for {inv['total']}." if inv["total"] else ".")
                    + " No payment is recorded against any invoice yet, so "
                      "this is the record of one to chase."),
            assignee=str(claim["approved_by"]), due_on=due, claim_id=claim_id)

        record(actor, "CLAIM_INVOICED", "project_claim", claim_id,
               before={"state": claim["state"]},
               after={"state": "INVOICED",
                      "invoice_number": inv["invoice_number"]},
               reason=body.note.strip() or f"settled against "
                                           f"{inv['invoice_number']}",
               cursor=cur)
    return {"claim_id": claim_id, "state": "INVOICED",
            "invoice_number": inv["invoice_number"], "todo_id": todo_id,
            "back_to": str(claim["approved_by"])}


# ── The list a person can actually write ──────────────────────────────

todos = APIRouter(prefix="/todos", tags=["todos"],
                  dependencies=[Depends(require_reader)])


@todos.get("")
def list_todos(period: str | None = None, assignee_actor: str | None = None,
               mine: bool = False, actor: Actor = Depends(require_reader)) -> dict:
    period = period or settings.period
    who = str(actor.actor_id) if mine else assignee_actor
    rows = query("""SELECT * FROM v_todo_live
                     WHERE period = %s
                       AND (%s::uuid IS NULL OR assignee_actor = %s::uuid)
                     ORDER BY overdue DESC, (due_on IS NULL), due_on,
                              sort_index""", (period, who, who))
    return {"period": period, "assignee_actor": who, "todos": rows,
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
                                         assignee_actor, due_on, worklist_kind,
                                         worklist_entity_id, verification_ref,
                                         opened_by)
                       VALUES (%s,%s,%s,%s,%s::uuid,%s,%s,%s,%s,%s)
                       RETURNING todo_id""",
                    (period, body.objective_id, body.title, body.detail,
                     body.assignee_actor, body.due_on, body.worklist_kind,
                     body.worklist_entity_id, body.verification_ref,
                     actor.display_name))
        todo_id = str(cur.fetchone()["todo_id"])
        record(actor, "TODO_OPEN", "todo", todo_id,
               after={"title": body.title, "assignee": body.assignee_actor,
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
        cur.execute("""SELECT status, assignee_actor, due_on, title
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
                          SET assignee_actor = COALESCE(%s::uuid, assignee_actor),
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
                    (body.assignee_actor, body.due_on, body.detail, status,
                     status, (body.blocked_reason or "").strip() or None,
                     status, status, actor.display_name, todo_id))
        record(actor, "TODO_CHANGE", "todo", todo_id,
               before={"status": was["status"],
                       "assignee": str(was["assignee_actor"] or "")},
               after={"status": status,
                      "assignee": body.assignee_actor
                                  or str(was["assignee_actor"] or ""),
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
