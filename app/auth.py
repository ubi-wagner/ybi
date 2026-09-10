"""Actor authentication and authorisation.

Two rules shape this module, both borrowed from the govwin estate where they
were learned expensively.

**Fail closed.** With no signing secret configured the service authenticates
nobody, rather than falling open to a default. A cost system that quietly
accepts unsigned sessions in production is worse than one that refuses to
start.

**An unauthenticated caller and a forbidden one are different answers.** 401
means "I do not know who you are"; 403 means "I know, and no". Collapsing them
is how a test harness comes to report a permission finding against a rig it
never logged into — a finding shaped exactly like a real one, from a script
that never knocked on the door.

Roles are not a hierarchy. An ADMIN provisions people and does not thereby
acquire the right to make cost judgments; an AUDITOR reads everything and
writes nothing. Separating administration from judgment is what makes the
decision trail worth reading.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from app.db import one

log = logging.getLogger("ybi.auth")

SESSION_COOKIE = "ybi_session"
SESSION_MAX_AGE = 12 * 60 * 60  # 12 hours; a working day, not a fortnight
_ALGORITHM = "HS256"


class Role(StrEnum):
    CONTROLLER = "CONTROLLER"
    EMPLOYEE = "EMPLOYEE"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


#: Everyone who may read the ledger, the queue and the workpapers.
READERS = frozenset({Role.CONTROLLER, Role.AUDITOR, Role.ADMIN})

#: Who may import, classify, seal and restate. Deliberately one role.
WRITERS = frozenset({Role.CONTROLLER})


class AuthNotConfigured(RuntimeError):
    """No signing secret. The service authenticates nobody."""


@dataclass(frozen=True)
class Actor:
    """The authenticated caller."""

    actor_id: str
    email: str
    display_name: str
    role: Role
    session_id: str
    employee_key: str | None = None

    @property
    def can_write(self) -> bool:
        return self.role in WRITERS

    @property
    def can_read(self) -> bool:
        return self.role in READERS

    def owns_employee(self, employee_key: str) -> bool:
        """True when this actor may certify for ``employee_key``.

        An employee certifies their own effort and nobody else's. That is the
        whole content of a 2 CFR 200.430(i) certification: a statement by the
        person who did the work, or by a supervisor with firsthand knowledge.
        A controller signing on an employee's behalf is not that.
        """
        return self.employee_key is not None and self.employee_key == employee_key


#: RFC 7518 section 3.2: an HMAC key for SHA-256 must be at least as long as
#: the hash output. A short secret is a weak signature, and a weak signature on
#: a session cookie is a forgeable actor.
MIN_SECRET_BYTES = 32


def jwt_secret() -> str:
    secret = os.environ.get("YBI_JWT_SECRET", "")
    if not secret:
        raise AuthNotConfigured(
            "YBI_JWT_SECRET is not set. Refusing to authenticate. "
            "Railway: add it as a service variable."
        )
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise AuthNotConfigured(
            f"YBI_JWT_SECRET is {len(secret.encode())} bytes; at least "
            f"{MIN_SECRET_BYTES} are required (RFC 7518 section 3.2). "
            f"Generate one with: python3 -c "
            f"'import secrets; print(secrets.token_urlsafe(48))'"
        )
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


def issue_token(*, actor_id: str, session_id: str, email: str, role: str,
                name: str, employee_key: str | None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(actor_id),
        "sid": str(session_id),
        "email": email,
        "role": role,
        "name": name,
        "emp": employee_key,
        "iat": now,
        "exp": now + SESSION_MAX_AGE,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=_ALGORITHM)


def read_token(token: str) -> dict | None:
    """Decode and verify a session token, or return None."""
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)


# ---------------------------------------------------------------- dependencies


def current_actor(request: Request) -> Actor:
    """Resolve the caller, or 401.

    The session is checked against the database as well as the signature, so a
    revoked session stops working immediately rather than at token expiry.
    Revocation that takes twelve hours to bite is not revocation.
    """
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(401, "Not signed in.")

    claims = read_token(token)
    if not claims:
        raise HTTPException(401, "Session is invalid or has expired.")

    row = one("""SELECT s.session_id, a.actor_id, a.email, a.display_name,
                        a.role, a.employee_key
                   FROM actor_session s
                   JOIN actor a USING (actor_id)
                  WHERE s.session_id = %s
                    AND s.revoked_at IS NULL
                    AND s.expires_at > now()
                    AND a.is_active""", (claims.get("sid"),))
    if not row:
        raise HTTPException(401, "Session is no longer valid.")

    return Actor(
        actor_id=str(row["actor_id"]),
        email=row["email"],
        display_name=row["display_name"],
        role=Role(row["role"]),
        session_id=str(row["session_id"]),
        employee_key=row["employee_key"],
    )


def require_role(*roles: Role):
    """Dependency factory: the caller must hold one of ``roles``.

    401 and 403 stay distinct. ``current_actor`` raises 401 when there is no
    valid session; only a caller we have positively identified can be given a
    403, so "I never signed in" can never be mistaken for "I was refused".
    """
    allowed = frozenset(roles)

    def guard(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in allowed:
            names = ", ".join(sorted(r.value for r in allowed))
            raise HTTPException(
                403, f"{actor.role.value} may not do this; requires {names}.")
        return actor

    return guard


#: Read the ledger, queue, rates and workpapers.
require_reader = require_role(Role.CONTROLLER, Role.AUDITOR, Role.ADMIN)

#: Import, classify, seal, restate.
require_controller = require_role(Role.CONTROLLER)

#: Provision actors.
require_admin = require_role(Role.ADMIN)
