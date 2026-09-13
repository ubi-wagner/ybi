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


# ── the calendar is theirs ───────────────────────────────────────────
#
# The first version derived United States federal holidays and took them out
# of the year. YBI's workbook carries a `Hours available` sheet — *Work Days*
# and *Hours Per Month*, by month — and it counts **261 days and 2,088 hours
# in 2025**, every weekday with nothing deducted. Deriving a second
# organisation's holidays and applying them here was inventing a fact that was
# already on file, and it put the draft 88 hours out against the `Allow Hours`
# their own record measures every person against.

from datetime import date

from app.domain.workdays import month_span, weekdays


def test_the_module_no_longer_invents_a_holiday_calendar():
    """A calendar is an organisational fact, not a rule to derive. The
    counts come from `work_month`, loaded from their sheet."""
    import inspect

    import app.domain.workdays as wd
    assert not hasattr(wd, "public_holidays"), (
        "holidays must come from the organisation's calendar, not from here")
    source = inspect.getsource(wd)
    # The rules that generated them, gone from the code rather than left
    # unused: Thanksgiving is a fourth Thursday and Memorial a last Monday,
    # and neither is this repository's fact to assert.
    body = source.split('"""', 2)[-1]
    for rule in ("_FIXED", "_FLOATING", "_nth_weekday", "_observed"):
        assert rule not in body, f"{rule} derives a holiday calendar"


def test_a_month_knows_its_own_first_and_last_day():
    assert month_span(date(2025, 2, 1)) == (date(2025, 2, 1), date(2025, 2, 28))
    assert month_span(date(2025, 12, 1)) == (date(2025, 12, 1), date(2025, 12, 31))


def test_a_weekend_is_neither_worked_nor_leave():
    """Somebody contracted for a five-day week is not paid for Saturday, so
    it is not leave either — it does not appear at all."""
    days = weekdays(date(2025, 1, 1), date(2025, 12, 31))
    assert len(days) == 261
    assert all(d.weekday() < 5 for d in days)


@pytest.mark.parametrize("month,count", [
    (1, 23), (2, 20), (3, 21), (4, 22), (5, 22), (6, 21),
    (7, 23), (8, 21), (9, 22), (10, 23), (11, 20), (12, 23),
])
def test_the_weekday_count_is_what_their_calendar_says(month, count):
    """Their `Work Days` row, month by month. The enumeration here places
    the dates and their sheet says how many there should be; where the two
    ever differ, `v_work_calendar_check` names the month rather than
    correcting it — a shutdown week is a fact about the organisation."""
    assert len(weekdays(*month_span(date(2025, month, 1)))) == count


def test_their_year_is_two_thousand_and_eighty_eight_hours():
    """261 work days at eight hours, which is the figure every `Allow Hours`
    in the hours log is measured against — and eight more than the
    `weekly_hours * 52` the employment terms give."""
    assert len(weekdays(date(2025, 1, 1), date(2025, 12, 31))) * 8 == 2088


def test_the_draft_reads_the_calendar_rather_than_deriving_one():
    draft = body_of("_calendar_months")
    assert "work_month" in draft, (
        "the month counts have to come from the organisation's calendar")


def test_the_draft_places_each_month_in_its_own_month():
    """Where the hours log has a month-by-month record it is placed month by
    month: smearing it over the year throws away the only part of it that is
    a fact."""
    adopt = body_of("adopt")
    assert 'proposed.get("months")' in adopt


def test_the_draft_says_what_their_calendar_does_not_separate():
    """It counts every weekday as available and deducts no holiday, so
    nothing in the draft tells a day off from a day worked. Named rather
    than left to be noticed."""
    draft = body_of("draft")
    assert "not_known" in draft
    assert "vacation" in draft.lower() and "sick" in draft.lower()


# ── it is a convenience, not an instruction ──────────────────────────

SCREEN = (ROOT / "web" / "src" / "pages" / "Timesheet.jsx").read_text()


def test_the_draft_declares_itself_optional():
    """The one way this exercise produces forty-three worthless signatures is
    a convenience that reads as an instruction. 200.430(i) wants the record
    of the person whose effort it was, so the answer has to say out loud that
    adopting is a choice rather than leaving the screen to imply it."""
    draft = body_of("draft")
    assert '"optional": True' in draft, (
        "every draft must declare itself optional — a pre-filled sheet that "
        "reads as the only route takes a signature on somebody else's "
        "account of the year")


def test_the_draft_names_what_somebody_may_do_instead():
    """"Optional" on its own is the dead end this repository keeps finding:
    true, and it does not tell anybody what the alternatives are. Three are
    legitimate — type your own days, adopt and then correct, or leave it —
    and each has to be named."""
    draft = body_of("draft")
    instead = re.search(r'"instead": \[(.*?)\n\s*\],', draft, re.S)
    assert instead, "the draft must name the alternatives in `instead`"
    assert instead.group(1).count('"') >= 6, (
        "one alternative is not a choice; name the routes somebody may take")


def test_the_screen_reads_the_alternatives_from_the_server():
    """A second copy of what the routes allow is one free to drift from them
    — the defect that produced a nav stricter than the API. The card renders
    `instead` rather than keeping its own list."""
    assert "draft.instead" in SCREEN, (
        "the card must render the server's alternatives, not its own")
    assert "draft.optional" in SCREEN


def test_adopting_is_not_certifying():
    """Two acts, two routes, two gates, and on two screens. Adopting puts
    hours on a sheet; signing says the sheet is true. One button doing both
    would take a signature from somebody who had only meant to accept a
    starting point — which is the whole thing 200.430(i) is written
    against."""
    adopt = body_of("adopt")
    # On the write, not on the prose. The first version of this asserted
    # that the word did not appear anywhere in the handler and failed
    # against correct code, because the docstring explains at length why
    # `v_certification_status` reads from the basis it sets. A test that
    # argues with a comment is worse than no test.
    assert "labor_certification" not in adopt, (
        "adopt must not write a certification — signing is "
        "/api/certify/sign, performed separately by the person themselves")
    assert re.search(r"does not certify", SCREEN), (
        "the card must say that adopting does not certify")
