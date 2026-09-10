"""Indirect cost rate computation (spec 4.3, 4.4, 4.7).

A rate is a pool divided by a base. What makes it defensible is not the division
but the discipline around it: what entered the pool, what entered the base, what
was removed and under what authority, and the fact that the method was fixed
before the answer was known.

That last point is 2 CFR 200.405(c). A rate derived to close a known billing gap
is a finding. :class:`RateComputation` therefore carries the methodology lock
timestamp through to the result, and :func:`compute_rate` refuses to produce a
postable rate from an unlocked methodology.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from fcs.money import (
    TOLERANCE,
    ZERO,
    money,
    quantize_money,
    quantize_rate,
    safe_divide,
)

__all__ = [
    "PoolLine",
    "CostPool",
    "AllocationBase",
    "RateComputation",
    "MethodologyNotLockedError",
    "compute_rate",
    "DE_MINIMIS_PRE_2024",
    "DE_MINIMIS_POST_2024",
]

#: 2 CFR 200.414(f). Raised from 10% to 15% by the 2024 revisions for awards
#: issued on or after 2024-10-01.
DE_MINIMIS_PRE_2024 = Decimal("0.10")
DE_MINIMIS_POST_2024 = Decimal("0.15")


class MethodologyNotLockedError(RuntimeError):
    """Raised when a postable rate is requested from an unlocked methodology."""


@dataclass(frozen=True)
class PoolLine:
    """One line in a cost pool, with its authority.

    ``included`` False means the line was considered and removed. Removed lines
    stay on the record: an auditor's first question about a pool is what is *not*
    in it, and a schedule that only shows inclusions cannot answer that.
    """

    label: str
    amount: Decimal
    included: bool = True
    authority: str = ""
    rationale: str = ""

    @classmethod
    def of(
        cls,
        label: str,
        amount,
        *,
        included: bool = True,
        authority: str = "",
        rationale: str = "",
    ) -> "PoolLine":
        return cls(
            label=label,
            amount=money(amount, field=label),
            included=included,
            authority=authority,
            rationale=rationale,
        )

    def excluded_as(self, authority: str, rationale: str = "") -> "PoolLine":
        """Return a copy of this line marked excluded under an authority."""
        return PoolLine(
            label=self.label,
            amount=self.amount,
            included=False,
            authority=authority,
            rationale=rationale,
        )


@dataclass(frozen=True)
class CostPool:
    """An indirect cost pool assembled from itemized lines."""

    kind: str
    period: str
    lines: Sequence[PoolLine] = field(default_factory=tuple)

    @property
    def amount(self) -> Decimal:
        return quantize_money(
            sum((line.amount for line in self.lines if line.included), ZERO)
        )

    @property
    def excluded_amount(self) -> Decimal:
        return quantize_money(
            sum((line.amount for line in self.lines if not line.included), ZERO)
        )

    @property
    def considered_amount(self) -> Decimal:
        """Everything looked at, included or not."""
        return quantize_money(self.amount + self.excluded_amount)

    def exclusion_schedule(self) -> list[PoolLine]:
        return [line for line in self.lines if not line.included]

    def with_lines(self, lines: Iterable[PoolLine]) -> "CostPool":
        return CostPool(kind=self.kind, period=self.period, lines=tuple(lines))


@dataclass(frozen=True)
class AllocationBase:
    """The denominator of a rate, itemized the same way a pool is."""

    kind: str
    period: str
    lines: Sequence[PoolLine] = field(default_factory=tuple)

    @property
    def amount(self) -> Decimal:
        return quantize_money(
            sum((line.amount for line in self.lines if line.included), ZERO)
        )

    @property
    def excluded_amount(self) -> Decimal:
        return quantize_money(
            sum((line.amount for line in self.lines if not line.included), ZERO)
        )

    def exclusion_schedule(self) -> list[PoolLine]:
        return [line for line in self.lines if not line.included]


@dataclass(frozen=True)
class RateComputation:
    """A computed rate together with everything needed to defend it."""

    kind: str
    period: str
    pool: CostPool
    base: AllocationBase
    scenario: str = ""
    methodology_locked_at: datetime | None = None
    methodology_note: str = ""

    @property
    def rate(self) -> Decimal:
        return quantize_rate(safe_divide(self.pool.amount, self.base.amount))

    @property
    def rate_percent(self) -> Decimal:
        return (self.rate * Decimal("100")).quantize(Decimal("0.01"))

    @property
    def is_methodology_locked(self) -> bool:
        return self.methodology_locked_at is not None

    def applied_to(self, base_amount) -> Decimal:
        """Apply this rate to a base amount."""
        return quantize_money(money(base_amount, field="base_amount") * self.rate)

    def require_locked(self) -> "RateComputation":
        """Raise unless the methodology was locked before the rate was computed.

        This is the 2 CFR 200.405(c) guard. It is deliberately awkward to bypass.
        """
        if not self.is_methodology_locked:
            raise MethodologyNotLockedError(
                f"{self.kind} rate for {self.period} cannot be used for a posted "
                f"disposition or a restated invoice: the methodology was never "
                f"locked. Lock the methodology, then recompute."
            )
        return self

    def reconciles_to(self, control_total: Decimal) -> bool:
        """True when the pool agrees with an independent control total."""
        return abs(self.pool.amount - money(control_total)) <= TOLERANCE

    def workpaper_rows(self) -> list[tuple[str, str, Decimal]]:
        """Flat rows for the printable rate workpaper."""
        rows: list[tuple[str, str, Decimal]] = []
        for line in self.pool.lines:
            section = "POOL" if line.included else "POOL - EXCLUDED"
            rows.append((section, f"{line.label} [{line.authority}]".strip(), line.amount))
        rows.append(("POOL", "Total indirect cost pool", self.pool.amount))
        for line in self.base.lines:
            section = "BASE" if line.included else "BASE - EXCLUDED"
            rows.append((section, f"{line.label} [{line.authority}]".strip(), line.amount))
        rows.append(("BASE", "Total allocation base", self.base.amount))
        return rows


def compute_rate(
    *,
    kind: str,
    period: str,
    pool: CostPool,
    base: AllocationBase,
    scenario: str = "",
    methodology_locked_at: datetime | None = None,
    methodology_note: str = "",
) -> RateComputation:
    """Compute a rate from a pool and a base."""
    if pool.period != period or base.period != period:
        raise ValueError(
            f"Period mismatch: rate {period}, pool {pool.period}, base {base.period}."
        )
    return RateComputation(
        kind=kind,
        period=period,
        pool=pool,
        base=base,
        scenario=scenario,
        methodology_locked_at=methodology_locked_at,
        methodology_note=methodology_note,
    )
