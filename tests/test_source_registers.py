"""The two registers YBI already keeps, which nothing had read.

Both have been on file since the foundation was loaded. Reading them changes
what we have to ask for from "please build us a register" — an afternoon of
somebody's week, which comes back in six — to "here are your assets, which of
these did federal money pay for".

The asset schedule is the one with teeth. It is a Crystal Reports export and
it prints its own subtotals, so the same rule the QuickBooks parsers follow
applies: every printed subtotal must equal what sits under it. That rule
caught two real parser defects here, both of which would have been invisible
in a workbook that looked complete.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.asset_schedule import parse_asset_schedule
from app.domain.lease_book import parse_lease_book

SOURCE = Path(__file__).resolve().parent.parent / "docs" / "source-documents"
SCHEDULE = next(SOURCE.rglob("*Fixed-Asset-Schedule*"), None)
LEASES = next(SOURCE.rglob("*Lease-Schedule*"), None)

needs_schedule = pytest.mark.skipif(SCHEDULE is None,
                                    reason="asset schedule not in the tree")
needs_leases = pytest.mark.skipif(LEASES is None,
                                  reason="lease schedule not in the tree")


@pytest.fixture(scope="module")
def schedule():
    return parse_asset_schedule(SCHEDULE)


# ── The asset register ────────────────────────────────────────────────

@needs_schedule
def test_every_sheet_ties_to_its_own_printed_total(schedule):
    """The control that found both defects.

    Without it the parser dropped every asset with no system number — the
    report prints the number only when it changes — including $2,388,438.81
    of Tech Block phase 2, and the workbook would have gone out to YBI
    missing $2.5m of their own property.
    """
    assert schedule.open_controls == (), "\n".join(
        f"{c.sheet}: printed {c.printed:,.2f}, parsed {c.parsed:,.2f}, "
        f"off by {c.variance:,.2f}" for c in schedule.open_controls)


@needs_schedule
def test_the_register_foots_to_its_own_summary_sheet(schedule):
    """The grand total on the summary sheet, reached from the detail."""
    assert schedule.total_cost == Decimal("23419573.64")


@needs_schedule
def test_it_reads_every_asset(schedule):
    assert len(schedule.assets) == 263
    assert all(a.gross_cost > 0 for a in schedule.assets)
    assert all(a.description for a in schedule.assets)


@needs_schedule
def test_an_asset_with_no_system_number_is_still_an_asset(schedule):
    """Fourteen rows on the Tech Block sheet carry a description and a cost
    and nothing in the first column."""
    phase2 = next((a for a in schedule.assets
                   if "TBB5 Phase-2" in a.description), None)
    assert phase2 is not None, "the largest single asset was dropped"
    assert phase2.gross_cost == Decimal("2388438.81")
    assert phase2.asset_id.startswith("FA-")


@needs_schedule
def test_the_superseded_aggregates_are_named_not_netted(schedule):
    """Two sheets open with an aggregate the detail below replaced, which the
    sheet's own total excludes. Loading them would overstate the basis by
    $1.5m; dropping them silently would be a $1.5m hole nobody could see."""
    excluded = {s.description: s.gross_cost for s in schedule.superseded}
    assert excluded == {"BUILDINGS": Decimal("180000.00"),
                        "CAPITAL IMPROVEMENTS": Decimal("1336695.00")}


@needs_schedule
def test_a_row_that_is_not_property_is_listed_rather_than_loaded(schedule):
    """Depreciation true-ups sit inside the asset block with no cost. They
    are not assets and they are not noise."""
    assert schedule.adjustments
    assert any("True Up" in a.description for a in schedule.adjustments)
    assert all(a.why for a in schedule.adjustments)


@needs_schedule
def test_the_report_below_the_totals_is_not_read_as_assets(schedule):
    """Below "Total Cost/Basis:" the sheets carry breakout sections, a
    month-by-month depreciation roll and the adjusting entries — rows with a
    description and a number that are not property. Reading to the end of the
    sheet loaded "Fitz Reimbursement" as an asset."""
    descriptions = {a.description for a in schedule.assets}
    for stray in ("Fitz Reimbursement", "NCDMM Reimbursement",
                  "YSU Reimbursement", "Alex Downie"):
        assert stray not in descriptions


@needs_schedule
def test_dates_are_read_and_nonsense_is_left_empty(schedule):
    """Excel serials, and nothing invented where the column holds text."""
    dated = [a for a in schedule.assets if a.in_service_on]
    assert len(dated) > 200
    assert all(1990 <= a.in_service_on.year <= 2030 for a in dated)


@needs_schedule
def test_what_the_register_does_not_carry(schedule):
    """The point of the whole exercise. 2 CFR 200.313(d)(1) requires source
    of funding in the property records; this register has no such column, and
    that is a finding in its own right independently of the rate."""
    assert not any(hasattr(a, "funding_source") for a in schedule.assets)


# ── The lease book ────────────────────────────────────────────────────

@needs_leases
def test_the_lease_book_reads_every_tenancy():
    tenancies = parse_lease_book(LEASES)
    assert len(tenancies) == 26
    assert sum((t.annual_rent for t in tenancies), Decimal("0")) == \
        Decimal("601269.48")


@needs_leases
def test_building_names_are_folded():
    """"ybi" and "YBI" being two buildings would make every square-foot
    control fail in a way nobody could see: the sum still foots, against the
    wrong denominator."""
    tenancies = parse_lease_book(LEASES)
    names = {t.building for t in tenancies}
    assert "YBI Incubator Building" in names
    assert "Tech Block Building 5" in names
    assert "ybi" not in names and "Tbb5" not in names


@needs_leases
def test_a_rolling_tenancy_keeps_its_term_instead_of_a_guessed_date():
    """Eight tenants have "monthly" where a start date belongs. A date that
    cannot be read is left empty; the word is kept, because it is the term."""
    tenancies = parse_lease_book(LEASES)
    rolling = [t for t in tenancies if t.rolling]
    assert len(rolling) == 8
    assert all(t.starts_on is None for t in rolling)
    assert all(t.term_note for t in rolling)


@needs_leases
def test_the_lease_book_carries_no_square_footage():
    """Which is the whole reason the space workbook exists. The book answers
    who and how much rent; only a floor plan answers how many square feet,
    and that is the driver 200.465 sizes the carve-out by."""
    tenancies = parse_lease_book(LEASES)
    assert not any(hasattr(t, "usable_sqft") for t in tenancies)
