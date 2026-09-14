"""The 2025 audit as one ordered journey, not a to-do list.

The door opened on the generic dashboard, which answers *what is outstanding*
and never *where am I in this*. Those are different questions and the second is
the one a controller closing a year holds: the file is closed in an order, each
step rests on the one before it, and **the order is the whole guarantee** —
classification is sealed before any rate exists. A landing page listing those
as two items on a list said nothing about that.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "081_the_walk.sql"
WALK = ROOT / "web" / "src" / "components" / "Walk.jsx"

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def test_nothing_on_the_walk_is_computed():
    """Every step reads the view that already owns its figure.

    A step deriving its own number would be a second definition of it, which
    is the defect this schema has recorded a dozen times — 13.0% and 2.2% at
    the same moment being the first.
    """
    # Comments stripped first. The migration's own header names all three
    # views in prose, so checking the raw text passed with the join pointed
    # at a view that does not exist — a test asserting prose rather than
    # code, which is the fourth instance of that shape in one day.
    body = re.sub(r"--[^\n]*", "", MIGRATION.read_text())
    for view in ("v_statement_reconciliation", "v_classification_coverage",
                 "v_partition_coverage"):
        # On a word boundary. `view in body` is a substring test, so
        # renaming the source to `v_classification_coverage_XX` satisfied it
        # perfectly and the assertion passed over a walk reading a view that
        # does not exist.
        assert re.search(rf"\b{view}\b", body), (
            f"the walk no longer reads {view}; it is deriving that figure "
            f"itself, which is a second definition of it")

    screen = WALK.read_text()
    assert "api.walk(" in screen, "the screen no longer reads the walk"
    for arith in ("/ 100", "* 100", "reduce("):
        assert arith not in screen, (
            f"the walk screen computes something ({arith}). Every figure is "
            f"read from the row the view recorded it in.")


def test_waiting_is_a_state_and_not_open():
    """A step whose predecessor is not done cannot honestly be called open.

    Printing it as OPEN offers work the server would refuse — no rate can
    exist before a seal, and the database says so.
    """
    body = MIGRATION.read_text()
    assert "'WAITING'" in body, (
        "WAITING is gone, so a step blocked by an earlier one now reads as "
        "work somebody can pick up")

    from app.db import query
    states = {r["state"] for r in
              query("SELECT DISTINCT state FROM v_audit_walk")}
    assert states <= {"DONE", "OPEN", "NO DATA", "WAITING"}, (
        f"the walk has grown a state nothing renders: {states}")


def test_no_data_is_not_a_pass():
    """Two steps need a document nobody here holds."""
    from app.db import query
    rows = query("""SELECT seq, step, state FROM v_audit_walk
                     WHERE period = %s ORDER BY seq""", ("2025",))
    if not rows:
        pytest.skip("no period loaded")
    assert not any(r["state"] == "TIES" for r in rows), (
        "the walk reports TIES, which is the register's word; a step is DONE, "
        "OPEN, NO DATA or WAITING")


def test_the_walk_counts_what_the_worklist_counts():
    """Both are on one page, so they must not answer one question two ways.

    The citation step counted all 757 live judgments beside a worklist row
    saying 363 — two true figures about "judgments with no document" at the
    same moment, which a reader has to reconcile in their head. NEEDS_EVIDENCE
    scopes to federally chargeable judgments, so the walk does too.
    """
    from app.db import query
    row = query("""SELECT detail FROM v_audit_walk
                    WHERE period = %s AND seq = 6""", ("2025",))
    if not row:
        pytest.skip("no period loaded")
    detail = row[0]["detail"]
    if "Nothing has been judged" in detail:
        pytest.skip("nothing judged, so there is nothing to compare")

    n = query("""SELECT count(*) AS n FROM v_worklist
                  WHERE period = %s AND kind = 'NEEDS_EVIDENCE'""", ("2025",))
    want = n[0]["n"]
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", detail)]
    assert want in nums, (
        f"the walk says {nums} and the worklist counts {want} judgments with "
        f"no document; one question, two answers, on one page")


def test_every_step_goes_somewhere():
    """A step with nowhere to go is a status line, not a walk."""
    from app.db import query
    rows = query("SELECT seq, step, goes_to FROM v_audit_walk ORDER BY seq")
    if not rows:
        pytest.skip("no period loaded")
    app = (ROOT / "web" / "src" / "App.jsx").read_text()
    routed = set(re.findall(r'<Route path="([^"]+)"', app))
    for r in rows:
        base = "/" + r["goes_to"].lstrip("/").split("/")[0]
        assert r["goes_to"] in routed or base in routed, (
            f"step {r['seq']} ({r['step']}) points at {r['goes_to']}, which "
            f"is not a route")
