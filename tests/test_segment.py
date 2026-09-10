"""Splitting a booked line into analytically distinct parts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.segment import Part, SegmentError, plan_segments

D = Decimal


def part(label, share, rationale="because") -> Part:
    return Part(label=label, share=D(str(share)), rationale=rationale)


SIXTY_FORTY = [part("Direct to ESP", "0.60"), part("G&A", "0.40")]


# ------------------------------------------------------------ reconciliation


def test_every_line_reconciles_to_the_cent():
    """Per line, not in aggregate. A group that foots while its lines do not
    is a set of wrong numbers that happen to cancel."""
    lines = {f"L{i}": D(str(v)) for i, v in
             enumerate(["100.01", "33.33", "0.07", "1234.56", "9999.99"])}
    plan = plan_segments(lines, SIXTY_FORTY)
    for line_id, rows in plan.by_line.items():
        assert sum(a for _, a in rows) == lines[line_id], line_id


def test_the_group_total_is_preserved():
    lines = {"L1": D("588538.89"), "L2": D("0.11")}
    plan = plan_segments(lines, SIXTY_FORTY)
    assert plan.total() == D("588539.00")


def test_thirds_still_reconcile():
    """The case that exposes naive proportional rounding."""
    parts = [part("A", "0.3333333333"), part("B", "0.3333333333"),
             part("C", "0.3333333334")]
    lines = {"L1": D("100.00"), "L2": D("0.01"), "L3": D("10.00")}
    plan = plan_segments(lines, parts)
    for line_id, rows in plan.by_line.items():
        assert sum(a for _, a in rows) == lines[line_id]


def test_residual_lands_on_the_largest_part():
    plan = plan_segments({"L1": D("0.05")}, SIXTY_FORTY)
    rows = dict(plan.by_line["L1"])
    assert rows[0] == D("0.03")   # 0.03 after absorbing the residual
    assert rows[1] == D("0.02")
    assert rows[0] + rows[1] == D("0.05")


def test_negative_lines_reconcile_too():
    """Credit memos and reversals are lines like any other."""
    plan = plan_segments({"L1": D("-12379.49")}, SIXTY_FORTY)
    rows = plan.by_line["L1"]
    assert sum(a for _, a in rows) == D("-12379.49")


# ------------------------------------------------------------ refusals


def test_one_part_is_not_a_split():
    with pytest.raises(SegmentError, match="at least two parts"):
        plan_segments({"L1": D("100")}, [part("Everything", "1.0")])


def test_shares_must_account_for_the_whole_line():
    with pytest.raises(SegmentError, match="must account for the whole line"):
        plan_segments({"L1": D("100")},
                      [part("A", "0.5"), part("B", "0.3")])


def test_shares_over_one_are_refused():
    with pytest.raises(SegmentError, match="must account for the whole line"):
        plan_segments({"L1": D("100")},
                      [part("A", "0.7"), part("B", "0.7")])


def test_a_negative_share_is_refused():
    with pytest.raises(SegmentError, match="negative share"):
        plan_segments({"L1": D("100")},
                      [part("A", "1.5"), part("B", "-0.5")])


def test_a_part_without_a_rationale_is_refused():
    """A split is a judgment; an unexplained one is worse than none."""
    with pytest.raises(SegmentError, match="needs a rationale"):
        Part(label="G&A", share=D("0.4"), rationale="   ")


def test_a_part_without_a_label_is_refused():
    with pytest.raises(SegmentError, match="needs a label"):
        Part(label="", share=D("0.4"), rationale="because")


def test_only_one_non_zero_share_divides_nothing():
    with pytest.raises(SegmentError, match="two parts must take a non-zero"):
        plan_segments({"L1": D("100")},
                      [part("All", "1.0"), part("None", "0.0")])


def test_a_group_of_only_zero_lines_has_nothing_to_split():
    with pytest.raises(SegmentError, match="every line in this group is zero"):
        plan_segments({"L1": D("0.00"), "L2": D("0")}, SIXTY_FORTY)


# ------------------------------------------------------------ zero handling


def test_zero_lines_are_skipped_not_given_rows_of_zeroes():
    plan = plan_segments({"L1": D("100.00"), "L2": D("0.00")}, SIXTY_FORTY)
    assert "L1" in plan.by_line
    assert "L2" not in plan.by_line
    assert plan.total() == D("100.00")


def test_a_zero_share_part_produces_no_segments():
    parts = [part("A", "0.5"), part("B", "0.5"), part("Unused", "0.0")]
    plan = plan_segments({"L1": D("100.00")}, parts)
    assert plan.part_total(2) == D("0")
    assert len(plan.by_line["L1"]) == 2


# ------------------------------------------------ the real 5227 judgment


def test_portfolio_consulting_split_across_many_lines():
    """5227 Portfolio consulting: $588,539 across 442 lines, no objective
    signal. The largest open judgment in the 2025 ledger, and the reason
    segmentation exists."""
    lines = {f"L{i:03d}": D("1331.53") for i in range(442)}
    lines["L000"] = D("588539.00") - D("1331.53") * 441

    plan = plan_segments(lines, SIXTY_FORTY)

    assert plan.total() == D("588539.00")
    assert plan.segment_count == 442 * 2
    for line_id, rows in plan.by_line.items():
        assert sum(a for _, a in rows) == lines[line_id]
    # And the parts foot to the group.
    assert plan.part_total(0) + plan.part_total(1) == D("588539.00")
