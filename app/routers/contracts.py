"""Charge codes, who may charge them, and what a contract earns against cost.

The cost side of this system reads backwards: the ledger arrives, the
controller judges it, a rate falls out. That works for a year already spent
and not at all for a year being worked. A charge code has to exist before
somebody books an hour to it, the person booking has to be allowed to, and
the money arriving has to be traceable to the deliverable that earned it.

The cost objective *is* the charge code. There is no second register of
codes, deliberately: an hour and a dollar spent on the same work have to land
in the same place, and two lists of "the thing you charge to" is how they
stop doing that.

Writes need `PROJECT` or `CONTROLLER` — the project manager runs this in
practice and the controller reaches everything. Reads need only that the
caller may read the cost record, because the auditor's whole job here is to
follow an employee through to the money.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_project, require_reader
from app.db import execute, one, query, transaction
from app.settings import settings

router = APIRouter(prefix="/contracts", tags=["contracts"],
                   dependencies=[Depends(require_reader)])


# ── charge codes ──────────────────────────────────────────────────────


class ChargeCodeIn(BaseModel):
    objective_id: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=2)
    objective_type: str = "PROGRAM"
    is_federal: bool = False
    is_final: bool = True
    cfda: str | None = None
    reason: str = Field(min_length=10)


class AuthoriseIn(BaseModel):
    employee_key: str = Field(min_length=1)
    role_on_project: str = ""
    reason: str = Field(min_length=10)
    opens_on: date | None = None
    closes_on: date | None = None


class RevokeIn(BaseModel):
    employee_key: str
    reason: str = Field(min_length=10)


@router.get("/charge-codes")
def charge_codes(period: str | None = None) -> dict:
    """Every code, with what has been charged to it and by how many people."""
    period = period or settings.period
    rows = query("""SELECT objective_id, label, objective_type, is_federal,
                           is_final, active, cfda, award_id, sponsor,
                           instrument, ceiling_federal, period_start, period_end,
                           people_authorised, hours_charged, people_charging,
                           wages_distributed, cost_classified
                      FROM v_charge_code WHERE period = %s
                      ORDER BY is_federal DESC, objective_id""", (period,))
    return {"period": period, "charge_codes": rows,
            # A code somebody has charged with nobody authorised on it. For
            # 2025 that is all of them — the mechanism did not exist while the
            # year was worked — and saying so is better than implying the
            # question was asked and passed.
            "charged_without_authority":
                [r["objective_id"] for r in rows
                 if r["hours_charged"] and not r["people_authorised"]]}


@router.post("/charge-codes", status_code=201)
def create_charge_code(body: ChargeCodeIn, period: str | None = None,
                       actor: Actor = Depends(require_project)) -> dict:
    """Open a new code. The project manager's job, and the controller's."""
    period = period or settings.period
    if one("SELECT 1 FROM cost_objective WHERE objective_id = %s",
           (body.objective_id,)):
        raise HTTPException(409, f"{body.objective_id} already exists.")
    if body.is_federal and not body.cfda:
        raise HTTPException(
            422, "A federal charge code needs its CFDA number. Without it the "
                 "award cannot reach the SEFA, and the Single Audit scope is "
                 "decided by what is on the SEFA.")
    execute("""INSERT INTO cost_objective
                 (objective_id, period, label, objective_type, is_federal,
                  is_final, cfda)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (body.objective_id, period, body.label, body.objective_type,
             body.is_federal, body.is_final, body.cfda))
    record(actor, "CHARGE_CODE_OPEN", "cost_objective", body.objective_id,
           after={"label": body.label, "is_federal": body.is_federal,
                  "cfda": body.cfda},
           reason=body.reason)
    return {"objective_id": body.objective_id, "period": period}


@router.get("/charge-codes/{objective_id}/people")
def code_people(objective_id: str, period: str | None = None) -> dict:
    """Who may charge this code, and who has."""
    period = period or settings.period
    granted = query("""SELECT employee_key, role_on_project, opens_on,
                              closes_on, granted_by, granted_at, reason
                         FROM v_charge_authorised
                        WHERE period = %s AND objective_id = %s
                        ORDER BY employee_key""", (period, objective_id))
    charged = query("""SELECT employee_key, hours, entries, first_charged,
                              last_charged, authorised
                         FROM v_employee_charging
                        WHERE period = %s AND objective_id = %s
                        ORDER BY hours DESC""", (period, objective_id))
    return {"period": period, "objective_id": objective_id,
            "authorised": granted, "charged": charged,
            "charged_without_authority":
                [c["employee_key"] for c in charged if not c["authorised"]]}


