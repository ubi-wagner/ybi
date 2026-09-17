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

#: What a filed page is a record of. The words the person signed are
#: STATEMENT — that is what is printed on the sheet they put their name to —
#: so this does not replace it, and a PAPER row carries STATEMENT like an
#: EMPLOYEE row does. What tells a reader the two apart is `certifier_role`
#: and the document beside it, which is exactly why the role exists rather
#: than a fourth wording nobody signed.
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
    #: Filing a page somebody signed, rather than signing here. The
    #: signature is theirs and the filing is yours, and the row keeps the
    #: two apart — see PAPER_STATEMENT and migration 120.
    on_paper: bool = False
    #: The scan, already through `POST /api/documents/upload`. This route
    #: writes no bytes: `storage.place()` is the only thing that decides
    #: where a file goes, which `tests/test_storage_paths.py` holds.
    evidence_id: str | None = None
    #: The date the page carries, which is not the date it was filed.
    paper_signed_on: date | None = None


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

    Three kinds of act, and the role is what tells them apart:

    * **EMPLOYEE** — the person signs their own, here. What 200.430(i) asks
      for first, and the only one anybody can do for themselves.
    * **SUPERVISOR** — somebody with firsthand knowledge of the work signs
      instead, in their own words. A different assertion, and it says so.
    * **PAPER** — the person signed a page and somebody else files it. The
      signature is theirs, the filing is the caller's, and the row keeps
      those apart: `signed_by` is read off the record for the employee whose
      effort it is, `actor_id` and `session_id` are whoever filed, and
      `evidence_id` is the page itself, which the schema will not let a
      PAPER row exist without.

    Nobody signs for anybody else by accident: the employee branch refuses
    an `employee_key` the caller does not own, and both other branches take
    a portfolio.
    """
    period = body.period or settings.period

    if body.as_supervisor and body.on_paper:
        raise HTTPException(
            422, "A signature is either yours or somebody else's. "
                 "`as_supervisor` asserts firsthand knowledge of the work; "
                 "`on_paper` files a page they signed themselves. Pick one.")

    if body.on_paper:
        # The same portfolio as a supervisor signature, for a different
        # reason. A supervisor is asserting something; a filer is
        # transcribing somebody else's assertion, and a wrong one claims a
        # person signed when they did not. So it stays with the people who
        # would know the page is genuine — the controller, and the project
        # managers `v_certification_chase` already sends to ask.
        if not actor.holds(Portfolio.CONTROLLER, Portfolio.PROJECT):
            raise HTTPException(
                403, "Filing somebody's signed certification needs the "
                     "CONTROLLER or PROJECT portfolio.")
        # Every one of these is also in the schema. The handler answers
        # first because a person meeting `paper_names_its_page` raw learns
        # only that a constraint exists — which is the defect
        # `acceptance_names_its_modification` shipped once, in the one place
        # this exercise is most likely to be looked at.
        if not body.evidence_id:
            raise HTTPException(
                422, "A filed certification names the page it was read off. "
                     "Upload the scan first, then file it against the "
                     "document id that comes back — a certification with no "
                     "document behind it asserts that somebody signed and "
                     "offers nothing to check it against.")
        if not one("SELECT 1 FROM evidence WHERE evidence_id = %s",
                   (body.evidence_id,)):
            raise HTTPException(404, f"No document {body.evidence_id} is on "
                                     f"file. Upload the scan first.")
        if body.paper_signed_on is None:
            raise HTTPException(
                422, "The page carries a date and the record keeps it apart "
                     "from the day it was filed: the gap between them is the "
                     "filing lag, and a reviewer is entitled to see it.")
        if body.paper_signed_on < date(int(period), 1, 1):
            raise HTTPException(
                422, f"That page is dated before {period} began, so it "
                     f"cannot be certifying {period} effort.")
        if body.paper_signed_on > date.today():
            raise HTTPException(
                422, "That page is dated in the future, which is a "
                     "transcription error rather than a signature.")
        role = "PAPER"
        statement = STATEMENT
    elif body.as_supervisor:
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
            422, "You have read the signed page and confirmed whose it is — "
                 "say so before it is filed."
            if role == "PAPER" else
            "The certification must be acknowledged before it is signed.")

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

    # **The name on the row is read from the record, never typed.** On an
    # EMPLOYEE signature it is the person signing; on a PAPER filing it is
    # the person whose page it is, which is not the person making the call.
    # Offering the filer a name box would let a typo put one person's
    # signature against another's effort, and there is nothing downstream
    # that could catch it — so `employee_key` decides the name, the way
    # `cost_objective.objective_type` decides which objective is
    # administrative rather than a literal somewhere.
    if role == "PAPER":
        # Their account's name first, then the payroll register's, then the
        # key. The register is terse — it carries "Ewing" where the account
        # says "Barb Ewing" — and a certification naming a surname is thinner
        # than the record can be. All three are read; none is typed.
        who = one("""SELECT COALESCE(
                              (SELECT a.display_name FROM actor a
                                WHERE a.employee_key = l.employee_key
                                  AND a.is_active LIMIT 1),
                              max(l.employee_name),
                              l.employee_key)                AS employee_name
                       FROM v_labor_effective l
                      WHERE l.period = %s AND l.employee_key = %s
                      GROUP BY l.employee_key""",
                  (period, body.employee_key))
        signed_by = (who or {}).get("employee_name") or body.employee_key
    else:
        signed_by = actor.display_name

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
               distribution_hash, user_agent, evidence_id, paper_signed_on)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING certification_id, signed_at""",
            (period, body.employee_key, role, actor.actor_id, actor.session_id,
             signed_by, date(int(period), 1, 1), date(int(period), 12, 31),
             statement, json.dumps(payload), _hash(rows),
             request.headers.get("user-agent", "")[:400],
             body.evidence_id if role == "PAPER" else None,
             body.paper_signed_on if role == "PAPER" else None))
        row = cur.fetchone()
        record(actor, "CERTIFY", "labor_certification",
               str(row["certification_id"]),
               after={"employee_key": body.employee_key, "role": role,
                      "objectives": len(rows), "signed_by": signed_by,
                      "evidence_id": body.evidence_id if role == "PAPER" else None,
                      "paper_signed_on": (body.paper_signed_on.isoformat()
                                          if role == "PAPER" and
                                          body.paper_signed_on else None)},
               reason=statement[:200], cursor=cur)

    return {"certification_id": str(row["certification_id"]),
            "signed_at": row["signed_at"], "employee_key": body.employee_key,
            "role": role, "objectives": len(rows), "signed_by": signed_by,
            "evidence_id": body.evidence_id if role == "PAPER" else None,
            "paper_signed_on": body.paper_signed_on if role == "PAPER" else None}


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
                   superseded_at, superseded_reason,
                   -- A filed page and the day it carries. A reviewer asking
                   -- what was attested needs the document as much as the row,
                   -- and the gap between these two dates is the filing lag.
                   evidence_id, paper_signed_on
              FROM labor_certification
             WHERE period = %s AND employee_key = %s
             ORDER BY signed_at DESC""", (period, employee_key)),
    }
