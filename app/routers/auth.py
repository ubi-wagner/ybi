"""Sign in, sign out, and who am I.

Login is deliberately quiet about which half of a credential was wrong: an
error that distinguishes "no such account" from "wrong password" is an account
enumeration oracle, and this system knows the names of everyone at the
organisation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.auth import (SESSION_COOKIE, SESSION_MAX_AGE, Actor, Portfolio, Role,
                      current_actor, hash_password, issue_token, require_admin,
                      session_expiry, verify_password)
from app.audit import record
from app.db import execute, one, query, transaction
from app.settings import settings

log = logging.getLogger("ybi.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ActorIn(BaseModel):
    email: EmailStr
    display_name: str
    role: Role
    password: str
    employee_key: str | None = None
    #: Portfolios to grant at the same time. Optional — an account with none
    #: can still keep a timesheet and send in documents, which is what most
    #: of the organisation needs.
    portfolios: list[Portfolio] = []
    grant_reason: str = ""


#: Failures in the window before sign-in is refused outright. bcrypt makes one
#: guess expensive; this is what makes a series of them expensive.
MAX_FAILURES = 8
LOCKOUT_WINDOW = "15 minutes"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    email = body.email.strip().lower()
    ip = request.client.host if request.client else ""

    failures = one("SELECT recent_login_failures(%s, %s::interval) AS n",
                   (email, LOCKOUT_WINDOW))["n"]
    if failures >= MAX_FAILURES:
        log.warning("sign-in refused for %s from %s — %d recent failures",
                    email, ip, failures)
        raise HTTPException(
            429, "Too many failed attempts. Wait fifteen minutes and try "
                 "again, or ask an administrator to reset your password.")

    row = one("""SELECT actor_id, email, display_name, role, password_hash,
                        employee_key
                   FROM actor WHERE email = %s AND is_active""", (email,))

    # Verify against a hash either way so a missing account and a wrong
    # password take the same time and give the same answer.
    stored = row["password_hash"] if row else "$2b$12$" + "x" * 53
    if not verify_password(body.password, stored) or not row:
        execute("""INSERT INTO login_attempt (email, ip, succeeded)
                   VALUES (%s, %s, false)""", (email, ip))
        log.info("failed sign-in for %s from %s", email, ip)
        raise HTTPException(401, "Email or password is incorrect.")

    execute("INSERT INTO login_attempt (email, ip, succeeded) VALUES (%s,%s,true)",
            (email, ip))

    with transaction() as cur:
        cur.execute("""INSERT INTO actor_session (actor_id, expires_at, user_agent)
                       VALUES (%s, %s, %s) RETURNING session_id""",
                    (row["actor_id"], session_expiry(),
                     request.headers.get("user-agent", "")[:400]))
        session_id = cur.fetchone()["session_id"]
        cur.execute("UPDATE actor SET last_login_at = now() WHERE actor_id = %s",
                    (row["actor_id"],))

    held = [r["portfolio"] for r in query(
        """SELECT portfolio::text AS portfolio FROM actor_portfolio
            WHERE actor_id = %s AND revoked_at IS NULL ORDER BY portfolio""",
        (row["actor_id"],))]
    signed_in = Actor(actor_id=str(row["actor_id"]), email=row["email"],
                      display_name=row["display_name"], role=Role(row["role"]),
                      session_id=str(session_id),
                      employee_key=row["employee_key"],
                      portfolios=frozenset(Portfolio(p) for p in held))
    record(signed_in, "SIGN_IN", "actor_session", str(session_id),
           reason=request.headers.get("user-agent", "")[:200])

    token = issue_token(actor_id=row["actor_id"], session_id=session_id,
                        email=row["email"], role=row["role"],
                        name=row["display_name"],
                        employee_key=row["employee_key"],
                        portfolios=held)
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.env != "dev",
        path="/",
    )
    return {"actor_id": str(row["actor_id"]), "email": row["email"],
            "display_name": row["display_name"], "role": row["role"],
            "employee_key": row["employee_key"], "portfolios": held}


@router.post("/logout")
def logout(response: Response, actor: Actor = Depends(current_actor)) -> dict:
    execute("UPDATE actor_session SET revoked_at = now() WHERE session_id = %s",
            (actor.session_id,))
    record(actor, "SIGN_OUT", "actor_session", actor.session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(actor: Actor = Depends(current_actor)) -> dict:
    # holds_bootstrap_password rides along so the shell can say so. An account
    # still on the shared seed password does not identify one person, and the
    # person who can fix that is the one signed into it.
    standing = one("""SELECT password_set_by::text AS password_set_by,
                             holds_bootstrap_password
                        FROM v_account_standing WHERE actor_id = %s""",
                   (actor.actor_id,)) or {}
    return {"actor_id": actor.actor_id, "email": actor.email,
            "display_name": actor.display_name, "role": actor.role.value,
            "employee_key": actor.employee_key,
            "portfolios": sorted(p.value for p in actor.portfolios),
            "may_seal": actor.may_seal,
            "is_admin": actor.is_admin,
            "is_staff": actor.is_staff,
            "can_write": actor.can_write, "can_read": actor.can_read,
            "may_provision": sorted(r.value for r in Role
                                    if actor.may_provision(r)),
            "password_set_by": standing.get("password_set_by"),
            "holds_bootstrap_password":
                bool(standing.get("holds_bootstrap_password")),
            # The shell reads this and puts the password screen in front of
            # everything else. Until it is False the account cannot write.
            "must_set_password": standing.get("password_set_by") != "SELF"}


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/password")
def change_password(body: PasswordIn, request: Request,
                    actor: Actor = Depends(current_actor)) -> dict:
    """Change your own password.

    Seeding provisions every account with one bootstrap password, which is
    what a bootstrap is. Without this the bootstrap password is the permanent
    password, shared across the controller, the auditor and two employees —
    and a record whose signatures anyone could have written is not a record.

    The current password is required, so a borrowed session cannot lock the
    owner out of their own account.

    Every other session is closed. The common reason to change a password is
    that someone else may have it, and a change that leaves their session open
    does not answer that. The session doing the changing survives, so the
    person is not signed out of the screen they are standing in.
    """
    row = one("SELECT password_hash FROM actor WHERE actor_id = %s",
              (actor.actor_id,))
    if not row or not verify_password(body.current_password, row["password_hash"]):
        log.warning("failed password change for %s from %s", actor.email,
                    request.client.host if request.client else "?")
        raise HTTPException(403, "That is not your current password.")
    if len(body.new_password) < 12:
        raise HTTPException(422, "A password must be at least 12 characters.")
    if body.new_password == body.current_password:
        raise HTTPException(422, "The new password is the same as the old one.")

    with transaction() as cur:
        cur.execute("""UPDATE actor
                          SET password_hash = %s, password_set_by = 'SELF',
                              password_set_at = now()
                        WHERE actor_id = %s""",
                    (hash_password(body.new_password), actor.actor_id))
        cur.execute("""UPDATE actor_session SET revoked_at = now()
                        WHERE actor_id = %s AND session_id <> %s
                          AND revoked_at IS NULL
                        RETURNING session_id""",
                    (actor.actor_id, actor.session_id))
        closed = len(cur.fetchall())
        # The password itself is never written to the log, only that it changed.
        record(actor, "PASSWORD_CHANGE", "actor", actor.actor_id,
               after={"other_sessions_closed": closed},
               reason="changed their own password", cursor=cur)
    log.info("%s changed their password, closed %d other sessions",
             actor.email, closed)
    return {"changed": True, "other_sessions_closed": closed}


@router.post("/actors", status_code=201)
def create_actor(body: ActorIn, admin: Actor = Depends(require_admin)) -> dict:
    """Provision an account.

    The ladder runs downward and only downward: a SYSTEM_ADMIN sets up the
    organisation's administrator, an ORG_ADMIN sets up controllers and
    employees, and neither can mint a peer. A database trigger says the same
    thing, so the rule holds if this handler is ever wrong.
    """
    if not admin.may_provision(body.role):
        raise HTTPException(
            403, f"{admin.role.value} may not create a {body.role.value} "
                 f"account. An account is set up by someone above it, never "
                 f"by a peer — ask a "
                 f"{'SYSTEM_ADMIN' if admin.role is Role.ORG_ADMIN else 'system administrator'}.")
    if body.role is Role.EMPLOYEE and not body.employee_key:
        raise HTTPException(422, "An EMPLOYEE account must name the employee "
                                 "it keeps time and certifies for.")
    if len(body.password) < 12:
        raise HTTPException(422, "A password must be at least 12 characters.")
    if body.portfolios and not body.grant_reason.strip():
        raise HTTPException(422, "Granting a portfolio needs a reason — it is "
                                 "a grant of authority over the cost record.")
    if one("SELECT 1 FROM actor WHERE email = %s",
           (body.email.strip().lower(),)):
        raise HTTPException(409, "That email already has an account.")
    if body.employee_key and one("SELECT 1 FROM actor WHERE employee_key = %s",
                                 (body.employee_key,)):
        raise HTTPException(409, f"{body.employee_key} already has an account.")

    with transaction() as cur:
        cur.execute("""INSERT INTO actor (email, display_name, role,
                                          password_hash, employee_key,
                                          password_set_by, provisioned_by)
                       VALUES (%s,%s,%s,%s,%s,'ADMIN',%s) RETURNING actor_id""",
                    (body.email.strip().lower(), body.display_name,
                     body.role.value, hash_password(body.password),
                     body.employee_key, admin.actor_id))
        actor_id = cur.fetchone()["actor_id"]
        for pf in body.portfolios:
            cur.execute("""INSERT INTO actor_portfolio
                             (actor_id, portfolio, granted_by, reason)
                           VALUES (%s,%s,%s,%s)""",
                        (actor_id, pf.value, admin.actor_id,
                         body.grant_reason.strip()))
        record(admin, "ACTOR_CREATE", "actor", str(actor_id),
               after={"email": body.email, "role": body.role.value,
                      "employee_key": body.employee_key,
                      "portfolios": [p.value for p in body.portfolios]},
               reason=body.grant_reason.strip() or "provisioned", cursor=cur)
    log.info("%s provisioned %s as %s (%s)", admin.email, body.email,
             body.role.value, ", ".join(p.value for p in body.portfolios) or "no portfolio")
    return {"actor_id": str(actor_id), "email": body.email,
            "role": body.role.value,
            "portfolios": [p.value for p in body.portfolios]}


class GrantIn(BaseModel):
    portfolio: Portfolio
    reason: str = Field(min_length=10)


@router.post("/actors/{actor_id}/portfolios", status_code=201)
def grant_portfolio(actor_id: str, body: GrantIn,
                    admin: Actor = Depends(require_admin)) -> dict:
    """Grant authority over a part of the cost record.

    Not to yourself. An administrator who needs a portfolio asks the
    administrator above them, and the trail then reads as two people agreeing
    rather than one person deciding. The table refuses a self-grant too.
    """
    if actor_id == admin.actor_id:
        raise HTTPException(
            403, "Nobody grants themselves authority over the cost record. "
                 "Ask the administrator above you — the trail should show two "
                 "people, not one.")
    target = one("SELECT display_name, role FROM actor WHERE actor_id = %s",
                 (actor_id,))
    if not target:
        raise HTTPException(404, "No such account.")
    with transaction() as cur:
        cur.execute("""INSERT INTO actor_portfolio
                         (actor_id, portfolio, granted_by, reason)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (actor_id, body.portfolio.value, admin.actor_id,
                     body.reason.strip()))
        record(admin, "PORTFOLIO_GRANT", "actor", actor_id,
               after={"portfolio": body.portfolio.value,
                      "to": target["display_name"]},
               reason=body.reason.strip(), cursor=cur)
    log.info("%s granted %s to %s", admin.email, body.portfolio.value,
             target["display_name"])
    return {"actor_id": actor_id, "portfolio": body.portfolio.value}


