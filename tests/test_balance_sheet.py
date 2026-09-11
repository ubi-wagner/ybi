"""The balance sheet parser.

Two controls are printed on the face of the report, which is exactly why they
are worth checking rather than trusting: the sheet has to balance, and its net
income has to be the P&L's. A third is not printed and matters most — every
subtotal against the sum of what sits under it, because a tree rebuilt from
header/total pairs can look reasonable while an account hangs off the wrong
parent.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.qbo import parse_balance_sheet

SOURCE = Path("docs/source-documents/accounting-records/"
              "2025_Balance-Sheet_QuickBooks.xlsx")

pytestmark = pytest.mark.skipif(not SOURCE.exists(),
                                reason="the 2025 balance sheet is not on file")


@pytest.fixture(scope="module")
def bs():
    return parse_balance_sheet(SOURCE, sha256="test")


def test_the_sheet_balances(bs):
    assert bs.assets == Decimal("16713219.80")
    assert bs.liabilities == Decimal("2362526.09")
    assert bs.equity == Decimal("14350693.71")
    assert bs.check_balance() == Decimal("0.00")


def test_net_income_ties_to_the_profit_and_loss(bs):
    """The cross-statement control. Two exports that disagree are two
    different moments in the books, and everything built on either is
    suspect."""
    assert bs.net_income == Decimal("4329.28")
    assert bs.check_net_income(Decimal("4329.28")) == Decimal("0.00")
    assert bs.check_net_income(Decimal("4329.27")) == Decimal("0.01")


def test_every_printed_subtotal_equals_what_sits_under_it(bs):
    failing = bs.failing_subtotals()
    assert failing == [], f"{len(failing)} subtotals do not foot: {failing[:3]}"


def test_a_building_is_not_filed_under_computer_equipment(bs):
    """1530 Computer Equipment is a header QuickBooks never totals. Pushing it
    as a parent meant nothing popped it and the next sibling fell inside —
    1570 TBB5, an $8.9M building, landed under computer equipment."""
    tbb5 = [p for p in bs.accounts if "Tech Block Bldg 5" in p]
    assert len(tbb5) == 1
    assert "Computer Equipment" not in tbb5[0]
    assert tbb5[0].endswith("Fixed Assets:1570 TBB5:1501 Tech Block Bldg 5")


def test_a_parents_own_balance_is_inside_its_own_total_and_not_its_parents(bs):
    """The credit cards carry a balance on the card itself and one per
    cardholder. Counting both the card's balance and the card's total
    double-counts it."""
    card = next(p for p in bs.accounts if p.endswith("2040 Chase Platinum Business Card"))
    assert bs.accounts[card][1] == Decimal("72.40")
    total = next(v for k, v in bs.rollups.items()
                 if k.endswith("2040 Chase Platinum Business Card"))
    assert total[1] == Decimal("14635.74")


def test_fixed_assets_carry_cost_and_accumulated_depreciation_together(bs):
    """What makes the sheet answer the 200.436(b) question at all: the contra
    account sits beside the cost it reduces."""
    def amount(fragment: str) -> Decimal:
        return next(v[1] for k, v in bs.accounts.items() if fragment in k)

    assert amount("1511 Buildings") == Decimal("8760612.01")
    assert amount("1512 Accum. Depr. - Buildings") == Decimal("-3650762.57")
    assert amount("1501 Tech Block Bldg 5") == Decimal("8922679.69")
    assert amount("1502 TBB5 Accumulated Depreciation") == Decimal("-2803893.23")
    assert bs.fixed_assets == Decimal("14154574.40")


def test_land_and_construction_in_progress_are_not_depreciated(bs):
    """Neither carries a contra account, which is correct and is the reason
    they have to be excluded from any depreciable-basis figure."""
    land = next(k for k in bs.accounts if "1500 Land" in k)
    cip = next(k for k in bs.accounts if "Construction in Progress" in k)
    assert bs.accounts[land][1] == Decimal("107530.00")
    assert bs.accounts[cip][1] == Decimal("438355.19")
    assert not any("Accum" in k and "1500" in k for k in bs.accounts)


def test_a_header_with_no_total_is_reported_rather_than_guessed_at(bs):
    assert any("1530 Computer Equipment" in w for w in bs.warnings)
    assert not any("Youngstown Business Incubator" in w for w in bs.warnings)


def test_the_innovation_hub_deferrals_are_read(bs):
    """$412,500 of cost share sitting in deferred revenue is the kind of thing
    that decides a cost-share conversation."""
    cost_share = next(v[1] for k, v in bs.accounts.items()
                      if "IH Cost Share Deferral" in k)
    advance = next(v[1] for k, v in bs.accounts.items()
                   if "IH Advance Deferral" in k)
    assert cost_share == Decimal("412500.00")
    assert advance == Decimal("330658.94")
