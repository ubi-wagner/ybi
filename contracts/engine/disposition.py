"""Recovery disposition -- the downstream contract reconciliation invariants.

This is a Python port of the FCS 1.4 rules in ``fcs14ValidateDisposition_``,
with the specification's review expectations added as warnings and with award
ceiling handling made explicit.

The module is deliberately free of Django imports. The disposition arithmetic is
the part of this system that must be provably correct, so it is testable without
a database.

Invariants (FCS_1_4_RECONCILIATION_QA.md, "Core invariants"):

4. ``allowable <= allocable <= actual`` is a *review expectation*;
   ``recoverable`` may not exceed ``allowable`` -- that one is hard.
5. Supported unrecovered is not a plug. When ``billed <= allowable`` it must
   equal ``allowable - billed`` within $0.01.
6. When ``billed > allowable``, unsupported must capture at least
   ``billed - allowable``.
7. Cost share is distinct from supported unrecovered / YBI-funded cost. It is
   never derived from the other fields and never nets against them.

Two further quantities the spec leaves implicit are computed here because the
2025 restatement needs them:

``additional_recoverable``
    What a restated invoice may still claim -- ``recoverable - billed`` when
    positive. This is the number that goes on a restated invoice to NCDMM.

``over_collection``
    Cash that must be returned -- ``billed - recoverable`` when positive. Note
    this uses *recoverable*, not *allowable*: an amount billed above the award
    ceiling must be returned even where allowable cost would otherwise support
    it. That is the Hybrid Phase 2 fact pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Sequence

from fcs.money import TOLERANCE, ZERO, money, quantize_money

__all__ = [
    "Disposition",
    "DispositionError",
    "Finding",
    "derive_disposition",
    "AMERICA_MAKES_OBJECTIVES",
    "assert_america_makes_objective",
]

#: FCS 1.4 invariant 10. Duplicated from ``foundation.constants`` so that this
#: module stays importable without Django.
AMERICA_MAKES_OBJECTIVES = ("DRIVE-AM", "HYBRID-II", "LTM")


class DispositionError(ValueError):
    """A hard invariant was violated."""


@dataclass(frozen=True)
class Finding:
    """A single validation result."""

    code: str
    message: str
    severity: str  # "ERROR" or "WARNING"

    @property
    def is_error(self) -> bool:
        return self.severity == "ERROR"


def _err(code: str, message: str) -> Finding:
    return Finding(code=code, message=message, severity="ERROR")


def _warn(code: str, message: str) -> Finding:
    return Finding(code=code, message=message, severity="WARNING")


@dataclass(frozen=True)
class Disposition:
    """Recovery classification for one objective-period (spec 3.13).

    Every field is a separate dimension. Spec 2.2: "No one field substitutes for
    another."
    """

    objective_id: str
    period: str

    # Cost dimensions, built upstream before any recovery analysis (invariant 3).
    actual: Decimal = ZERO          # fully burdened actual cost
    allocable: Decimal = ZERO       # portion allocable to this objective
    allowable: Decimal = ZERO       # portion allowable under 2 CFR 200 Subpart E

    # Recovery dimensions.
    recoverable: Decimal = ZERO     # contractually recoverable, ceiling-capped
    billed: Decimal = ZERO          # billed / recognized recovery
    cash_recovered: Decimal = ZERO

    # Separate dimensions that never net against the above (invariant 7).
    cost_share: Decimal = ZERO
    supported_unrecovered: Decimal = ZERO
    unsupported: Decimal = ZERO
    economic_only_foregone: Decimal = ZERO

    #: Total authorized federal ceiling, when the award carries one.
    ceiling: Decimal | None = None

    _MONEY_FIELDS: Sequence[str] = field(
        default=(
            "actual",
            "allocable",
            "allowable",
            "recoverable",
            "billed",
            "cash_recovered",
            "cost_share",
            "supported_unrecovered",
            "unsupported",
            "economic_only_foregone",
        ),
        repr=False,
        compare=False,
    )

    # -- derived views ---------------------------------------------------

    @property
    def additional_recoverable(self) -> Decimal:
        """What a restated invoice may still claim."""
        return quantize_money(max(ZERO, self.recoverable - self.billed))

    @property
    def over_collection(self) -> Decimal:
        """Cash that must be returned to the pass-through entity."""
        return quantize_money(max(ZERO, self.billed - self.recoverable))

    @property
    def ceiling_constrained(self) -> Decimal:
        """Allowable cost that cannot be recovered because of the ceiling."""
        return quantize_money(max(ZERO, self.allowable - self.recoverable))

    @property
    def operating_result(self) -> Decimal:
        """Recovery less fully burdened actual cost."""
        return quantize_money(self.billed - self.actual)

    # -- validation ------------------------------------------------------

    def validate(self) -> list[Finding]:
        """Return every finding. Errors are hard stops; warnings are review items."""
        findings: list[Finding] = []

        for name in self._MONEY_FIELDS:
            value = getattr(self, name)
            if value < -TOLERANCE:
                findings.append(
                    _err("NEGATIVE_AMOUNT", f"{name} cannot be negative (got {value}).")
                )

        # Invariant 4 (hard half): recoverable may not exceed allowable.
        if self.recoverable > self.allowable + TOLERANCE:
            findings.append(
                _err(
                    "RECOVERABLE_EXCEEDS_ALLOWABLE",
                    f"Recoverable cost {self.recoverable} cannot exceed allowable "
                    f"cost {self.allowable}.",
                )
            )

        if self.supported_unrecovered > self.allowable + TOLERANCE:
            findings.append(
                _err(
                    "UNRECOVERED_EXCEEDS_ALLOWABLE",
                    f"Supported unrecovered {self.supported_unrecovered} cannot "
                    f"exceed allowable cost {self.allowable}.",
                )
            )

        # Invariant 6: billed above allowable must be captured as unsupported.
        if self.billed > self.allowable + TOLERANCE:
            excess = self.billed - self.allowable
            if self.unsupported + TOLERANCE < excess:
                findings.append(
                    _err(
                        "UNSUPPORTED_UNDERSTATED",
                        f"Billed {self.billed} exceeds allowable {self.allowable}; "
                        f"unsupported must capture at least {quantize_money(excess)}, "
                        f"got {self.unsupported}.",
                    )
                )
        else:
            # Invariant 5: supported unrecovered is not a plug.
            expected = max(ZERO, self.allowable - self.billed)
            if abs(expected - self.supported_unrecovered) > TOLERANCE:
                findings.append(
                    _err(
                        "UNRECOVERED_NOT_RECONCILED",
                        f"Supported unrecovered must equal allowable less billed "
                        f"({quantize_money(expected)}) when billed does not exceed "
                        f"allowable; got {self.supported_unrecovered}.",
                    )
                )

        # Ceiling is a hard contractual limit where one exists.
        if self.ceiling is not None:
            if self.recoverable > self.ceiling + TOLERANCE:
                findings.append(
                    _err(
                        "RECOVERABLE_EXCEEDS_CEILING",
                        f"Recoverable cost {self.recoverable} exceeds the award "
                        f"ceiling {self.ceiling}.",
                    )
                )
            if self.billed > self.ceiling + TOLERANCE:
                findings.append(
                    _warn(
                        "BILLED_EXCEEDS_CEILING",
                        f"Billed {self.billed} exceeds the award ceiling "
                        f"{self.ceiling} by "
                        f"{quantize_money(self.billed - self.ceiling)}. This is an "
                        f"over-collection requiring return regardless of allowable "
                        f"cost.",
                    )
                )

        # Invariant 4 (review half): allowable <= allocable <= actual.
        if self.allocable > self.actual + TOLERANCE:
            findings.append(
                _warn(
                    "ALLOCABLE_EXCEEDS_ACTUAL",
                    f"Allocable cost {self.allocable} exceeds fully burdened actual "
                    f"cost {self.actual}. Review the allocation.",
                )
            )
        if self.allowable > self.allocable + TOLERANCE:
            findings.append(
                _warn(
                    "ALLOWABLE_EXCEEDS_ALLOCABLE",
                    f"Allowable cost {self.allowable} exceeds allocable cost "
                    f"{self.allocable}. Review the allowability determination.",
                )
            )

        if self.cash_recovered > self.billed + TOLERANCE:
            findings.append(
                _warn(
                    "CASH_EXCEEDS_BILLED",
                    f"Cash recovered {self.cash_recovered} exceeds billed "
                    f"{self.billed}.",
                )
            )

        return findings

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.validate() if f.is_error]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.validate() if not f.is_error]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def validate_strict(self) -> "Disposition":
        """Return self, raising :class:`DispositionError` on any hard violation."""
        errors = self.errors
        if errors:
            raise DispositionError(
                f"{self.objective_id} {self.period}: "
                + "; ".join(f.message for f in errors)
            )
        return self

    def with_(self, **changes: Decimal) -> "Disposition":
        """Return a copy with fields replaced, coercing to money."""
        coerced = {
            k: (money(v, field=k) if k in self._MONEY_FIELDS else v)
            for k, v in changes.items()
        }
        return replace(self, **coerced)


def derive_disposition(
    *,
    objective_id: str,
    period: str,
    actual,
    allocable,
    allowable,
    billed,
    cash_recovered=ZERO,
    cost_share=ZERO,
    identified_unsupported=ZERO,
    economic_only_foregone=ZERO,
    ceiling=None,
) -> Disposition:
    """Build a :class:`Disposition` with recovery fields derived, never plugged.

    ``supported_unrecovered`` and ``unsupported`` are *computed* from the cost
    and billing facts rather than accepted as inputs, which is what invariant 5
    means by "not a plug". ``identified_unsupported`` lets a reviewer record
    unsupported amounts discovered independently of the arithmetic; the derived
    value is the larger of the two.

    ``cost_share`` is carried straight through and never participates in the
    derivation (invariant 7).
    """
    actual_d = money(actual, field="actual")
    allocable_d = money(allocable, field="allocable")
    allowable_d = money(allowable, field="allowable")
    billed_d = money(billed, field="billed")
    ceiling_d = None if ceiling is None else money(ceiling, field="ceiling")

    # Recoverable is allowable cost, capped by the contractual ceiling.
    recoverable = allowable_d if ceiling_d is None else min(allowable_d, ceiling_d)

    supported_unrecovered = max(ZERO, allowable_d - billed_d)
    unsupported = max(
        money(identified_unsupported, field="identified_unsupported"),
        max(ZERO, billed_d - allowable_d),
    )

    return Disposition(
        objective_id=objective_id,
        period=period,
        actual=actual_d,
        allocable=allocable_d,
        allowable=allowable_d,
        recoverable=quantize_money(recoverable),
        billed=billed_d,
        cash_recovered=money(cash_recovered, field="cash_recovered"),
        cost_share=money(cost_share, field="cost_share"),
        supported_unrecovered=quantize_money(supported_unrecovered),
        unsupported=quantize_money(unsupported),
        economic_only_foregone=money(
            economic_only_foregone, field="economic_only_foregone"
        ),
        ceiling=ceiling_d,
    )


def assert_america_makes_objective(objective_id: str) -> str:
    """Enforce FCS 1.4 invariant 10."""
    if objective_id not in AMERICA_MAKES_OBJECTIVES:
        raise DispositionError(
            f"Only {', '.join(AMERICA_MAKES_OBJECTIVES)} may be updated through the "
            f"America Makes disposition updater (got {objective_id!r})."
        )
    return objective_id
