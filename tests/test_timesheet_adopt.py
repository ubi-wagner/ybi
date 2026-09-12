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


def test_what_is_adopted_is_not_recorded_as_contemporaneous():
    """It is not contemporaneous and recording it as though it were is the
    one lie that matters here. `v_certification_status.reconstructed` reads
    from this. `ADOPTED` since `070` — see the grade tests below for why it
    is no longer `RECALL`."""
    adopt = body_of("adopt")
    assert "'ADOPTED'" in adopt
    assert "'AS_WORKED'" not in adopt


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


# ── adopting must not make the record worse ──────────────────────────
#
# Migration `070`. `adopt` wrote `basis = 'RECALL'`, which grades
# `UNSUPPORTED` unconditionally — so a person who read the controller's
# reconstruction and signed it took their own distribution from
# `MANAGEMENT_RECONSTRUCTION` down a rung. Same numbers, same provenance,
# plus a signature. Measured on the live record before the fix:
#
#     before adopting   RECONSTRUCTION   MANAGEMENT_RECONSTRUCTION
#     after submitting  TIMESHEET        UNSUPPORTED
#
# Across forty-three people that is every workpaper reading
# `evidence_quality` getting worse for doing the work.

import os

dbonly = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                            reason="needs a database")

PERIOD = "2095"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2095-01-01','2095-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                cursor.execute(
                    """INSERT INTO cost_objective (objective_id, period, label,
                                                   objective_type, is_federal)
                       VALUES ('T-OBJ',%s,'Test','PROGRAM',false)
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                yield cursor


def an_entry(cur, basis, *, work_date="2095-06-03"):
    cur.execute("""SELECT actor_id FROM actor LIMIT 1""")
    row = cur.fetchone()
    if row is None:                       # a bare database has no accounts
        pytest.skip("no actor to enter time as")
    cur.execute("""INSERT INTO timesheet_entry
                     (period, employee_key, work_date, objective_id, hours,
                      basis, entered_by, entered_by_name)
                   VALUES (%s,'TESTER',%s,'T-OBJ',8,%s,%s,'test')
                RETURNING entry_id""",
                (PERIOD, work_date, basis, row["actor_id"]))
    return cur.fetchone()["entry_id"]


def grade_of(cur, entry_id):
    cur.execute("""SELECT entry_grade::text AS g FROM v_timesheet_entry
                    WHERE entry_id = %s""", (entry_id,))
    return cur.fetchone()["g"]


@dbonly
def test_an_adopted_reconstruction_keeps_the_grade_it_came_from(cur):
    """Carried across, not raised. It *is* the reconstruction, which already
    holds that grade on `labor_allocation.evidence_quality`; adopting neither
    adds a document nor takes one away."""
    assert grade_of(cur, an_entry(cur, "ADOPTED")) == "MANAGEMENT_RECONSTRUCTION"


@dbonly
def test_adopting_is_not_graded_as_contemporaneous(cur):
    """The strengthening a signature does belongs on
    `v_certification_status`, not in a column about documentary support.
    `CORROBORATED` would claim a record made at the time."""
    assert grade_of(cur, an_entry(cur, "ADOPTED")) != "CORROBORATED"
    assert grade_of(cur, an_entry(cur, "ADOPTED",
                                  work_date="2095-12-31")) != "CORROBORATED"


@dbonly
def test_recall_still_means_what_it_always_meant(cur):
    """`RECALL` was never wrong — it is exactly right for a day somebody
    types from memory, and it stays UNSUPPORTED. The defect was that the
    enum had no way to say the hours came from the organisation's
    reconstruction, which is `ingest_channel = 'GENERATED'` in `038` for the
    same reason."""
    assert grade_of(cur, an_entry(cur, "RECALL")) == "UNSUPPORTED"


@dbonly
def test_adopting_never_grades_below_the_reconstruction(cur):
    """The property, rather than the two spellings of it: whatever the
    mapping says, an adopted entry must not rank below what
    `labor_allocation` already carries for the same hours."""
    cur.execute("""SELECT enumlabel, enumsortorder FROM pg_enum
                    WHERE enumtypid = 'evidence_grade'::regtype""")
    order = {r["enumlabel"]: r["enumsortorder"] for r in cur.fetchall()}
    adopted = grade_of(cur, an_entry(cur, "ADOPTED"))
    assert order[adopted] >= order["MANAGEMENT_RECONSTRUCTION"], (
        f"adopting graded {adopted}, below the reconstruction it came from")


def test_a_hand_typed_day_may_not_claim_it_was_adopted():
    """It says the hours came from the controller's rebuild and carries that
    grade, so a day somebody types claiming it would take
    MANAGEMENT_RECONSTRUCTION for a figure nobody rebuilt. The picker never
    offers it; the handler is the gate for a request that does not come from
    the picker."""
    entry = body_of("put_entry")
    assert "TimeBasis.ADOPTED" in entry, (
        "POST /timesheet/entry must refuse the adopted basis")


def test_the_basis_picker_does_not_offer_adopted():
    """A person cannot assert that the organisation reconstructed their day
    for them, so it is not on the list they choose from."""
    picker = re.search(r"^BASES\s*=\s*\[(.*?)^\]", SOURCE, re.S | re.M)
    assert picker, "no BASES picker found"
    assert "ADOPTED" not in picker.group(1)


@dbonly
def test_it_holds_on_the_shape_the_real_entries_have(cur):
    """The fixture period above is in the future, so `lag_days` is negative
    and every entry would reach the contemporaneous branch anyway — which
    makes it a stringent test of precedence and a weak test of the real
    case. A 2025 sheet adopted in 2026 has a lag of about 437 days, where
    the fall-through is `UNSUPPORTED`, and that is the shape all
    forty-three people have.
    """
    entry = an_entry(cur, "ADOPTED", work_date="2019-06-03")
    cur.execute("""SELECT lag_days, entry_grade::text AS g
                     FROM v_timesheet_entry WHERE entry_id = %s""", (entry,))
    row = cur.fetchone()
    assert row["lag_days"] > 45, "the point of this test is a long lag"
    assert row["g"] == "MANAGEMENT_RECONSTRUCTION"


# ── contracted hours are not project hours ───────────────────────────
#
# The first version divided `expected_hours` — `weekly_hours * 52`, what the
# person was *compensated* for — across every weekday of the span and booked
# all of it to cost objectives. That asserts forty-three people each worked
# 1 January, 4 July, Thanksgiving and Christmas, took no holiday, no vacation
# and no sick day, and did it for a whole year. On a certification whose own
# wording is "including the time I was not working on any project", and which
# contained none of it.

from datetime import date

from app.domain.workdays import (public_holidays, split_contracted,
                                 split_days)


def test_the_holidays_are_derived_rather_than_listed():
    """Rules, not a table: a fixed date or an nth weekday. A hand-kept list
    is the shape this codebase keeps finding wrong, and it would need
    editing every December."""
    h = public_holidays(2025)
    assert len(h) == 11
    assert date(2025, 12, 25) in h                 # Christmas, a Thursday
    assert date(2025, 11, 27) in h                 # Thanksgiving, 4th Thursday
    assert date(2025, 5, 26) in h                  # Memorial, last Monday
    assert date(2025, 1, 20) in h                  # MLK, 3rd Monday


@pytest.mark.parametrize("year,actual,observed", [
    (2026, date(2026, 7, 4), date(2026, 7, 3)),    # Saturday -> Friday before
    (2027, date(2027, 7, 4), date(2027, 7, 5)),    # Sunday   -> Monday after
])
def test_a_fixed_holiday_on_a_weekend_is_taken_on_a_weekday(year, actual, observed):
    """2025 happens to put all eleven on weekdays, so the rule is not
    exercised by the year in front of us — which is exactly when a rule
    rots."""
    h = public_holidays(year)
    assert observed in h and actual not in h
    assert observed.weekday() < 5


def test_a_weekend_is_neither_worked_nor_leave():
    """A person contracted for a five-day week is not paid for Saturday, so
    it is not leave either — it does not appear at all."""
    worked, holidays = split_days(date(2025, 1, 1), date(2025, 12, 31))
    assert len(worked) == 250 and len(holidays) == 11
    assert len(worked) + len(holidays) == 261      # the weekdays of 2025
    assert all(d.weekday() < 5 for d in worked + holidays)


def test_no_project_work_is_booked_on_a_public_holiday():
    """The one that makes a reconstruction unbelievable on sight."""
    worked, holidays = split_days(date(2025, 1, 1), date(2025, 12, 31))
    assert date(2025, 12, 25) not in worked
    assert date(2025, 7, 4) not in worked
    assert date(2025, 12, 25) in holidays
    # Christmas Eve is not a federal holiday and stays a working day, which
    # is the other half: the calendar must not invent days off either.
    assert date(2025, 12, 24) in worked


@pytest.mark.parametrize("contracted,weekly,holidays", [
    ("2080.00", "40", 11),      # the full-year, full-time case
    ("1040.00", "20", 11),      # half time — the leave halves with the day
    ("173.33", "40", 11),       # a month-long span: leave cannot exceed it
    ("2080.00", "40", 0),       # a span with no holiday in it
    ("0.00", "40", 11),         # no contracted hours at all
])
def test_the_split_always_adds_to_what_the_person_was_paid_for(
        contracted, weekly, holidays):
    """Leave is not a deduction. The person was compensated for the whole
    contracted figure; the draft says how much of it was project work and
    how much was a paid day off, and the two come back to the total.

    This calls the code rather than restating its arithmetic — the first
    version recomputed the split in the test and so passed happily with the
    handler spending the leave on projects as well.
    """
    expected = Decimal(contracted)
    work, leave = split_contracted(expected, Decimal(weekly), holidays)
    assert work + leave == expected
    assert work >= 0 and leave >= 0


def test_the_full_year_case_is_the_one_on_the_record():
    work, leave = split_contracted(Decimal("2080.00"), Decimal("40"), 11)
    assert leave == Decimal("88.00")        # 11 days at the contracted 8.00
    assert work == Decimal("1992.00")


def test_a_span_too_short_to_hold_its_holidays_is_all_leave():
    """Rather than a negative number of project hours, which the spreader
    would then quietly drop."""
    work, leave = split_contracted(Decimal("16.00"), Decimal("40"), 11)
    assert work == Decimal("0.00") and leave == Decimal("16.00")


def test_the_draft_hands_leave_to_the_objective_that_exists_for_it():
    """`cost_objective` has carried a LEAVE row since `017` — *paid leave:
    holiday, PTO, sick* — and nothing had ever written it. It is
    `is_final = false`, so `v_timesheet_distribution` leaves it out and it
    can move no share and no rate; what it changes is whether the sheet
    claims somebody worked on Christmas."""
    adopt = body_of("adopt")
    assert '"LEAVE"' in adopt, "the holidays have to be booked somewhere"


def test_the_draft_says_what_it_cannot_know():
    """Public holidays are defensible; which Tuesday in August somebody was
    away is on no record here. None is invented and the gap is named — the
    intake rule applied to a calendar."""
    draft = body_of("draft")
    assert "not_known" in draft
    assert "sick" in draft.lower() and "vacation" in draft.lower()
