-- 071 — the working calendar is theirs, and so are the hours
--
-- The adopt route needed to know which days somebody was working and
-- invented a United States federal holiday calendar to answer it. That was
-- wrong twice, and the workbook says so on two sheets nothing had read:
--
--   **`Hours available`** — a row headed *Work Days* and a row headed
--   *Hours Per Month*, by month, from October 2023 to July 2026. YBI counts
--   **261 work days in 2025 and 2,088 hours**, which is every weekday with
--   **no holiday deducted at all**. Eleven federal holidays taken out of
--   that was not a correction, it was a second organisation's calendar
--   imposed on this one.
--
--   **`Hours Log`** — 1.2MB, 45 people, 144 person-months for 2025, with
--   hours by objective, `TS Hours` as logged, `Allow Hours` as the month's
--   capacity, `Variance` between them, and an `Adj-` set normalising the
--   logged hours to the capacity. Gaffney logged 2,682 hours against 2,088
--   available; her adjusted hours come to exactly 2,088, and her objective
--   mix matches `labor_allocation`'s wage shares to two decimal places.
--
-- So the distribution this whole system computes a rate over was **built
-- from these hours**, and the loader took only the finished wage figures.
-- The hours themselves — the evidence a reviewer asks for, and the only
-- thing that can make a draft timesheet say *in March you logged 168 hours*
-- rather than smearing a year — were on the record and in no database.
--
-- Nothing here changes a rate. `labor_allocation` still carries the
-- distribution and `v_labor_effective` still reads it; this is the source
-- underneath it, loaded so it can be shown, checked and drawn on.

CREATE TABLE IF NOT EXISTS work_month (
    period           text        NOT NULL REFERENCES fiscal_period(period),
    month_start      date        NOT NULL,
    work_days        integer     NOT NULL,
    available_hours  numeric(8,2) NOT NULL,
    source_document  text        NOT NULL DEFAULT '',
    loaded_at        timestamptz NOT NULL DEFAULT now(),
    loaded_by        text        NOT NULL DEFAULT '',
    PRIMARY KEY (period, month_start),
    CONSTRAINT work_days_are_a_month   CHECK (work_days BETWEEN 0 AND 31),
    CONSTRAINT available_hours_positive CHECK (available_hours >= 0),
    -- A month that claims days must say how many hours they hold, or the
    -- two disagree silently the first time somebody divides by one of them.
    CONSTRAINT hours_need_days CHECK (work_days > 0 OR available_hours = 0)
);

COMMENT ON TABLE work_month IS
    'The organisation''s own working calendar, transcribed from the '
    '`Hours available` sheet of the controller''s grant reconciliation '
    'workbook. It is what `Allow Hours` on every row of the hours log is '
    'measured against, so it is the denominator their record already uses '
    'rather than one this system invented.';

COMMENT ON COLUMN work_month.work_days IS
    'Working days YBI counts in the month. For 2025 these are the weekdays '
    'with no holiday deducted, which is a fact about their calendar and not '
    'a rule to apply elsewhere.';


-- The raw hours, at the grain the record keeps them: a person, a month, an
-- objective. `logged` is what the timesheet said and `adjusted` is that
-- normalised to the month's capacity — both kept, because the difference is
-- the controller's judgment and collapsing it would hide that a judgment
-- was made.
CREATE TABLE IF NOT EXISTS labor_month (
    period           text        NOT NULL REFERENCES fiscal_period(period),
    employee_key     text        NOT NULL,
    month_start      date        NOT NULL,
    objective_id     text        NOT NULL REFERENCES cost_objective(objective_id),
    logged_hours     numeric(8,2) NOT NULL DEFAULT 0,
    adjusted_hours   numeric(8,2) NOT NULL DEFAULT 0,
    source_document  text        NOT NULL DEFAULT '',
    source_label     text        NOT NULL DEFAULT '',
    loaded_at        timestamptz NOT NULL DEFAULT now(),
    loaded_by        text        NOT NULL DEFAULT '',
    PRIMARY KEY (period, employee_key, month_start, objective_id),
    CONSTRAINT month_hours_sane
        CHECK (logged_hours >= 0 AND adjusted_hours >= 0
               AND logged_hours <= 744 AND adjusted_hours <= 744)
);

COMMENT ON TABLE labor_month IS
    'The hours log as kept: a person, a month, an objective. `logged_hours` '
    'is what was booked and `adjusted_hours` is that normalised to the '
    'month''s capacity — the figures `labor_allocation` distributes wages '
    'by. Loaded as evidence rather than as an input: nothing computes a '
    'rate from this table.';


-- What a person's month comes to, beside what the calendar says it holds.
CREATE OR REPLACE VIEW v_labor_month AS
SELECT m.period, m.employee_key, m.month_start,
       to_char(m.month_start, 'FMMonth YYYY')        AS month_label,
       sum(m.logged_hours)                           AS logged_hours,
       sum(m.adjusted_hours)                         AS adjusted_hours,
       count(*)                                      AS objectives,
       w.work_days, w.available_hours,
       sum(m.logged_hours) - w.available_hours       AS logged_variance,
       -- Three states, not a bare difference: a month the calendar does not
       -- cover cannot be compared, and reporting that as a variance of the
       -- whole month's hours would be a false alarm every time.
       CASE WHEN w.available_hours IS NULL           THEN 'NO CALENDAR'
            WHEN sum(m.adjusted_hours) = w.available_hours THEN 'TIES'
            ELSE 'OPEN' END                          AS adjusted_state
  FROM labor_month m
  LEFT JOIN work_month w
         ON w.period = m.period AND w.month_start = m.month_start
 GROUP BY m.period, m.employee_key, m.month_start, w.work_days,
          w.available_hours;


-- **Their calendar against the calendar itself.**
--
-- Their `Work Days` should be the weekdays of the month, and for 2025 every
-- month of it is. Saying so is the point: a transcription nobody checked is
-- a number somebody typed, and if a month ever differs — a shutdown week, a
-- holiday they do deduct — that difference is a fact about the
-- organisation worth reading rather than a defect to correct.
CREATE OR REPLACE VIEW v_work_calendar_check AS
SELECT w.period, w.month_start,
       to_char(w.month_start, 'FMMonth YYYY')        AS month_label,
       w.work_days                                   AS says,
       d.weekdays                                    AS weekdays,
       w.work_days - d.weekdays                      AS difference,
       w.available_hours,
       round(w.available_hours / NULLIF(w.work_days, 0), 2) AS hours_per_day,
       CASE WHEN w.work_days = d.weekdays THEN 'TIES' ELSE 'OPEN' END AS state
  FROM work_month w
  CROSS JOIN LATERAL (
      SELECT count(*) AS weekdays
        FROM generate_series(w.month_start,
                             (w.month_start + interval '1 month'
                              - interval '1 day')::date,
                             interval '1 day') AS g(d)
       WHERE extract(isodow FROM g.d) < 6) d;

COMMENT ON VIEW v_work_calendar_check IS
    'What the organisation says a month holds, against the weekdays it '
    'actually has. OPEN is not a defect — it is a month where YBI counts '
    'something other than every weekday, which is exactly what a working '
    'calendar is for.';