class RevokeIn(BaseModel):
    portfolio: Portfolio
    reason: str = Field(min_length=10)


@router.post("/actors/{actor_id}/portfolios/revoke")
def revoke_portfolio(actor_id: str, body: RevokeIn,
                     admin: Actor = Depends(require_admin)) -> dict:
    """Take it back, in writing.

    Revoking is a second row's worth of writing rather than a delete. Who
    could do what, and when, is part of the audit file: a judgment recorded
    in March by somebody whose authority ended in June was still authorised
    when it was made, and the file has to be able to show that.
    """
    with transaction() as cur:
        cur.execute("""UPDATE actor_portfolio
                          SET revoked_at = now(), revoked_by = %s,
                              revoked_reason = %s
                        WHERE actor_id = %s AND portfolio = %s
                          AND revoked_at IS NULL
                        RETURNING granted_at""",
                    (admin.actor_id, body.reason.strip(), actor_id,
                     body.portfolio.value))
        if not cur.fetchone():
            raise HTTPException(404, "That account does not hold it.")
        cur.execute("""UPDATE actor_session SET revoked_at = now()
                        WHERE actor_id = %s AND revoked_at IS NULL""",
                    (actor_id,))
        record(admin, "PORTFOLIO_REVOKE", "actor", actor_id,
               after={"portfolio": body.portfolio.value},
               reason=body.reason.strip(), cursor=cur)
    return {"actor_id": actor_id, "portfolio": body.portfolio.value,
            "revoked": True}


