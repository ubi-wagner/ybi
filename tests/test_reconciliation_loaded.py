"""The eleven, proved in the direction that can fail.

CI applies the migrations to a bare database — right, because the schema is
what is under test and a suite needing a seeded ledger is one nobody can run
on a fresh clone. But it left the register proved only in the **empty**
direction: `test_a_loaded_period_still_evaluates` skipped there, and the
loaded direction lived in `scripts/reconcile.py` against a foundation only a
developer had.

`tests/fixture_period.py` builds a period from the control definitions. These
run it, and then **break each control on purpose**, one at a time, to prove
it can still see a difference.

That second half is the point. A fixture that makes the register go green
proves the register can say yes. It says nothing about whether it can say no
— and a control that cannot say no is the whole failure mode `029` was
written for: eleven points reporting agreement over no books at all.

Every test writes inside a transaction that is rolled back.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from fixture_period import (CLEARING, NET_INCOME, PERIOD, WAGES_ADMIN,
                            add_line, build, register)

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.fixture
def books(cur):
    """A period with books in it, rolled back with the rest."""
    return build(cur)


def controls(cur) -> dict[str, dict]:
    return {r["control"]: r for r in register(cur)}


def open_ones(cur) -> list[str]:
    return [c for c, r in controls(cur).items() if not r["ties"]]


# ── The register in the direction it is meant to pass ─────────────────

def test_every_control_is_evaluable_on_a_loaded_period(cur, books):
    """The other half of `029`'s guard.

    A control that cannot be evaluated has not passed — and a guard that
    makes *everything* unevaluable would be just as useless in the other
    direction.
    """
    rows = register(cur)
    assert len(rows) >= 11, f"only {len(rows)} controls in the register"
    unevaluable = [r["control"] for r in rows if not r["evaluable"]]
    assert not unevaluable, (
        f"these cannot be evaluated on a fully loaded period: {unevaluable}. "
        f"Each one says what it needs; the fixture is missing it.")


def test_the_whole_register_ties(cur, books):
    assert not open_ones(cur), (
        "the fixture is meant to tie at every point, so an open one is "
        "either a defect in a control or a fixture that encodes the wrong "
        "shape — and the second is worse")


def test_an_empty_period_is_not_a_tying_period(cur):
    """`029` in its original direction, held here too.

    Both sides of most controls are COALESCE(..., 0), so an empty period
    compares zero against zero and looks green. It reported all eleven
    points tying over no books at all until 029 fixed it.
    """
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES ('2098','2098-01-01','2098-12-31')
                   ON CONFLICT DO NOTHING""")
    rows = register(cur, "2098")
    assert rows, "an empty period produces no register at all"
    assert not any(r["evaluable"] for r in rows), (
        "a period with no books has controls reporting themselves evaluable")
    assert not any(r["ties"] for r in rows), (
        "a period with no books reports points tying, which is the defect "
        "029 exists to close")


# ── And in the direction that matters ─────────────────────────────────

def test_pl_footing_sees_a_sheet_that_disagrees(cur, books):
    cur.execute("""UPDATE bs_account SET amount = amount + 1
                    WHERE period = %s AND leaf = 'Net income'""", (PERIOD,))
    assert "PL_FOOTING" in open_ones(cur)


def test_pl_footing_survives_a_p_and_l_with_no_cogs(cur, books):
    """The defect `054` closes, held as a test rather than as a comment.

    A `FILTER` matching no rows is NULL and NULL propagates, so one COALESCE
    around the whole expression made a P&L with no COGS section compute its
    net income as nought. The fixture has no COGS and no Other Income, which
    is how this was found in the first place.
    """
    cur.execute("""SELECT count(*) AS n FROM pl_account
                    WHERE period = %s AND section IN ('COGS','Other Income')""",
                (PERIOD,))
    assert cur.fetchone()["n"] == 0, (
        "the fixture has grown a COGS or Other Income section, so it no "
        "longer exercises the case 054 was written for")
    got = controls(cur)["PL_FOOTING"]
    assert got["left_value"] == NET_INCOME, (
        f"net income computed as {got['left_value']} against {NET_INCOME}. "
        f"An absent section must contribute nothing rather than erase the "
        f"sum.")


def test_bs_footing_sees_a_sheet_that_does_not_balance(cur, books):
    cur.execute("""UPDATE bs_account SET amount = amount + 100
                    WHERE period = %s AND side = 'ASSET'""", (PERIOD,))
    assert "BS_FOOTING" in open_ones(cur)


def test_promote_complete_sees_a_line_that_never_landed(cur, books):
    """71 lines carrying $24,082.67 went that way before the natural key
    learned to number repeats.

    Staged and not landed, rather than landed and then deleted —
    `ledger_line` is append-only and the schema refuses the second outright,
    which is also the more faithful shape: the promote path drops a line, it
    does not remove one afterwards.
    """
    cur.execute("""INSERT INTO staging_line
                     (batch_id, row_number, natural_key, account, txn_date,
                      memo, amount)
                   VALUES (%s, 999, %s, 'Expenses:Occupancy:5300 Rent',
                           %s, 'Dropped on promote', 1000)""",
                (books["batch_id"], f"{PERIOD}-9999", f"{PERIOD}-11-30"))
    assert "GL_PROMOTE_COMPLETE" in open_ones(cur)


def test_subtotals_see_a_printed_total_the_lines_do_not_make(cur, books):
    """An export that saved formulas without their cached values read as
    zero and reconciled against zero."""
    cur.execute("""UPDATE staging_subtotal SET parsed_total = parsed_total - 5
                    WHERE batch_id = %s""", (books["batch_id"],))
    assert "GL_SUBTOTALS" in open_ones(cur)


