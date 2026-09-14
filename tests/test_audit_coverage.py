"""Every route that changes something has to say so.

The audit trail is the product here. A handler that writes to the database
and does not record what it did leaves a change nobody can attribute, and the
whole file is worth less for it — not by much, and not visibly, which is
exactly the problem. It is the kind of gap that arrives with a new endpoint
written in a hurry and is found by an auditor rather than by us.

So this is a structural test rather than a behavioural one: it reads the
routers and fails on any POST, PUT, PATCH or DELETE whose handler neither
calls ``record`` nor writes an audit_log row itself. It cannot prove the
recorded content is right — the drives do that — but it can prove that
nothing mutating was added without anybody thinking about the trail.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

#: Routes that change nothing on the record and so have nothing to record.
#: Each one is here because somebody decided it, not because it was missed.
EXEMPT: dict[tuple[str, str], str] = {}


def mutating_routes():
    for path in sorted(ROUTERS.glob("*.py")):
        src = path.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)):
                    continue
                method = dec.func.attr.upper()
                if method not in MUTATING:
                    continue
                route = ""
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    route = dec.args[0].value
                yield (path.stem, method, route, node.name,
                       ast.get_source_segment(src, node) or "")


def records_something(body: str) -> bool:
    """Either through the helper, or by writing the row itself.

    ``undo`` does the latter, and has to: an undo entry carries
    ``undoes_entry_id`` to tie it to what it reversed, and ``record`` has no
    way to set that. Writing the INSERT by hand there is deliberate.
    """
    return bool(re.search(r"\brecord\s*\(", body)
                or re.search(r"INSERT\s+INTO\s+audit_log", body, re.I))


ROUTES = list(mutating_routes())


def test_there_are_mutating_routes_to_check():
    """A test that silently checks nothing is worse than no test."""
    assert len(ROUTES) > 30, f"only found {len(ROUTES)} mutating routes"


@pytest.mark.parametrize(
    "router,method,route,handler,body", ROUTES,
    ids=[f"{r[0]}:{r[1]}:{r[2] or '/'}" for r in ROUTES])
def test_mutating_route_records_what_it_did(router, method, route, handler, body):
    if (router, handler) in EXEMPT:
        pytest.skip(EXEMPT[(router, handler)])
    assert records_something(body), (
        f"{method} /api/{router}{route} ({handler}) changes something and "
        f"records nothing. Call record(actor, ...) with the actor from the "
        f"session — or add it to EXEMPT above with a reason, if it genuinely "
        f"changes nothing on the record.")


@pytest.mark.parametrize(
    "router,method,route,handler,body", ROUTES,
    ids=[f"{r[0]}:{r[1]}:{r[2] or '/'}" for r in ROUTES])
def test_mutating_route_takes_its_actor_from_the_session(router, method, route,
                                                         handler, body):
    """The actor is never a parameter.

    ``audit_log.actor`` used to be a string the caller supplied, which records
    a claim rather than a fact — and the claim is made by the person the trail
    exists to hold to account. Every mutating handler therefore resolves an
    Actor through a dependency.
    """
    if (router, handler) in EXEMPT:
        pytest.skip(EXEMPT[(router, handler)])
    if router == "auth" and handler in ("login", "logout"):
        return          # login has no session yet; logout ends the one it has
    assert re.search(r"Depends\((require_|current_actor)", body), (
        f"{method} /api/{router}{route} ({handler}) does not resolve an actor "
        f"from the session. An audit entry whose actor came from the request "
        f"body records a claim, not a fact.")


#: A name in a request is a label. ``upload`` says so in a comment two
#: hundred lines above ``accept``, which is the route that did not.
ACTOR_NAME = re.compile(r"\b(\w+_by)\b")


def actor_named_parameters(body: str) -> set[str]:
    """Every ``*_by`` the handler takes from the request.

    Two spellings, because both are written: a query or form parameter in the
    signature (``accepted_by: str = ""``), and a field on the body model read
    as ``body.created_by``.
    """
    signature = body.split(")", 1)[0]
    found = {n for n in ACTOR_NAME.findall(signature)}
    found |= set(re.findall(r"\bbody\.(\w+_by)\b", body))
    return found


@pytest.mark.parametrize(
    "router,method,route,handler,body", ROUTES,
    ids=[f"{r[0]}:{r[1]}:{r[2] or '/'}" for r in ROUTES])
def test_a_name_in_the_request_is_only_ever_a_label(router, method, route,
                                                    handler, body):
    """Resolving an Actor is not the same as using one.

    The test above proves every mutating handler resolves an Actor through a
    dependency. ``POST /api/imports/{batch_id}/accept`` did — and then wrote
    ``accepted_by`` straight from the query string into ``staging_batch`` and
    into ``ledger_import.imported_by``, which is the permanent provenance
    record every ledger line points back to. The screen sent the literal
    string ``tom``, so who promoted the general ledger was whatever the URL
    said, and the trail could not disagree.

    Eight of the nine routes carrying such a parameter already reassigned it
    from the session; one did not, and nothing could tell them apart. This is
    that check. Keeping the parameter is deliberate — a document can be
    received on somebody else's behalf — but it is a label the session
    overrides, never an identity the caller asserts.
    """
    if (router, handler) in EXEMPT:
        pytest.skip(EXEMPT[(router, handler)])
    for name in sorted(actor_named_parameters(body)):
        assert re.search(rf"^\s*{name} = actor\.display_name", body, re.M), (
            f"{method} /api/{router}{route} ({handler}) takes `{name}` from "
            f"the request and never overrides it from the session, so a "
            f"caller names whoever they like on the record. Write "
            f"`{name} = actor.display_name or {name}` before using it.")
