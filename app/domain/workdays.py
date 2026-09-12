"""Which days of a month somebody could have been working.

**The calendar is theirs.** An earlier version of this module derived United
States federal holidays and took them out of the year, which was wrong twice:
YBI's own workbook carries a `Hours available` sheet — *Work Days* and *Hours
Per Month*, by month — and it counts **261 days and 2,088 hours in 2025**,
every weekday with nothing deducted. Deriving a second organisation's holidays
and applying them here was inventing a fact that was already on file.

So the counts come from `work_month`, loaded from that sheet, and this module
does only the part a table of monthly counts cannot: say *which* dates they
are. `v_work_calendar_check` compares the two and names any month where they
disagree, which is a fact about the organisation rather than a defect.
"""

from __future__ import annotations

from datetime import date, timedelta


def weekdays(start: date, end: date) -> list[date]:
    """The Monday-to-Friday dates of a span, inclusive.

    Weekends are left out rather than given a share: somebody contracted for
    a five-day week is not paid for Saturday, so it is neither work nor
    leave and does not appear at all.
    """
    out, day = [], start
    while day <= end:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def month_span(month_start: date) -> tuple[date, date]:
    """The first and last day of the month `month_start` opens."""
    if month_start.month == 12:
        nxt = date(month_start.year + 1, 1, 1)
    else:
        nxt = date(month_start.year, month_start.month + 1, 1)
    return month_start, nxt - timedelta(days=1)
