"""Splitting a booked line into analytically distinct parts.

The controller works in groups — an account and a payee, often hundreds of
lines. A judgment like "sixty per cent of portfolio consulting is direct to
ESP, the rest is G&A" is made once about the group and has to land on every
line in it, because classification and evidence attach per line.

Two properties the arithmetic must have, and neither is automatic:

**Every line reconciles exactly.** Not the group in aggregate — each line. The
database gate checks per line, and rightly: a group that foots while its lines
do not is a set of wrong numbers that happen to cancel. Rounding residual is
placed on the largest part of each line, which is where it distorts least.

**A share of zero produces no segment.** A part that takes nothing from a line
is not a judgment about that line, and an empty segment would fail the
"a single segment is not a split" rule for no reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .core import money

__all__ = ["Part", "SegmentPlan", "plan_segments", "SegmentError"]

TOLERANCE = Decimal("0.01")
ONE = Decimal("1")


class SegmentError(ValueError):
    """A segmentation that cannot be applied."""


@dataclass(frozen=True)
class Part:
    """One analytical part of a split, as a share of each line."""

    label: str
    share: Decimal
    rationale: str
    citation: str = ""

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise SegmentError("Every part needs a label.")
        if not self.rationale.strip():
            raise SegmentError(
                f"Part {self.label!r} needs a rationale. A split is a judgment; "
                f"an unexplained one is worse than none.")
        if self.share < 0:
            raise SegmentError(f"Part {self.label!r} has a negative share.")


@dataclass(frozen=True)
class SegmentPlan:
    """The amounts a split produces, per line."""

    #: line_id -> [(part index, amount)]
    by_line: dict[str, list[tuple[int, Decimal]]]
    parts: tuple[Part, ...]

    @property
    def segment_count(self) -> int:
        return sum(len(v) for v in self.by_line.values())

    def total(self) -> Decimal:
        return money(sum(
            (amount for rows in self.by_line.values() for _, amount in rows),
            Decimal(0)))

    def part_total(self, index: int) -> Decimal:
        return money(sum(
            (amount for rows in self.by_line.values()
             for i, amount in rows if i == index),
            Decimal(0)))


def plan_segments(lines: dict[str, Decimal], parts: list[Part]) -> SegmentPlan:
    """Split each line in ``lines`` across ``parts`` by share.

    ``lines`` maps line_id to its booked amount. Returns the amounts to write,
    with each line's rounding residual absorbed by its largest part.
    """
    if len(parts) < 2:
        raise SegmentError(
            "A split needs at least two parts. Splitting a line into one part "
            "changes nothing and hides the fact that no judgment was made.")

    total_share = sum((p.share for p in parts), Decimal(0))
    if abs(total_share - ONE) > Decimal("0.0001"):
        raise SegmentError(
            f"Shares total {total_share}, not 1. A split must account for the "
            f"whole line.")

    if sum(1 for p in parts if p.share > 0) < 2:
        raise SegmentError(
            "At least two parts must take a non-zero share, or nothing has "
            "actually been divided.")

    by_line: dict[str, list[tuple[int, Decimal]]] = {}
    for line_id, booked in lines.items():
        booked = money(booked)
        if booked == 0:
            # A zero line has nothing to divide. Left unsegmented rather than
            # given a row of zeroes that assert a judgment about no money.
            continue

        rows: list[tuple[int, Decimal]] = []
        for index, part in enumerate(parts):
            if part.share == 0:
                continue
            rows.append((index, money(booked * part.share)))

        if len(rows) < 2:
            continue

        # Residual to the largest part of THIS line, by absolute size, so the
        # line reconciles to the cent.
        residual = money(booked - sum((a for _, a in rows), Decimal(0)))
        if residual != 0:
            biggest = max(range(len(rows)), key=lambda i: abs(rows[i][1]))
            idx, amount = rows[biggest]
            rows[biggest] = (idx, money(amount + residual))

        assert money(sum((a for _, a in rows), Decimal(0))) == booked
        by_line[line_id] = rows

    if not by_line:
        raise SegmentError(
            "Nothing to segment: every line in this group is zero.")

    return SegmentPlan(by_line=by_line, parts=tuple(parts))
