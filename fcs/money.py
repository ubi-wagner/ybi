"""Money primitives for FCS.

Every monetary value in this system is a :class:`decimal.Decimal`. Floats are
never used for money, and the module refuses to construct a Money value from a
float so the rule cannot be violated by accident.

The system reconciles to the cent. ``TOLERANCE`` is the single definition of
"agrees" used by every control, gate, and invariant check, and matches the
``$0.01`` tolerance the FCS 1.4 specification requires.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Union

__all__ = [
    "ZERO",
    "ONE",
    "CENT",
    "TOLERANCE",
    "Money",
    "money",
    "rate",
    "quantize_money",
    "quantize_rate",
    "total",
    "agrees",
    "is_zero",
    "non_negative",
    "safe_divide",
]

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")

#: Two amounts agree when they differ by no more than this.
TOLERANCE = Decimal("0.01")

#: Rates carry more precision than money so that pool / base division does not
#: lose accuracy before it is applied to a base.
RATE_PRECISION = Decimal("0.00000001")

Money = Decimal
Numeric = Union[int, str, Decimal]


class MoneyError(ValueError):
    """Raised when a value cannot be interpreted as money."""


def money(value: Numeric | None, *, field: str = "value") -> Decimal:
    """Coerce ``value`` to a cent-quantized :class:`Decimal`.

    Floats are rejected outright. ``None`` and empty string become zero, which
    matches how the source spreadsheets represent an absent amount.
    """
    if isinstance(value, float):
        raise MoneyError(
            f"{field}: float is not an acceptable money value ({value!r}). "
            "Pass a str, int, or Decimal."
        )
    if value is None or value == "":
        return ZERO
    try:
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise MoneyError(f"{field}: cannot interpret {value!r} as money") from exc


def rate(value: Numeric | None, *, field: str = "rate") -> Decimal:
    """Coerce ``value`` to a Decimal rate without cent-quantizing it."""
    if isinstance(value, float):
        raise MoneyError(
            f"{field}: float is not an acceptable rate value ({value!r}). "
            "Pass a str, int, or Decimal."
        )
    if value is None or value == "":
        return ZERO
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise MoneyError(f"{field}: cannot interpret {value!r} as a rate") from exc


def quantize_money(value: Decimal) -> Decimal:
    """Round a Decimal to cents, half-up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    """Round a Decimal rate to the system rate precision."""
    return value.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def total(values: Iterable[Numeric | None], *, field: str = "value") -> Decimal:
    """Sum an iterable of money values, quantizing the result."""
    acc = ZERO
    for value in values:
        acc += money(value, field=field)
    return quantize_money(acc)


def agrees(left: Decimal, right: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """True when two amounts agree within ``tolerance`` (inclusive)."""
    return abs(left - right) <= tolerance


def is_zero(value: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """True when an amount is zero within ``tolerance``."""
    return abs(value) <= tolerance


def non_negative(value: Decimal, *, field: str) -> Decimal:
    """Return ``value``, raising if it is negative beyond tolerance.

    A value inside ``-TOLERANCE..0`` is treated as a rounding artefact and
    normalized to zero rather than rejected.
    """
    if value < -TOLERANCE:
        raise MoneyError(f"{field} cannot be negative (got {value}).")
    return ZERO if value < ZERO else value


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide, returning zero when the denominator is zero.

    A rate over an empty base is zero, not an error: an objective with no base
    simply carries no indirect cost.
    """
    if denominator == ZERO:
        return ZERO
    return numerator / denominator