class ActiveIn(BaseModel):
    is_active: bool
    reason: str = Field(min_length=10)


@router.post("/actors/{actor_id}/active")
def set_active(actor_id: str, body: ActiveIn,
               admin: Actor = Depends(require_admin)) -> dict:
    """Turn an account off, or back on. Never delete one.

    Every judgment, certification and upload points at an actor row. Deleting
    the account would orphan the record it authorised, which is the opposite
    of what the record is for.
    """
    if actor_id == admin.actor_id:
        raise HTTPException(422, "You cannot deactivate your own account.")
    target = one("SELECT display_name, role FROM actor WHERE actor_id = %s",
                 (actor_id,))
    if not target:
        raise HTTPException(404, "No such account.")
    if not admin.may_provision(Role(target["role"])):
        raise HTTPException(
            403, f"{admin.role.value} may not change a {target['role']} "
                 f"account.")
    with transaction() as cur:
        cur.execute("UPDATE actor SET is_active = %s WHERE actor_id = %s",
                    (body.is_active, actor_id))
        if not body.is_active:
            cur.execute("""UPDATE actor_session SET revoked_at = now()
                            WHERE actor_id = %s AND revoked_at IS NULL""",
                        (actor_id,))
        record(admin, "ACTOR_ACTIVE", "actor", actor_id,
               after={"is_active": body.is_active,
                      "who": target["display_name"]},
               reason=body.reason.strip(), cursor=cur)
    return {"actor_id": actor_id, "is_active": body.is_active}


