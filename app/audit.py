"""Recording who did what.

One rule: **the actor is never a parameter.** It is resolved from the
authenticated session and written from the ``Actor`` the dependency produced.
Before there were accounts, ``audit_log.actor`` was a string the caller
supplied, which records a claim rather than a fact — and the claim is made by
the person the trail exists to hold to account.

``record`` therefore takes an ``Actor``, not a name. Passing a string is a type
error, which is the point.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from app.auth import Actor
from app.db import execute

log = logging.getLogger("ybi.audit")


def _json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=_encode)


def _encode(value: Any):
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def note(by: str, action: str, entity: str, entity_id: str, *,
         before: Any = None, after: Any = None, reason: str = "",
         cursor=None) -> None:
    """One audit entry for something a **mechanism** did, in its own name.

    `actor_id` and `session_id` are NULL and `actor` is the mechanism —
    `deployment bootstrap` — because there was no session to record. Naming a
    person here would put their signature on an act they were not present
    for, which is the one thing the trail is for. Migration `087` defines the
    shape and exempts it from *every change names an account and a session*
    by asking two questions instead: is anything named at all, and does the
    row claim a person.

    Use `record()` wherever there is an actor. This is for the boot
    transcribing a document the deployment ships, and for nothing else.
    """
    params = (by, action, entity, str(entity_id),
              _json(before), _json(after), reason)
    sql = """INSERT INTO audit_log (actor, action, entity, entity_id,
                                    before_state, after_state, reason)
             VALUES (%s,%s,%s,%s,%s,%s,%s)"""
    if cursor is not None:
        cursor.execute(sql, params)
    else:
        execute(sql, params)
    log.info("%s %s %s by %s", action, entity, entity_id, by)


def record(actor: Actor, action: str, entity: str, entity_id: str, *,
           before: Any = None, after: Any = None, reason: str = "",
           cursor=None) -> None:
    """Write one audit entry, with identity taken from the session.

    Pass ``cursor`` to enlist in a caller's transaction, so the trail commits
    with the thing it describes. An audit row that survives a rolled-back
    change describes something that never happened.
    """
    params = (actor.display_name or actor.email, actor.actor_id,
              actor.session_id, actor.role.value, action, entity,
              str(entity_id), _json(before), _json(after), reason)
    sql = """INSERT INTO audit_log (actor, actor_id, session_id, actor_role,
                                    action, entity, entity_id,
                                    before_state, after_state, reason)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    if cursor is not None:
        cursor.execute(sql, params)
    else:
        execute(sql, params)
    log.info("%s %s %s by %s", action, entity, entity_id, actor.email)
