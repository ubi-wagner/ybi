"""A capability the application cannot reach is one nobody has.

`POST /api/rates/compute` was complete on the server, named in a comment on
the screen that should have called it, and **called by nothing in the SPA** —
so the single figure this whole system exists to produce could only be made by
somebody running a script. It shipped that way for the life of the rate
engine, and it was found by walking the runbook rather than by any test.

It is not the first. `CLAUDE.md` records the same shape three times before it:
the restatement had five complete routes and no page, the timesheet draft had
two and no card, and the lane comparison had an API that could only ever
answer with zeroes. Each was found by somebody reading one area closely.

**This is the sweep, so the fourth is caught by a test rather than by
noticing.** It derives the routes from the running application and the calls
from `api.js`, and there is no list of either in it — the same construction as
`tests/test_no_register_is_dead.py`, which is the answer to the dead-register
shape rather than the twelfth instance of it.

What it does *not* claim: that a reachable route is reachable *by the right
person*, or that the screen calling it is one they can find. Those are
`drive_access.py` and the nav rules. This asks the cruder question that was
never asked at all — **is there a door.**
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPA = ROOT / "web" / "src"
API_JS = SPA / "api.js"

#: Routes with no call in the SPA **on purpose**, each with the reason.
#:
#: An entry that is no longer needed fails the test, so this list can only
#: shrink by somebody noticing — the opposite of how the four dead
#: capabilities got there. A reason under twenty-five characters fails too:
#: an allowlist entry with no reason is the defect wearing a permission slip.
#: Keys are in the swept form — method and the path with `/api` and any
#: parameter normalised away, which is what `routes()` produces.
#:
#: **Two lists, because two different facts.** Conflating them is how an
#: allowlist stops meaning anything: "this will never have a screen" and
#: "nobody has built the screen yet" lead to different work, and a single
#: list of exceptions reads as the first while filling up with the second.
NO_DOOR_ON_PURPOSE = {
    "GET health":
        "the deployment healthcheck, called by Railway and not by a person",
    "GET docs":
        "FastAPI's own interactive schema page, for a developer not a user",
    "GET openapi.json":
        "the schema itself, for tooling rather than for a screen",
}

#: Served, useful, and **no screen reaches it**. Each is a real gap with the
#: screen it belongs on, found by this sweep rather than by anybody noticing.
#: None of them is on the Monday path — the two that were, `POST rates/unseal`
#: and `GET dashboard/refusals`, were given doors rather than written down
#: here.
#:
#: An entry that gains a door fails this test until it is removed, so the list
#: can only shrink by somebody doing the work.
NO_DOOR_YET = {
    "GET chart/splits": "the 2026 split drivers — belongs on /chart",
    "PUT chart/splits": "recording a split's shares — belongs on /chart",
    "GET classify/materiality": "the materiality threshold — /classify",
    "PUT classify/materiality": "setting it — /classify, controller only",
    "GET rates/allocation": "allocation by objective — /review/rate has room",
    "GET export/exceptions": "an export the other four already have links for",
    "GET export/reconciliation": "likewise; /reports or /reconcile",
    "POST classify/defer": "deferring a group rather than judging it",
    "POST classify/segment/reverse": "reversing a segment judgment",
    "POST lanes/*/promote": "promoting a lane's overrides into the queue",
    "POST reconcile/aliases": "writing an alias; the screen only reads them",
}

def _norm(path: str) -> str:
    """`/api/documents/{id}/facts` and `/documents/${id}/facts` to one shape.

    Brace-aware rather than a regex, because the substitutions are nested:
    `/documents/library${s ? `?${s}` : ""}` carries a `${...}` inside a
    `${...}`, and `[^{}]*` stops at the inner brace. That one read as
    unreachable while the Library screen was plainly working — and a sweep
    that cries wolf is worse than no sweep, because it teaches the reader
    the list is wrong and the next real one they dismiss.

    `${...}` is consumed before `{...}` for the same reason: the other order
    eats the braces and leaves the dollar, so every parameterised call read
    as `$*` and matched nothing. That reported sixty live routes as orphans.
    """
    out, i = [], 0
    while i < len(path):
        if path.startswith("${", i) or path[i] == "{":
            depth, j = 0, i
            while j < len(path):
                if path[j] == "{":
                    depth += 1
                elif path[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("*")
            i = j + 1
            continue
        out.append(path[i])
        i += 1
    p = "".join(out).split("?")[0].strip("/")
    if p.startswith("api/"):
        p = p[4:]
    p = re.sub(r"\*+", "*", p)
    # A substitution glued to the end of a static segment was a query string
    # being built, not a path segment: `/documents/library${s ? `?..` : ""}`
    # is the library route, whatever the caller appends to it.
    if p.endswith("*") and len(p) > 1 and p[-2] != "/":
        p = p[:-1]
    return p.strip("/")


def routes() -> set[str]:
    """Every /api route the application actually serves."""
    from app.main import app
    out = set()
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api"):
            continue
        for method in sorted(getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}):
            out.add(f"{method} {_norm(path)}")
    return out


def spa_calls() -> set[str]:
    """Every path `api.js` asks for, with the method it asks for it with.

    Read from the source rather than by running it: a template literal's
    static parts are enough to know which route is meant, and executing a
    browser module to find out would be a second implementation of the
    question.
    """
    src = API_JS.read_text()
    calls: set[str] = set()
    # req("/rates/seal", { method: "POST", ... })  and  req(`/x/${y}`)
    for m in re.finditer(
            r"""(?:req|sendForm)\(\s*(["\'`])(.+?)\1(.*?)(?=\n\s*\w+:|\n\};|\Z)""",
            src, re.S):
        path = _norm(m.group(2))
        tail = m.group(3)[:220]
        meth = re.search(r"method:\s*[\"\'](\w+)[\"\']", tail)
        method = meth.group(1) if meth else ("POST" if "sendForm" in m.group(0)
                                             else "GET")
        calls.add(f"{method} {path}")

    # **A URL handed to the browser is a door too**, and it is not always in
    # `api.js`. A document opens in the page and an export downloads, so
    # those paths are built as absolute `/api/...` strings for an `iframe`
    # src or an `a href` rather than fetched — `test_no_screen_reaches_past_
    # the_request_layer` fails a `fetch(` outside `api.js` and says nothing
    # about a link, correctly. So the whole SPA is scanned for them.
    #
    # Reading only `req()` in only `api.js` reported the CSV exports and the
    # timesheet workbook as unreachable while both were plainly download
    # links a controller uses.
    for f in sorted(SPA.rglob("*.js")) + sorted(SPA.rglob("*.jsx")):
        for m in re.finditer(r"/api/[A-Za-z0-9_\-/{}$().?=&]*", f.read_text()):
            calls.add(f"GET {_norm(m.group(0))}")
    return calls


def test_the_spa_reaches_every_capability_the_server_offers():
    """The sweep. A route with no caller is a capability nobody has."""
    served, called = routes(), spa_calls()
    # A GET the screen makes with a query string still reaches the same route.
    known = set(NO_DOOR_ON_PURPOSE) | set(NO_DOOR_YET)
    orphans = sorted(r for r in served if r not in called and r not in known)
    assert not orphans, (
        "these routes are served and the application cannot reach them — "
        "each is a capability nobody has, which is how "
        "POST /api/rates/compute shipped for the life of the rate engine:\n  "
        + "\n  ".join(orphans))


def test_the_allowlist_only_shrinks_by_somebody_noticing():
    """An entry that is no longer needed has to fail, or the list becomes the
    hand-kept map it exists to replace."""
    served, called = routes(), spa_calls()
    both = {**NO_DOOR_ON_PURPOSE, **NO_DOOR_YET}
    stale = sorted(k for k in both if k not in served)
    assert not stale, (
        "these are allowed to have no door and are no longer served at all — "
        "remove them: " + ", ".join(stale))
    # The half that makes the list shrink: a gap somebody has since closed.
    closed = sorted(k for k in NO_DOOR_YET if k in called)
    assert not closed, (
        "these now have a door — take them off NO_DOOR_YET: "
        + ", ".join(closed))
    thin = sorted(k for k, v in both.items() if len(v) < 25)
    assert not thin, (
        "an allowlist entry with no reason is the defect wearing a permission "
        "slip: " + ", ".join(thin))


def test_the_sweep_derives_both_sides_and_keeps_no_list_of_its_own():
    """The construction is the point. A hand-kept list of routes would be
    wrong the first week, which is what every instance of this defect had in
    common."""
    source = Path(__file__).read_text()
    body = source.split("def routes()")[1].split("def spa_calls()")[0]
    assert "app.routes" in body, "routes must come from the application"
    assert "api.js" in source, "the calls must come from the SPA's one door"
    # Nothing but the allowlist may name a route literally.
    named = set(re.findall(r'"((?:GET|POST|PUT|PATCH|DELETE) [a-z][^"]*)"',
                           source))
    assert named <= set(NO_DOOR_ON_PURPOSE) | set(NO_DOOR_YET), (
        "a route named literally outside the allowlist is a hand-kept map: "
        + ", ".join(sorted(named - set(NO_DOOR_ON_PURPOSE)
                           - set(NO_DOOR_YET))))
