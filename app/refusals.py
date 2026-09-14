"""Recording what the system refused.

`audit.record` is called by a handler that succeeded. Nothing calls anything
when a handler refuses, so the most frustrating case — somebody pressed a
button and the system said no — left no trace anywhere.

This is middleware rather than a decorator on each route, for the same reason
the actor is never a parameter: a rule that depends on every handler
remembering it is a rule that holds until somebody forgets. A route added next
year records its refusals without knowing this file exists.

Only mutating methods. A refused GET is usually somebody opening a screen
they do not hold, which the boundary tests already prove and which would bury
the writes that matter in noise.
"""

from __future__ import annotations

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("ybi.refusals")

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Never recorded, whatever they answer. A failed sign-in is a security event
#: with its own handling and its own rate limit, and writing the attempted
#: path here would put a stream of anonymous rows in front of the refusals a
#: person can actually act on.
SKIP = ("/api/auth/login", "/api/auth/logout", "/api/events")


def _detail(body: bytes) -> str:
    """The message the API gave, not the JSON it gave it in.

    A reader wants "A rate cannot be computed while a control is open", not
    `{"detail": "..."}`. Falls back to the raw body, truncated, because an
    unparseable error is still worth having.
    """
    if not body:
        return ""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return body.decode("utf-8", "replace")[:500]
    if isinstance(parsed, dict):
        for key in ("detail", "message", "error"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value[:500]
            if value is not None:
                return json.dumps(value)[:500]
    return json.dumps(parsed)[:500]


class RecordRefusals:
    """Write a `refusal` row for every mutating request answered 4xx or 5xx."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in MUTATING:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(s) for s in SKIP):
            await self.app(scope, receive, send)
            return

        status = 0
        chunks: list[bytes] = []

        async def watch(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and status >= 400:
                # Error bodies are small. Anything large enough to stream is
                # not an error body, and is left alone.
                if len(chunks) < 8:
                    chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception as exc:                           # noqa: BLE001
            # The case most worth recording, and the one this middleware
            # missed at first: an unhandled exception propagates out of the
            # application before any status is sent, so the `status >= 400`
            # check below never ran and a crash left no trace here at all.
            # Starlette turns it into a 500 further out; the note about it
            # has to be taken here, on the way past.
            try:
                self._write(scope, 500, f"{type(exc).__name__}: {exc}"[:500])
            except Exception:                              # noqa: BLE001
                log.exception("could not record a fault for %s %s",
                              scope.get("method"), path)
            raise

        if status < 400:
            return

        try:
            self._write(scope, status, _detail(b"".join(chunks)))
        except Exception:                                  # noqa: BLE001
            # Recording a refusal must never turn a refusal into a crash. The
            # request has already been answered by this point; all that is at
            # stake is the note about it, and a log line is the right place
            # for the failure to record a failure.
            log.exception("could not record a refusal for %s %s",
                          scope.get("method"), path)

    @staticmethod
    def _write(scope: Scope, status: int, detail: str) -> None:
        from app.db import execute

        # The session is resolved the same way the dependencies resolve it, so
        # a refusal names the same person an audit entry would have. Anonymous
        # is a real answer here — a 401 is precisely the case where there is
        # nobody to name — and the column is nullable for it.
        # "anonymous" covers two different things and both are honest. A 401
        # has nobody to name by definition. And a body FastAPI rejects as
        # malformed is refused *before* any dependency runs, so the session
        # was never resolved even though the caller had one — the request
        # never got far enough for the system to learn who they were.
        actor_id = None
        label = "anonymous"
        actor = scope.get("state", {}).get("actor") if scope.get("state") else None
        if actor is not None:
            actor_id = getattr(actor, "actor_id", None)
            label = (getattr(actor, "display_name", "")
                     or getattr(actor, "email", "") or "anonymous")

        execute("""INSERT INTO refusal
                     (actor_id, actor, method, path, status, detail)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (actor_id, label, scope["method"], scope.get("path", ""),
                 status, detail))
