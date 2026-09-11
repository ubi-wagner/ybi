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

**Rank and judgment are different things.** There are two axes here and
keeping them apart is what makes the decision trail worth reading.

``Role`` is the provisioning ladder, and it only runs downward: a
SYSTEM_ADMIN sets up the organisation's administrator, an ORG_ADMIN sets up
controllers and employees, and nobody provisions a peer or a superior.
Rank says who may create accounts. It says nothing about who may judge
cost — an administrator who could also classify would be one person with
both the keys and the pen.

``Portfolio`` is judgment, and it is a set rather than a ladder. A person
holds the union of what has been granted to them: the main controller holds
CONTROLLER, a facilities manager holds FACILITIES, and someone who runs both
facilities and inventory holds both. Nothing accumulates into CONTROLLER,
because CONTROLLER is the only portfolio that can seal a decision set,
unseal one, or compute a rate — and the guarantee the system rests on is
that classifications were fixed before any rate existed.
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
    """Rank on the provisioning ladder. Not authority over cost."""

    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    CONTROLLER = "CONTROLLER"
    EMPLOYEE = "EMPLOYEE"
    AUDITOR = "AUDITOR"


class Portfolio(StrEnum):
    """Authority over a part of the cost record. Held as a set."""

    CONTROLLER = "CONTROLLER"
    INVENTORY = "INVENTORY"
    PROJECT = "PROJECT"
    FACILITIES = "FACILITIES"
    OFFICE = "OFFICE"


#: Rank, low number first. Provisioning runs strictly downward; the database
#: enforces the same thing in provisioning_runs_downward().
RANK = {Role.SYSTEM_ADMIN: 0, Role.ORG_ADMIN: 1,
        Role.CONTROLLER: 2, Role.EMPLOYEE: 2, Role.AUDITOR: 2}

#: Who may provision accounts at all.
ADMINS = frozenset({Role.SYSTEM_ADMIN, Role.ORG_ADMIN})

#: Everyone who may read the ledger, the queue and the workpapers.
#:
#: An employee is not here: they read their own time and their own documents,
#: which are their own screens, not this one.
#:
#: Nor is SYSTEM_ADMIN. That account exists to stand the software up and to
#: appoint the organisation's administrator — it belongs to whoever is
#: running the system, who may be outside the organisation entirely. Letting
#: it read every employee's timesheet and take the audit package away because
#: it can also create accounts is exactly the conflation this module is
#: written to avoid, and exactly what a reviewer would ask about first. It
#: sees the roster and nothing else.
#:
#: ORG_ADMIN is here, because that is the organisation's own executive
#: reading the organisation's own books.
READERS = frozenset({Role.CONTROLLER, Role.AUDITOR, Role.ORG_ADMIN})


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
    portfolios: frozenset[Portfolio] = frozenset()

    def holds(self, *portfolios: Portfolio) -> bool:
        """True when the actor holds any of these portfolios."""
        return bool(self.portfolios & frozenset(portfolios))

    @property
    def may_seal(self) -> bool:
        """Seal, unseal, compute a rate, restate an invoice.

        The one authority nothing else adds up to. A facilities manager with
        every other portfolio still cannot fix the classifications and then
        produce a number from them, because that is the sequence the whole
        record is built to prove.
        """
        return Portfolio.CONTROLLER in self.portfolios

    @property
    def can_write(self) -> bool:
        """Holds authority over some part of the cost record."""
        return bool(self.portfolios)

    @property
    def can_read(self) -> bool:
        return self.role in READERS

    @property
    def is_admin(self) -> bool:
        return self.role in ADMINS

    @property
    def is_staff(self) -> bool:
        """Has a timesheet and a document inbox — which is everyone on the
        payroll, controllers included. A controller is an employee too."""
        return self.employee_key is not None

    def may_provision(self, role: Role) -> bool:
        return self.is_admin and RANK[self.role] < RANK[role]

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
                name: str, employee_key: str | None,
                portfolios: list[str] | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(actor_id),
        "sid": str(session_id),
        "email": email,
        "role": role,
        "name": name,
        "emp": employee_key,
        # Carried for readability in a decoded token. Authority is read from
        # the database on every request, not from here: a portfolio revoked
        # at ten past nine must not survive in a cookie until nine at night.
        "pf": sorted(portfolios or []),
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
                        a.role, a.employee_key,
                        COALESCE((SELECT array_agg(p.portfolio::text)
                                    FROM actor_portfolio p
                                   WHERE p.actor_id = a.actor_id
                                     AND p.revoked_at IS NULL), '{}')
                          AS portfolios
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
        portfolios=frozenset(Portfolio(p) for p in row["portfolios"]),
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


