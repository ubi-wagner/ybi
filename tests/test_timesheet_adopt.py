"""Adopting the controller's reconstruction as your own record.

The one act that turns somebody else's account of your year into yours. 2 CFR
200.430(i) does not require a contemporaneous record; it requires one that
reflects the work actually performed, supported, and reviewed after the fact.
A reconstruction the person reads, corrects and signs meets that. A
reconstruction nobody ever saw does not — which is where 2025 has been
sitting, with zero timesheet entries and zero certifications against
$1,835,047 of labour.

The arithmetic is the part that went wrong twice, so it is a pure function
and it is tested here rather than through the route.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.routers.timesheet import spread_hours

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "app" / "routers" / "timesheet.py").read_text()


# ── the arithmetic ───────────────────────────────────────────────────

@pytest.mark.parametrize("total,days", [
    ("2080.00", 261), ("978.68", 261), ("25.31", 261), ("5.84", 261),
    ("0.07", 261),             # fewer cents than days
    ("1.00", 3), ("100.00", 7), ("0.01", 1), ("7.77", 52),
])
def test_the_hours_adopted_are_the_hours_the_draft_showed(total, days):
    """A distribution that quietly loses a few hours is what
    `allocation_proof` refuses one level up. The first version dumped the
    residual on the last day, and where the daily rate rounded *up* the
    residual went negative and was skipped: 25.31 hours became 26.00."""
    got = spread_hours(Decimal(total), days)
    assert sum(got) == Decimal(total)
    assert len(got) == days


def test_no_day_is_more_than_a_cent_from_the_mean():
    """Otherwise 31 December carries a spike that means nothing, and a
    reviewer reads a pattern into an artefact of rounding."""
    got = spread_hours(Decimal("978.68"), 261)
    assert max(got) - min(got) <= Decimal("0.01")


def test_a_total_too_small_for_every_day_still_lands_in_full():
    """Seven cents over 261 days. Rounding every day to zero would lose the
    objective from the sheet entirely — a short run of real days is the
    honest answer."""
    got = spread_hours(Decimal("0.07"), 261)
    assert sum(got) == Decimal("0.07")
    assert sum(1 for h in got if h > 0) == 7


def test_no_days_is_an_empty_split_rather_than_a_division_by_zero():
    """An employment span with no working days in the period is a real
    state, and the draft says so rather than failing."""
    assert spread_hours(Decimal("100.00"), 0) == []


def test_the_split_does_not_depend_on_how_often_it_is_asked():
    a = spread_hours(Decimal("171799.06"), 261)
    b = spread_hours(Decimal("171799.06"), 261)
    assert a == b


# ── the rules the route holds ────────────────────────────────────────

def body_of(name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=^@router|\Z)", SOURCE,
                  re.S | re.M)
    assert m, f"no handler {name}"
    return m.group(0)


def test_the_draft_reads_employment_terms_from_the_register_of_terms():
    """`v_timesheet_coverage` is `FROM v_timesheet_entry`, so somebody with
    no entries has no row in it — and that is exactly who the draft is for.
    Reading `expected_hours` from there told a person with terms on the
    record that nobody had recorded any, and no draft could ever become
    adoptable: its precondition was satisfied only by already having the
    entries it exists to create."""
    draft = body_of("draft")
    terms = re.search(r"expected_hours[^\"]*?FROM\s+(\w+)", draft, re.S)
    assert terms and terms.group(1) == "v_employment_expected", (
        "the draft must read expected_hours from v_employment_expected")


def test_nobody_adopts_for_anybody_else():
    """The router's first rule, and this does not bend it: the entries are
    written for the calling actor's own employee key and there is no
    parameter naming somebody else."""
    adopt = body_of("adopt")
    # The signature carries the gate; `... or True` here would be an
    # assertion whose entire content is the thing it prints.
    signature = re.search(r"def adopt\(.*?\) -> dict:", adopt, re.S).group(0)
    assert "require_own_writes" in signature, (
        "adopt must sit behind require_own_writes — an account on a password "
        "somebody else chose cannot write a timesheet")
    assert "key = actor.employee_key" in adopt
    assert not re.search(r"body\.employee_key", adopt), (
        "adopt must not take an employee key from the request")


def test_what_is_adopted_is_recorded_as_recalled():
    """It is not contemporaneous and recording it as though it were is the
    one lie that matters here. `v_certification_status.reconstructed` reads
    from this."""
    assert "'RECALL'" in body_of("adopt")


def test_adopting_has_to_be_acknowledged():
    """An unacknowledged adoption is the controller's reconstruction wearing
    somebody else's name."""
    assert "body.acknowledged" in body_of("adopt")


def test_a_day_holds_twenty_four_hours_and_the_handler_says_so_first():
    """`timesheet_hours_sane` and `timesheet_day_must_fit` are in the schema
    and stand behind this, but a person should not meet a raw trigger
    message. The first version wrote one entry per objective dated the last
    day of the period — 978.68 hours on 31 December — which the schema
    refused outright."""
    adopt = body_of("adopt")
    assert "per_day_total > 24" in adopt, (
        "adopt must check the per-day total before it writes")
    assert "holds 24" in adopt, (
        "and say so in words the person can act on")
