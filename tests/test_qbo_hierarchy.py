"""Account hierarchy reconstruction in the QuickBooks general ledger parser.

QuickBooks prints the account tree as header / total pairs in one column rather
than by indentation, and it prints a parent's own direct lines *before* its
sub-accounts. Two consequences the parser has to get right:

1. Sub-accounts sharing a leaf name under different parents must not collide.
   YBI's 2025 chart has "Drive AM" under both "3900 Grant Income" (579,240.87)
   and "Grant Expenses" (181,880.88); merging them overstates the account by
   761,121.75 and silently breaks the subtotal control.

2. A header following "Total for X" may be X's child or X's sibling. The
   "with sub-accounts" rollup rows are what distinguish them.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path

from app.domain.qbo import QBO_GENERAL_LEDGER, parse_general_ledger

HEADER = textwrap.dedent("""\
    Youngstown Business Incubator,,,,,,,,
    General Ledger,,,,,,,,
    "January 1 - December 31, 2025",,,,,,,,
    ,,,,,,,,
    ,Date,Transaction Type,Num,Name,Memo/Description,Split,Amount,Balance
    """)

# A leaf name reused under two different parents, which is the collision case.
COLLIDING = HEADER + textwrap.dedent("""\
    3900 Grant Income,,,,,,,,
    Drive AM,,,,,,,,
    ,01/31/2025,Invoice,9092,NCDMM - America Makes:Drive AM,Jan,1100 AR,"400.00","400.00"
    ,02/28/2025,Invoice,9133,NCDMM - America Makes:Drive AM,Feb,1100 AR,"179.24","579.24"
    Total for Drive AM,,,,,,,"579.24",
    Total for 3900 Grant Income with sub-accounts,,,,,,,"579.24",
    ,,,,,,,,
    Grant Expenses,,,,,,,,
    Drive AM,,,,,,,,
    ,03/26/2025,Bill,LTM-4,Defense & Energy Systems,Partner,2000 AP,"181.88","181.88"
    Total for Drive AM,,,,,,,"181.88",
    Total for Grant Expenses with sub-accounts,,,,,,,"181.88",
    """)

# A parent carrying its own direct lines *and* sub-accounts, closed by a rollup.
NESTED = HEADER + textwrap.dedent("""\
    5080 Fundraising,,,,,,,,
    5089 Special Events,,,,,,,,
    ,04/01/2025,Expense,,Venue,Direct event cost,1010 Checking,"13.94","13.94"
    Total for 5089 Special Events,,,,,,,"13.94",
    AMUX Event,,,,,,,,
    ,05/01/2025,Expense,,Caterer,AMUX,1010 Checking,"20.40","20.40"
    Total for AMUX Event,,,,,,,"20.40",
    Shark Tank Events,,,,,,,,
    ,06/01/2025,Expense,,Printer,Shark Tank,1010 Checking,"120.24","120.24"
    Total for Shark Tank Events,,,,,,,"120.24",
    Total for 5089 Special Events with sub-accounts,,,,,,,"154.58",
    Total for 5080 Fundraising with sub-accounts,,,,,,,"154.58",
    """)

# Flat sibling accounts with no rollups at all — the common case, and the one
# that breaks if a leaf total is never popped.
FLAT = HEADER + textwrap.dedent("""\
    1000 Chase-Building Reserve Fund,,,,,,,,
    ,03/26/2025,Journal Entry,202500133,,Payables funding,2000 AP,"(420.81)","(420.81)"
    Total for 1000 Chase-Building Reserve Fund,,,,,,,"(420.81)",
    1002 Home Savings Building Reserve,,,,,,,,
    ,01/13/2025,Check,SVCCHRG,,Service charge,5000 Bank,"(32.95)","(32.95)"
    Total for 1002 Home Savings Building Reserve,,,,,,,"(32.95)",
    """)


def _parse(tmp_path: Path, text: str, name: str = "gl.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return parse_general_ledger(p, QBO_GENERAL_LEDGER)


# ----------------------------------------------------- name collision


def test_same_leaf_name_under_two_parents_does_not_collide(tmp_path):
    st = _parse(tmp_path, COLLIDING)
    assert st.subtotals["3900 Grant Income:Drive AM"] == Decimal("579.24")
    assert st.subtotals["Grant Expenses:Drive AM"] == Decimal("181.88")


def test_lines_carry_the_qualified_account_path(tmp_path):
    st = _parse(tmp_path, COLLIDING)
    accounts = {l.account for l in st.lines}
    assert accounts == {"3900 Grant Income:Drive AM", "Grant Expenses:Drive AM"}


def test_colliding_leaves_each_reconcile(tmp_path):
    st = _parse(tmp_path, COLLIDING)
    assert [r for r in st.subtotal_check() if abs(r[3]) > Decimal("0.01")] == []


# ------------------------------------------------------ nesting depth


def test_parent_direct_lines_and_children_are_separated(tmp_path):
    st = _parse(tmp_path, NESTED)
    assert st.subtotals["5080 Fundraising:5089 Special Events"] == Decimal("13.94")
    assert (st.subtotals["5080 Fundraising:5089 Special Events:AMUX Event"]
            == Decimal("20.40"))
    assert (st.subtotals["5080 Fundraising:5089 Special Events:Shark Tank Events"]
            == Decimal("120.24"))


def test_children_are_not_reparented_to_the_grandparent(tmp_path):
    """The bug this guards: popping on the parent's own leaf total."""
    st = _parse(tmp_path, NESTED)
    assert "5080 Fundraising:AMUX Event" not in st.subtotals
    assert all(l.account.startswith("5080 Fundraising:5089 Special Events")
               for l in st.lines)


