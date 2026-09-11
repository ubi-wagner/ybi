"""Effort distribution and its certification.

An employee sees their own distribution and signs it. Nobody signs for anybody
else — not the controller, not an admin. That is the whole content of a
2 CFR 200.430(i) certification: a statement by the person who did the work, or
by a supervisor with firsthand knowledge of it.

The statement covers **total** activity, not the federal slice. Certifying only
the federally charged portion proves nothing about the denominator, which is
what makes the percentages mean anything.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.audit import record
from app.auth import (Actor, Portfolio, current_actor, require_own_writes,
                      require_reader)
from app.db import one, query, transaction
from app.settings import settings

router = APIRouter(prefix="/certify", tags=["certify"])

#: The words that get signed. Held here rather than typed by the signer so
#: every certification says the same thing, and so the wording can be produced
#: on request years later.
STATEMENT = (
    "I certify that the distribution of effort shown above is a reasonable "
    "reflection of the total activity for which I was compensated in the "
    "period stated, across all activities, federally funded or otherwise. I "
    "understand this certification supports charges to Federal awards and that "
    "it will be relied upon by the organisation's auditors."
)

SUPERVISOR_STATEMENT = (
    "I certify that I have firsthand knowledge of the work performed and that "
    "the distribution of effort shown above is a reasonable reflection of the "
    "total activity for which this employee was compensated in the period "
    "stated, across all activities, federally funded or otherwise."
)


class SignIn_(BaseModel):
    employee_key: str
    period: str | None = None
    as_supervisor: bool = False
    acknowledged: bool = False


def _distribution(period: str, employee_key: str) -> list[dict]:
    return query("""
        SELECT objective_id, original_units, reconstructed_units,
               effective_units, share, distributed_wages, payroll_wages,
               evidence_quality, rationale, is_reconstructed
          FROM v_labor_effective
         WHERE period = %s AND employee_key = %s
         ORDER BY effective_units DESC""", (period, employee_key))


def _hash(rows: list[dict]) -> str:
    """Fingerprint the distribution as signed.

    Matches the hash v_certification_status computes, so a later change to any
    objective's effort makes the signature visibly stale rather than silently
    wrong.
    """
    body = "|".join(
        f"{r['objective_id']}:{r['effective_units']}"
        for r in sorted(rows, key=lambda r: r["objective_id"]))
    return hashlib.md5(body.encode()).hexdigest()


@router.get("/mine")
def mine(period: str = None, actor: Actor = Depends(current_actor)) -> dict:
    """The signed-in employee's own distribution."""
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(
            403, "This account is not linked to an employee, so it has no "
                 "effort distribution to certify.")
    rows = _distribution(period, actor.employee_key)
    status = one("""SELECT * FROM v_certification_status
                     WHERE period = %s AND employee_key = %s""",
                 (period, actor.employee_key))
    return {"period": period, "employee_key": actor.employee_key,
            "statement": STATEMENT, "distribution": rows, "status": status}


@router.post("/sign")
def sign(body: SignIn_, request: Request,
         actor: Actor = Depends(require_own_writes)) -> dict:
    """Sign an effort distribution.

    An EMPLOYEE may sign only their own. A SUPERVISOR signature is a separate
    role and is not yet issued to anyone, so in practice this is the employee's
    own signature — which is what the regulation asks for first.
    """
    period = body.period or settings.period

    if body.as_supervisor:
        # Certifying somebody else's effort is a judgment about work you
        # have firsthand knowledge of, so it follows the portfolio rather
        # than rank: a project manager knows who worked on their project,
        # and an administrator who provisions accounts does not.
        if not actor.holds(Portfolio.CONTROLLER, Portfolio.PROJECT):
            raise HTTPException(
                403, "Certifying on somebody else's behalf needs the "
                     "CONTROLLER or PROJECT portfolio — 2 CFR 200.430(i) "
                     "wants a signature from someone with firsthand "
                     "knowledge of the work.")
        role = "SUPERVISOR"
        statement = SUPERVISOR_STATEMENT
    else:
        if not actor.owns_employee(body.employee_key):
            raise HTTPException(
                403, "You may certify only your own effort. A certification "
                     "signed by someone else is not what 2 CFR 200.430(i) asks "
                     "for.")
        role = "EMPLOYEE"
        statement = STATEMENT

    if not body.acknowledged:
        raise HTTPException(
            422, "The certification must be acknowledged before it is signed.")

    rows = _distribution(period, body.employee_key)
    if not rows:
        raise HTTPException(404, "No effort distribution recorded for that "
                                 "employee and period.")

    total_share = sum(Decimal(str(r["share"])) for r in rows)
    if abs(total_share - Decimal(1)) > Decimal("0.001"):
        raise HTTPException(
            422, f"The distribution totals {total_share:.1%} of effort, not "
                 f"100%. A certification has to cover total activity.")

    payload = [
        {"objective_id": r["objective_id"],
         "effective_units": str(r["effective_units"]),
         "share": str(r["share"]),
         "distributed_wages": str(r["distributed_wages"])}
        for r in rows]

    with transaction() as cur:
        # A fresh signature supersedes the previous one for this employee and
        # period. Two live certifications would leave it ambiguous which
        # numbers were attested.
        cur.execute("""UPDATE labor_certification
                          SET superseded_at = now(),
                              superseded_reason = 'superseded by a later signature'
                        WHERE period = %s AND employee_key = %s
                          AND certifier_role = %s AND superseded_at IS NULL""",
                    (period, body.employee_key, role))
        cur.execute("""
            INSERT INTO labor_certification
              (period, employee_key, certifier_role, actor_id, session_id,
               signed_by, period_start, period_end, statement, distribution,
               distribution_hash, user_agent)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING certification_id, signed_at""",
            (period, body.employee_key, role, actor.actor_id, actor.session_id,
             actor.display_name, date(int(period), 1, 1), date(int(period), 12, 31),
             statement, json.dumps(payload), _hash(rows),
             request.headers.get("user-agent", "")[:400]))
        row = cur.fetchone()
        record(actor, "CERTIFY", "labor_certification",
               str(row["certification_id"]),
               after={"employee_key": body.employee_key, "role": role,
                      "objectives": len(rows)},
               reason=statement[:200], cursor=cur)

    return {"certification_id": str(row["certification_id"]),
            "signed_at": row["signed_at"], "employee_key": body.employee_key,
            "role": role, "objectives": len(rows)}


@router.get("/status")
def status(period: str = None, _: Actor = Depends(require_reader)) -> list[dict]:
    """Who has signed, who has not, and whose signature has gone stale."""
    period = period or settings.period
    return query("""SELECT * FROM v_certification_status
                     WHERE period = %s
                     ORDER BY certified, payroll_wages DESC""", (period,))


@router.get("/{employee_key}")
def for_employee(employee_key: str, period: str = None,
                 _: Actor = Depends(require_reader)) -> dict:
    """One employee's distribution and every signature it has carried.

    Superseded signatures are included: a reviewer asking what was attested and
    when needs the ones that were replaced as much as the current one.
    """
    period = period or settings.period
    return {
        "period": period,
        "employee_key": employee_key,
        "distribution": _distribution(period, employee_key),
        "certifications": query("""
            SELECT certification_id, certifier_role, signed_by, signed_at,
                   statement, distribution, distribution_hash,
                   superseded_at, superseded_reason
              FROM labor_certification
             WHERE period = %s AND employee_key = %s
             ORDER BY signed_at DESC""", (period, employee_key)),
    }
