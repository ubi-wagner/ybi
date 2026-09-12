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
from decimal import ROUND_DOWN, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import (Actor, Role, current_actor, require_controller,
                      require_own_writes)
from app.db import one, query, transaction
from app.settings import settings
from app.domain.core import money
from app.domain.workdays import month_span, weekdays
from app.statelock import turn
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
    donated: bool = False
    #: Supplied on a second attempt, after the first came back with the soft
    #: limits it would breach. Nobody is stopped from working a long day; they
    #: are asked to say why, once.
    override_reason: str = ""


class SubmitIn(BaseModel):
    weekly_hours: float = Field(gt=0, le=80, default=40)
    acknowledged: bool = False
    #: Supplied on a second attempt when the sheet covers less of the period
    #: than the policy asks for. A short year, records genuinely lost, a person
    #: who left in August — all real, and none of them a reason to refuse the
    #: submission outright.
    below_coverage_reason: str = ""


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
        if actor.can_read:
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
              actor: Actor = Depends(require_own_writes)) -> dict:
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

    # **`ADOPTED` is not a basis anybody chooses.** It says the hours came
    # from the controller's reconstruction and the person affirmed them, and
    # it carries that reconstruction's grade — so a hand-typed day claiming
    # it would take `MANAGEMENT_RECONSTRUCTION` for a figure nobody rebuilt.
    # The picker never offers it; this is the gate for a request that does
    # not come from the picker.
    if body.basis == TimeBasis.ADOPTED:
        raise HTTPException(
            422, "ADOPTED is written only by adopting the reconstruction on "
                 "your draft — it says those hours came from the controller's "
                 "rebuild of the year. For a day you are entering yourself, "
                 "say what it actually rests on: your calendar, a project "
                 "record, a dated deliverable, or memory.")

    p_start, p_end = _period_bounds(period)
    if not (p_start <= body.work_date <= p_end):
        raise HTTPException(
            422, f"{body.work_date} is outside {period} "
                 f"({p_start} to {p_end}).")
    if body.work_date > date.today():
        raise HTTPException(
            422, "That day has not happened yet. Time is recorded after it is "
                 "worked, not before.")

    # Is this person allowed to charge this code?
    #
    # Enforced only where the code has somebody on it. A code nobody has been
    # assigned to predates the mechanism — which for the whole of 2025 is all
    # of them, because the year was worked before any of this existed — and
    # refusing those would make reconstructing the year impossible. A code
    # with an assignment list is a code being managed, and charging outside
    # the list is then a real answer to a question somebody asked.
    #
    # v_charge_authorised is the single place the question is answered. The
    # screen asks it to decide what to offer and this asks it to decide what
    # to accept; neither gets its own opinion about who may charge what.
    managed = one("""SELECT count(*) AS n FROM charge_authority
                      WHERE period = %s AND objective_id = %s
                        AND revoked_at IS NULL""",
                  (period, body.objective_id))["n"]
    if managed:
        allowed = one("""SELECT opens_on, closes_on FROM v_charge_authorised
                          WHERE period = %s AND objective_id = %s
                            AND employee_key = %s""",
                      (period, body.objective_id, key))
        if not allowed:
            raise HTTPException(
                403, f"You are not authorised to charge {body.objective_id}. "
                     f"{managed} person(s) are. Ask the project manager or "
                     f"the controller to assign you before booking time to "
                     f"it.")
        opens, closes = allowed["opens_on"], allowed["closes_on"]
        if opens and body.work_date < opens:
            raise HTTPException(
                422, f"Your assignment to {body.objective_id} starts on "
                     f"{opens}. {body.work_date} is before it.")
        if closes and body.work_date > closes:
            raise HTTPException(
                422, f"Your assignment to {body.objective_id} ended on "
                     f"{closes}. {body.work_date} is after it.")

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

    # ── the soft limits ─────────────────────────────────────────────
    #
    # Paid hours only, and not applied to donated ones at all. The guardrail
    # exists to catch a mistyped paid day; a volunteer Saturday on top of a
    # full week is not a mistake, and asking somebody to justify every hour
    # they gave away is how a guardrail becomes noise that gets clicked past.
    day_total = one("""SELECT COALESCE(sum(hours), 0) AS h FROM timesheet_entry
                        WHERE employee_key=%s AND work_date=%s
                          AND superseded_at IS NULL AND NOT donated
                          AND objective_id <> %s""",
                    (key, body.work_date, body.objective_id))["h"]
    week_start = body.work_date - timedelta(days=body.work_date.weekday())
    week_total = one("""SELECT COALESCE(sum(hours), 0) AS h FROM timesheet_entry
                         WHERE employee_key=%s AND superseded_at IS NULL
                           AND NOT donated
                           AND work_date BETWEEN %s AND %s
                           AND NOT (work_date = %s AND objective_id = %s)""",
                     (key, week_start, week_start + timedelta(days=6),
                      body.work_date, body.objective_id))["h"]

    breaches = []
    new_day = float(day_total) + body.hours
    new_week = float(week_total) + body.hours
    if body.donated:
        breaches = []          # see the note above
    elif new_day > DAY_SOFT_LIMIT:
        breaches.append({
            "limit": "DAY_OVER_8", "would_be": round(new_day, 2),
            "message": f"That makes {new_day:g} hours on "
                       f"{body.work_date:%A %-d %B} — more than a normal "
                       f"{DAY_SOFT_LIMIT}-hour day."})
    if not body.donated and new_week > WEEK_SOFT_LIMIT:
        breaches.append({
            "limit": "WEEK_OVER_40", "would_be": round(new_week, 2),
            "message": f"That makes {new_week:g} hours in the week of "
                       f"{week_start:%-d %B} — more than a normal "
                       f"{WEEK_SOFT_LIMIT}-hour week."})

    if breaches and not body.override_reason.strip():
        raise HTTPException(409, {
            "error": "OVER_SOFT_LIMIT",
            "message": "This is allowed, but say why so it does not look "
                       "like a slip later.",
            "breaches": breaches})

    overrode = [b["limit"] for b in breaches]

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
                          basis, note, entered_by, entered_by_name,
                          donated, overrode, override_reason)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING entry_id""",
                    (period, key, body.work_date, body.objective_id,
                     body.hours, body.basis, body.note.strip(),
                     actor.actor_id, actor.display_name, body.donated,
                     overrode, body.override_reason.strip() or None))
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
                      "hours": body.hours, "basis": str(body.basis),
                      "donated": body.donated, "overrode": overrode},
               reason=body.note.strip()[:400], cursor=cur)

    day = one("""SELECT hours FROM v_timesheet_day
                  WHERE employee_key = %s AND work_date = %s""",
              (key, body.work_date))
    return {"entry_id": entry_id, "replaced": bool(replaced),
            "day_hours": float(day["hours"]) if day else 0.0}


@router.post("/entry/remove")
def remove_entry(body: RemoveIn, period: str = None,
                 actor: Actor = Depends(require_own_writes)) -> dict:
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


#: Soft limits. A day over eight hours or a week over forty is usually a slip
#: and occasionally a real week, so it is a question rather than a refusal —
#: and the answer stays on the record, because "why is there a fourteen-hour
#: day in March" is exactly what a reviewer asks two years later.
DAY_SOFT_LIMIT = 8
WEEK_SOFT_LIMIT = 40


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


class AdoptIn(BaseModel):
    #: Which objectives of the draft the person is adopting. Empty means all
    #: of them — the ordinary case, and still an explicit act.
    objective_ids: list[str] = []
    acknowledged: bool = False
    note: str = ""


def spread_hours(total: Decimal, days: int) -> list[Decimal]:
    """Split `total` hours across `days`, exactly, by largest remainder.

    **Rounding to the nearest cent is what gets this wrong**, and it did:
    rounding rounds up as often as down, and where it rounds up the residual
    goes negative. MBAC's 25.31 hours over 261 days is 0.09697 a day, which
    became 0.10 and adopted 26.00 — more than the draft showed, with the
    negative last day silently dropped by a `<= 0` guard. The sheet said one
    figure and the record held another.

    So: floor every day to the cent, which can only ever be short, and hand
    the spare cents out one at a time. The total is exact by construction and
    no day is more than a cent from the mean, which also keeps the last
    working day from carrying a visible spike that means nothing.

    A total too small to give every day a cent still lands in full, on as
    many days as there are cents — better a short run of real days than a
    year of zeroes that loses the objective entirely.
    """
    if days <= 0:
        return []
    daily = (total / days).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    spare = int(((total - daily * days) * 100).to_integral_value())
    return [daily + (Decimal("0.01") if i < spare else Decimal(0))
            for i in range(days)]


def _calendar_months(period: str, employee_key: str) -> list[dict]:
    """Each month of the employed span, with its dates and what YBI says it
    holds.

    **The counts are theirs.** `work_month` is transcribed from the
    `Hours available` sheet of the controller's workbook — *Work Days* and
    *Hours Per Month* — which for 2025 is 261 days and 2,088 hours, every
    weekday with no holiday deducted. This used to derive federal holidays
    and take them out, which imposed another organisation's calendar on this
    one and made the draft disagree with the `Allow Hours` the record itself
    measures every person against.

    The dates are enumerated here because a table of monthly counts cannot
    say *which* days they are; `v_work_calendar_check` holds the two against
    each other and names any month where they differ.
    """
    p_start, p_end = _period_bounds(period)
    terms = one("""SELECT from_date, to_date, weekly_hours
                     FROM v_employment_expected
                    WHERE period = %s AND employee_key = %s""",
                (period, employee_key))
    start = max(terms["from_date"], p_start) if terms else p_start
    end = min(terms["to_date"] or p_end, p_end) if terms else p_end
    # A week of the organisation's own calendar, so a part-time person's
    # capacity is a fraction of the month rather than a guess at one.
    scale = Decimal(1)
    if terms and terms["weekly_hours"]:
        scale = Decimal(str(terms["weekly_hours"])) / 40

    out = []
    for row in query("""SELECT month_start, work_days, available_hours
                          FROM work_month WHERE period = %s
                         ORDER BY month_start""", (period,)):
        m_start, m_end = month_span(row["month_start"])
        days = [d for d in weekdays(max(m_start, start), min(m_end, end))]
        if not days:
            continue
        whole = weekdays(m_start, m_end)
        # Employed for part of a month: the share of its days they were here.
        part = (Decimal(len(days)) / len(whole)) if whole else Decimal(0)
        out.append({
            "month_start": row["month_start"],
            "days": days,
            "work_days": row["work_days"],
            "available": money(Decimal(str(row["available_hours"]))
                               * scale * part)})
    return out


@router.get("/draft")
def draft(period: str = None,
          actor: Actor = Depends(current_actor)) -> dict:
    """What the controller's reconstruction says your year was.

    **Nothing here is on your timesheet.** It is a proposal, in the same
    sense every other proposal in this system is one: the controller rebuilt
    the 2025 distribution from payroll and hours logs, that reconstruction is
    already on the record as *their* account of the work, and this is it
    shown to the person whose work it was.

    Why a draft at all. Forty-three people cannot reconstruct a year from
    memory, and the honest alternative to showing them the reconstruction is
    not a better record — it is no record, which is where 2025 has been
    sitting. 200.430(i) does not require a contemporaneous record; it
    requires one that reflects the work actually performed, supported, and
    reviewed after the fact. A reconstruction the person reads, corrects and
    signs meets that. A reconstruction nobody ever saw does not.

    Why it is hours and not dollars. `labor_allocation` distributes *wages*,
    so the draft turns each objective's share of the person's wages into the
    same share of their contracted hours. That needs employment terms, and
    where those are missing this answers with what is missing rather than
    with a guess — a year of hours invented against an unknown denominator
    is the thing the coverage check exists to refuse.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(
            403, "Only an employee has a timesheet. This account is not "
                 "linked to one.")
    key = actor.employee_key
    p_start, p_end = _period_bounds(period)

    # **The terms come from the register of terms, not from the coverage
    # view.** `v_timesheet_coverage` is `FROM v_timesheet_entry`, so somebody
    # with no entries has no row in it at all — and that is exactly who this
    # screen is for. Reading `expected_hours` from there made the draft
    # answer "nobody has recorded your employment terms" to a person whose
    # terms were on the record, and no draft could ever become adoptable:
    # its precondition was satisfied only by already having the entries it
    # exists to create. `entered_hours` genuinely is a coverage question and
    # is honestly zero when the view has nothing to say.
    terms = one("""SELECT expected_hours, employed_days, weekly_hours
                     FROM v_employment_expected
                    WHERE period = %s AND employee_key = %s""", (period, key))
    expected = Decimal(str(terms["expected_hours"] or 0)) if terms else Decimal(0)
    cover = one("""SELECT entered_hours FROM v_timesheet_coverage
                    WHERE period = %s AND employee_key = %s""", (period, key))

    rows = query("""SELECT objective_id,
                           COALESCE(reconstructed_units, original_units) AS units,
                           evidence_quality::text AS grade, rationale,
                           source_label
                      FROM labor_allocation
                     WHERE period = %s AND employee_key = %s
                     ORDER BY COALESCE(reconstructed_units, original_units) DESC""",
                 (period, key))
    total = sum(Decimal(str(r["units"] or 0)) for r in rows)

    if not rows:
        return {"period": period, "employee_key": key, "lines": [],
                "expected_hours": str(expected), "adoptable": False,
                "because": "The controller's reconstruction has no line for "
                           "you in this period, so there is nothing to "
                           "propose. Record your time directly."}
    if expected <= 0:
        return {"period": period, "employee_key": key, "lines": [],
                "expected_hours": "0", "adoptable": False,
                "because": "Nobody has recorded your employment terms for "
                           "this period, so there are no contracted hours to "
                           "divide. Until then a draft would be a year of "
                           "hours against an unknown denominator. Ask the "
                           "administrator to record your status, your "
                           "contracted hours and the dates you worked."}

    months = _calendar_months(period, key)
    if not months:
        return {"period": period, "employee_key": key, "lines": [],
                "expected_hours": str(expected), "adoptable": False,
                "because": "The organisation's working calendar has no month "
                           "covering your employment span, so there is "
                           "nothing to place these hours in. Load it from "
                           "the `Hours available` sheet of the grant "
                           "reconciliation workbook."}

    available = money(sum(m["available"] for m in months))
    all_days = [d for m in months for d in m["days"]]

    # **The hours log, where the person has one.** `labor_month` is the
    # controller's `Hours Log` sheet at the grain it is kept — a person, a
    # month, an objective — and `labor_allocation`'s wage distribution is a
    # linear function of it (correlation 1.000000 on all eight full-year
    # people). Nine of forty-five have a month-by-month record; the other
    # thirty-six carry one summary row, so for them the year is all there is
    # and the draft says so rather than inventing twelve months.
    logged = query("""SELECT month_start, objective_id,
                             sum(adjusted_hours) AS hours
                        FROM labor_month
                       WHERE period = %s AND employee_key = %s
                       GROUP BY month_start, objective_id
                       HAVING sum(adjusted_hours) > 0
                       ORDER BY month_start, sum(adjusted_hours) DESC""",
                   (period, key))
    by_month: dict = {}
    for r in logged:
        by_month.setdefault(r["month_start"], []).append(r)

    lines, monthly = [], []
    if by_month:
        totals: dict[str, Decimal] = {}
        for m in months:
            rows_m = by_month.get(m["month_start"], [])
            hours_m = money(sum(Decimal(str(r["hours"])) for r in rows_m))
            for r in rows_m:
                totals[r["objective_id"]] = money(
                    totals.get(r["objective_id"], Decimal(0))
                    + Decimal(str(r["hours"])))
            monthly.append({
                "month": m["month_start"].strftime("%B"),
                "month_start": str(m["month_start"]),
                "days": len(m["days"]),
                "available": str(m["available"]),
                "hours": str(hours_m),
                "lines": [{"objective_id": r["objective_id"],
                           "hours": str(Decimal(str(r["hours"])))}
                          for r in rows_m]})
        drawn = money(sum(totals.values()))
        for oid, h in sorted(totals.items(), key=lambda kv: -kv[1]):
            src = next((r for r in rows if r["objective_id"] == oid), None)
            lines.append({
                "objective_id": oid,
                "share": str((h / drawn).quantize(Decimal("0.0001"))
                             if drawn else Decimal(0)),
                "hours": str(h),
                "grade": src["grade"] if src else "MANAGEMENT_RECONSTRUCTION",
                "rationale": (src["rationale"] if src else
                              "From the hours log for this period."),
                "source": src["source_label"] if src else "Hours Log"})
        work_hours = drawn
    else:
        # No monthly record: the year's distribution, over the hours their
        # own calendar says the span holds.
        for r in rows:
            units = Decimal(str(r["units"] or 0))
            share = (units / total) if total else Decimal(0)
            lines.append({
                "objective_id": r["objective_id"],
                "share": str(share.quantize(Decimal("0.0001"))),
                "hours": str((available * share).quantize(Decimal("0.01"))),
                "grade": r["grade"],
                "rationale": r["rationale"],
                "source": r["source_label"]})
        work_hours = money(sum(Decimal(l["hours"]) for l in lines))

    return {"period": period, "employee_key": key, "lines": lines,
            "expected_hours": str(expected),
            "available_hours": str(available),
            "work_hours": str(work_hours),
            "months": monthly,
            "from_hours_log": bool(by_month),
            "working_days": len(all_days),
            "hours_per_day": str((work_hours / len(all_days)).quantize(
                Decimal("0.01")) if all_days else Decimal(0)),
            "already_entered": str(cover["entered_hours"] or 0) if cover else "0",
            "adoptable": True,
            "because": ("This is your own hours log, month by month, as the "
                        "controller keeps it — not a figure spread evenly "
                        "over the year. Adopting records it under your name; "
                        "correct anything that is wrong first, because what "
                        "you adopt is what you will be certifying."
                        if by_month else
                        "This is the controller's reconstruction, not your "
                        "timesheet. There is no month-by-month record of "
                        "your hours, so it is the year's distribution spread "
                        "evenly. Adopting records it under your name — "
                        "correct anything that is wrong first, because what "
                        "you adopt is what you will be certifying."),
            #: Their calendar counts every weekday as available and deducts
            #: no holiday, so nothing here separates a day off from a day
            #: worked. Said out loud rather than left to be noticed.
            "not_known": ("YBI's calendar counts every weekday as available "
                          f"— {len(all_days)} of them here, and no holiday "
                          "taken out — so nothing in this draft separates a "
                          "day you were off from a day you worked. Move any "
                          "holiday, vacation or sick day to Paid leave "
                          "before you submit.")}


