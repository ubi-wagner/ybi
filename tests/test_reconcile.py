"""Attributing a difference between two source documents to specific lines.

The point of the attribution engine is not that it finds an answer. It is
that it refuses to when the answer would be a guess — a difference that four
different sets of lines could equally explain has not been explained by
picking one.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.qbo import parse_general_ledger
from app.domain.reconcile import MAX_LINES, Candidate, attribute


def c(line_id: str, amount: str, **kw) -> Candidate:
    return Candidate(line_id=line_id, amount=Decimal(amount), **kw)


# ── Finding the lines ────────────────────────────────────────────────

def test_single_line_explains_the_whole_difference():
    a = attribute(Decimal("280.40"), [c("a", "280.40"), c("b", "13478.26"),
                                      c("d", "5000.00")])
    assert a.unique
    assert [x.line_id for x in a.lines] == ["a"]
    assert a.total == Decimal("280.40")


def test_two_lines():
    a = attribute(Decimal("267.21"), [c("a", "180.00"), c("b", "87.21"),
                                      c("d", "3260.87")])
    assert a.unique
    assert sorted(x.line_id for x in a.lines) == ["a", "b"]


def test_three_lines_uses_meet_in_the_middle():
    a = attribute(Decimal("6300.00"), [c("a", "3000.00"), c("b", "3000.00"),
                                       c("d", "300.00"), c("e", "13478.26"),
                                       c("f", "2173.91")])
    assert a.unique
    assert sorted(x.line_id for x in a.lines) == ["a", "b", "d"]


def test_four_lines():
    a = attribute(Decimal("622.26"), [c("a", "326.27"), c("b", "166.79"),
                                      c("d", "102.20"), c("e", "27.00"),
                                      c("f", "5000.00"), c("g", "1086.96")])
    assert a.unique
    assert sorted(x.line_id for x in a.lines) == ["a", "b", "d", "e"]


def test_smallest_explanation_wins():
    """One line that adds up beats two that also do. An elaborate story is
    not a better story."""
    a = attribute(Decimal("100.00"), [c("whole", "100.00"),
                                      c("half", "50.00"), c("other", "50.00")])
    assert a.unique
    assert [x.line_id for x in a.lines] == ["whole"]


# ── Refusing to guess ────────────────────────────────────────────────

def test_ambiguity_proposes_nothing():
    a = attribute(Decimal("50.00"), [c("a", "50.00"), c("b", "50.00")])
    assert not a.unique
    assert a.lines == []
    assert "More than one combination" in a.why_not()


def test_no_combination_says_so():
    a = attribute(Decimal("99.99"), [c("a", "50.00"), c("b", "30.00")])
    assert not a.unique
    assert a.solutions == 0
    assert "does not" in a.why_not() or "No combination" in a.why_not()


def test_five_lines_is_beyond_evidence():
    """Five lines that happen to add up is numerology, not attribution."""
    lines = [c(str(i), "10.00") for i in range(5)]
    a = attribute(Decimal("50.00"), lines)
    assert not a.unique
    assert a.solutions == 0
    assert str(MAX_LINES) in a.why_not()


def test_a_zero_difference_is_not_a_difference():
    a = attribute(Decimal("0.00"), [c("a", "10.00")])
    assert not a.unique
    assert a.searched == 0


# ── Keeping the search honest and small ──────────────────────────────

def test_lines_running_the_other_way_are_not_candidates():
    """A credit cannot be part of a debit difference. Allowing it turns every
    difference into a solvable puzzle, which is the opposite of evidence."""
    a = attribute(Decimal("100.00"),
                  [c("a", "600.00"), c("b", "-500.00"), c("d", "100.00")])
    assert a.unique
    assert [x.line_id for x in a.lines] == ["d"]


def test_lines_larger_than_the_difference_are_not_candidates():
    a = attribute(Decimal("100.00"), [c("big", "999999.00"), c("a", "100.00")])
    assert a.unique
    assert a.searched == 1


def test_a_line_is_never_used_twice():
    a = attribute(Decimal("200.00"), [c("a", "100.00")])
    assert a.solutions == 0


def test_search_stays_fast_on_a_realistic_account():
    """The Rising Tides account has 124 lines and four differences were
    attributed against it. Four-line subsets of 124 is 9.5 million tuples;
    this has to not do that."""
    import time
    lines = [c(f"l{i}", f"{100 + i}.{i % 100:02d}") for i in range(140)]
    lines.append(c("x", "7.77"))
    start = time.monotonic()
    a = attribute(Decimal("7.77"), lines)
    assert a.unique and a.lines[0].line_id == "x"
    # Something pathological shows up as seconds, not as a wrong answer.
    assert time.monotonic() - start < 5


# ── Opening balances, which the balance sheet tie rests on ───────────

HEADER = textwrap.dedent("""\
    Youngstown Business Incubator,,,,,,,,
    General Ledger,,,,,,,,
    "January 1 - December 31, 2025",,,,,,,,
    ,,,,,,,,
    ,Date,Transaction Type,Num,Name,Memo/Description,Split,Amount,Balance
    """)

WITH_OPENING = HEADER + textwrap.dedent("""\
    1010 Huntington - Operating Account,,,,,,,,
    ,Beginning Balance,,,,,,,"117656.07"
    ,03/26/2025,Journal Entry,202500133,,Payables funding,2000 AP,"(420.81)","117235.26"
    Total for 1010 Huntington - Operating Account,,,,,,,"(420.81)",
    2007 Huntington Construction LOC,,,,,,,,
    ,Beginning Balance,,,,,,,"(552546.37)"
    ,06/30/2025,Journal Entry,202500900,,Paid off,1010 Checking,"552546.37","0.00"
    Total for 2007 Huntington Construction LOC,,,,,,,"552546.37",
    """)


def test_opening_balances_are_kept(tmp_path: Path):
    p = tmp_path / "gl.csv"
    p.write_text(WITH_OPENING)
    g = parse_general_ledger(p)
    assert g.openings["1010 Huntington - Operating Account"] == Decimal("117656.07")
    assert g.openings["2007 Huntington Construction LOC"] == Decimal("-552546.37")


def test_opening_balance_is_not_a_transaction(tmp_path: Path):
    """It is a position, not activity. Counting it as a line would overstate
    the year by the whole balance sheet."""
    p = tmp_path / "gl.csv"
    p.write_text(WITH_OPENING)
    g = parse_general_ledger(p)
    assert len(g.lines) == 2
    assert g.total == Decimal("552125.56")
    assert not [r for r in g.subtotal_check() if r[3] != 0]


def test_closing_is_opening_plus_movement(tmp_path: Path):
    """The whole point: an account that ends at zero is why the balance sheet
    omits it, and the ledger has to be able to say so."""
    p = tmp_path / "gl.csv"
    p.write_text(WITH_OPENING)
    g = parse_general_ledger(p)
    totals = g.account_totals()
    loc = "2007 Huntington Construction LOC"
    assert g.openings[loc] + totals[loc] == Decimal("0.00")


UNCACHED_TOTAL = HEADER + textwrap.dedent("""\
    2100 Payroll Liabilities,,,,,,,,
    ,Beginning Balance,,,,,,,"1000.00"
    ,01/31/2025,Journal Entry,1,,Accrual,1010 Checking,"250.00","1250.00"
    Total for 2100 Payroll Liabilities,,,,,,,,
    """)


def test_a_total_with_no_printed_figure_is_not_a_passing_control(tmp_path: Path):
    """An export that saved formulas without their values leaves the total
    cell empty. Reading that as zero — or worse, falling back to the running
    Balance column — turns a control into a rubber stamp."""
    p = tmp_path / "gl.csv"
    p.write_text(UNCACHED_TOTAL)
    g = parse_general_ledger(p)
    assert "2100 Payroll Liabilities" in g.unprinted_subtotals
    # It is excluded from the check rather than compared against 0.00 and
    # reported as a mismatch, or compared against 1250.00 and reported as one.
    assert g.subtotal_check() == []
