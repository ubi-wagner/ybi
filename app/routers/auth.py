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


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    email = body.email.strip().lower()
    row = one("""SELECT actor_id, email, display_name, role, password_hash,
                        employee_key
                   FROM actor WHERE email = %s AND is_active""", (email,))

    # Verify against a hash either way so a missing account and a wrong
    # password take the same time and give the same answer.
    stored = row["password_hash"] if row else "$2b$12$" + "x" * 53
    if not verify_password(body.password, stored) or not row:
        log.info("failed sign-in for %s", email)
        raise HTTPException(401, "Email or password is incorrect.")

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
    return {"actor_id": actor.actor_id, "email": actor.email,
            "display_name": actor.display_name, "role": actor.role.value,
            "employee_key": actor.employee_key,
            "can_write": actor.can_write, "can_read": actor.can_read}


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
    owner out of their own account. Other sessions are left alone: signing
    someone out of a screen they are working in is not what they asked for.
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

    execute("UPDATE actor SET password_hash = %s WHERE actor_id = %s",
            (hash_password(body.new_password), actor.actor_id))
    # The password itself is never written to the log, only that it changed.
    record(actor, "PASSWORD_CHANGE", "actor", actor.actor_id,
           reason="changed their own password")
    log.info("%s changed their password", actor.email)
    return {"changed": True}


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
                                    employee_key)
                 VALUES (%s,%s,%s,%s,%s) RETURNING actor_id""",
              (body.email.strip().lower(), body.display_name, body.role.value,
               hash_password(body.password), body.employee_key))
    record(admin, "ACTOR_CREATE", "actor", str(row["actor_id"]),
           after={"email": body.email, "role": body.role.value,
                  "employee_key": body.employee_key},
           reason="provisioned")
    log.info("%s provisioned %s as %s", admin.email, body.email, body.role.value)
    return {"actor_id": str(row["actor_id"]), "email": body.email,
            "role": body.role.value}


@router.get("/actors")
def list_actors(admin: Actor = Depends(require_admin)) -> list[dict]:
    from app.db import query
    return query("""SELECT actor_id, email, display_name, role, is_active,
                           employee_key, created_at, last_login_at
                      FROM actor ORDER BY role, email""")
