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
from app.auth import Actor, Role, current_actor
from app.db import one, query, transaction
from app.settings import settings

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
    basis: str
    note: str = ""


class SubmitIn(BaseModel):
    weekly_hours: float = Field(gt=0, le=80, default=40)
    acknowledged: bool = False


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

    valid = {b for b, _, _ in BASES}
    if body.basis not in valid:
        raise HTTPException(422, f"Unknown basis {body.basis!r}.")

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

    weeks = float(row["weeks_in_period"])
    expected = round(weeks * body.weekly_hours, 2)
    entered = float(row["entered_hours"])
    cover = round(entered / expected, 4) if expected else 0

    if cover < MIN_COVERAGE:
        raise HTTPException(
            422,
            f"The sheet holds {entered:,.1f} hours, which is "
            f"{cover:.0%} of the {expected:,.0f} hours a {body.weekly_hours:g}"
            f"-hour week over this period implies. A part-filled sheet cannot "
            f"stand for the whole year — it would say the objectives you have "
            f"reached so far were all of it. Fill in the rest, or record the "
            f"time you were not working as paid leave.")

    with transaction() as cur:
        cur.execute("""INSERT INTO timesheet_submission
                         (period, employee_key, weekly_hours, entered_hours,
                          expected_hours, coverage, submitted_by, submitted_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING
                       RETURNING submission_id""",
                    (period, key, body.weekly_hours, entered, expected, cover,
                     actor.actor_id, actor.display_name))
        got = cur.fetchone()
        if not got:
            raise HTTPException(409, "This timesheet is already submitted.")
        record(actor, "TIME_SUBMIT", "timesheet_submission",
               str(got["submission_id"]),
               after={"period": period, "entered_hours": entered,
                      "expected_hours": expected, "coverage": cover},
               reason=f"{cover:.0%} of a {body.weekly_hours:g}-hour week",
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

    total = sum(float(r["hours"]) for r in dist)
    return {"period": period, "employee_key": key,
            "chargeable_hours": total,
            "leave_hours": float(leave["hours"]) if leave else 0.0,
            "distribution": dist, "variance": variance,
            "effective": effective, "status": status,
            "coverage": cover, "min_coverage": MIN_COVERAGE,
            "submitted": bool(cover and cover["submitted_at"])}