class ResetIn(BaseModel):
    new_password: str


@router.post("/actors/{actor_id}/password")
def reset_password(actor_id: str, body: ResetIn,
                   admin: Actor = Depends(require_admin)) -> dict:
    """Reset someone else's password. ADMIN only.

    The manual has always said to ask the administrator for a reset, and
    until now there was no way for them to do one short of writing SQL by
    hand — which is exactly the kind of out-of-band change this system exists
    to make unnecessary.

    A reset closes every session that account has open, including the one the
    person may be sitting in: a reset is for when the account may be in the
    wrong hands, and leaving those sessions alive answers nothing. It is
    recorded against the administrator who did it, and the account is marked
    as holding an administrator-set password until its owner replaces it.
    """
    if len(body.new_password) < 12:
        raise HTTPException(422, "A password must be at least 12 characters.")
    target = one("SELECT email, display_name, role FROM actor "
                 "WHERE actor_id = %s", (actor_id,))
    if not target:
        raise HTTPException(404, "No such account.")
    if actor_id == admin.actor_id:
        raise HTTPException(
            422, "Use the password change on your own account — a reset is "
                 "for handing an account back to somebody else.")
    if not admin.may_provision(Role(target["role"])):
        raise HTTPException(
            403, f"{admin.role.value} may not reset a {target['role']} "
                 f"password. Rank runs downward here as well.")

    with transaction() as cur:
        cur.execute("""UPDATE actor
                          SET password_hash = %s, password_set_by = 'ADMIN',
                              password_set_at = now()
                        WHERE actor_id = %s""",
                    (hash_password(body.new_password), actor_id))
        cur.execute("""UPDATE actor_session SET revoked_at = now()
                        WHERE actor_id = %s AND revoked_at IS NULL
                        RETURNING session_id""", (actor_id,))
        closed = len(cur.fetchall())
        record(admin, "PASSWORD_RESET", "actor", actor_id,
               after={"sessions_closed": closed, "email": target["email"]},
               reason=f"reset by {admin.email}", cursor=cur)
    log.warning("%s reset the password for %s, closed %d sessions",
                admin.email, target["email"], closed)
    return {"reset": True, "email": target["email"], "sessions_closed": closed}