def test_rollups_reconcile_against_the_subtree(tmp_path):
    st = _parse(tmp_path, NESTED)
    assert st.rollups["5080 Fundraising:5089 Special Events"] == Decimal("154.58")
    assert st.subtree_total("5080 Fundraising:5089 Special Events") == Decimal("154.58")
    assert [r for r in st.rollup_check() if abs(r[3]) > Decimal("0.01")] == []


def test_rollups_are_kept_apart_from_leaf_totals(tmp_path):
    """A parent rollup must never be reconciled as if it were a leaf total."""
    st = _parse(tmp_path, NESTED)
    assert "5080 Fundraising" in st.rollups
    assert "5080 Fundraising" not in st.subtotals


# --------------------------------------------------------- flat case


def test_flat_siblings_do_not_nest(tmp_path):
    st = _parse(tmp_path, FLAT)
    assert set(st.subtotals) == {
        "1000 Chase-Building Reserve Fund",
        "1002 Home Savings Building Reserve",
    }
    assert st.rollups == {}
    assert [r for r in st.subtotal_check() if abs(r[3]) > Decimal("0.01")] == []


# ---------------------------------------------- the real 2025 ledger

REAL_GL = Path("docs/source-documents/accounting-records/"
               "2025_General-Ledger_QuickBooks.xlsx")


def test_real_2025_ledger_reconciles_completely():
    """Every printed control in the real export ties, at every depth.

    15,500 dated lines is the control from KNOWN_CONTROLS_2025.csv.
    """
    if not REAL_GL.exists():          # pragma: no cover - source not vendored
        import pytest
        pytest.skip("2025 general ledger not present")

    st = parse_general_ledger(REAL_GL)

    assert len(st.lines) == 15_500
    assert [r for r in st.subtotal_check() if abs(r[3]) > Decimal("0.01")] == []
    assert [r for r in st.rollup_check() if abs(r[3]) > Decimal("0.01")] == []

    # The collision that motivated the fix, in the real data.
    assert st.subtotals["3900 Grant Income:Drive AM"] == Decimal("579240.87")
    assert st.subtotals["Grant Expenses:Drive AM"] == Decimal("181880.88")

    # Rollups reconcile to the P&L control totals.
    assert st.rollups["3900 Grant Income"] == Decimal("3183899.26")
    assert st.rollups["5129 Payroll Expenses:5139 Wages"] == Decimal("1789993.94")
    assert st.rollups["5129 Payroll Expenses"] == Decimal("2197014.24")
