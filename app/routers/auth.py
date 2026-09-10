"""Sign in, sign out, and who am I.

Login is deliberately quiet about which half of a credential was wrong: an
error that distinguishes "no such account" from "wrong password" is an account
enumeration oracle, and this system knows the names of everyone at the
organisation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from app.auth import (SESSION_COOKIE, SESSION_MAX_AGE, Actor, Role,
                      current_actor, hash_password, issue_token, require_admin,
                      session_expiry, verify_password)
from app.audit import record
from app.db import execute, one, transaction
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

    signed_in = Actor(actor_id=str(row["actor_id"]), email=row["email"],
                      display_name=row["display_name"], role=Role(row["role"]),
                      session_id=str(session_id),
                      employee_key=row["employee_key"])
    record(signed_in, "SIGN_IN", "actor_session", str(session_id),
           reason=request.headers.get("user-agent", "")[:200])

    token = issue_token(actor_id=row["actor_id"], session_id=session_id,
                        email=row["email"], role=row["role"],
                        name=row["display_name"],
                        employee_key=row["employee_key"])
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
            "employee_key": row["employee_key"]}


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
            "can_write": actor.can_write, "can_read": actor.can_read,
            "password_set_by": standing.get("password_set_by"),
            "holds_bootstrap_password":
                bool(standing.get("holds_bootstrap_password"))}


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


@router.post("/actors")
def create_actor(body: ActorIn, admin: Actor = Depends(require_admin)) -> dict:
    """Provision an actor. ADMIN only."""
    if body.role is Role.EMPLOYEE and not body.employee_key:
        raise HTTPException(422, "An EMPLOYEE actor must name the employee it "
                                 "certifies for.")
    existing = one("SELECT 1 FROM actor WHERE email = %s",
                   (body.email.strip().lower(),))
    if existing:
        raise HTTPException(409, "That email already has an account.")

    row = one("""INSERT INTO actor (email, display_name, role, password_hash,
                                    employee_key, password_set_by)
                 VALUES (%s,%s,%s,%s,%s,'ADMIN') RETURNING actor_id""",
              (body.email.strip().lower(), body.display_name, body.role.value,
               hash_password(body.password), body.employee_key))
    record(admin, "ACTOR_CREATE", "actor", str(row["actor_id"]),
           after={"email": body.email, "role": body.role.value,
                  "employee_key": body.employee_key},
           reason="provisioned")
    log.info("%s provisioned %s as %s", admin.email, body.email, body.role.value)
    return {"actor_id": str(row["actor_id"]), "email": body.email,
            "role": body.role.value}


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
    target = one("SELECT email, display_name FROM actor WHERE actor_id = %s",
                 (actor_id,))
    if not target:
        raise HTTPException(404, "No such account.")
    if actor_id == admin.actor_id:
        raise HTTPException(
            422, "Use the password change on your own account — a reset is "
                 "for handing an account back to somebody else.")

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
    from app.db import query
    return query("""SELECT actor_id, email, display_name, role, is_active,
                           employee_key, created_at, last_login_at,
                           password_set_by::text AS password_set_by,
                           password_set_at, holds_bootstrap_password,
                           live_sessions, failures_24h
                      FROM v_account_standing ORDER BY role, email""")
