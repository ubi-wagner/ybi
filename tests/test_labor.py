"""Labor distribution and 2 CFR 200.430(i) certification rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from foundation.engine.labor import (
    APPROVED,
    CORROBORATED,
    MANAGEMENT_RECONSTRUCTION,
    TEST_ASSUMPTION,
    UNSUPPORTED,
    EmployeeDistribution,
    LaborAllocation,
    LaborCertification,
    LaborValidationError,
)
from fcs.money import ZERO

D = Decimal

EMPLOYEE_CERT = LaborCertification(
    certified_by="B. Ewing",
    role="EMPLOYEE",
    certified_on=date(2026, 9, 10),
    period_start=date(2025, 1, 1),
    period_end=date(2025, 12, 31),
    scope_note="Annual certification of 2025 effort distribution.",
)

SUPERVISOR_CERT = LaborCertification(
    certified_by="Board Chair",
    role="SUPERVISOR",
    certified_on=date(2026, 9, 10),
    period_start=date(2025, 1, 1),
    period_end=date(2025, 12, 31),
)


def alloc(**kwargs) -> LaborAllocation:
    base = dict(
        employee_id="EWING",
        period="2025",
        objective_id="LTM",
        payroll_wages="192087.13",
        original_units="0",
    )
    base.update(kwargs)
    for key in ("payroll_wages", "original_units", "reconstructed_units"):
        if key in base and base[key] is not None:
            base[key] = D(str(base[key]))
    return LaborAllocation(**base)


# ------------------------------------------------- immutable original time


def test_reconstruction_does_not_overwrite_the_original():
    a = alloc(original_units="100", reconstructed_units="650",
              evidence_quality=CORROBORATED, rationale="Contract oversight logs.")
    assert a.original_units == D("100")
    assert a.reconstructed_units == D("650")
    assert a.effective_units == D("650")
    assert a.is_reconstructed


def test_effective_units_fall_back_to_the_original():
    a = alloc(original_units="100")
    assert not a.is_reconstructed
    assert a.effective_units == D("100")


# ----------------------------------------------- certification requirements


def test_reconstruction_may_not_be_supported_while_unsupported():
    a = alloc(reconstructed_units="500", evidence_quality=UNSUPPORTED,
              rationale="Reviewed calendars.")
    assert any("UNSUPPORTED" in p for p in a.validate())


def test_reconstruction_requires_a_rationale():
    a = alloc(reconstructed_units="500", evidence_quality=CORROBORATED, rationale="  ")
    assert any("requires a rationale" in p for p in a.validate())


def test_management_reconstruction_needs_evidence_or_certification():
    bare = alloc(reconstructed_units="500",
                 evidence_quality=MANAGEMENT_RECONSTRUCTION,
                 rationale="Reconstructed from calendars.")
    assert any("needs evidence or an employee or supervisor" in p
               for p in bare.validate())

    with_cert = alloc(reconstructed_units="500",
                      evidence_quality=MANAGEMENT_RECONSTRUCTION,
                      rationale="Reconstructed from calendars.",
                      certifications=(EMPLOYEE_CERT,))
    assert with_cert.validate() == []

    with_evidence = alloc(reconstructed_units="500",
                          evidence_quality=MANAGEMENT_RECONSTRUCTION,
                          rationale="Reconstructed from calendars.",
                          evidence_ids=("EV-0012",))
    assert with_evidence.validate() == []


def test_supervisor_certification_also_satisfies_the_requirement():
    a = alloc(reconstructed_units="500",
              evidence_quality=MANAGEMENT_RECONSTRUCTION,
              rationale="Reconstructed from calendars.",
              certifications=(SUPERVISOR_CERT,))
    assert a.validate() == []
    assert a.has_supervisor_certification
    assert not a.has_employee_certification


def test_test_assumption_labor_may_not_be_approved():
    a = alloc(original_units="100", evidence_quality=TEST_ASSUMPTION,
              review_status=APPROVED)
    assert any("TEST ASSUMPTION labor cannot be APPROVED" in p for p in a.validate())


def test_test_assumption_labor_may_sit_in_review():
    a = alloc(original_units="100", evidence_quality=TEST_ASSUMPTION,
              review_status="OPEN")
    assert a.validate() == []


@pytest.mark.parametrize("missing", ["employee_id", "period", "objective_id"])
def test_identity_fields_are_required(missing):
    a = alloc(**{missing: ""})
    assert any("required" in p for p in a.validate())


def test_negative_units_are_refused():
    a = alloc(original_units="-5")
    assert any("cannot be negative" in p for p in a.validate())


def test_validate_strict_raises():
    with pytest.raises(LaborValidationError):
        alloc(original_units="-5").validate_strict()


def test_certification_period_coverage():
    assert EMPLOYEE_CERT.covers(date(2025, 6, 30))
    assert not EMPLOYEE_CERT.covers(date(2024, 12, 31))


# ------------------------------------------- 100% distribution (spec 4.2)


def test_undistributed_payroll_is_a_hard_stop():
    dist = EmployeeDistribution(
        employee_id="EWING", period="2025", payroll_wages=D("192087.13"), allocations=()
    )
    assert any("Undistributed payroll is a hard stop" in p for p in dist.validate())


def test_zero_payroll_with_no_allocations_is_acceptable():
    dist = EmployeeDistribution(
        employee_id="UNGER", period="2025", payroll_wages=ZERO, allocations=()
    )
    assert dist.is_valid


def test_distribution_foots_to_payroll_exactly():
    """Rounding residual lands on the largest objective rather than failing."""
    dist = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("192087.13"),
        allocations=(
            alloc(objective_id="ESP", original_units="1189.41"),
            alloc(objective_id="HUB", original_units="815"),
            alloc(objective_id="YBI", original_units="353.62"),
            alloc(objective_id="FUNDRAISING", original_units="126.32"),
            alloc(objective_id="HYBRID-II", original_units="57.60"),
        ),
    )
    distributed = dist.distributed_wages()
    assert sum(distributed.values(), ZERO) == D("192087.13")
    assert dist.is_valid


def test_allocations_from_another_employee_are_refused():
    dist = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("100"),
        allocations=(alloc(employee_id="GAFFNEY", original_units="10"),),
    )
    assert any("appears in the distribution for EWING" in p for p in dist.validate())


def test_allocations_from_another_period_are_refused():
    dist = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("100"),
        allocations=(alloc(period="2024", original_units="10"),),
    )
    assert any("period 2024" in p for p in dist.validate())


def test_zero_effort_units_cannot_distribute_payroll():
    dist = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("100"),
        allocations=(alloc(original_units="0"),),
    )
    assert any("total effort units are zero" in p for p in dist.validate())


# ------------------------------------- reclassifying never-billed exec time
#
# The case that motivates the workflow: an executive whose time was never direct
# billed but who in fact spent at least a quarter of the year overseeing the
# three America Makes contracts, with the balance a genuine G&A contribution.


def test_executive_time_reclassified_to_contracts_needs_certification_first():
    uncertified = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("192087.13"),
        allocations=(
            alloc(objective_id="DRIVE-AM", original_units="0",
                  reconstructed_units="260", evidence_quality=MANAGEMENT_RECONSTRUCTION,
                  rationale="Contract oversight; calendar and PMR attendance."),
            alloc(objective_id="YBI", original_units="1560"),
        ),
    )
    problems = uncertified.validate()
    assert any("needs evidence or an employee or supervisor" in p for p in problems)
    assert "DRIVE-AM" in uncertified.uncertified_objectives()


def test_certified_executive_reclassification_distributes_cleanly():
    dist = EmployeeDistribution(
        employee_id="EWING",
        period="2025",
        payroll_wages=D("192087.13"),
        allocations=(
            alloc(objective_id="DRIVE-AM", original_units="0",
                  reconstructed_units="217", evidence_quality=MANAGEMENT_RECONSTRUCTION,
                  rationale="Contract oversight; calendar and PMR attendance.",
                  certifications=(EMPLOYEE_CERT, SUPERVISOR_CERT)),
            alloc(objective_id="HYBRID-II", original_units="0",
                  reconstructed_units="217", evidence_quality=MANAGEMENT_RECONSTRUCTION,
                  rationale="Contract oversight; calendar and PMR attendance.",
                  certifications=(EMPLOYEE_CERT, SUPERVISOR_CERT)),
            alloc(objective_id="LTM", original_units="0",
                  reconstructed_units="216", evidence_quality=MANAGEMENT_RECONSTRUCTION,
                  rationale="Contract oversight; calendar and PMR attendance.",
                  certifications=(EMPLOYEE_CERT, SUPERVISOR_CERT)),
            alloc(objective_id="YBI", original_units="0", reconstructed_units="1950",
                  evidence_quality=CORROBORATED,
                  rationale="Residual general administration.",
                  certifications=(EMPLOYEE_CERT,)),
        ),
    )
    assert dist.is_valid
    assert dist.uncertified_objectives() == []

    # A quarter of the year across the three America Makes contracts.
    am_share = sum(
        dist.share_of(o) for o in ("DRIVE-AM", "HYBRID-II", "LTM")
    )
    assert D("0.24") < am_share < D("0.26")

    distributed = dist.distributed_wages()
    assert sum(distributed.values(), ZERO) == D("192087.13")
    # G&A contribution survives alongside the direct charges (invariant 7 spirit).
    assert distributed["YBI"] > distributed["DRIVE-AM"]
