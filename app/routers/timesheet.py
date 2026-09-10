"""The employee's own timesheet.

2 CFR 200.430(i) asks for records that reflect the work actually performed,
certified by the person who performed it. The 2025 distribution was rebuilt
by the controller from payroll and hours logs — careful, and still somebody
else's account of what an employee did. This is where an employee keeps their
own.

Nobody enters time for anybody else. Not the controller, not an administrator.
A timesheet somebody else filled in is precisely the thing a certification is
supposed to rule out, so the rule is in the handler and not in a convention.

What the system decides rather than the person: whether an entry is
contemporaneous. That is the distance between the day worked and the day
recorded, and the row carries both.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, Role, current_actor, require_controller
from app.db import one, query, transaction
from app.settings import settings
from app.vocab import EmploymentStatus, TimeBasis

router = APIRouter(prefix="/timesheet", tags=["timesheet"])

#: Bases an entry can rest on, weakest last. The wording is what an employee
#: reads, so it says what the record actually is rather than naming a code.
BASES = [
    ("AS_WORKED", "As I worked, or the same week",
     "Recorded at the time. Only available within a week of the day worked."),
    ("CALENDAR", "From my calendar",
     "Rebuilt from diary entries — meetings, site visits, blocked time."),
    ("PROJECT_RECORD", "From project records",
     "Notes, tickets, commits, minutes, trip reports."),
    ("DELIVERABLE", "From a dated deliverable",
     "A report, drawing or invoice that fixes when the work happened."),
    ("RECALL", "From memory",
     "Honest recollection with nothing behind it. Recorded as unsupported, "
     "which is better than a guess dressed up as a record."),
]

CONTEMPORANEOUS_DAYS = 7


class EntryIn(BaseModel):
    work_date: date
    objective_id: str
    hours: float = Field(gt=0, le=24)
    basis: TimeBasis
    note: str = ""


class SubmitIn(BaseModel):
    weekly_hours: float = Field(gt=0, le=80, default=40)
    acknowledged: bool = False


class EmploymentIn(BaseModel):
    employee_key: str
    status: EmploymentStatus
    weekly_hours: float = Field(gt=0, le=80)
    employed_from: date
    employed_to: date | None = None
    source_document: str = ""
    note: str = ""


class WithdrawIn(BaseModel):
    reason: str


class RemoveIn(BaseModel):
    work_date: date
    objective_id: str
    reason: str = ""


def _employee(actor: Actor, employee_key: str | None) -> str:
    """Whose timesheet this call is about, and whether it may be seen.

    An employee sees their own. A controller or auditor may read anyone's —
    reviewing the record is their job — but writing is handled separately and
    is always the employee's own.
    """
    if employee_key and employee_key != actor.employee_key:
        if actor.role in (Role.CONTROLLER, Role.AUDITOR, Role.ADMIN):
            return employee_key
        raise HTTPException(403, "You may only see your own timesheet.")
    if not actor.employee_key:
        raise HTTPException(
            403, "This account is not linked to an employee, so it has no "
                 "timesheet of its own. Name an employee to look at theirs.")
    return actor.employee_key


def _period_bounds(period: str) -> tuple[date, date]:
    row = one("SELECT start_date, end_date FROM fiscal_period WHERE period = %s",
              (period,))
    if not row:
        raise HTTPException(404, f"No period {period}.")
    return row["start_date"], row["end_date"]


@router.get("/objectives")
def objectives(period: str = None, actor: Actor = Depends(current_actor)) -> dict:
    """What time can be booked to.

    The same cost objectives the ledger is classified into — so an hour and a
    dollar spent on the same work land in the same place — plus paid leave,
    which is compensated activity and has to be recorded even though it is not
    a final cost objective.
    """
    period = period or settings.period
    rows = query("""SELECT objective_id, label, objective_type, is_federal,
                           is_final
                      FROM cost_objective
                     WHERE active AND period = %s
                     ORDER BY is_final DESC, is_federal DESC, objective_id""",
                 (period,))
    return {"period": period, "objectives": rows,
            "bases": [{"basis": b, "label": l, "detail": d} for b, l, d in BASES],
            "contemporaneous_days": CONTEMPORANEOUS_DAYS}


@router.get("/entries")
def entries(period: str = None, employee_key: str = None,
            start: date = None, end: date = None,
            actor: Actor = Depends(current_actor)) -> dict:
    """Entries and day totals for a range — a month, a week, a year."""
    period = period or settings.period
    key = _employee(actor, employee_key)
    p_start, p_end = _period_bounds(period)
    start = start or p_start
    end = end or p_end

    rows = query("""
        SELECT entry_id, work_date, objective_id, objective_label, hours,
               basis::text AS basis, note, lag_days, timing,
               entry_grade::text AS entry_grade, is_final, is_federal,
               entered_at, entered_by_name
          FROM v_timesheet_entry
         WHERE period = %s AND employee_key = %s
           AND work_date BETWEEN %s AND %s
         ORDER BY work_date, objective_id""", (period, key, start, end))

    days = query("""
        SELECT work_date, hours, entries, weakest_grade::text AS weakest_grade
          FROM v_timesheet_day
         WHERE period = %s AND employee_key = %s
           AND work_date BETWEEN %s AND %s
         ORDER BY work_date""", (period, key, start, end))

    return {"period": period, "employee_key": key,
            "start": start, "end": end,
            "entries": rows, "days": days,
            "editable": key == actor.employee_key}


@router.post("/entry")
def put_entry(body: EntryIn, period: str = None,
              actor: Actor = Depends(current_actor)) -> dict:
    """Record time against one day and one objective.

    Correcting an entry supersedes it rather than editing it, the same way a
    classification is superseded. Both stay on the record, so a reviewer can
    see that a figure moved and when.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(
            403, "Only an employee records their own time. This account is "
                 "not linked to one.")
    key = actor.employee_key

    p_start, p_end = _period_bounds(period)
    if not (p_start <= body.work_date <= p_end):
        raise HTTPException(
            422, f"{body.work_date} is outside {period} "
                 f"({p_start} to {p_end}).")
    if body.work_date > date.today():
        raise HTTPException(
            422, "That day has not happened yet. Time is recorded after it is "
                 "worked, not before.")

    lag = (date.today() - body.work_date).days
    if body.basis == "AS_WORKED" and lag > CONTEMPORANEOUS_DAYS:
        raise HTTPException(
            422, f"That day was {lag} days ago, so this is not a record made "
                 f"as the work was done. Say what you are working from "
                 f"instead — a calendar, project records, a deliverable, or "
                 f"memory.")

    if not one("SELECT 1 FROM cost_objective WHERE objective_id = %s AND active",
               (body.objective_id,)):
        raise HTTPException(422, f"No active objective {body.objective_id!r}.")

    with transaction() as cur:
        # Stand the old entry down first. The partial unique index is
        # immediate, so two live entries for one day and objective cannot
        # coexist even for the length of a statement — which is the index
        # doing its job, and why this is three statements rather than one.
        cur.execute("""UPDATE timesheet_entry
                          SET superseded_at = now()
                        WHERE period = %s AND employee_key = %s
                          AND work_date = %s AND objective_id = %s
                          AND superseded_at IS NULL
                        RETURNING entry_id, hours""",
                    (period, key, body.work_date, body.objective_id))
        replaced = cur.fetchall()

        cur.execute("""INSERT INTO timesheet_entry
                         (period, employee_key, work_date, objective_id, hours,
                          basis, note, entered_by, entered_by_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING entry_id""",
                    (period, key, body.work_date, body.objective_id,
                     body.hours, body.basis, body.note.strip(),
                     actor.actor_id, actor.display_name))
        entry_id = cur.fetchone()["entry_id"]

        # Now the superseded rows can name what replaced them.
        if replaced:
            cur.execute("""UPDATE timesheet_entry SET superseded_by = %s
                            WHERE entry_id = ANY(%s)""",
                        (entry_id, [r["entry_id"] for r in replaced]))
        record(actor, "TIME_ENTRY", "timesheet_entry", str(entry_id),
               before={"hours": str(replaced[0]["hours"])} if replaced else None,
               after={"work_date": str(body.work_date),
                      "objective_id": body.objective_id,
                      "hours": body.hours, "basis": body.basis},
               reason=body.note.strip()[:400], cursor=cur)

    day = one("""SELECT hours FROM v_timesheet_day
                  WHERE employee_key = %s AND work_date = %s""",
              (key, body.work_date))
    return {"entry_id": entry_id, "replaced": bool(replaced),
            "day_hours": float(day["hours"]) if day else 0.0}