def refuse_issued_password(actor: Actor) -> None:
    """Nobody writes to the record on a password somebody else chose.

    An account is provisioned with a password an administrator picks and
    hands over. Until its owner replaces it, two people know it — so a
    classification, a certification or a grant made from that account
    identifies a pair of people rather than one, and a record whose
    signatures anyone could have written is not a record.

    This is the same reason the seed password is refused, and the seed
    password is only the worst case of it: one password, everybody.

    Reading stays open, so somebody can look around first, and changing your
    own password is never blocked — otherwise the gate would have no exit.
    """
    row = one("""SELECT password_set_by::text AS origin
                   FROM actor WHERE actor_id = %s""", (actor.actor_id,))
    if row and row["origin"] != "SELF":
        raise HTTPException(403, {
            "error": "PASSWORD_NOT_YOUR_OWN",
            "message": ("Choose your own password before recording anything. "
                        "The one you signed in with was issued to you by "
                        "somebody else, so it does not yet say who you are."),
            "origin": row["origin"]})


def require_portfolio(*portfolios: Portfolio):
    """Dependency factory: the caller must hold one of ``portfolios``.

    The refusal names what would be needed, because "403" on its own sends
    somebody to find an administrator without knowing what to ask for.
    """
    wanted = frozenset(portfolios)

    def guard(actor: Actor = Depends(current_actor)) -> Actor:
        if not actor.holds(*wanted):
            names = ", ".join(sorted(p.value for p in wanted))
            held = ", ".join(sorted(p.value for p in actor.portfolios))
            raise HTTPException(
                403, f"This needs the {names} portfolio. "
                     f"{actor.display_name} holds {held or 'none'}. "
                     f"An administrator can grant it.")
        refuse_issued_password(actor)
        return actor

    return guard


#: Read the ledger, queue, rates and workpapers.
require_reader = require_role(Role.CONTROLLER, Role.AUDITOR,
                              Role.SYSTEM_ADMIN, Role.ORG_ADMIN)

#: Classify, import, reconcile — and seal. The only portfolio that can fix
#: the judgments and then produce a number from them.
require_controller = require_portfolio(Portfolio.CONTROLLER)

#: The narrower portfolios. Each gates the part of the record it owns, so
#: granting somebody facilities does not hand them the asset register.
require_inventory = require_portfolio(Portfolio.INVENTORY, Portfolio.CONTROLLER)
require_project = require_portfolio(Portfolio.PROJECT, Portfolio.CONTROLLER)
require_facilities = require_portfolio(Portfolio.FACILITIES, Portfolio.CONTROLLER)
require_office = require_portfolio(Portfolio.OFFICE, Portfolio.CONTROLLER)

def _admin_guard(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role not in ADMINS:
        raise HTTPException(
            403, f"{actor.role.value} may not provision accounts; requires "
                 f"SYSTEM_ADMIN or ORG_ADMIN.")
    refuse_issued_password(actor)
    return actor


#: Provision actors. *Which* accounts they may create is a separate question,
#: answered by Actor.may_provision and by the database's ladder trigger.
require_admin = _admin_guard

#: Everyone signed in, reading. Their own time, their own certification,
#: their own documents — the things that belong to the person rather than to
#: a portfolio.
require_signed_in = current_actor


def require_own_writes(actor: Actor = Depends(current_actor)) -> Actor:
    """Signed in, and on a password only they know.

    The personal writes need this as much as the portfolio ones do — more,
    arguably. A certification is a statement by a named person that they did
    the work, and a timesheet is the evidence under it. Made from an account
    whose password two people know, neither is worth much.

    This was missed the first time: the gate covered portfolios and
    administration and left the three screens everybody actually uses wide
    open. A newcomer could sign a 2 CFR 200.430(i) certification on the
    password an administrator had handed them an hour earlier.
    """
    refuse_issued_password(actor)
    return actor