@router.post("/charge-codes/{objective_id}/authorise", status_code=201)
def authorise(objective_id: str, body: AuthoriseIn, period: str | None = None,
              actor: Actor = Depends(require_project)) -> dict:
    """Let somebody charge this code.

    Nobody authorises themselves. It is the rule the portfolios follow and it
    holds here for the same reason: an assignment is a statement by one person
    about another, and one made by its own beneficiary says nothing.
    """
    period = period or settings.period
    if not one("SELECT 1 FROM cost_objective WHERE objective_id = %s",
               (objective_id,)):
        raise HTTPException(404, f"No charge code {objective_id}.")
    if actor.employee_key and actor.employee_key == body.employee_key:
        raise HTTPException(
            403, "Nobody authorises themselves onto a charge code. Ask the "
                 "project manager or the controller.")
    # Somebody who can actually book time. The payroll register is the roster
    # — `employment` holds the terms of a week, which not everybody has yet —
    # and an account linked to an employee key counts too, for a newcomer who
    # is on the books before the register is next loaded.
    known = one("""SELECT 1 AS ok FROM labor_allocation
                    WHERE employee_key = %s LIMIT 1""", (body.employee_key,)) \
        or one("""SELECT 1 AS ok FROM employment
                   WHERE employee_key = %s LIMIT 1""", (body.employee_key,)) \
        or one("""SELECT 1 AS ok FROM actor
                   WHERE employee_key = %s LIMIT 1""", (body.employee_key,))
    if not known:
        raise HTTPException(
            422, f"{body.employee_key} is on no payroll register and no "
                 f"account. A charge code is authorised to somebody who can "
                 f"book time to it.")
    existing = one("""SELECT authority_id FROM charge_authority
                       WHERE period=%s AND objective_id=%s AND employee_key=%s
                         AND revoked_at IS NULL""",
                   (period, objective_id, body.employee_key))
    if existing:
        raise HTTPException(
            409, f"{body.employee_key} already holds a live grant on "
                 f"{objective_id}. Revoke it first — an amendment supersedes, "
                 f"it does not sit beside.")
    row = one("""INSERT INTO charge_authority
                   (period, objective_id, employee_key, role_on_project,
                    granted_by, reason, opens_on, closes_on)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING authority_id""",
              (period, objective_id, body.employee_key, body.role_on_project,
               actor.display_name, body.reason, body.opens_on, body.closes_on))
    record(actor, "CHARGE_AUTHORISE", "cost_objective", objective_id,
           after={"employee_key": body.employee_key,
                  "role": body.role_on_project,
                  "opens_on": str(body.opens_on) if body.opens_on else None,
                  "closes_on": str(body.closes_on) if body.closes_on else None},
           reason=body.reason)
    return {"authority_id": str(row["authority_id"]),
            "objective_id": objective_id, "employee_key": body.employee_key}


@router.post("/charge-codes/{objective_id}/revoke")
def revoke(objective_id: str, body: RevokeIn, period: str | None = None,
           actor: Actor = Depends(require_project)) -> dict:
    """Take the assignment away. The grant stays on the record, revoked."""
    period = period or settings.period
    row = one("""UPDATE charge_authority
                    SET revoked_at = now(), revoked_reason = %s
                  WHERE period=%s AND objective_id=%s AND employee_key=%s
                    AND revoked_at IS NULL
                  RETURNING authority_id""",
              (body.reason, period, objective_id, body.employee_key))
    if not row:
        raise HTTPException(
            404, f"{body.employee_key} holds no live grant on {objective_id}.")
    record(actor, "CHARGE_REVOKE", "cost_objective", objective_id,
           after={"employee_key": body.employee_key}, reason=body.reason)
    return {"objective_id": objective_id, "employee_key": body.employee_key,
            "revoked": True}


# ── contracts ─────────────────────────────────────────────────────────


class TermIn(BaseModel):
    term_key: str = Field(min_length=2)
    term_value: str = Field(min_length=1)
    citation: str = ""
    note: str = ""


class MilestoneIn(BaseModel):
    milestone_id: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2)
    description: str = ""
    clin: str = ""
    value: float = 0
    due_on: date | None = None


class MilestoneStateIn(BaseModel):
    state: str
    on_date: date | None = None
    reason: str = Field(min_length=5)


class ReceiptIn(BaseModel):
    received_on: date
    amount: float
    method: str = ""
    reference: str = ""
    note: str = ""