def test_the_section_control_sees_a_mis_sectioned_account(cur, books):
    """Reading an expense as revenue moves the section without moving the
    grand total, which is the only reason this control is separate from the
    account-by-account one."""
    cur.execute("""UPDATE pl_account SET section = 'Income'
                    WHERE period = %s AND leaf = '5300 Rent'""", (PERIOD,))
    assert "GL_PL_SECTION" in open_ones(cur)


def test_the_account_control_sees_money_moved_between_two_expenses(cur, books):
    """Sections tie while accounts do not: money moved between two expense
    accounts nets to nothing at the section line."""
    cur.execute("""UPDATE pl_account SET amount = amount + 1000
                    WHERE period = %s AND leaf = '5300 Rent'""", (PERIOD,))
    cur.execute("""UPDATE pl_account SET amount = amount - 1000
                    WHERE period = %s AND leaf = '5110 Admin Wages'""", (PERIOD,))
    got = open_ones(cur)
    assert "GL_PL_ACCOUNT" in got
    assert "GL_PL_SECTION" not in got, (
        "the section control moved too, so this test is not proving what it "
        "says — the two accounts must be in the same section")


def test_the_coverage_control_sees_an_account_on_only_one_side(cur, books):
    """A P&L account with no ledger behind it cannot be classified, and a
    ledger account off the P&L is cost with nowhere to land."""
    cur.execute("""INSERT INTO pl_account (period, account, leaf, section, amount)
                   VALUES (%s,'Expenses:5400 Phantom','5400 Phantom',
                           'Expense', 0.01)""", (PERIOD,))
    assert "GL_PL_COVERAGE" in open_ones(cur)


def test_the_balance_sheet_control_sees_an_account_that_does_not_prove(cur, books):
    """The tie the system could not make until the ledger's openings were
    kept. It proves the sheet off the ledger rather than trusting two
    exports to agree."""
    cur.execute("""UPDATE gl_opening SET amount = amount + 250
                    WHERE period = %s AND account LIKE '%%Cash'""", (PERIOD,))
    assert "GL_BS_ACCOUNT" in open_ones(cur)


def test_the_coverage_control_sees_an_absent_account_with_a_balance(cur, books):
    """QuickBooks omits an account that ends at zero, which is a complete
    explanation and a checkable one. An absent account still carrying a
    balance is a hole in the sheet.

    The fixture's clearing account is the one that makes this testable: with
    nothing absent, the control counts nought either way and passes over a
    case it never saw.
    """
    cur.execute("""SELECT count(*) AS n FROM v_gl_bs_account
                    WHERE period = %s AND NOT on_balance_sheet""", (PERIOD,))
    assert cur.fetchone()["n"] == 1, (
        "the fixture no longer has an account absent from the sheet, so this "
        "control would pass vacuously")
    # Make it close at something rather than at nothing — a third movement
    # that never comes back.
    add_line(cur, books, "Assets:Current:1099 Clearing", "BALANCE_SHEET",
             "Assets", CLEARING, "Left hanging")
    assert "GL_BS_COVERAGE" in open_ones(cur)


def test_the_payroll_control_sees_a_difference_the_other_ten_cannot(cur, books):
    """The eleventh, and the one that pays for itself.

    The fringe base comes from the effort distribution rather than from the
    ledger's wage accounts, so a difference between them is two denominators
    for one rate. This is the shape of the $45,000 donor credit that sat in
    an intern wage account for a year: it moved the fringe rate from 22.45%
    to 21.90% and ten of the eleven controls were blind to it.
    """
    credit = Decimal("45000.00")
    # A donor credit booked against a wage account, which is exactly what
    # happened: a pledge to fund interns, posted as a credit to 5142 Intern
    # Wages rather than as contributions income.
    add_line(cur, books, "Expenses:Payroll:5110 Admin Wages", "P&L", "Expense",
             -credit, "Bacon pledge, miscoded")
    # And the cash it arrived as, so the books still agree with themselves.
    add_line(cur, books, "Assets:Current:1010 Cash", "BALANCE_SHEET", "Assets",
             credit, "Bacon pledge received")
    # Keep the two statements in step with the ledger, so the other ten stay
    # quiet and this one is demonstrably the only one that can see it. That
    # is the claim the test makes, not incidental tidiness.
    cur.execute("""UPDATE pl_account SET amount = amount - %s
                    WHERE period = %s AND leaf = '5110 Admin Wages'""",
                (credit, PERIOD))
    cur.execute("""UPDATE bs_account SET amount = amount + %s
                    WHERE period = %s AND leaf IN ('Net income','1010 Cash')""",
                (credit, PERIOD))

    got = open_ones(cur)
    assert got == ["PAYROLL_REGISTER"], (
        f"expected the payroll register to be the only point that moved; "
        f"{got} did. If the others moved too, the fixture's statements were "
        f"not kept in step and the claim this test makes is not being "
        f"tested.")
    row = controls(cur)["PAYROLL_REGISTER"]
    assert row["variance"] == credit, (
        f"the register is out by {row['variance']}, not by the {credit} the "
        f"credit moved")


def test_the_fixture_is_small_enough_to_read(cur, books):
    """A fixture nobody reads is a fixture nobody checks, and an unchecked
    fixture that encodes a wrong shape makes the controls agree with a
    misunderstanding for ever."""
    assert books["ledger_lines"] <= 20
    assert WAGES_ADMIN > 0 and NET_INCOME > 0