@router.get("/actors")
def list_actors(admin: Actor = Depends(require_admin)) -> list[dict]:
    """The roster, with account standing.

    holds_bootstrap_password is the row that matters: it names the accounts
    that do not yet identify one person.
    """
    return query("""SELECT actor_id, email, display_name, role::text AS role,
                           is_active, employee_key, created_at, last_login_at,
                           password_set_by::text AS password_set_by,
                           password_set_at, holds_bootstrap_password,
                           live_sessions, failures_24h,
                           portfolios::text[] AS portfolios, may_seal,
                           provisioned_by_name
                      FROM v_account_standing
                     ORDER BY provisioning_rank(role), display_name""")


@router.get("/roster-gaps")
def roster_gaps(admin: Actor = Depends(require_admin)) -> dict:
    """People the books know about who cannot sign in.

    The payroll register names everyone who was paid in 2025. An account is
    what turns one of those names into somebody who can keep their own
    timesheet and send in their own receipts — and until they have one, their
    effort has to be reconstructed on their behalf, which is the weakest
    evidence in the system.

    The register carries surnames only, so the email address has to be typed
    in by somebody who knows it. The suggestion below follows the convention
    the existing accounts use and is a starting point, not an answer.
    """
    rows = query("""
        SELECT DISTINCT l.employee_key,
               max(l.employee_name)                      AS employee_name,
               max(l.payroll_wages)                      AS payroll_wages
          FROM v_labor_effective l
         WHERE NOT EXISTS (SELECT 1 FROM actor a
                            WHERE a.employee_key = l.employee_key)
         GROUP BY l.employee_key
         ORDER BY max(l.payroll_wages) DESC NULLS LAST""")
    for r in rows:
        r["suggested_email"] = f"{r['employee_key'].lower()}@ybi.org"
    have = one("""SELECT count(*) AS n FROM actor
                   WHERE employee_key IS NOT NULL AND is_active""")
    return {"without_account": len(rows), "with_account": have["n"],
            "people": rows,
            "note": ("Email addresses are a suggestion from the naming "
                     "convention, not a lookup. Correct each one before "
                     "creating the account.")}