@router.get("")
def contracts(period: str | None = None) -> dict:
    """Every contract, earned against spent."""
    period = period or settings.period
    rows = query("""SELECT award_id, objective_id, sponsor, instrument,
                           ceiling_federal, cost_share_required, period_start,
                           period_end, objective_label, is_federal, cfda,
                           milestones, milestones_done, terms, invoiced,
                           received, cost_classified, labor_distributed
                      FROM v_award_performance WHERE period = %s
                      ORDER BY ceiling_federal DESC, award_id""", (period,))
    return {"period": period, "contracts": rows}


# ── the auditor's path ────────────────────────────────────────────────
#
# Declared before `/{award_id}`. FastAPI matches in declaration order and a
# one-segment path parameter swallows every literal that follows it, so
# /contracts/employees came back as "no contract employees in 2025".

@router.get("/employees/{employee_key}/charging")
def employee_charging(employee_key: str, period: str | None = None) -> dict:
    """Pick an employee, see everything they billed against.

    The first step of the review the auditor actually does, and the one the
    system could not answer before: what did this person charge, was anybody
    asked, and which contract does each code belong to.
    """
    period = period or settings.period
    charged = query("""SELECT objective_id, objective_label, is_federal,
                              award_id, sponsor, hours, entries, first_charged,
                              last_charged, authorised
                         FROM v_employee_charging
                        WHERE period = %s AND employee_key = %s
                        ORDER BY hours DESC""", (period, employee_key))
    granted = query("""SELECT objective_id, objective_label, role_on_project,
                              award_id, sponsor, opens_on, closes_on,
                              granted_by, granted_at, reason
                         FROM v_charge_authorised
                        WHERE period = %s AND employee_key = %s
                        ORDER BY objective_id""", (period, employee_key))
    distributed = query("""SELECT objective_id, reconstructed_units AS wages,
                                  evidence_quality::text AS grade
                             FROM labor_allocation
                            WHERE period = %s AND employee_key = %s
                            ORDER BY reconstructed_units DESC""",
                        (period, employee_key))
    emp = one("""SELECT employee_key, employee_name
                   FROM labor_allocation
                  WHERE employee_key = %s LIMIT 1""", (employee_key,))
    return {"period": period, "employee_key": employee_key,
            "employee_name": (emp or {}).get("employee_name", employee_key),
            "charged": charged, "authorised": granted,
            "distributed": distributed,
            "unauthorised": [c["objective_id"] for c in charged
                             if not c["authorised"]]}


@router.get("/employees")
def employees(period: str | None = None) -> dict:
    """Everybody who charged anything, or is distributed to anything."""
    period = period or settings.period
    rows = query("""SELECT la.employee_key,
                           max(la.employee_name)                  AS employee_name,
                           sum(la.reconstructed_units)            AS wages,
                           count(DISTINCT la.objective_id)        AS objectives,
                           COALESCE((SELECT sum(t.hours) FROM timesheet_entry t
                                      WHERE t.employee_key = la.employee_key
                                        AND t.period = la.period
                                        AND t.superseded_at IS NULL), 0) AS hours,
                           COALESCE((SELECT count(*) FROM charge_authority ca
                                      WHERE ca.employee_key = la.employee_key
                                        AND ca.period = la.period
                                        AND ca.revoked_at IS NULL), 0) AS authorised_codes
                      FROM labor_allocation la
                     WHERE la.period = %s
                     GROUP BY la.employee_key, la.period
                     ORDER BY sum(la.reconstructed_units) DESC""", (period,))
    return {"period": period, "employees": rows}


