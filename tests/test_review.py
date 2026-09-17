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
    # Asserted as a property rather than as a spelling. This used to require
    # the literal `l.statement = 'P&L'` in the body, which `064` broke while
    # making the scope *more* correct — the predicate moved into
    # `v_cost_line` so four places could stop each keeping their own copy of
    # it. A test that pins the wording argues with a correct change; the
    # thing that actually matters is which lines are counted.
    assert "v_cost_line" in body or "statement" in body, (
        "coverage no longer says what it is scoped to at all")
    assert "balance_sheet" not in body.lower(), (
        "balance sheet movements are not cost to classify, and counting "
        "both sides of a transfer makes the measure that gates sealing "
        "meaningless")

    handler = (ROOT / "app" / "routers" / "classify.py").read_text()
    m = re.search(r"def coverage\(.*?\n(?=\n@router)", handler, re.S)
    assert m, "the coverage handler is gone"
    fn = m.group(0)
    assert "v_classification_coverage" in fn, (
        "the coverage handler computes its own figure again")
    assert "FROM ledger_line" not in fn, (
        "the coverage handler is back to reading the ledger directly, which "
        "is a second definition of the scope")


def test_no_handler_anywhere_derives_coverage_for_itself():
    """And the list of handlers to check is not kept by hand.

    The assertion above names `classify.py`, which is the file the defect was
    found in — so `dashboard.py` grew the next copy of the scope and nothing
    saw it. It scoped to `l.statement = 'P&L'`, which is the predicate `064`
    moved into `v_cost_line` because **income is on the P&L**, and the
    controller's home screen read **59.7% classified** while the view read
    **100.0%**, at the same moment, over the same 757 judgments. The figure a
    reader quotes was the wrong one, on a denominator that was 41% grant
    income.

    A test written about one file is the hand-kept map wearing a test's
    clothes. Every router is swept and there is no list in it.

    The shape is specific, because four legitimate queries join these two
    registers and aggregate: a **period-wide** total — `ledger_line` driving,
    LEFT JOIN to live decisions so undecided lines survive, an aggregate, and
    no GROUP BY. That is a denominator. The four that are fine either group
    (the queue, by account and payee) or inner-join from the decision side,
    which can only ever measure what *is* classified, never the scope.
    """
    offenders = []
    for f in sorted((ROOT / "app" / "routers").glob("*.py")):
        src = f.read_text()
        for m in re.finditer(r'"""(.*?)"""', src, re.S):
            q = m.group(1)
            if "ledger_line" not in q or "decision_line" not in q:
                continue
            if not re.search(r"\b(sum|count)\s*\(", q):
                continue
            if re.search(r"\bGROUP\s+BY\b", q, re.I):
                continue
            if not re.search(r"LEFT\s+JOIN\s+decision_line", q, re.I):
                continue
            offenders.append(f"{f.name}:{src[:m.start()].count(chr(10)) + 1}")
    assert not offenders, (
        "a handler derives a classification scope from the ledger instead of "
        "reading v_classification_coverage, which is where `039` put the "
        "definition after it answered 13.0% and 2.2% at once: "
        + ", ".join(offenders))


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


