"""Labor distribution and certification (spec 4.2, and 2 CFR 200.430(i)).

Two rules shape this module.

**Spec invariant 2 -- original time is immutable; reconstruction is a separate
record.** A :class:`LaborAllocation` carries ``original_units`` and
``reconstructed_units`` side by side. Reconstruction never overwrites the
original; it supersedes it for effective-value purposes while both remain on the
record.

**Spec 4.2 -- 100% of actual payroll must distribute.** Undistributed payroll is
a hard stop, not a rounding difference. :class:`EmployeeDistribution` enforces
both the 100%-of-effort rule and the reconciliation to payroll dollars.

The certification rules are a port of ``fcs13ValidateLabor_`` from FCS 1.4, which
in turn implements 2 CFR 200.430(i). They exist to make one specific workflow
safe: reclassifying executive and support staff time that was never direct
billed -- an executive who in fact spent a quarter of her year overseeing three
federal contracts -- into direct charges, supported by certification rather than
by assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Sequence

from fcs.money import (
    TOLERANCE,
    ZERO,
    money,
    quantize_money,
    rate as to_rate,
    safe_divide,
)

__all__ = [
    "LaborCertification",
    "LaborAllocation",
    "EmployeeDistribution",
    "LaborValidationError",
    "UNSUPPORTED",
    "TEST_ASSUMPTION",
    "MANAGEMENT_RECONSTRUCTION",
    "APPROVED",
]

UNSUPPORTED = "UNSUPPORTED"
TEST_ASSUMPTION = "TEST ASSUMPTION"
MANAGEMENT_RECONSTRUCTION = "MANAGEMENT RECONSTRUCTION"
CORROBORATED = "CORROBORATED"
VERIFIED = "VERIFIED"
APPROVED = "APPROVED"

#: Effort distribution must total 100% within this tolerance.
EFFORT_TOLERANCE = Decimal("0.0001")


class LaborValidationError(ValueError):
    """A labor record violates 2 CFR 200.430(i) or a spec invariant."""


@dataclass(frozen=True)
class LaborCertification:
    """An employee or supervisor certification of an effort distribution.

    2 CFR 200.430(i)(1)(ii) requires the distribution to be incorporated into the
    official records of the entity. A certification stored here is that record --
    it is not an attachment to a spreadsheet.
    """

    certified_by: str
    role: str  # "EMPLOYEE" or "SUPERVISOR"
    certified_on: date
    period_start: date
    period_end: date
    scope_note: str = ""
    evidence_id: str = ""

    def covers(self, day: date) -> bool:
        return self.period_start <= day <= self.period_end

    @property
    def is_employee(self) -> bool:
        return self.role.upper() == "EMPLOYEE"

    @property
    def is_supervisor(self) -> bool:
        return self.role.upper() == "SUPERVISOR"


@dataclass(frozen=True)
class LaborAllocation:
    """One employee-period-objective labor record.

    ``original_units`` is the effort as first recorded and is never mutated.
    ``reconstructed_units`` is a separate, later determination. ``effective_units``
    prefers the reconstruction when one exists.
    """

    employee_id: str
    period: str
    objective_id: str
    payroll_wages: Decimal = ZERO
    original_units: Decimal = ZERO
    reconstructed_units: Decimal | None = None
    evidence_quality: str = UNSUPPORTED
    review_status: str = "OPEN"
    rationale: str = ""
    certifications: Sequence[LaborCertification] = field(default_factory=tuple)
    evidence_ids: Sequence[str] = field(default_factory=tuple)

    @property
    def is_reconstructed(self) -> bool:
        return self.reconstructed_units is not None

    @property
    def effective_units(self) -> Decimal:
        return (
            self.original_units
            if self.reconstructed_units is None
            else self.reconstructed_units
        )

    @property
    def has_employee_certification(self) -> bool:
        return any(c.is_employee for c in self.certifications)

    @property
    def has_supervisor_certification(self) -> bool:
        return any(c.is_supervisor for c in self.certifications)

    @property
    def is_certified(self) -> bool:
        return self.has_employee_certification or self.has_supervisor_certification

    def validate(self) -> list[str]:
        """Return every violation. Empty list means the record is acceptable."""
        problems: list[str] = []

        if not self.employee_id:
            problems.append("Employee is required.")
        if not self.period:
            problems.append("Period is required.")
        if not self.objective_id:
            problems.append("Objective is required.")

        for name, value in (
            ("payroll_wages", self.payroll_wages),
            ("original_units", self.original_units),
            ("effective_units", self.effective_units),
        ):
            if value < ZERO:
                problems.append(f"{name} cannot be negative (got {value}).")

        if self.is_reconstructed:
            if self.evidence_quality == UNSUPPORTED:
                problems.append(
                    "Reconstructed effort cannot be saved as supported while "
                    "evidence quality is UNSUPPORTED."
                )
            if not self.rationale.strip():
                problems.append("Reconstructed effort requires a rationale.")
            if (
                self.evidence_quality == MANAGEMENT_RECONSTRUCTION
                and not self.is_certified
                and not any(e.strip() for e in self.evidence_ids)
            ):
                problems.append(
                    "Management reconstruction needs evidence or an employee or "
                    "supervisor certification (2 CFR 200.430(i))."
                )

        if self.evidence_quality == TEST_ASSUMPTION and self.review_status == APPROVED:
            problems.append("TEST ASSUMPTION labor cannot be APPROVED.")

        return problems

    def validate_strict(self) -> "LaborAllocation":
        problems = self.validate()
        if problems:
            raise LaborValidationError(
                f"{self.employee_id} / {self.period} / {self.objective_id}: "
                + " ".join(problems)
            )
        return self


@dataclass(frozen=True)
class EmployeeDistribution:
    """Every labor allocation for one employee-period.

    Spec 4.2: 100% of actual payroll must distribute to final objectives or to
    legitimate indirect or excluded functions.
    """

    employee_id: str
    period: str
    payroll_wages: Decimal
    allocations: Sequence[LaborAllocation] = field(default_factory=tuple)

    @property
    def total_units(self) -> Decimal:
        return sum((a.effective_units for a in self.allocations), ZERO)

    def share_of(self, objective_id: str) -> Decimal:
        """Fraction of this employee's effort on one objective."""
        units = sum(
            (a.effective_units for a in self.allocations if a.objective_id == objective_id),
            ZERO,
        )
        return safe_divide(units, self.total_units)

    def wages_for(self, objective_id: str) -> Decimal:
        """Payroll dollars attributable to one objective."""
        return quantize_money(self.payroll_wages * self.share_of(objective_id))

    def distributed_wages(self) -> dict[str, Decimal]:
        """Payroll dollars by objective.

        The largest objective absorbs any rounding residual so the distribution
        foots to payroll exactly. Spec 4.2 makes undistributed payroll a hard
        stop, and a cent of rounding is not a reason to fail a control.
        """
        objectives = []
        for allocation in self.allocations:
            if allocation.objective_id not in objectives:
                objectives.append(allocation.objective_id)

        result = {obj: self.wages_for(obj) for obj in objectives}
        if not result:
            return result

        residual = quantize_money(self.payroll_wages - sum(result.values(), ZERO))
        if residual != ZERO:
            largest = max(result, key=lambda k: result[k])
            result[largest] = quantize_money(result[largest] + residual)
        return result

    def validate(self) -> list[str]:
        problems: list[str] = []

        for allocation in self.allocations:
            problems.extend(allocation.validate())
            if allocation.employee_id != self.employee_id:
                problems.append(
                    f"Allocation for {allocation.employee_id} appears in the "
                    f"distribution for {self.employee_id}."
                )
            if allocation.period != self.period:
                problems.append(
                    f"Allocation for period {allocation.period} appears in the "
                    f"distribution for {self.period}."
                )

        if not self.allocations:
            if self.payroll_wages != ZERO:
                problems.append(
                    f"{self.employee_id} has payroll of {self.payroll_wages} for "
                    f"{self.period} with no distribution. Undistributed payroll is a "
                    f"hard stop (spec 4.2)."
                )
            return problems

        if self.total_units <= ZERO:
            problems.append(
                f"{self.employee_id} / {self.period}: total effort units are zero, "
                f"so payroll cannot be distributed."
            )
            return problems

        distributed = sum(self.distributed_wages().values(), ZERO)
        if abs(distributed - self.payroll_wages) > TOLERANCE:
            problems.append(
                f"{self.employee_id} / {self.period}: distributed wages "
                f"{distributed} do not reconcile to payroll {self.payroll_wages}."
            )

        return problems

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    def validate_strict(self) -> "EmployeeDistribution":
        problems = self.validate()
        if problems:
            raise LaborValidationError(" ".join(problems))
        return self

    def uncertified_objectives(self) -> list[str]:
        """Objectives whose allocation lacks any certification.

        These are the records that cannot support a direct charge to a federal
        award. For a reclassification of previously indirect executive time into
        direct charges, this list is the work queue.
        """
        return sorted(
            {
                a.objective_id
                for a in self.allocations
                if a.effective_units > ZERO and not a.is_certified
            }
        )