@router.post("/adopt")
def adopt(body: AdoptIn, period: str = None,
          actor: Actor = Depends(require_own_writes)) -> dict:
    """Adopt the reconstruction as your own record.

    The one act that turns somebody else's account of your year into yours.
    It is **yours to perform and nobody else's** — the router's first rule is
    that nobody enters time for anybody else, and this does not bend it: the
    entries are written under the calling actor, for the calling actor's own
    employee key, and there is no parameter naming somebody else.

    `basis = ADOPTED`, always. It is not contemporaneous and recording it as
    though it were would be the one lie that matters here; `AS_WORKED` is
    refused by the schema more than seven days after the fact anyway, and
    `v_certification_status.reconstructed` reads from this.

    It was `RECALL` and that made the record **worse for being certified**:
    RECALL grades `UNSUPPORTED`, so a person who read the reconstruction and
    signed it took their own distribution from
    `MANAGEMENT_RECONSTRUCTION` down a rung — same numbers, same provenance,
    plus a signature. `ADOPTED` (migration `070`) carries the
    reconstruction's grade across instead. RECALL still means what it always
    meant for a day somebody types from memory.

    **One entry per objective per working day, and the schema decided that,
    not this handler.** The first version wrote one entry per objective dated
    the last day of the period, reasoning that spreading a reconstruction
    across the calendar manufactures a daily record nobody has. The concern
    is real and the table had already answered it: `timesheet_hours_sane`
    caps a row at 24 hours and `timesheet_day_must_fit` caps a person-day at
    24 across rows, so the unit of `timesheet_entry` **is** a day. 978.68
    hours on 31 December is not a coarser record, it is a refused one — read
    the schema, never recall it.

    So the year is spread uniformly across the weekdays of the employed span.
    Uniform is the honest shape: it is visibly the same split every day,
    which together with RECALL on every row tells a reviewer at a glance that
    this is a reconstruction. Varying it to look contemporaneous is what
    would manufacture precision.

    The rounding residual lands on the last working day rather than being
    dropped, so the hours adopted are the hours the draft showed. A
    distribution that quietly loses a few hours per objective is the thing
    `allocation_proof` exists to refuse one level up.
    """
    period = period or settings.period
    if not actor.employee_key:
        raise HTTPException(
            403, "Only an employee records their own time. This account is "
                 "not linked to one.")
    if not body.acknowledged:
        raise HTTPException(
            422, "Adopting says this is a true record of your own work. It "
                 "has to be acknowledged — that is the whole point of the "
                 "act, and an unacknowledged adoption would be the "
                 "controller's reconstruction wearing your name.")
    key = actor.employee_key
    p_start, p_end = _period_bounds(period)

    proposed = draft(period=period, actor=actor)
    if not proposed["adoptable"]:
        raise HTTPException(409, proposed["because"])
    wanted = set(body.objective_ids) or {l["objective_id"]
                                         for l in proposed["lines"]}
    unknown = wanted - {l["objective_id"] for l in proposed["lines"]}
    if unknown:
        raise HTTPException(
            422, f"The draft has no line for {', '.join(sorted(unknown))}. "
                 f"Adopting can only accept what was proposed; record "
                 f"anything else as an entry of your own.")

    months = _calendar_months(period, key)
    all_days = [d for m in months for d in m["days"]]
    # A day holds 24 hours and the trigger says so. Refuse in words here
    # rather than let the person meet `RUBY has 31.50 hours on 2025-03-04`.
    per_day_total = (sum(Decimal(l["hours"]) for l in proposed["lines"]
                         if l["objective_id"] in wanted) / len(all_days)
                     if all_days else Decimal(0))
    if per_day_total > 24:
        raise HTTPException(
            409, f"Adopting this would book {per_day_total.quantize(Decimal('0.01'))} "
                 f"hours a day across {len(all_days)} working days, and a day "
                 f"holds 24. The hours and the employed span disagree — ask "
                 f"the administrator to check your terms.")

    # **Each month's hours in that month.** Where the hours log has a
    # month-by-month record it is placed month by month, because that is the
    # grain the record is kept at and smearing it over the year would throw
    # away the only part of it that is a fact. Where there is no monthly
    # record the year is spread evenly, and the draft says which it is.
    plan: list[tuple] = []
    if proposed.get("months"):
        for m in proposed["months"]:
            days_m = next((c["days"] for c in months
                           if str(c["month_start"]) == m["month_start"]), [])
            if not days_m:
                continue
            for ln in m["lines"]:
                if ln["objective_id"] not in wanted:
                    continue
                plan.append((ln["objective_id"], Decimal(ln["hours"]),
                             days_m, m["month"]))
    else:
        for line in proposed["lines"]:
            if line["objective_id"] not in wanted:
                continue
            plan.append((line["objective_id"], Decimal(line["hours"]),
                         all_days, "the year"))

    grade = {l["objective_id"]: l for l in proposed["lines"]}
    written, hours = 0, Decimal(0)
    with turn(period) as cur:
        for objective, total_h, days_m, when in plan:
            if total_h <= 0 or not days_m:
                continue
            src = grade.get(objective, {})
            note = (f"Adopted from the controller's hours log for {when} "
                    f"({total_h} hours over {len(days_m)} working days; "
                    f"{src.get('grade', 'MANAGEMENT_RECONSTRUCTION')}). "
                    f"{src.get('rationale', '')}"
                    + (f" {body.note.strip()}" if body.note.strip() else ""))[:900]
            for d, h in zip(days_m, spread_hours(total_h, len(days_m))):
                if h <= 0:
                    continue
                cur.execute(
                    """INSERT INTO timesheet_entry
                         (period, employee_key, work_date, objective_id, hours,
                          basis, note, entered_by, entered_by_name)
                       VALUES (%s,%s,%s,%s,%s,'ADOPTED',%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (period, key, d, objective, h,
                     note, actor.actor_id, actor.display_name))
                written += 1
                hours = hours + h

        record(actor, "TIMESHEET_ADOPT", "timesheet_entry", key,
               after={"period": period, "entries": written,
                      "hours": str(hours), "working_days": len(all_days),
                      "months": len(proposed.get("months") or []),
                      "objectives": sorted(wanted)},
               reason=(body.note.strip()
                       or "Adopted the controller's reconstruction as my own "
                          "record of the period."),
               cursor=cur)
    if not written:
        raise HTTPException(
            409, "Nothing was adopted: every line of the draft came to zero "
                 "hours. Nothing has been recorded.")
    return {"period": period, "employee_key": key, "entries": written,
            "hours": str(hours), "working_days": len(all_days),
            "months": len(proposed.get("months") or []),
            "from_hours_log": bool(proposed.get("from_hours_log")),
            "next": "Submit the sheet, then sign the certification. What you "
                    "sign is what is on the sheet now, so change anything "
                    "that is wrong before you do."}


@router.post("/submit")
def submit(body: SubmitIn, period: str = None,
           actor: Actor = Depends(require_own_writes)) -> dict:
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

    short = cover < MIN_COVERAGE
    if short and not body.below_coverage_reason.strip():
        # Refusing outright was the first design, and it was wrong. Somebody
        # on medical leave, somebody who left in August, somebody whose 2025
        # calendar is genuinely gone — none of them could submit honestly, so
        # the only way past was to invent hours until the number went green.
        # A gate that cannot be passed honestly gets passed dishonestly.
        raise HTTPException(409, {
            "error": "SHORT_COVERAGE",
            "message":
                f"The sheet holds {entered:,.1f} hours against the "
                f"{expected:,.0f} your terms imply ({basis}), which is "
                f"{cover:.0%}. That is below the {MIN_COVERAGE:.0%} a complete "
                f"period normally reaches. If the rest is genuinely missing — "
                f"a short year, records you no longer have — say so and submit "
                f"it. Do not pad the sheet to reach a number.",
            "coverage": float(cover), "minimum": MIN_COVERAGE,
            "entered_hours": entered, "expected_hours": expected})
    if short and len(body.below_coverage_reason.strip()) <= 20:
        raise HTTPException(
            422, "That reason is too short to stand as the evidence for a "
                 "gap in a year's record. Say what is missing and why.")

    with transaction() as cur:
        cur.execute("""INSERT INTO timesheet_submission
                         (period, employee_key, weekly_hours, entered_hours,
                          expected_hours, coverage, submitted_by,
                          submitted_name, minimum_coverage,
                          below_coverage_reason)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING
                       RETURNING submission_id""",
                    (period, key, weekly, entered, expected, cover,
                     actor.actor_id, actor.display_name, MIN_COVERAGE,
                     body.below_coverage_reason.strip() or None))
        got = cur.fetchone()
        if not got:
            raise HTTPException(409, "This timesheet is already submitted.")
        record(actor, "TIME_SUBMIT", "timesheet_submission",
               str(got["submission_id"]),
               after={"period": period, "entered_hours": entered,
                      "expected_hours": expected, "coverage": cover},
               reason=(f"{cover:.0%} of {expected:,.0f} hours — {basis}"
                       + (f" · short: {body.below_coverage_reason.strip()}"
                          if short else "")),
               cursor=cur)
    return {"submitted": True, "coverage": cover, "entered_hours": entered,
            "expected_hours": expected, "below_minimum": short}


@router.post("/withdraw")
def withdraw(body: WithdrawIn, period: str = None,
             actor: Actor = Depends(require_own_writes)) -> dict:
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


# ── Donated time, and what it is worth ────────────────────────────────
#
# Hours given rather than paid. They never enter the paid labour
# distribution — that would move every other share — so they are valued
# separately or not at all.
#
# `donation_rate` has been in the schema since `019` with every invariant it
# needs: immutable once set, no delete, one live rate per person per period,
# a basis of at least ten characters, a positive rate. **Nothing has ever
# written it.** `DONATION_RATE_MISSING` is a worklist kind pointing at a
# screen where there was nothing to do on arrival — which is the same defect
# as a BLOCKING item that doing the work cannot clear, one step earlier.

class DonationRateIn(BaseModel):
    employee_key: str
    hourly_rate: Decimal = Field(gt=0)
    #: What the rate rests on. Ten characters is the schema's floor and it is
    #: not arbitrary: 2 CFR 200.306(e) wants a rate consistent with what the
    #: organisation pays for similar work, or with the labour market where it
    #: has no such work — and "market" is not a statement of either.
    basis: str = Field(min_length=11)
    source_document: str = ""


@router.get("/donations")
def donations(period: str = None,
              actor: Actor = Depends(current_actor)) -> dict:
    """Donated hours by person, and what each is valued at.

    A read, so anybody signed in sees it — including the person whose hours
    they are, which is the point: somebody who gave a day should be able to
    see that it was recorded and what it was put at.
    """
    period = period or settings.period
    rows = query("""SELECT * FROM v_donated_time WHERE period = %s
                     ORDER BY employee_key, objective_id""", (period,))
    people = {}
    for r in rows:
        p = people.setdefault(r["employee_key"], {
            "employee_key": r["employee_key"], "hours": Decimal(0),
            "objectives": [], "hourly_rate": r["hourly_rate"],
            "rate_basis": r["rate_basis"], "valued_at": Decimal(0),
            "rate_missing": r["rate_missing"]})
        p["hours"] += r["hours"]
        if r["valued_at"] is not None:
            p["valued_at"] += r["valued_at"]
        p["objectives"].append({"objective_id": r["objective_id"],
                                "label": r["objective_label"],
                                "is_federal": r["is_federal"],
                                "hours": str(r["hours"]),
                                "valued_at": (str(r["valued_at"])
                                              if r["valued_at"] is not None
                                              else None)})
    out = [{**p, "hours": str(p["hours"]),
            "hourly_rate": str(p["hourly_rate"]) if p["hourly_rate"] else None,
            "valued_at": str(p["valued_at"]) if not p["rate_missing"] else None}
           for p in people.values()]
    return {"period": period, "people": out,
            "unvalued": sum(1 for p in out if p["rate_missing"]),
            # Deliberately not a total across everybody: a total over a
            # population where some are unvalued reads as the value of the
            # donated time, and it is the value of the part somebody has got
            # to. The count of the rest is beside it for that reason.
            "valued_total": str(sum(Decimal(p["valued_at"]) for p in out
                                    if not p["rate_missing"]))}


@router.put("/donation-rate")
def put_donation_rate(body: DonationRateIn, period: str = None,
                      actor: Actor = Depends(require_controller)) -> dict:
    """What an hour of somebody's donated time is worth.

    The controller's judgment and nobody else's — **a volunteer valuing their
    own time is the whole problem 2 CFR 200.306(e) is guarding against**, and
    the rate has to be consistent with what YBI pays for similar work, or
    with the labour market where it has no such work. So the basis is
    required and the schema will not take a short one.

    Superseded, never edited. The rate is immutable once set, which is what
    makes "what was this valued at when the rate was computed" answerable
    afterwards; a second rate closes the first and both stay.
    """
    period = period or settings.period
    key = body.employee_key.upper()
    with turn(period) as cur:
        cur.execute("""SELECT count(*) AS n FROM v_timesheet_entry
                        WHERE period = %s AND employee_key = %s AND donated""",
                    (period, key))
        if not cur.fetchone()["n"]:
            # Not a refusal of a wrong value — a refusal of a value with
            # nothing to apply to. A rate against nobody's hours is a figure
            # somebody will later find and wonder about.
            raise HTTPException(
                422, f"{key} has no donated hours in {period}, so there is "
                     f"nothing for a rate to value. Record the hours first.")

        # The handler half of `nobody_values_their_own_time`. The trigger is
        # what makes it hold when this is wrong; this is what makes the
        # refusal a sentence somebody can act on rather than a constraint
        # violation.
        if actor.employee_key and actor.employee_key.upper() == key:
            raise HTTPException(
                422, "A donated hour cannot be valued by the person who gave "
                     "it. 2 CFR 200.306(e) wants a rate consistent with what "
                     "YBI pays for similar work, and that is a judgment "
                     "about your time rather than yours to make. Ask one of "
                     "the other controllers.")

        cur.execute("""SELECT rate_id, hourly_rate FROM donation_rate
                        WHERE period = %s AND employee_key = %s
                          AND superseded_at IS NULL""", (period, key))
        prior = cur.fetchone()
        if prior:
            # Close the old one first: `one_live_donation_rate` is a partial
            # unique index and is checked at the insert, not at COMMIT.
            cur.execute("""UPDATE donation_rate SET superseded_at = now()
                            WHERE rate_id = %s""", (prior["rate_id"],))
        cur.execute("""INSERT INTO donation_rate
                         (period, employee_key, hourly_rate, basis,
                          source_document, set_by, set_by_name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       RETURNING rate_id""",
                    (period, key, body.hourly_rate, body.basis.strip(),
                     body.source_document.strip(), actor.actor_id,
                     actor.display_name))
        rate_id = cur.fetchone()["rate_id"]
        record(actor, "DONATION_RATE", "employee", key,
               before=({"hourly_rate": str(prior["hourly_rate"])}
                       if prior else None),
               after={"hourly_rate": str(body.hourly_rate),
                      "basis": body.basis.strip()},
               reason=body.basis.strip()[:400], cursor=cur)
        cur.execute("""SELECT sum(hours) AS hours, sum(valued_at) AS valued
                         FROM v_donated_time
                        WHERE period = %s AND employee_key = %s""",
                    (period, key))
        got = cur.fetchone()
    return {"rate_id": rate_id, "employee_key": key,
            "hourly_rate": str(body.hourly_rate),
            "superseded": bool(prior),
            "hours": str(got["hours"]), "valued_at": str(got["valued"])}


@router.get("/roster")
def roster(period: str = None,
           actor: Actor = Depends(current_actor)) -> list[dict]:
    """Everyone's timesheet at a glance. The controller's screen.

    Reading is review, which is the controller's job; writing a timesheet
    never is.
    """
    period = period or settings.period
    if not actor.can_read:
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
    # **`v_timesheet_coverage` is `FROM v_timesheet_entry`, so somebody with
    # no entries has no row in it — and their employment terms are still on
    # the record.** Returning nothing here told the screen the terms were
    # unknown while the draft card beside it printed "2,080 contracted
    # hours" from `v_employment_expected`: two cards on one screen
    # disagreeing about the same fact at the same moment, which is 13.0%
    # and 2.2% in a smaller place. It also disabled *Submit*, the one thing
    # somebody with a full sheet and no coverage row would want.
    #
    # The terms come from the register of terms either way, so the two
    # cannot disagree rather than being patched where they happened to.
    terms = one("""SELECT expected_hours, employed_days, weekly_hours,
                          statuses, from_date AS employed_from,
                          to_date AS employed_to
                     FROM v_employment_expected
                    WHERE period = %s AND employee_key = %s""", (period, key))
    if cover is None:
        cover = {"period": period, "employee_key": key, "entered_hours": 0,
                 "chargeable_hours": 0, "leave_hours": 0, "days_with_time": 0,
                 "donated_hours": 0, "coverage": None,
                 "submitted_coverage": None, "submitted_at": None,
                 "first_day": None, "last_day": None,
                 "expected_hours": None, "employed_days": None,
                 "weekly_hours": None, "statuses": None,
                 "employed_from": None, "employed_to": None,
                 "terms_known": False}
    else:
        cover = dict(cover)
    if terms:
        cover.update(dict(terms))
        cover["terms_known"] = terms["expected_hours"] is not None
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