@router.get("/{award_id}")
def contract(award_id: str, period: str | None = None) -> dict:
    """One contract: its terms, its milestones, its invoices and its money."""
    period = period or settings.period
    head = one("""SELECT * FROM v_award_performance
                   WHERE award_id = %s AND period = %s""", (award_id, period))
    if not head:
        raise HTTPException(404, f"No contract {award_id} in {period}.")
    # Each provision with the document it was read out of and whether that
    # document contains what the citation names. A citation with no document
    # behind it is somebody's recollection of a contract, which is the rule
    # `load_contract_terms.py` has always opened with — and six provisions on
    # two federal subawards cited clauses that are not in either agreement
    # for as long as nothing could ask.
    terms = query("""SELECT t.term_key, t.term_value, t.citation, t.note,
                            t.recorded_by, t.recorded_at,
                            c.state        AS citation_state,
                            c.looked_for   AS citation_looked_for,
                            c.document     AS citation_document
                       FROM award_term t
                       LEFT JOIN v_award_citation_check c
                              ON c.award_id = t.award_id
                             AND c.term_key = t.term_key
                      WHERE t.award_id = %s
                      ORDER BY t.term_key""", (award_id,))
    citations = one("""SELECT agreement, page_count, agreement_is_an_image,
                              terms, found, not_in_document, untestable,
                              unevaluable
                         FROM v_award_citations WHERE award_id = %s""",
                    (award_id,))
    milestones = query("""SELECT milestone_id, name, clin, description, value,
                                 due_on, delivered_on, accepted_on,
                                 state::text AS state, invoices, invoiced,
                                 received, outstanding
                            FROM v_milestone_status WHERE award_id = %s
                            ORDER BY due_on NULLS LAST, milestone_id""",
                       (award_id,))
    invoices = query("""SELECT i.invoice_id, i.invoice_number, i.seq,
                               i.invoice_date, i.direct_claimed,
                               i.indirect_claimed, i.cost_share, i.status,
                               i.milestone_id,
                               COALESCE((SELECT sum(r.amount) FROM receipt r
                                          WHERE r.invoice_id = i.invoice_id), 0)
                                 AS received
                          FROM invoice i WHERE i.award_id = %s
                          ORDER BY i.invoice_date, i.seq""", (award_id,))
    people = query("""SELECT employee_key, hours, entries, authorised
                        FROM v_employee_charging
                       WHERE period = %s AND objective_id = %s
                       ORDER BY hours DESC""", (period, head["objective_id"]))
    return {"period": period, "contract": head, "terms": terms,
            "citations": citations, "milestones": milestones,
            "invoices": invoices, "people": people}


@router.put("/{award_id}/terms", status_code=201)
def put_term(award_id: str, body: TermIn,
             actor: Actor = Depends(require_project)) -> dict:
    """Record a provision, with the clause it came from."""
    if not one("SELECT 1 FROM award WHERE award_id = %s", (award_id,)):
        raise HTTPException(404, f"No contract {award_id}.")
    execute("""INSERT INTO award_term
                 (award_id, term_key, term_value, citation, note, recorded_by)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (award_id, term_key) DO UPDATE
                 SET term_value = EXCLUDED.term_value,
                     citation = EXCLUDED.citation,
                     note = EXCLUDED.note,
                     recorded_by = EXCLUDED.recorded_by,
                     recorded_at = now()""",
            (award_id, body.term_key, body.term_value, body.citation,
             body.note, actor.display_name))
    record(actor, "AWARD_TERM", "award", award_id,
           after={"term": body.term_key, "value": body.term_value[:200],
                  "citation": body.citation},
           reason=f"{body.term_key} recorded")
    return {"award_id": award_id, "term_key": body.term_key}


