"""Recovery disposition invariants.

Mirrors the FCS 1.4 QA harness: deterministic pathways plus randomized invariant
combinations. The randomized half uses Hypothesis rather than a hand-rolled
generator, so failures shrink to a minimal reproducing case.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contracts.engine.disposition import (
    AMERICA_MAKES_OBJECTIVES,
    Disposition,
    DispositionError,
    assert_america_makes_objective,
    derive_disposition,
)
from fcs.money import TOLERANCE, ZERO

D = Decimal


def make(**kwargs) -> Disposition:
    base = dict(
        objective_id="LTM",
        period="2025",
        actual="0",
        allocable="0",
        allowable="0",
        billed="0",
    )
    base.update(kwargs)
    return derive_disposition(**base)


# --------------------------------------------------------------- invariant 5


def test_billed_below_allowable_derives_supported_unrecovered():
    d = make(actual="100000", allocable="95000", allowable="90000", billed="70000")
    assert d.supported_unrecovered == D("20000.00")
    assert d.unsupported == ZERO
    assert d.is_valid


def test_billed_equal_to_allowable_leaves_nothing_unrecovered():
    d = make(actual="90000", allocable="90000", allowable="90000", billed="90000")
    assert d.supported_unrecovered == ZERO
    assert d.unsupported == ZERO
    assert d.is_valid


def test_supported_unrecovered_may_not_be_plugged():
    """A hand-entered supported-unrecovered that does not reconcile is rejected."""
    d = make(actual="100000", allocable="100000", allowable="90000", billed="70000")
    plugged = d.with_(supported_unrecovered="25000")
    codes = {f.code for f in plugged.errors}
    assert "UNRECOVERED_NOT_RECONCILED" in codes
    with pytest.raises(DispositionError, match="Supported unrecovered must equal"):
        plugged.validate_strict()


def test_supported_unrecovered_within_a_cent_is_accepted():
    d = make(actual="90000", allocable="90000", allowable="90000", billed="70000")
    assert d.with_(supported_unrecovered="20000.01").is_valid
    assert d.with_(supported_unrecovered="19999.99").is_valid
    assert not d.with_(supported_unrecovered="20000.02").is_valid


def test_supported_unrecovered_may_not_exceed_allowable():
    d = make(allowable="1000", billed="0").with_(supported_unrecovered="1500")
    assert "UNRECOVERED_EXCEEDS_ALLOWABLE" in {f.code for f in d.errors}


# --------------------------------------------------------------- invariant 6


def test_billed_above_allowable_captures_unsupported():
    d = make(actual="60000", allocable="55000", allowable="50000", billed="80000")
    assert d.unsupported == D("30000.00")
    assert d.supported_unrecovered == ZERO
    assert d.is_valid


def test_understated_unsupported_is_rejected():
    d = make(allowable="50000", billed="80000").with_(unsupported="10000")
    assert "UNSUPPORTED_UNDERSTATED" in {f.code for f in d.errors}


def test_unsupported_may_exceed_the_arithmetic_excess():
    """Invariant 6 says 'at least', so a reviewer may record more."""
    d = make(allowable="50000", billed="80000").with_(unsupported="35000")
    assert d.is_valid


def test_identified_unsupported_is_honoured_when_larger():
    d = make(allowable="50000", billed="52000", identified_unsupported="9000")
    assert d.unsupported == D("9000.00")
    assert d.is_valid


# --------------------------------------------------------------- invariant 4


def test_recoverable_may_not_exceed_allowable():
    d = make(allowable="1000", billed="0").with_(recoverable="1500")
    assert "RECOVERABLE_EXCEEDS_ALLOWABLE" in {f.code for f in d.errors}


def test_allowable_above_allocable_is_a_warning_not_an_error():
    d = make(actual="100", allocable="50", allowable="80", billed="80")
    assert d.is_valid
    assert "ALLOWABLE_EXCEEDS_ALLOCABLE" in {f.code for f in d.warnings}


def test_allocable_above_actual_is_a_warning_not_an_error():
    d = make(actual="50", allocable="80", allowable="80", billed="80")
    assert d.is_valid
    assert "ALLOCABLE_EXCEEDS_ACTUAL" in {f.code for f in d.warnings}


# --------------------------------------------------------------- invariant 7


def test_cost_share_never_participates_in_the_derivation():
    without = make(actual="100", allocable="100", allowable="100", billed="40")
    with_share = make(
        actual="100", allocable="100", allowable="100", billed="40", cost_share="250000"
    )
    assert with_share.supported_unrecovered == without.supported_unrecovered
    assert with_share.unsupported == without.unsupported
    assert with_share.recoverable == without.recoverable
    assert with_share.cost_share == D("250000.00")
    assert with_share.is_valid


# ------------------------------------------------------------------- ceiling


def test_ceiling_caps_recoverable_below_allowable():
    d = make(actual="600000", allocable="600000", allowable="600000", billed="400000",
             ceiling="500043")
    assert d.recoverable == D("500043.00")
    assert d.ceiling_constrained == D("99957.00")
    # Supported unrecovered still measures against allowable, not the ceiling.
    assert d.supported_unrecovered == D("200000.00")
    assert d.additional_recoverable == D("100043.00")
    assert d.is_valid


def test_billing_above_the_ceiling_raises_an_over_collection_warning():
    d = make(actual="600000", allocable="600000", allowable="600000",
             billed="512509.12", ceiling="500043")
    assert d.over_collection == D("12466.12")
    assert "BILLED_EXCEEDS_CEILING" in {f.code for f in d.warnings}
    assert d.is_valid  # a warning, because the cost itself is supported


def test_over_collection_uses_recoverable_not_allowable():
    """Cash above the ceiling must come back even where cost supports it."""
    d = make(actual="900000", allocable="900000", allowable="900000",
             billed="600000", ceiling="500043")
    assert d.unsupported == ZERO          # cost is fully supported
    assert d.over_collection == D("99957.00")  # but the cash is not keepable


# ------------------------------------------------------- negative amounts


@pytest.mark.parametrize(
    "field", ["actual", "allocable", "allowable", "billed", "cost_share"]
)
def test_negative_amounts_are_rejected(field):
    d = make(allowable="100", billed="100").with_(**{field: "-1"})
    assert "NEGATIVE_AMOUNT" in {f.code for f in d.errors}


def test_rounding_sized_negatives_are_tolerated():
    d = make(allowable="100", billed="100").with_(actual="-0.004")
    assert "NEGATIVE_AMOUNT" not in {f.code for f in d.errors}


# --------------------------------------------------------------- invariant 10


def test_only_america_makes_objectives_reach_the_updater():
    for objective in AMERICA_MAKES_OBJECTIVES:
        assert assert_america_makes_objective(objective) == objective


@pytest.mark.parametrize("objective", ["ESP", "MBAC", "RISING-TIDES", "YBI", ""])
def test_non_america_makes_objectives_are_refused(objective):
    with pytest.raises(DispositionError, match="America Makes disposition updater"):
        assert_america_makes_objective(objective)


# ------------------------------------------------------ real 2025 fact patterns
#
# From the controller's Grant Reconciliation Workbook, "Summary Sheet". These are
# the numbers the 2025 restatement has to explain, so they are regression cases.

YBI_2025_BILLED_VS_ACTUAL = {
    "DRIVE-AM": (D("668909.02"), D("506630.94")),
    "HYBRID-II": (D("512509.12"), D("253639.06")),
    "LTM": (D("164857.44"), D("142280.20")),
}


@pytest.mark.parametrize("objective", sorted(YBI_2025_BILLED_VS_ACTUAL))
def test_2025_as_billed_produces_unsupported_not_a_plug(objective):
    """At de minimis, every America Makes grant was billed above actual cost."""
    billed, actual = YBI_2025_BILLED_VS_ACTUAL[objective]
    d = derive_disposition(
        objective_id=objective,
        period="2025",
        actual=actual,
        allocable=actual,
        allowable=actual,
        billed=billed,
    )
    assert d.unsupported == billed - actual
    assert d.supported_unrecovered == ZERO
    assert d.over_collection == billed - actual
    assert d.is_valid


def test_2025_total_overdraw_matches_the_controller_summary():
    total = sum(
        (billed - actual) for billed, actual in YBI_2025_BILLED_VS_ACTUAL.values()
    )
    assert total == D("443725.38")


def test_a_higher_rate_can_close_ltm_but_not_hybrid():
    """The restatement thesis, tested.

    Applying additional indirect recovery on top of what was billed closes the
    LTM gap at a plausible rate and cannot close Hybrid at any rate, because
    Hybrid was billed at more than double its actual cost.
    """
    for objective, (billed, actual) in YBI_2025_BILLED_VS_ACTUAL.items():
        required_uplift = (billed - actual) / actual
        if objective == "LTM":
            assert required_uplift < D("0.20")
        elif objective == "DRIVE-AM":
            assert D("0.30") < required_uplift < D("0.35")
        else:
            assert required_uplift > D("1.0")


# ------------------------------------------------------- randomized invariants

money_amounts = st.decimals(
    min_value=D("0"),
    max_value=D("2000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
optional_ceiling = st.one_of(st.none(), money_amounts)


@settings(max_examples=1000, deadline=None)
@given(
    actual=money_amounts,
    allocable=money_amounts,
    allowable=money_amounts,
    billed=money_amounts,
    cost_share=money_amounts,
    identified_unsupported=money_amounts,
    ceiling=optional_ceiling,
)
def test_derived_dispositions_always_satisfy_the_hard_invariants(
    actual, allocable, allowable, billed, cost_share, identified_unsupported, ceiling
):
    d = derive_disposition(
        objective_id="LTM",
        period="2025",
        actual=actual,
        allocable=allocable,
        allowable=allowable,
        billed=billed,
        cost_share=cost_share,
        identified_unsupported=identified_unsupported,
        ceiling=ceiling,
    )

    assert d.errors == [], [f.message for f in d.errors]

    # Invariant 4: recoverable never exceeds allowable.
    assert d.recoverable <= d.allowable + TOLERANCE

    # Invariant 5: when billed does not exceed allowable, unrecovered reconciles.
    if d.billed <= d.allowable + TOLERANCE:
        expected = max(ZERO, d.allowable - d.billed)
        assert abs(d.supported_unrecovered - expected) <= TOLERANCE

    # Invariant 6: when billed exceeds allowable, unsupported captures the excess.
    if d.billed > d.allowable + TOLERANCE:
        assert d.unsupported + TOLERANCE >= d.billed - d.allowable

    # Invariant 7: cost share passes through untouched.
    assert d.cost_share == d.with_(cost_share=cost_share).cost_share

    # Ceiling is never breached by recoverable.
    if d.ceiling is not None:
        assert d.recoverable <= d.ceiling + TOLERANCE

    # Derived views are never negative.
    assert d.additional_recoverable >= ZERO
    assert d.over_collection >= ZERO
    assert d.ceiling_constrained >= ZERO


@settings(max_examples=200, deadline=None)
@given(allowable=money_amounts, billed=money_amounts)
def test_additional_recoverable_and_over_collection_are_mutually_exclusive(
    allowable, billed
):
    d = derive_disposition(
        objective_id="LTM",
        period="2025",
        actual=allowable,
        allocable=allowable,
        allowable=allowable,
        billed=billed,
    )
    assert d.additional_recoverable == ZERO or d.over_collection == ZERO
