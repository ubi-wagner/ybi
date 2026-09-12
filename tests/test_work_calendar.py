"""The organisation's own working calendar, and the hours log under it.

Migration `071`. The adopt route needed to know which days somebody was
working and derived a United States federal holiday calendar to answer it.
Two sheets of the controller's workbook that nothing had read say otherwise:

  `Hours available` — a *Work Days* row and an *Hours Per Month* row, by
  month. YBI counts **261 days and 2,088 hours in 2025**, every weekday with
  no holiday deducted at all.

  `Hours Log` — 45 people, 144 person-months, hours by objective, with
  `Allow Hours` per month measured against exactly that calendar.

So the calendar was never this repository's to invent, and `labor_allocation`
— the distribution the whole rate model rests on — was built from those hours
with only the finished wage figures loaded.

Own rows, own transaction, rolled back.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2096"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2096-01-01','2096-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                yield cursor


def a_month(cur, month, days, hours):
    cur.execute("""INSERT INTO work_month (period, month_start, work_days,
                                           available_hours)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (period, month_start) DO UPDATE
                     SET work_days = EXCLUDED.work_days,
                         available_hours = EXCLUDED.available_hours""",
                (PERIOD, date(2096, month, 1), days, hours))


def check(cur, month):
    cur.execute("""SELECT says, weekdays, difference, hours_per_day, state
                     FROM v_work_calendar_check
                    WHERE period = %s AND month_start = %s""",
                (PERIOD, date(2096, month, 1)))
    return cur.fetchone()


# ── the calendar against the calendar ────────────────────────────────

def weekday_count(year: int, month: int) -> int:
    """Counted with the standard library, so the control is checked against
    something other than the code that feeds it — and so the number is not
    one somebody wrote from memory. The first draft of this test asserted
    January 2096 had 23 weekdays; it has 22."""
    import calendar
    return sum(1 for _, wd in
               ((d, calendar.weekday(year, month, d))
                for d in range(1, calendar.monthrange(year, month)[1] + 1))
               if wd < 5)


def test_a_month_that_counts_its_weekdays_ties(cur):
    """A transcription nobody checked is a number somebody typed."""
    n = weekday_count(2096, 1)
    a_month(cur, 1, n, str(n * 8) + ".00")
    row = check(cur, 1)
    assert row["weekdays"] == n
    assert row["difference"] == 0 and row["state"] == "TIES"
    assert row["hours_per_day"] == Decimal("8.00")


def test_a_month_that_counts_something_else_is_named_not_corrected(cur):
    """OPEN is not a defect here — a shutdown week, or a holiday YBI does
    deduct, is a fact about the organisation and the whole reason a working
    calendar exists. The control says which month and by how much."""
    short = weekday_count(2096, 1) - 5          # a shutdown week
    a_month(cur, 1, short, str(short * 8) + ".00")
    row = check(cur, 1)
    assert row["state"] == "OPEN"
    assert row["difference"] == -5


def test_hours_and_days_cannot_disagree_about_whether_a_month_exists(cur):
    """A month claiming hours against no days divides by zero the first time
    somebody asks what a day of it holds."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        a_month(cur, 2, 0, "160.00")


def test_a_month_with_no_days_and_no_hours_is_allowed(cur):
    """A period the organisation was closed for is a real state."""
    a_month(cur, 2, 0, "0.00")
    assert check(cur, 2)["says"] == 0


# ── the hours log ────────────────────────────────────────────────────

def an_objective(cur, oid="T-OBJ"):
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES (%s,%s,'Test','PROGRAM',false)
                   ON CONFLICT DO NOTHING""", (oid, PERIOD))
    return oid


def logged(cur, month, hours, adjusted, oid="T-OBJ"):
    an_objective(cur, oid)
    cur.execute("""INSERT INTO labor_month
                     (period, employee_key, month_start, objective_id,
                      logged_hours, adjusted_hours)
                   VALUES (%s,'TESTER',%s,%s,%s,%s)""",
                (PERIOD, date(2096, month, 1), oid, hours, adjusted))


def test_logged_and_adjusted_are_both_kept(cur):
    """The difference between them is the controller's judgment — Gaffney
    logged 2,682 hours against 2,088 available — and collapsing it would
    hide that a judgment was made."""
    a_month(cur, 1, 23, "184.00")
    logged(cur, 1, "220.00", "184.00")
    cur.execute("""SELECT logged_hours, adjusted_hours, available_hours,
                          logged_variance, adjusted_state
                     FROM v_labor_month
                    WHERE period = %s AND employee_key = 'TESTER'""", (PERIOD,))
    row = cur.fetchone()
    assert row["logged_hours"] == Decimal("220.00")
    assert row["adjusted_hours"] == Decimal("184.00")
    assert row["logged_variance"] == Decimal("36.00")
    assert row["adjusted_state"] == "TIES"


def test_a_month_the_calendar_does_not_cover_cannot_be_compared(cur):
    """Three states, not a bare difference: reporting a whole month's hours
    as the variance would be a false alarm every time."""
    logged(cur, 3, "100.00", "100.00")
    cur.execute("""SELECT available_hours, adjusted_state FROM v_labor_month
                    WHERE period = %s AND month_start = %s""",
                (PERIOD, date(2096, 3, 1)))
    row = cur.fetchone()
    assert row["available_hours"] is None
    assert row["adjusted_state"] == "NO CALENDAR"


def test_adjusted_hours_that_miss_the_capacity_are_open(cur):
    a_month(cur, 4, 22, "176.00")
    logged(cur, 4, "176.00", "150.00")
    cur.execute("""SELECT adjusted_state FROM v_labor_month
                    WHERE period = %s AND month_start = %s""",
                (PERIOD, date(2096, 4, 1)))
    assert cur.fetchone()["adjusted_state"] == "OPEN"


def test_a_month_cannot_hold_more_hours_than_a_month_has(cur):
    """The constraint that caught the real defect: thirty-six people carry a
    single summary row labelled December, one of them at 1,739 hours, and
    loading it as December would have said they worked that in one month."""
    import psycopg
    a_month(cur, 5, 22, "176.00")
    with pytest.raises(psycopg.errors.CheckViolation):
        logged(cur, 5, "1739.25", "1739.25")
