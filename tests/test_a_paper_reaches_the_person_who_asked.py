"""Two ways a finished paper never reaches anybody, and neither is a 404.

The controller opened `/reports`, pressed Download on three invoices in
sixteen seconds, and got nothing. Every one answered **200** with an
`EXPORT` row written, so the server log said the system was working — which
is the shape this repository already calls the worst a fault can take:
healthy to everything watching.

Two defects underneath, and the tests here are about the shapes rather than
the two instances:

  * **A literal route declared after a parameterised sibling never runs.**
    Starlette matches in declaration order, so `/restate/reconciliation`
    reached `detail(restatement_id="reconciliation")` and answered 500 on
    `invalid input syntax for type uuid`. The route existed,
    `test_every_capability_has_a_door` saw it in the route table, the SPA
    had a button for it, and the tests called the assembly function
    directly — so nothing anywhere could see that the door was walled up.
    *Reachable is not capable*, one level further in: the path resolves and
    the wrong handler answers.

  * **A Download button that sends `Content-Disposition: inline`.** Whether
    a browser prefers the `download` attribute over the server's own header
    is a thing browsers disagree about, so the save worked in some hands and
    not in others. `app/papers.py` is the one place that decides, and the
    default is the save.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _api_routes():
    out = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path or not path.startswith("/api"):
            continue
        for m in (getattr(r, "methods", None) or set()) - {"HEAD", "OPTIONS"}:
            out.append((m, path, getattr(r, "name", "")))
    return out


# ── a route the router will never reach ──────────────────────────────

def test_no_route_is_shadowed_by_a_parameterised_sibling():
    """`/x/{id}` declared before `/x/literal` swallows it.

    Derived from the running application rather than from a list, so a route
    added tomorrow in the wrong order fails here on the day it is written.
    It found exactly one across two hundred routes, and that one had shipped.
    """
    routes = _api_routes()
    shadowed = []
    for i, (method, path, name) in enumerate(routes):
        if "{" not in path:
            continue
        rx = re.compile("^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$")
        for method2, path2, name2 in routes[i + 1:]:
            if method2 == method and "{" not in path2 and rx.match(path2):
                shadowed.append(
                    f"{method} {path2} ({name2}) is shadowed by {path} "
                    f"({name}), which is declared first — move the literal "
                    f"route above the parameterised one")
    assert not shadowed, "\n".join(shadowed)


# ── a paper saves unless somebody asks to look at it ─────────────────

#: Every route that renders a PDF for a person to keep. The query string is
#: what the screen sends; `inline=1` is the preview frame and nothing else.
PAPERS = [
    "/api/reports/invoice/9062",
    "/api/restate/award/AM-DRIVE-AM/memo?period=2025",
    "/api/restate/award/AM-DRIVE-AM/acceptance?period=2025",
    "/api/restate/reconciliation?period=2025",
]


def test_the_helper_saves_by_default_and_shows_only_when_asked():
    """The rule, tested where it is defined.

    No database: this is a statement about one function, and asserting it
    through four routes would be testing the routes' plumbing rather than
    the rule they all read.
    """
    from app.papers import as_pdf

    assert as_pdf(b"%PDF-", "x.pdf").headers["content-disposition"] \
        .startswith("attachment"), (
        "a paper saves by default — a button reading Download has to "
        "download on every browser rather than on most of them")
    assert as_pdf(b"%PDF-", "x.pdf", inline=True).headers["content-disposition"] \
        .startswith("inline")
    for inline in (False, True):
        assert as_pdf(b"%PDF-", "x.pdf", inline).headers[
            "x-content-type-options"] == "nosniff"


def test_every_pdf_route_reads_that_helper_rather_than_writing_its_own():
    """`money()`'s eight spellings, in the header that decides whether a
    document arrives. All four composed their own and all four said
    `inline`, including the three behind a button reading Download."""
    import pathlib

    offenders = []
    for f in pathlib.Path("app/routers").glob("*.py"):
        src = re.sub(r"#.*", "", f.read_text())
        for m in re.finditer(r'["\']Content-Disposition["\']\s*:\s*(.{0,60})',
                             src, re.I):
            said = m.group(1)
            if "application/pdf" in src and "inline; filename" in said:
                offenders.append(f"{f.name}: {said.strip()[:50]}")
    assert not offenders, (
        "a router composes its own inline disposition for a PDF rather than "
        "going through app/papers.py::as_pdf: " + "; ".join(offenders))


# ── and the route actually answers ───────────────────────────────────

@pytest.fixture()
def tom():
    """Signed in, through the real door."""
    import os

    if not os.getenv("DATABASE_URL"):
        pytest.skip("needs a database")
    c = TestClient(app)
    r = c.post("/api/auth/login",
               json={"email": os.getenv("YBI_DRIVE_EMAIL", "tmetzinger@ybi.org"),
                     "password": os.getenv("YBI_DRIVE_PASSWORD", "")})
    if r.status_code != 200:
        pytest.skip(f"cannot sign in on this record ({r.status_code})")
    return c


def test_the_reconciliation_answers_a_pdf_through_its_own_route(tom):
    """Through the route, not the assembly function.

    The assembly was green the whole time the route was answering 500 —
    which is what made this invisible. A test that calls `_reconciliation()`
    proves the paper, and says nothing about whether anybody can get it.
    """
    r = tom.get("/api/restate/reconciliation?period=2025")
    if r.status_code == 404:
        pytest.skip("no America Makes restatement stands on this record")
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"
    assert r.headers["content-disposition"].startswith("attachment")

    shown = tom.get("/api/restate/reconciliation?period=2025&inline=1")
    assert shown.headers["content-disposition"].startswith("inline")