@router.post("/entry/remove")
def remove_entry(body: RemoveIn, period: str = None,
                 actor: Actor = Depends(current_actor)) -> dict:
    """Take an entry off the timesheet.

    It is superseded, not deleted. A timesheet where hours can vanish without
    trace supports nothing.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(403, "This account has no timesheet of its own.")

    with transaction() as cur:
        # No superseded_by: nothing replaced it, it is simply off the sheet.
        cur.execute("""UPDATE timesheet_entry
                          SET superseded_at = now()
                        WHERE period = %s AND employee_key = %s
                          AND work_date = %s AND objective_id = %s
                          AND superseded_at IS NULL
                        RETURNING entry_id, hours""",
                    (period, actor.employee_key, body.work_date,
                     body.objective_id))
        removed = cur.fetchall()
        if not removed:
            raise HTTPException(404, "Nothing recorded there.")
        record(actor, "TIME_REMOVE", "timesheet_entry",
               str(removed[0]["entry_id"]),
               before={"hours": str(removed[0]["hours"]),
                       "objective_id": body.objective_id,
                       "work_date": str(body.work_date)},
               reason=body.reason.strip()[:400] or "removed by the employee",
               cursor=cur)
    return {"removed": len(removed)}


#: How much of a period a timesheet must cover before its owner can call it
#: finished. Not 100%: a year rebuilt from a calendar will have gaps no honest
#: person can close. Low enough to be reachable, high enough that a fortnight
#: cannot stand in for a year.
MIN_COVERAGE = 0.90


@router.get("/coverage")
def coverage(period: str = None, employee_key: str = None,
             actor: Actor = Depends(current_actor)) -> dict:
    """How much of the period is on the sheet, and what that leaves."""
    period = period or settings.period
    key = _employee(actor, employee_key)
    row = one("""SELECT * FROM v_timesheet_coverage
                  WHERE period = %s AND employee_key = %s""", (period, key))
    return {"period": period, "employee_key": key,
            "coverage": row, "min_coverage": MIN_COVERAGE}


@router.post("/submit")
def submit(body: SubmitIn, period: str = None,
           actor: Actor = Depends(current_actor)) -> dict:
    """Call the timesheet finished for the period.

    Until this happens the sheet is a work in progress and the controller's
    reconstruction still speaks for the employee. That is deliberate: one day
    entered against one award would otherwise claim the whole year and
    redistribute a year of wages on the strength of eight hours.

    What is recorded is not just the fact of submission but the arithmetic
    behind it — the hours claimed per week, the hours on the sheet, and the
    proportion of the period they cover — because that is what an auditor
    would otherwise have to reconstruct.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(403, "This account has no timesheet of its own.")
    key = actor.employee_key
    if not body.acknowledged:
        raise HTTPException(
            422, "Submitting says the sheet is a complete record of the "
                 "period. It has to be acknowledged.")

    row = one("""SELECT * FROM v_timesheet_coverage
                  WHERE period = %s AND employee_key = %s""", (period, key))
    if not row or not row["entered_hours"]:
        raise HTTPException(422, "There is no time on this sheet to submit.")

    entered = float(row["entered_hours"])

    # The denominator is employment terms, not a figure supplied by the person
    # being measured. A full-time year is 2,080 hours and somebody who started
    # in July is owed half of it; asking everyone for a full year makes the
    # part-year employee — whose time is hardest to reconstruct — the one who
    # cannot record it.
    if row["terms_known"]:
        expected = float(row["expected_hours"])
        weekly = float(row["weekly_hours"])
        basis = (f"{row['statuses']}, {weekly:g} hours a week, "
                 f"{row['employed_from']} to {row['employed_to']}")
    else:
        raise HTTPException(
            422,
            "Nobody has recorded your employment terms for this period, so "
            "there is nothing to measure a complete year against. Ask the "
            "controller to record your status, your contracted hours and the "
            "dates you worked, and then submit.")

    cover = round(entered / expected, 4) if expected else 0

    if cover < MIN_COVERAGE:
        raise HTTPException(
            422,
            f"The sheet holds {entered:,.1f} hours against the {expected:,.0f} "
            f"your terms imply ({basis}), which is {cover:.0%}. A part-filled "
            f"sheet cannot stand for the period — it would say the objectives "
            f"you have reached so far were all of it. Fill in the rest, or "
            f"record the time you were not working as paid leave.")

    with transaction() as cur:
        cur.execute("""INSERT INTO timesheet_submission
                         (period, employee_key, weekly_hours, entered_hours,
                          expected_hours, coverage, submitted_by, submitted_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING
                       RETURNING submission_id""",
                    (period, key, weekly, entered, expected, cover,
                     actor.actor_id, actor.display_name))
        got = cur.fetchone()
        if not got:
            raise HTTPException(409, "This timesheet is already submitted.")
        record(actor, "TIME_SUBMIT", "timesheet_submission",
               str(got["submission_id"]),
               after={"period": period, "entered_hours": entered,
                      "expected_hours": expected, "coverage": cover},
               reason=f"{cover:.0%} of {expected:,.0f} hours — {basis}",
               cursor=cur)
    return {"submitted": True, "coverage": cover, "entered_hours": entered,
            "expected_hours": expected}