@router.post("/{award_id}/milestones", status_code=201)
def create_milestone(award_id: str, body: MilestoneIn,
                     actor: Actor = Depends(require_project)) -> dict:
    if not one("SELECT 1 FROM award WHERE award_id = %s", (award_id,)):
        raise HTTPException(404, f"No contract {award_id}.")
    if one("SELECT 1 FROM milestone WHERE milestone_id = %s",
           (body.milestone_id,)):
        raise HTTPException(409, f"{body.milestone_id} already exists.")
    execute("""INSERT INTO milestone
                 (milestone_id, award_id, name, description, clin, value,
                  due_on, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (body.milestone_id, award_id, body.name, body.description,
             body.clin, body.value, body.due_on, actor.display_name))
    record(actor, "MILESTONE_OPEN", "milestone", body.milestone_id,
           after={"award_id": award_id, "name": body.name,
                  "value": body.value, "due_on": str(body.due_on or "")},
           reason=f"milestone opened on {award_id}")
    return {"milestone_id": body.milestone_id, "award_id": award_id}


@router.post("/milestones/{milestone_id}/state")
def set_milestone_state(milestone_id: str, body: MilestoneStateIn,
                        actor: Actor = Depends(require_project)) -> dict:
    """Move a milestone along.

    A state that claims a date has to carry it — the schema refuses
    DELIVERED with no delivery date — because a status somebody set is not
    the same as a thing that happened.
    """
    m = one("SELECT state::text AS state FROM milestone WHERE milestone_id = %s",
            (milestone_id,))
    if not m:
        raise HTTPException(404, f"No milestone {milestone_id}.")
    col = {"DELIVERED": "delivered_on", "ACCEPTED": "accepted_on"}.get(body.state)
    if col and not body.on_date:
        raise HTTPException(
            422, f"{body.state} needs the date it happened. A status without "
                 f"one is a claim rather than a record.")
    try:
        if col:
            execute(f"""UPDATE milestone SET state = %s, {col} = %s
                         WHERE milestone_id = %s""",
                    (body.state, body.on_date, milestone_id))
        else:
            execute("UPDATE milestone SET state = %s WHERE milestone_id = %s",
                    (body.state, milestone_id))
    except Exception as exc:                       # noqa: BLE001
        raise HTTPException(422, str(exc).split("\n")[0])
    record(actor, "MILESTONE_STATE", "milestone", milestone_id,
           before={"state": m["state"]},
           after={"state": body.state,
                  "on_date": str(body.on_date) if body.on_date else None},
           reason=body.reason)
    return {"milestone_id": milestone_id, "state": body.state}


@router.get("/milestones/{milestone_id}")
def milestone(milestone_id: str, period: str | None = None) -> dict:
    """A milestone, the invoice against it, the money in, and what it cost.

    This is the auditor's last step: from a deliverable to the invoice that
    claimed it, the receipt that settled it, and the cost carried on the
    objective underneath. The cost side is what has been *classified* to the
    objective, so it is honest about being incomplete rather than reporting a
    margin nobody can support.
    """
    period = period or settings.period
    m = one("""SELECT * FROM v_milestone_status WHERE milestone_id = %s""",
            (milestone_id,))
    if not m:
        raise HTTPException(404, f"No milestone {milestone_id}.")
    invoices = query("""SELECT i.invoice_id, i.invoice_number, i.invoice_date,
                               i.direct_claimed, i.indirect_claimed,
                               i.cost_share, i.status, i.total
                          FROM invoice i WHERE i.milestone_id = %s
                          ORDER BY i.invoice_date""", (milestone_id,))
    receipts = query("""SELECT r.receipt_id, r.invoice_id, r.received_on,
                               r.amount, r.method, r.reference, r.recorded_by
                          FROM receipt r
                          JOIN invoice i ON i.invoice_id = r.invoice_id
                         WHERE i.milestone_id = %s
                         ORDER BY r.received_on""", (milestone_id,))
    lines = query("""SELECT il.description, il.category::text AS category,
                            il.personnel, il.quantity, il.rate, il.amount,
                            i.invoice_number
                       FROM invoice_line il
                       JOIN invoice i ON i.invoice_id = il.invoice_id
                      WHERE i.milestone_id = %s
                      ORDER BY i.invoice_date, il.sequence""", (milestone_id,))
    cost = query("""SELECT d.pool::text AS pool,
                           sum(l.amount)  AS amount,
                           count(*)       AS lines
                      FROM ledger_line l
                      -- `dl.live` is redundant against the inner join to a
                      -- live decision below, and it is here anyway: the rule
                      -- is "every join to decision_line by line_id filters
                      -- live", and a rule with an exception for "unless the
                      -- next join happens to be inner" is one somebody gets
                      -- wrong the day they change this to a LEFT JOIN.
                      JOIN decision_line dl ON dl.line_id = l.line_id
                                           AND dl.live
                      JOIN decision d ON d.decision_id = dl.decision_id
                                     AND d.reversed_at IS NULL
                     WHERE d.objective_id = %s AND l.period = %s
                     GROUP BY d.pool ORDER BY sum(l.amount) DESC""",
                 (m["objective_id"], period))
    labor = query("""SELECT employee_key, employee_name,
                            reconstructed_units AS wages, evidence_quality::text AS grade
                       FROM labor_allocation
                      WHERE objective_id = %s AND period = %s
                      ORDER BY reconstructed_units DESC""",
                  (m["objective_id"], period))
    return {"period": period, "milestone": m, "invoices": invoices,
            "receipts": receipts, "invoice_lines": lines,
            "cost_by_pool": cost, "labor": labor}


@router.post("/invoices/{invoice_id}/receipts", status_code=201)
def add_receipt(invoice_id: str, body: ReceiptIn,
                actor: Actor = Depends(require_project)) -> dict:
    """Money in, against the claim that earned it."""
    inv = one("SELECT award_id FROM invoice WHERE invoice_id = %s::uuid",
              (invoice_id,))
    if not inv:
        raise HTTPException(404, "No such invoice.")
    row = one("""INSERT INTO receipt
                   (invoice_id, received_on, amount, method, reference, note,
                    recorded_by)
                 VALUES (%s::uuid,%s,%s,%s,%s,%s,%s) RETURNING receipt_id""",
              (invoice_id, body.received_on, body.amount, body.method,
               body.reference, body.note, actor.display_name))
    record(actor, "RECEIPT", "invoice", invoice_id,
           after={"amount": body.amount, "received_on": str(body.received_on),
                  "reference": body.reference},
           reason=f"receipt recorded against {inv['award_id'] or 'no award'}")
    return {"receipt_id": str(row["receipt_id"]), "invoice_id": invoice_id}
