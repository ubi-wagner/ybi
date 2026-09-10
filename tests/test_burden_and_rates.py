"""MTDC base construction, burden buildup, and rate computation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from foundation.engine.burden import (
    MTDC_SUBAWARD_CAP_POST_2024,
    MTDC_SUBAWARD_CAP_PRE_2024,
    RateSet,
    SubawardCost,
    apply_burden,
    build_mtdc_base,
    subaward_cap_for,
)
from foundation.engine.rates import (
    DE_MINIMIS_POST_2024,
    DE_MINIMIS_PRE_2024,
    AllocationBase,
    CostPool,
    MethodologyNotLockedError,
    PoolLine,
    compute_rate,
)
from fcs.money import ZERO

D = Decimal


# ------------------------------------------------------------ subaward cap


def test_both_america_makes_agreements_carry_the_pre_2024_cap():
    """Hybrid Phase 2 (2023-09-08) and Project 88 / LTM (2024-09-24)."""
    assert subaward_cap_for(date(2023, 9, 8)) == MTDC_SUBAWARD_CAP_PRE_2024
    assert subaward_cap_for(date(2024, 9, 24)) == MTDC_SUBAWARD_CAP_PRE_2024


def test_awards_issued_from_october_2024_carry_the_raised_cap():
    assert subaward_cap_for(date(2024, 10, 1)) == MTDC_SUBAWARD_CAP_POST_2024
    assert subaward_cap_for(date(2025, 1, 1)) == MTDC_SUBAWARD_CAP_POST_2024


def test_unknown_award_date_is_treated_conservatively():
    assert subaward_cap_for(None) == MTDC_SUBAWARD_CAP_PRE_2024


# ------------------------------------------------------------------ MTDC


def test_contractor_costs_sit_in_the_base_in_full():
    base = build_mtdc_base(
        direct_labor="212326",
        services="605402",
        award_date=date(2024, 9, 24),
    )
    assert base.base == D("817728.00")


def test_subrecipient_costs_are_capped_in_the_base():
    """The Project 88 determination that decides whether 10% was over- or understated."""
    partners = [
        SubawardCost("OSU", D("100000"), is_subrecipient=True),
        SubawardCost("UNI", D("100000"), is_subrecipient=True),
        SubawardCost("UTK", D("100000"), is_subrecipient=True),
    ]
    base = build_mtdc_base(
        direct_labor="212326", subawards=partners, award_date=date(2024, 9, 24)
    )
    # Only the first $25,000 of each reaches the base.
    assert base.subawards_included == D("75000.00")
    assert base.subawards_excluded == D("225000.00")
    assert base.base == D("287326.00")
    assert base.total_direct_cost == D("512326.00")


def test_mixed_determinations_are_handled_per_partner():
    partners = [
        SubawardCost("OSU", D("80000"), is_subrecipient=True),
        SubawardCost("Humtown", D("30000"), is_subrecipient=False),
    ]
    base = build_mtdc_base(subawards=partners, award_date=date(2024, 9, 24))
    assert base.subawards_included == D("55000.00")  # 25,000 capped + 30,000 in full
    assert base.subawards_excluded == D("55000.00")


def test_equipment_and_capital_are_excluded_from_the_base():
    base = build_mtdc_base(
        direct_labor="100000", equipment="50000", capital_expenditures="200000"
    )
    assert base.base == D("100000.00")
    assert base.total_excluded == D("250000.00")
    labels = {row[0] for row in base.exclusion_schedule()}
    assert "Equipment" in labels
    assert "Capital expenditures" in labels


def test_exclusion_schedule_carries_authority():
    base = build_mtdc_base(equipment="1000")
    assert all(row[2] == "2 CFR 200.1 (MTDC)" for row in base.exclusion_schedule())


# --------------------------------------------------------------- burden


def test_burden_buildup_sums_to_fully_burdened_cost():
    base = build_mtdc_base(direct_labor="100000", fringe="22450", services="50000")
    rates = RateSet.of(fringe_rate="0.2245", ga_rate="0.3595")
    b = apply_burden(
        objective_id="LTM", period="2025", direct_labor="100000", base=base, rates=rates
    )
    assert b.direct_labor == D("100000.00")
    assert b.fringe == D("22450.00")
    assert b.direct_nonlabor == D("50000.00")
    assert b.ga == D("61995.78")  # 172,450 x 0.3595
    assert b.fully_burdened == D("234445.78")
    assert b.fully_burdened == sum(
        (b.direct_labor, b.fringe, b.direct_nonlabor, b.facilities, b.ga), ZERO
    )


def test_de_minimis_burden_reproduces_the_project_88_budget():
    """Schedule B billed $81,772.76 of indirect, which is exactly 10% of the base."""
    base = build_mtdc_base(
        direct_labor="212326", services="605402", award_date=date(2024, 9, 24)
    )
    rates = RateSet.of(ga_rate=DE_MINIMIS_PRE_2024)
    b = apply_burden(
        objective_id="LTM", period="2025", direct_labor="212326", base=base, rates=rates
    )
    assert b.ga == D("81772.80")  # Schedule B shows 81,772.76 -- 4 cents of rounding
    assert abs(b.ga - D("81772.76")) <= D("0.05")


def test_effective_indirect_rate_is_reported_back():
    base = build_mtdc_base(direct_labor="100000")
    rates = RateSet.of(ga_rate="0.25")
    b = apply_burden(
        objective_id="LTM", period="2025", direct_labor="100000", base=base, rates=rates
    )
    assert b.effective_indirect_rate == D("0.25")


def test_zero_base_produces_zero_indirect_not_an_error():
    base = build_mtdc_base()
    rates = RateSet.of(ga_rate="0.40")
    b = apply_burden(
        objective_id="LTM", period="2025", direct_labor="0", base=base, rates=rates
    )
    assert b.ga == ZERO
    assert b.effective_indirect_rate == ZERO


# ----------------------------------------------------------------- rates


def test_fringe_rate_reproduces_the_2025_control():
    """Spec 4.3 known controls: wages 1,789,993.94, fringe 401,783.60, ~22.446%."""
    pool = CostPool(
        kind="FRINGE",
        period="2025",
        lines=(
            PoolLine.of("Employee benefits", "194353.59", authority="GL 5130"),
            PoolLine.of("401(k) match and profit sharing", "56519.42", authority="GL 5133"),
            PoolLine.of("Payroll taxes", "150910.59", authority="GL 5141"),
        ),
    )
    base = AllocationBase(
        kind="S&W",
        period="2025",
        lines=(PoolLine.of("Salaries and wages", "1789993.94", authority="GL 5139"),),
    )
    computed = compute_rate(kind="FRINGE", period="2025", pool=pool, base=base)

    assert pool.amount == D("401783.60")
    assert base.amount == D("1789993.94")
    assert computed.rate_percent == D("22.45")
    assert computed.reconciles_to(D("401783.60"))


def test_excluded_pool_lines_stay_on_the_record():
    pool = CostPool(
        kind="G&A",
        period="2025",
        lines=(
            PoolLine.of("M&A expenses", "936268.91"),
            PoolLine.of(
                "Fundraising", "306484.11", included=False, authority="2 CFR 200.442"
            ),
            PoolLine.of(
                "Bad debt", "12037.85", included=False, authority="2 CFR 200.426"
            ),
        ),
    )
    assert pool.amount == D("936268.91")
    assert pool.excluded_amount == D("318521.96")
    assert pool.considered_amount == D("1254790.87")
    assert len(pool.exclusion_schedule()) == 2


def test_unlocked_methodology_cannot_back_a_posted_rate():
    """The 2 CFR 200.405(c) guard."""
    pool = CostPool(kind="G&A", period="2025", lines=(PoolLine.of("Pool", "100"),))
    base = AllocationBase(kind="MTDC", period="2025", lines=(PoolLine.of("Base", "1000"),))
    computed = compute_rate(kind="G&A", period="2025", pool=pool, base=base)

    assert not computed.is_methodology_locked
    with pytest.raises(MethodologyNotLockedError, match="methodology was never"):
        computed.require_locked()


def test_locked_methodology_may_back_a_posted_rate():
    pool = CostPool(kind="G&A", period="2025", lines=(PoolLine.of("Pool", "100"),))
    base = AllocationBase(kind="MTDC", period="2025", lines=(PoolLine.of("Base", "1000"),))
    computed = compute_rate(
        kind="G&A",
        period="2025",
        pool=pool,
        base=base,
        methodology_locked_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        methodology_note="Direct allocation method, Appendix IV B.4.",
    )
    assert computed.require_locked() is computed
    assert computed.rate == D("0.10")


def test_period_mismatch_is_refused():
    pool = CostPool(kind="G&A", period="2024", lines=())
    base = AllocationBase(kind="MTDC", period="2025", lines=())
    with pytest.raises(ValueError, match="Period mismatch"):
        compute_rate(kind="G&A", period="2025", pool=pool, base=base)


def test_zero_base_yields_zero_rate_rather_than_dividing_by_zero():
    pool = CostPool(kind="G&A", period="2025", lines=(PoolLine.of("Pool", "500"),))
    base = AllocationBase(kind="MTDC", period="2025", lines=())
    assert compute_rate(kind="G&A", period="2025", pool=pool, base=base).rate == ZERO


def test_de_minimis_constants_match_the_regulation():
    assert DE_MINIMIS_PRE_2024 == D("0.10")
    assert DE_MINIMIS_POST_2024 == D("0.15")


def test_workpaper_rows_label_inclusions_and_exclusions():
    pool = CostPool(
        kind="G&A",
        period="2025",
        lines=(
            PoolLine.of("M&A", "100"),
            PoolLine.of("Fundraising", "50", included=False, authority="2 CFR 200.442"),
        ),
    )
    base = AllocationBase(kind="MTDC", period="2025", lines=(PoolLine.of("MTDC", "1000"),))
    rows = compute_rate(kind="G&A", period="2025", pool=pool, base=base).workpaper_rows()
    sections = {row[0] for row in rows}
    assert sections == {"POOL", "POOL - EXCLUDED", "BASE"}
    assert any("2 CFR 200.442" in row[1] for row in rows)