def test_coverage_counts_cost_and_not_income():
    """A cost pool is for cost, and grant income has no answer in one.

    `039` scoped coverage to the P&L because balance-sheet movements are not
    cost. True, and one level too coarse: **income is on the P&L**. 242 of
    the 999 groups the controller was being asked to judge were revenue —
    `3900 Grant Income`, `4015 Program Fees` — $6,876,763.86, 40.3% of the
    scope, four of them at the very top of the queue by size, and not one of
    them answerable.

    Two things came off that. A quarter of the queue could not be actioned,
    with the unanswerable rows sorted to the top because they were large; and
    coverage read 13.0% where the truth against cost was 21.8% — the figure
    on every workpaper, in the 990's NOT FILEABLE banner and in the rate's
    working-figure caveat, wrong by a factor of 1.7 in the pessimistic
    direction.

    Asserted against the definition rather than against row counts, because
    on the empty database CI builds from the migrations every count is zero
    and a count test would pass without proving anything.
    """
    body = _view("v_cost_line")
    assert "Income" in body and "section" in body, (
        "v_cost_line no longer excludes the P&L's Income section")
    assert "'P&L'" in body, (
        "v_cost_line no longer excludes balance sheet movements")
    # Other Income stays: 2 CFR 200.406 applicable credits — refunds,
    # rebates, adjustments — reduce cost rather than being revenue, so
    # somebody has to judge them. The cut is the Income *section*, which is
    # why this is `<> 'Income'` and not `amount > 0` or `NOT IN (...)`.
    assert "Other Income" not in body.replace("-- ", ""), (
        "Other Income was cut from the scope. 200.406 applicable credits "
        "reduce cost and need a judgment")

    # And nothing may keep a second copy of the scope. Four places did.
    for f in ("app/routers/classify.py", "app/routers/documents.py"):
        src = (ROOT / f).read_text()
        assert "statement = 'P&L'" not in src, (
            f"{f} keeps its own copy of the classification scope, which is "
            f"how 13.0% and 2.2% happened")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_no_income_reaches_the_scope_on_a_loaded_ledger():
    """The same rule, against real rows.

    Skips rather than passing vacuously where no ledger is loaded — nought
    income lines out of nought is the empty case satisfying the assertion,
    not the guarantee holding. `scripts/drive_buildup.py` covers it against
    the seeded record.
    """
    from app.db import one
    loaded = one("SELECT count(*) AS n FROM ledger_line WHERE statement = 'P&L'")
    if not loaded or not loaded["n"]:
        pytest.skip("no P&L loaded; drive_buildup covers the loaded case")
    bad = one("SELECT count(*) AS n FROM v_cost_line WHERE section = 'Income'")
    assert bad["n"] == 0, (
        f"{bad['n']} income lines are being offered as cost to classify")


# ── Part IX cross-foots ───────────────────────────────────────────────

def test_the_return_puts_every_dollar_of_compensation_in_a_function():
    """Part IX printed $2,191,777.54 of payroll with nothing in any of the
    three columns the return prints.

    `EXCLUDED` is a rate judgment and it is right — `add_labor()` already puts
    the distribution in MTDC, so a DIRECT judgment on a wage account would
    count the payroll twice. What it says nothing about is which column of the
    return a salary belongs in, and the classification log set both from one
    judgment. The row did not cross-foot on a tax return.
    """
    import os
    if not os.getenv("DATABASE_URL"):
        import pytest
        pytest.skip("needs a database")
    from app.db import query

    rows = query("""SELECT function_990, sum(amount) AS amount
                      FROM v_form_990_functional
                     WHERE period = '2025'
                       AND natural_category = '5129 Payroll Expenses'
                     GROUP BY 1""")
    if not rows:
        import pytest
        pytest.skip("no payroll on this record")
    by = {r["function_990"]: r["amount"] for r in rows}
    printed = sum(v for k, v in by.items()
                  if k in ("PROGRAM", "MANAGEMENT_AND_GENERAL", "FUNDRAISING"))
    assert printed == sum(by.values()), (
        "compensation is on the return in a function or it is nowhere: "
        f"{ {k: str(v) for k, v in by.items()} }")
    assert by.get("NOT_APPLICABLE", 0) == 0


def test_the_990_workbook_prints_every_column_the_handler_accumulates():
    """The handler has always carried a NOT_APPLICABLE bucket and the sheet
    never showed it, so a row whose total exceeded its three functions left
    the reader nothing to reconcile to."""
    import inspect

    from app.domain import review_workbooks

    src = inspect.getsource(review_workbooks.build_form_990)
    for key in ("PROGRAM", "MANAGEMENT_AND_GENERAL", "FUNDRAISING",
                "NOT_YET_CLASSIFIED", "NOT_APPLICABLE", "total"):
        assert f'"{key}"' in src, f"Part IX does not print {key}"