@router.post("/withdraw")
def withdraw(body: WithdrawIn, period: str = None,
             actor: Actor = Depends(current_actor)) -> dict:
    """Take a submission back, with a reason.

    The submission stays on the record marked withdrawn. The distribution
    falls back to the reconstruction, and any signature given for the
    timesheet becomes stale on its own, because the numbers behind it moved.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(403, "This account has no timesheet of its own.")
    if not body.reason.strip():
        raise HTTPException(422, "Withdrawing a submission needs a reason.")

    with transaction() as cur:
        cur.execute("""UPDATE timesheet_submission
                          SET withdrawn_at = now(), withdrawn_reason = %s
                        WHERE period = %s AND employee_key = %s
                          AND withdrawn_at IS NULL
                        RETURNING submission_id""",
                    (body.reason.strip(), period, actor.employee_key))
        got = cur.fetchall()
        if not got:
            raise HTTPException(404, "Nothing submitted for that period.")
        record(actor, "TIME_WITHDRAW", "timesheet_submission",
               str(got[0]["submission_id"]), reason=body.reason.strip()[:400],
               cursor=cur)
    return {"withdrawn": True}


@router.get("/employment")
def employment(period: str = None, employee_key: str = None,
               actor: Actor = Depends(current_actor)) -> dict:
    """The terms a timesheet is measured against."""
    period = period or settings.period
    key = _employee(actor, employee_key)
    spans = query("""SELECT employment_id, status::text AS status, weekly_hours,
                            employed_from, employed_to, source_document, note,
                            recorded_name, recorded_at
                       FROM employment
                      WHERE period = %s AND employee_key = %s
                        AND superseded_at IS NULL
                      ORDER BY employed_from""", (period, key))
    expected = one("""SELECT * FROM v_employment_expected
                       WHERE period = %s AND employee_key = %s""", (period, key))
    return {"period": period, "employee_key": key, "spans": spans,
            "expected": expected}


@router.put("/employment")
def put_employment(body: EmploymentIn, period: str = None,
                   actor: Actor = Depends(require_controller)) -> dict:
    """Record what somebody was employed to do, and when.

    Payroll's fact, so the controller records it. Deliberately not the
    employee's to set: it is the denominator their own timesheet is tested
    against, and nobody should be able to move the bar they are being measured
    at.

    Terms that changed mid-year are two spans, not an edit. Overlapping spans
    are refused at COMMIT, so closing the old one and opening the new one is a
    single act.
    """
    period = period or settings.period
    p_start, p_end = _period_bounds(period)
    if body.employed_to and body.employed_to < body.employed_from:
        raise HTTPException(422, "The end of the span is before its start.")
    if body.employed_from > p_end or (body.employed_to or p_end) < p_start:
        raise HTTPException(422, f"That span lies outside {period}.")

    r = one("""INSERT INTO employment
                 (period, employee_key, status, weekly_hours, employed_from,
                  employed_to, source_document, note, recorded_by, recorded_name)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING employment_id""",
            (period, body.employee_key.upper(), body.status, body.weekly_hours,
             body.employed_from, body.employed_to, body.source_document.strip(),
             body.note.strip(), actor.actor_id, actor.display_name))
    record(actor, "EMPLOYMENT", "employee", body.employee_key.upper(),
           after={"status": body.status, "weekly_hours": body.weekly_hours,
                  "from": str(body.employed_from),
                  "to": str(body.employed_to) if body.employed_to else None},
           reason=body.source_document.strip()[:400] or "employment terms recorded")
    expected = one("""SELECT expected_hours FROM v_employment_expected
                       WHERE period = %s AND employee_key = %s""",
                   (period, body.employee_key.upper()))
    return {"employment_id": r["employment_id"],
            "expected_hours": expected["expected_hours"] if expected else None}


@router.get("/roster")
def roster(period: str = None,
           actor: Actor = Depends(current_actor)) -> list[dict]:
    """Everyone's timesheet at a glance. The controller's screen.

    Reading is review, which is the controller's job; writing a timesheet
    never is.
    """
    period = period or settings.period
    if actor.role not in (Role.CONTROLLER, Role.AUDITOR, Role.ADMIN):
        raise HTTPException(403, "The roster is for whoever reviews the record.")
    return query("""
        SELECT a.employee_key,
               max(a.employee_name)                       AS employee_name,
               max(a.payroll_wages)                       AS payroll_wages,
               x.expected_hours, x.weekly_hours, x.statuses,
               x.from_date AS employed_from, x.to_date AS employed_to,
               (x.expected_hours IS NOT NULL)             AS terms_known,
               c.entered_hours, c.chargeable_hours, c.leave_hours,
               c.days_with_time, c.coverage, c.submitted_at,
               s.certified, s.stale, s.signed_at, s.from_timesheet
          FROM labor_allocation a
          LEFT JOIN v_employment_expected x
                 ON x.period = a.period AND x.employee_key = a.employee_key
          LEFT JOIN v_timesheet_coverage c
                 ON c.period = a.period AND c.employee_key = a.employee_key
          LEFT JOIN v_certification_status s
                 ON s.period = a.period AND s.employee_key = a.employee_key
         WHERE a.period = %s
         GROUP BY a.employee_key, x.expected_hours, x.weekly_hours, x.statuses,
                  x.from_date, x.to_date, c.entered_hours, c.chargeable_hours,
                  c.leave_hours, c.days_with_time, c.coverage, c.submitted_at,
                  s.certified, s.stale, s.signed_at, s.from_timesheet
         ORDER BY max(a.payroll_wages) DESC""", (period,))


@router.get("/months")
def months(period: str = None, employee_key: str = None,
           actor: Actor = Depends(current_actor)) -> list[dict]:
    """Entered against expected, month by month — where the gap actually is."""
    period = period or settings.period
    key = _employee(actor, employee_key)
    return query("""SELECT month_start, month_label, entered_hours,
                           chargeable_hours, leave_hours, days_with_time,
                           expected_hours, coverage
                      FROM v_timesheet_month
                     WHERE period = %s AND employee_key = %s
                     ORDER BY month_start""", (period, key))


@router.get("/summary")
def summary(period: str = None, employee_key: str = None,
            actor: Actor = Depends(current_actor)) -> dict:
    """What the timesheet adds up to, and how it compares.

    The comparison is the point. Where an employee's own record differs from
    the reconstruction made for them, that difference is a finding for the
    controller — not something for either side to overwrite.
    """
    period = period or settings.period
    key = _employee(actor, employee_key)

    dist = query("""
        SELECT d.objective_id, o.label AS objective_label, o.is_federal,
               d.hours, d.days, d.first_day, d.last_day,
               d.weakest_grade::text AS weakest_grade, d.mean_lag_days
          FROM v_timesheet_distribution d
          JOIN cost_objective o USING (objective_id)
         WHERE d.period = %s AND d.employee_key = %s
         ORDER BY d.hours DESC""", (period, key))

    leave = one("""SELECT COALESCE(sum(hours), 0) AS hours
                     FROM v_timesheet_entry
                    WHERE period = %s AND employee_key = %s
                      AND NOT is_final""", (period, key))

    variance = query("""
        SELECT objective_id, timesheet_hours, timesheet_share,
               reconstructed_share, share_variance, wage_variance
          FROM v_labor_variance
         WHERE period = %s AND employee_key = %s
           AND abs(COALESCE(share_variance, 0)) > 0.005
         ORDER BY abs(COALESCE(wage_variance, 0)) DESC""", (period, key))

    effective = query("""
        SELECT objective_id, source, effective_units, share, distributed_wages,
               evidence_quality::text AS evidence_quality
          FROM v_labor_effective
         WHERE period = %s AND employee_key = %s
         ORDER BY effective_units DESC""", (period, key))

    status = one("""SELECT * FROM v_certification_status
                     WHERE period = %s AND employee_key = %s""", (period, key))

    cover = one("""SELECT * FROM v_timesheet_coverage
                    WHERE period = %s AND employee_key = %s""", (period, key))
    by_month = query("""SELECT month_label, entered_hours, expected_hours,
                               coverage, days_with_time
                          FROM v_timesheet_month
                         WHERE period = %s AND employee_key = %s
                         ORDER BY month_start""", (period, key))

    total = sum(float(r["hours"]) for r in dist)
    return {"period": period, "employee_key": key,
            "chargeable_hours": total,
            "leave_hours": float(leave["hours"]) if leave else 0.0,
            "distribution": dist, "variance": variance,
            "effective": effective, "status": status,
            "coverage": cover, "min_coverage": MIN_COVERAGE,
            "months": by_month,
            "submitted": bool(cover and cover["submitted_at"])}
