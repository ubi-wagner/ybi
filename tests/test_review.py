"""The three deliverables, and the things they must not do.

Each of these is a rule somebody would otherwise have to remember. They are
cheap to hold here and expensive to rediscover in fieldwork.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
PAGES = ROOT / "web" / "src" / "pages"


def _view(name: str) -> str:
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        m = re.search(rf"CREATE (?:OR REPLACE )?VIEW {name} AS(.*?);\s*(?:COMMENT|CREATE|--|$)",
                      src, re.S)
        if m:
            # Comments explain the choice; they are not the choice. Asserting
            # over them makes a test that a comment can fail.
            return re.sub(r"--[^\n]*", "", m.group(1))
    raise AssertionError(f"{name} is not defined in any migration")


def test_the_rate_buildup_reads_the_column_the_system_maintains():
    """`rate.superseded_by` exists on the table and nothing writes it.

    Recomputing and unsealing both express supersession by setting `status`,
    and every other reader — export, restate, /rates/current — filters on
    that. Filtering on the dead column returns superseded rates as live,
    which is exactly what this view did on its first run: four rates marked
    SUPERSEDED, presented as the rate on file.
    """
    body = _view("v_rate_buildup")
    assert "status <> 'SUPERSEDED'" in body, (
        "v_rate_buildup does not filter on status. A superseded rate shown "
        "as live is a rate somebody will quote.")
    assert "superseded_by" not in body, (
        "v_rate_buildup filters on rate.superseded_by, which no code path "
        "writes — the filter is a no-op and every superseded rate comes back.")


def test_nothing_writes_rate_superseded_by():
    """If that ever changes, the test above needs revisiting rather than luck."""
    writers = [
        f"{p.name}:{i}"
        for p in sorted((ROOT / "app").rglob("*.py"))
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if "superseded_by" in line and "UPDATE rate" in line
    ]
    assert not writers, (
        "something now sets rate.superseded_by: " + ", ".join(writers)
        + ". v_rate_buildup filters on status instead — make them agree.")


def test_the_functional_allocation_never_spreads_unjudged_cost():
    """NOT_YET_CLASSIFIED is a column, not a rounding of the other three.

    An allocation that distributes cost nobody has judged is one nobody can
    support. The totals are meant to be short until the queue is empty.
    """
    body = _view("v_form_990_functional")
    assert "NOT_YET_CLASSIFIED" in body, (
        "v_form_990_functional has no NOT_YET_CLASSIFIED bucket, so "
        "unclassified cost is either dropped or spread. Both are wrong.")
    assert "LEFT JOIN" in body.upper(), (
        "the view inner-joins to decision, which silently drops every "
        "unclassified line rather than showing it.")


@pytest.mark.parametrize("page", ["RateReview.jsx", "Form990.jsx", "Auditor.jsx"])
def test_every_review_screen_states_what_is_unfinished(page):
    src = (PAGES / page).read_text()
    assert "gate bad" in src or "Not fileable" in src or "not a final" in src, (
        f"{page} presents figures with no statement of what is incomplete. "
        f"A reviewer handed a total forms a view before they reach a footnote.")


@pytest.mark.parametrize("page", ["RateReview.jsx", "Form990.jsx", "Auditor.jsx"])
def test_no_review_screen_computes_a_figure(page):
    """Read back, never recomputed.

    A figure derived twice is a figure that can disagree with itself, and the
    one on the workpaper would be the one nobody could reproduce. The screens
    may total what the endpoint gave them; they may not build a rate.
    """
    src = (PAGES / page).read_text()
    for banned in ("pool_amount /", "/ base_amount", "* 100) /"):
        assert banned not in src, (
            f"{page} appears to compute a rate from its parts ({banned!r}). "
            f"Read it from the endpoint, which reads it from the rate on file.")


def test_the_workbooks_say_on_their_first_sheet_what_is_unfinished():
    """A workbook travels. The caveat has to travel with it."""
    src = (ROOT / "app" / "domain" / "review_workbooks.py").read_text()
    assert src.count("NOT FINAL") >= 1 and "NOT FILEABLE" in src, (
        "a deliverable workbook can leave without saying it is incomplete. "
        "Somebody forwards it and quotes a figure out of it.")
    assert "_caveat" in src and src.index("def _caveat") < src.index("def build_rate_buildup"), (
        "the caveat helper must exist and be applied before any figure")
