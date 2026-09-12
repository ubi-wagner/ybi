"""Which days somebody was working, and which they were paid not to be.

A timesheet is a record of days, so a reconstruction spread across a year has
to know what a year contains. The first version of the adopt route did not:
it divided the contracted hours by *every weekday in the employed span* and
booked the result to project objectives, which asserts that forty-three people
each worked 1 January, 4 July, Thanksgiving and Christmas, took no holiday, no
vacation and no sick day, and did it for a whole year. On a signed 2 CFR
200.430(i) certification whose own wording is *"including the time I was not
working on any project"*, containing none of it.

Two facts, and the difference between them is the point:

**The public holidays are derivable.** They are rules, not a list — a fixed
date or an nth weekday, with a Saturday observed on the Friday before and a
Sunday on the Monday after. Deriving them means no hand-kept table to fall out
of date, which is the defect this codebase keeps finding. What is *not*
derivable is whether a given employer observes them, so the set is an
assumption the person adopting is shown and can correct, not a fact asserted
on their behalf.

**Personal leave is not derivable at all.** Nobody but the employee knows
which Tuesday in August they were away, and the record does not carry it. So
none is invented: the draft books the public holidays it can defend and says
plainly that vacation and sick days are missing and are the person's to move.
That is the intake rule — *a blank is unanswered, and unanswered is a value* —
applied to a calendar.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.domain.core import money

#: The eleven United States federal holidays, as the rules that generate them.
#: `(month, weekday, nth)` for the floating ones, where weekday is Monday=0;
#: a bare `(month, day)` for the fixed ones.
_FIXED = ((1, 1), (6, 19), (7, 4), (11, 11), (12, 25))
_FLOATING = ((1, 0, 3), (2, 0, 3), (5, 0, -1), (9, 0, 1), (10, 0, 2),
             (11, 3, 4))


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    """The nth `weekday` of a month; `nth = -1` means the last one."""
    if nth < 0:
        last = (date(year, month + 1, 1) - timedelta(days=1) if month < 12
                else date(year, 12, 31))
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    first += timedelta(days=(weekday - first.weekday()) % 7)
    return first + timedelta(weeks=nth - 1)


def _observed(day: date) -> date:
    """A fixed-date holiday on a weekend is taken on the nearest weekday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def public_holidays(year: int) -> list[date]:
    """The observed federal holidays of a year, in order."""
    fixed = {_observed(date(year, m, d)) for m, d in _FIXED}
    floating = {_nth_weekday(year, m, w, n) for m, w, n in _FLOATING}
    return sorted(fixed | floating)


def split_days(start: date, end: date) -> tuple[list[date], list[date]]:
    """The weekdays of a span, split into days worked and public holidays.

    Weekends are neither: a person contracted for a five-day week is not paid
    for Saturday, so it is not leave and it is not work. Only the days they
    were compensated for appear at all.
    """
    worked: list[date] = []
    observed: list[date] = []
    holidays = set()
    for y in range(start.year, end.year + 1):
        holidays |= set(public_holidays(y))
    day = start
    while day <= end:
        if day.weekday() < 5:
            (observed if day in holidays else worked).append(day)
        day += timedelta(days=1)
    return worked, observed


def split_contracted(expected: Decimal, weekly_hours: Decimal,
                     holidays: int) -> tuple[Decimal, Decimal]:
    """Divide compensated hours into project work and paid leave.

    `expected` is `weekly_hours * 52` — what the person was *paid* for, paid
    holidays included. Spending all of it on cost objectives is what said
    forty-three people worked every weekday of the year, so the holidays come
    out first, at the contracted daily rate.

    **Leave is not a deduction.** The total still comes to the contracted
    figure, so coverage is unchanged; and the LEAVE objective is
    `is_final = false`, so `v_timesheet_distribution` leaves it out and no
    share between objectives — and therefore no rate — moves at all. What
    changes is only whether the sheet claims somebody worked on Christmas.
    """
    daily = (weekly_hours / 5) if weekly_hours else Decimal(0)
    leave = money(daily * holidays)
    if leave > expected:        # a span too short to hold them
        leave = expected
    return money(expected - leave), leave
