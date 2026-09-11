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
    """`rate.superseded_by` was a column nothing wrote.

    Recomputing and unsealing both express supersession by setting `status`,
    and every other reader — export, restate, /rates/current — filters on
    that. Filtering on the dead column returned superseded rates as live,
    which is exactly what this view did on its first run: four rates marked
    SUPERSEDED, presented as the rate on file.
    """
    body = _view("v_rate_buildup")
    assert "status <> 'SUPERSEDED'" in body, (
        "v_rate_buildup does not filter on status. A superseded rate shown "
        "as live is a rate somebody will quote.")


def test_no_view_anywhere_reads_the_dead_column():
    """The widening that should have come with the first fix.

    That test named one view, because one view was where the bug was found.
    `v_form_990_readiness` had the identical filter thirty lines below the
    comment explaining why not to, and survived for as long as the narrow
    test did — its `rate_on_file` flag went true the moment any rate existed
    and could never go false again, on the screen that says whether a tax
    return may be filed.

    Migration `050` corrects it and drops the column, so this is now a
    statement about the schema rather than a hope about readers.

    The sweep reads the schema as Postgres does: migrations run in filename
    order and a `CREATE OR REPLACE` supersedes what came before it, so only
    the *last* definition of each view is a reader. An applied migration is
    never edited — 033 still carries the defect in its original body, and a
    test that failed on that would be a test asking for history to be
    rewritten.
    """
    live: dict[str, tuple[str, str]] = {}
    loose: list[str] = []
    for path in sorted(SQL.glob("*.sql")):
        # Comments are where the rule is written down; they are not readers.
        body = re.sub(r"--[^\n]*", "", path.read_text())
        for statement in body.split(";"):
            named = re.search(r"CREATE (?:OR REPLACE )?VIEW\s+(\w+)",
                              statement, re.I)
            if named:
                live[named.group(1)] = (path.name, statement)
            elif re.search(r"\brate\.superseded_by\b", statement, re.I):
                # Anything that is not a view and still names the column.
                loose.append(path.name)

    offenders = [f"{where}:{name}"
                 for name, (where, statement) in sorted(live.items())
                 if re.search(r"\brate\b", statement, re.I)
                 and "superseded_by" in statement]
    assert not offenders + loose, (
        "these read rate.superseded_by, which nothing writes and 050 drops: "
        + ", ".join(offenders + loose))


def test_the_dead_column_is_gone_from_the_schema():
    """The definitive version of the test above.

    Sweeping migration text catches a reader; it cannot prove the column is
    gone, because a later migration could add it back and the sweep would
    only notice once something read it. This asks the database.
    """
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("needs a database; the sweep above covers the text")
    from app.db import one, open_pool, run_migrations
    open_pool()
    run_migrations()
    row = one("""SELECT count(*) AS n FROM information_schema.columns
                  WHERE table_name = 'rate' AND column_name = 'superseded_by'""")
    assert row["n"] == 0, (
        "rate.superseded_by is back. Supersession is expressed through "
        "status; two ways to say one thing is what produced this twice.")


def test_nothing_writes_rate_superseded_by():
    """If the column ever comes back, it comes back deliberately."""
    writers = [
        f"{p.name}:{i}"
        for p in sorted((ROOT / "app").rglob("*.py"))
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if "superseded_by" in line and "UPDATE rate" in line
    ]
    assert not writers, (
        "something now sets rate.superseded_by: " + ", ".join(writers)
        + ". It was dropped in 050; supersession is expressed through status.")


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


def test_coverage_is_defined_once():
    """"How much of the cost has been classified" had two answers.

    At the same moment, over the same single decision, the classification
    screen said 13.0% and the auditor's report said 2.2% — the handler
    scoped to the P&L and the view counted every ledger line including both
    sides of every transfer. The *classified* dollars differed too, because
    one measured a group by what it moved and the other by its net position.

    A figure derived twice is one that can disagree with itself, and the
    workpaper carries the version nobody can reproduce. The definition lives
    in the view; the handler reads it.
    """
    body = _view("v_classification_coverage")
    assert "l.statement = 'P&L'" in body, (
        "coverage no longer scopes to the P&L. Balance sheet movements are "
        "not cost to classify, and counting both sides of a transfer makes "
        "the measure that gates sealing meaningless.")

    handler = (ROOT / "app" / "routers" / "classify.py").read_text()
    m = re.search(r"def coverage\(.*?\n(?=\n@router)", handler, re.S)
    assert m, "the coverage handler is gone"
    fn = m.group(0)
    assert "v_classification_coverage" in fn, (
        "the coverage handler computes its own figure again")
    assert "FROM ledger_line" not in fn, (
        "the coverage handler is back to reading the ledger directly, which "
        "is a second definition of the scope")


def test_the_coverage_row_can_be_checked_by_hand():
    """classified + unclassified = scope, and the percentage comes from them.

    The old view printed net sums beside a percentage taken over absolute
    sums, so 1,678,057.27 against 12,693,242.03 sat next to a figure of
    2.2% and a reader checking the arithmetic on one row could not make it
    come out. Every column is the same measure now.
    """
    body = _view("v_classification_coverage")
    for col in ("scope_dollars", "classified", "unclassified",
                "pct_dollars_covered"):
        assert col in body, f"{col} is gone from the coverage view"
    # All three money columns are absolute over the same population; a net
    # sum among them is what broke the row before.
    money = re.findall(r"sum\((abs\()?amount\)?\)", body)
    assert money and all(m == "abs(" for m in money), (
        "a coverage column is summing net amounts again; the columns beside "
        "it are absolute and the row will not add up")
