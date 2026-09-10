-- =====================================================================
-- Timesheets: the employee's own record of their own time
--
-- The 2025 distribution came from the controller's workbook. It is a careful
-- reconstruction and it is the best evidence anyone has, but 2 CFR
-- 200.430(i) does not ask the controller what an employee did. It asks for
-- records that reflect the work performed, supported by a statement from the
-- person who performed it or a supervisor with firsthand knowledge.
--
-- So this is the other half: the employee records their own time, against the
-- same cost objectives the ledger is classified into, and certifies their own
-- numbers rather than being handed someone else's to sign.
--
-- Three things the schema decides rather than the person entering:
--
--   1. Whether an entry is contemporaneous. That is the difference between
--      entered_at and work_date, not a claim anyone gets to make. An entry
--      typed eight months later is a reconstruction however carefully it was
--      done, and it says so.
--   2. That a reconstruction names what it was reconstructed from. A calendar,
--      a project record, an invoice — or memory, which is allowed and is
--      graded as what it is.
--   3. That a day holds no more than twenty-four hours, checked across the
--      whole day at COMMIT rather than per row.
--
-- Nothing here is edited in place. Correcting an entry supersedes it, the way
-- correcting a classification supersedes a decision.
-- =====================================================================

-- ── One vocabulary ───────────────────────────────────────────────────
--
-- labor_allocation arrived carrying the workbook's column headings — "Drive
-- AM", "Dig Eng M7", "YBI" — which are not the objective ids the ledger, the
-- awards and the classification queue use. Only fifty of the ninety-seven
-- rows joined to cost_objective at all, so labour could not be tied to the
-- award it supported without someone matching strings by eye.
--
-- The mapping is recorded rather than applied silently: two of these are
-- judgments (the workbook's "Hybrid" is Hybrid II, its "YBI" is general
-- administration) and a reviewer is entitled to see them stated.

CREATE TABLE labor_objective_map (
  source_label  text PRIMARY KEY,
  objective_id  text NOT NULL REFERENCES cost_objective,
  note          text NOT NULL DEFAULT ''
);

INSERT INTO labor_objective_map (source_label, objective_id, note) VALUES
  ('AM Other',     'AM-OTHER',     ''),
  ('DLA',          'DLA',          ''),
  ('Dig Eng M7',   'DIG-ENG',      'M7 is the workbook''s task suffix, not a separate objective.'),
  ('Drive AM',     'DRIVE-AM',     ''),
  ('ESP',          'ESP',          ''),
  ('Fundraising',  'FUNDRAISING',  ''),
  ('Hub',          'HUB',          ''),
  ('Hybrid',       'HYBRID-II',    'The only Hybrid award in the period is Hybrid II.'),
  ('IIOT',         'IIOT',         ''),
  ('LTM',          'LTM',          ''),
  ('MBAC',         'MBAC',         ''),
  ('Rising Tides', 'RISING-TIDES', ''),
  ('VGV',          'VGV',          ''),
  ('Xjet',         'XJET',         ''),
  ('YBI',          'YBI-GA',       'The workbook''s residual column is general administration.'),
  ('Youth',        'YOUTH',        '');

ALTER TABLE labor_allocation ADD COLUMN source_label text NOT NULL DEFAULT '';
UPDATE labor_allocation SET source_label = objective_id WHERE source_label = '';
UPDATE labor_allocation a
   SET objective_id = m.objective_id
  FROM labor_objective_map m
 WHERE m.source_label = a.objective_id
   AND a.objective_id <> m.objective_id;

-- Now it can be held to the vocabulary.
ALTER TABLE labor_allocation
  ADD CONSTRAINT labor_allocation_objective_fkey
  FOREIGN KEY (objective_id) REFERENCES cost_objective (objective_id);


-- ── Somewhere to put the time that is not a final cost objective ─────
--
-- Paid leave is compensated activity, so a distribution that omits it
-- overstates every other share. It is not a final cost objective — it is
-- absorbed in fringe — so it is recorded and then excluded from the base,
-- which is a different thing from ignoring it.

INSERT INTO cost_objective (objective_id, period, label, objective_type,
                            is_federal, is_final, active)
VALUES ('LEAVE', '2025', 'Paid leave — holiday, PTO, sick', 'LEAVE',
        false, false, true)
ON CONFLICT (objective_id) DO NOTHING;


-- ── The entries ──────────────────────────────────────────────────────

CREATE TYPE time_basis AS ENUM (
  'AS_WORKED',        -- recorded while doing it, or within the week
  'CALENDAR',         -- rebuilt from the diary
  'PROJECT_RECORD',   -- from notes, tickets, commits, meeting minutes
  'DELIVERABLE',      -- from a dated deliverable or invoice
  'RECALL'            -- from memory, which is allowed and graded as such
);

CREATE TABLE timesheet_entry (
  entry_id        bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  employee_key    text NOT NULL,
  work_date       date NOT NULL,
  objective_id    text NOT NULL REFERENCES cost_objective,
  hours           numeric(5,2) NOT NULL,
  basis           time_basis NOT NULL,
  note            text NOT NULL DEFAULT '',
  entered_by      uuid NOT NULL REFERENCES actor,
  entered_by_name text NOT NULL DEFAULT '',
  entered_at      timestamptz NOT NULL DEFAULT now(),
  superseded_at   timestamptz,
  superseded_by   bigint REFERENCES timesheet_entry,

  CONSTRAINT timesheet_hours_sane CHECK (hours > 0 AND hours <= 24),
  -- The claim that something was recorded as it was worked is a claim about
  -- time, and the row carries both timestamps, so it can simply be checked.
  CONSTRAINT as_worked_must_be_prompt
    CHECK (basis <> 'AS_WORKED' OR entered_at::date - work_date <= 7),
  -- superseded_at alone is a removal; with superseded_by it is a correction
  -- and names the row that replaced it. A row never supersedes itself.
  CONSTRAINT timesheet_supersession_ordered
    CHECK (superseded_by IS NULL OR superseded_at IS NOT NULL),
  CONSTRAINT timesheet_supersession_not_self
    CHECK (superseded_by IS NULL OR superseded_by <> entry_id)
);

-- One live entry per person, day and objective. A correction supersedes.
CREATE UNIQUE INDEX one_live_entry_per_day_objective
  ON timesheet_entry (period, employee_key, work_date, objective_id)
  WHERE superseded_at IS NULL;
CREATE INDEX ON timesheet_entry (employee_key, work_date)
  WHERE superseded_at IS NULL;

-- What was entered is what was entered. Only the supersession columns move.
CREATE TRIGGER timesheet_entry_immutable
  BEFORE UPDATE OF period, employee_key, work_date, objective_id, hours,
                   basis, note, entered_by, entered_at
  ON timesheet_entry
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER timesheet_entry_no_delete
  BEFORE DELETE ON timesheet_entry
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- A day holds twenty-four hours. Checked across the day at COMMIT, because
-- entering eight hours against three objectives is three inserts and the
-- twenty-fifth hour only exists once they are all in.
CREATE OR REPLACE FUNCTION timesheet_day_within_bounds() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE total numeric(6,2);
BEGIN
  SELECT COALESCE(sum(hours), 0) INTO total
    FROM timesheet_entry
   WHERE employee_key = NEW.employee_key AND work_date = NEW.work_date
     AND superseded_at IS NULL;
  IF total > 24 THEN
    RAISE EXCEPTION
      '% has % hours on %, and a day holds 24.',
      NEW.employee_key, total, NEW.work_date;
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER timesheet_day_must_fit
  AFTER INSERT OR UPDATE ON timesheet_entry
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION timesheet_day_within_bounds();


-- ── How good is this record ──────────────────────────────────────────
--
-- The lag between doing the work and writing it down is the whole question,
-- and the row answers it without anybody being asked.

CREATE VIEW v_timesheet_entry AS
SELECT e.*,
       (e.entered_at::date - e.work_date)              AS lag_days,
       CASE WHEN e.entered_at::date - e.work_date <= 7   THEN 'CONTEMPORANEOUS'
            WHEN e.entered_at::date - e.work_date <= 45  THEN 'NEAR_TERM'
            ELSE 'RECONSTRUCTED' END                   AS timing,
       CASE WHEN e.basis = 'RECALL'                              THEN 'UNSUPPORTED'
            WHEN e.entered_at::date - e.work_date <= 7           THEN 'CORROBORATED'
            WHEN e.basis IN ('CALENDAR','PROJECT_RECORD','DELIVERABLE')
                                                                 THEN 'MANAGEMENT_RECONSTRUCTION'
            ELSE 'UNSUPPORTED' END::evidence_grade     AS entry_grade,
       o.label                                         AS objective_label,
       o.is_federal, o.is_final
  FROM timesheet_entry e
  JOIN cost_objective o USING (objective_id)
 WHERE e.superseded_at IS NULL;

COMMENT ON VIEW v_timesheet_entry IS
  'Live entries, with the grade the timing and the basis earn. A record made '
  'within the week of the work is contemporaneous; one made eight months '
  'later is a reconstruction however carefully it was built.';


CREATE VIEW v_timesheet_day AS
SELECT period, employee_key, work_date,
       sum(hours)                                  AS hours,
       count(*)                                    AS entries,
       min(entry_grade)                            AS weakest_grade,
       bool_or(is_final)                           AS has_chargeable_time
  FROM v_timesheet_entry
 GROUP BY period, employee_key, work_date;


-- The distribution the timesheet implies. Leave is recorded and then left out
-- of the base: it is not a final cost objective, and including it would
-- understate every share that is.
CREATE VIEW v_timesheet_distribution AS
SELECT period, employee_key, objective_id,
       sum(hours)                                   AS hours,
       count(*)                                     AS days,
       min(work_date)                               AS first_day,
       max(work_date)                               AS last_day,
       min(entry_grade)                             AS weakest_grade,
       max(entered_at)                              AS last_entered_at,
       round(avg(lag_days))                         AS mean_lag_days
  FROM v_timesheet_entry
 WHERE is_final
 GROUP BY period, employee_key, objective_id;


-- ── Saying the sheet is finished ─────────────────────────────────────
--
-- A part-filled timesheet must never speak for a year. One day entered
-- against one award would otherwise say that award was the whole of it, and
-- redistribute a year of wages on the strength of eight hours.
--
-- So a timesheet stands in for the reconstruction only once its owner says it
-- is complete, and saying so is a separate act with its own record: how many
-- hours a week they worked, how many hours are on the sheet, and therefore
-- how much of the period it actually covers.

CREATE TABLE timesheet_submission (
  submission_id   bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  employee_key    text NOT NULL,
  weekly_hours    numeric(5,2) NOT NULL,
  entered_hours   numeric(9,2) NOT NULL,
  expected_hours  numeric(9,2) NOT NULL,
  coverage        numeric(6,4) NOT NULL,
  submitted_by    uuid NOT NULL REFERENCES actor,
  submitted_name  text NOT NULL DEFAULT '',
  submitted_at    timestamptz NOT NULL DEFAULT now(),
  withdrawn_at    timestamptz,
  withdrawn_reason text,

  CONSTRAINT submission_weekly_hours_sane
    CHECK (weekly_hours > 0 AND weekly_hours <= 80),
  CONSTRAINT submission_withdrawal_pair
    CHECK ((withdrawn_at IS NULL) = (withdrawn_reason IS NULL))
);

CREATE UNIQUE INDEX one_live_submission_per_period
  ON timesheet_submission (period, employee_key) WHERE withdrawn_at IS NULL;

CREATE TRIGGER timesheet_submission_immutable
  BEFORE UPDATE OF period, employee_key, weekly_hours, entered_hours,
                   expected_hours, coverage, submitted_by, submitted_at
  ON timesheet_submission
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER timesheet_submission_no_delete
  BEFORE DELETE ON timesheet_submission
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ── Which record speaks for an employee ──────────────────────────────
--
-- Firsthand outranks secondhand. Where an employee has entered their own
-- time, that is the distribution; where they have not, the controller's
-- reconstruction still stands, because an unfinished timesheet is not an
-- assertion that nothing happened.
--
-- Rewritten rather than replaced: everything downstream — the certification
-- hash, the audit package, the employee's own screen — reads this view, and
-- it keeps every column it had.

DROP VIEW IF EXISTS v_labor_effective CASCADE;
CREATE VIEW v_labor_effective AS
WITH wages AS (
  SELECT period, employee_key, max(payroll_wages) AS payroll_wages,
         max(employee_name) AS employee_name
    FROM labor_allocation GROUP BY period, employee_key),
ts AS (
  -- Only a submitted timesheet. An unfinished one is a work in progress, not
  -- an assertion about the year.
  SELECT d.period, d.employee_key, d.objective_id, d.hours, d.weakest_grade,
         d.mean_lag_days
    FROM v_timesheet_distribution d
   WHERE EXISTS (SELECT 1 FROM timesheet_submission s
                  WHERE s.period = d.period
                    AND s.employee_key = d.employee_key
                    AND s.withdrawn_at IS NULL)),
merged AS (
  -- An employee with any live timesheet time is represented by it entirely.
  SELECT t.period, t.employee_key, t.objective_id,
         0::numeric(12,2)                            AS original_units,
         NULL::numeric(12,2)                         AS reconstructed_units,
         t.hours                                     AS effective_units,
         'TIMESHEET'                                 AS source,
         t.weakest_grade                             AS evidence_quality,
         'Entered by the employee against their own record of the work. '
         || 'Mean lag between the work and the entry: '
         || COALESCE(t.mean_lag_days, 0)::text || ' days.' AS rationale,
         false                                       AS is_reconstructed
    FROM ts t
  UNION ALL
  SELECT a.period, a.employee_key, a.objective_id,
         a.original_units, a.reconstructed_units,
         COALESCE(a.reconstructed_units, a.original_units),
         CASE WHEN a.reconstructed_units IS NOT NULL
              THEN 'RECONSTRUCTION' ELSE 'ORIGINAL' END,
         a.evidence_quality, a.rationale,
         (a.reconstructed_units IS NOT NULL)
    FROM labor_allocation a
   WHERE NOT EXISTS (SELECT 1 FROM ts t
                      WHERE t.period = a.period
                        AND t.employee_key = a.employee_key))
SELECT m.period, m.employee_key,
       COALESCE(w.employee_name, m.employee_key)     AS employee_name,
       m.objective_id, m.source,
       COALESCE(w.payroll_wages, 0)                  AS payroll_wages,
       m.original_units, m.reconstructed_units, m.effective_units,
       m.evidence_quality, m.rationale, m.is_reconstructed,
       SUM(m.effective_units) OVER (PARTITION BY m.period, m.employee_key)
                                                     AS employee_units,
       CASE WHEN SUM(m.effective_units)
                   OVER (PARTITION BY m.period, m.employee_key) > 0
            THEN round(m.effective_units
                       / SUM(m.effective_units)
                           OVER (PARTITION BY m.period, m.employee_key), 6)
            ELSE 0 END                               AS share,
       round(COALESCE(w.payroll_wages, 0)
             * CASE WHEN SUM(m.effective_units)
                          OVER (PARTITION BY m.period, m.employee_key) > 0
                    THEN m.effective_units
                         / SUM(m.effective_units)
                             OVER (PARTITION BY m.period, m.employee_key)
                    ELSE 0 END, 2)                   AS distributed_wages
  FROM merged m
  LEFT JOIN wages w USING (period, employee_key);

COMMENT ON VIEW v_labor_effective IS
  'The distribution that speaks for each employee: their own timesheet once '
  'they have submitted it as complete, the controller''s reconstruction until '
  'then. Firsthand outranks secondhand — but only a finished record counts '
  'as firsthand for a whole period.';


-- How much of the period a timesheet actually covers, submitted or not. This
-- is what the employee is shown before they are asked to call it finished.
CREATE VIEW v_timesheet_coverage AS
SELECT p.period, e.employee_key,
       sum(e.hours)                                   AS entered_hours,
       sum(e.hours) FILTER (WHERE e.is_final)         AS chargeable_hours,
       sum(e.hours) FILTER (WHERE NOT e.is_final)     AS leave_hours,
       count(DISTINCT e.work_date)                    AS days_with_time,
       min(e.work_date)                               AS first_day,
       max(e.work_date)                               AS last_day,
       round((p.end_date - p.start_date + 1) / 7.0, 2) AS weeks_in_period,
       (SELECT s.coverage FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_coverage,
       (SELECT s.submitted_at FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_at
  FROM v_timesheet_entry e
  JOIN fiscal_period p ON p.period = e.period
 GROUP BY p.period, p.start_date, p.end_date, e.employee_key;


-- ── Where the two records disagree ───────────────────────────────────
--
-- This is the control the whole exercise turns on. When an employee''s own
-- record differs materially from the reconstruction made for them, that is a
-- finding — for the controller to look at, not for either side to overwrite.

CREATE VIEW v_labor_variance AS
WITH ts AS (
  SELECT period, employee_key, objective_id, hours,
         hours / NULLIF(sum(hours) OVER (PARTITION BY period, employee_key), 0)
           AS share
    FROM v_timesheet_distribution),
recon AS (
  SELECT a.period, a.employee_key, a.objective_id,
         COALESCE(a.reconstructed_units, a.original_units) AS units,
         COALESCE(a.reconstructed_units, a.original_units)
           / NULLIF(sum(COALESCE(a.reconstructed_units, a.original_units))
                      OVER (PARTITION BY a.period, a.employee_key), 0) AS share,
         a.payroll_wages
    FROM labor_allocation a)
SELECT COALESCE(t.period, r.period)                 AS period,
       COALESCE(t.employee_key, r.employee_key)     AS employee_key,
       COALESCE(t.objective_id, r.objective_id)     AS objective_id,
       t.hours                                      AS timesheet_hours,
       round(COALESCE(t.share, 0), 4)               AS timesheet_share,
       round(COALESCE(r.share, 0), 4)               AS reconstructed_share,
       round(COALESCE(t.share, 0) - COALESCE(r.share, 0), 4) AS share_variance,
       round(COALESCE(max(r.payroll_wages) OVER (
                PARTITION BY COALESCE(t.employee_key, r.employee_key)), 0)
             * (COALESCE(t.share, 0) - COALESCE(r.share, 0)), 2)
                                                    AS wage_variance
  FROM ts t
  FULL JOIN recon r
    ON t.period = r.period AND t.employee_key = r.employee_key
   AND t.objective_id = r.objective_id;

COMMENT ON VIEW v_labor_variance IS
  'The employee''s own record against the reconstruction made for them. A '
  'material difference is a finding, not something for either side to '
  'silently overwrite.';


-- ── The certification hash has to follow the effective distribution ──
--
-- It was computed from labor_allocation directly. Now that a timesheet can
-- be the distribution, a signature would not go stale when the timesheet
-- changed underneath it — which is the one thing the staleness check exists
-- to prevent.

-- Replaced, not dropped: v_worklist reads this view, and dropping it would
-- take the work list with it. CREATE OR REPLACE can only append columns, so
-- the new ones go on the end and every existing column keeps its position.
CREATE OR REPLACE VIEW v_certification_status AS
WITH dist AS (
  SELECT period, employee_key,
         max(employee_name)                       AS employee_name,
         max(payroll_wages)                       AS payroll_wages,
         count(*)                                 AS objectives,
         bool_or(is_reconstructed)                AS reconstructed,
         bool_or(source = 'TIMESHEET')            AS from_timesheet,
         min(evidence_quality)                    AS weakest_grade,
         md5(string_agg(objective_id || ':' || effective_units::text,
                        '|' ORDER BY objective_id)) AS current_hash
    FROM v_labor_effective GROUP BY period, employee_key),
cert AS (
  SELECT period, employee_key,
         max(signed_at)                                       AS signed_at,
         max(distribution_hash)                               AS signed_hash,
         bool_or(certifier_role = 'EMPLOYEE')                 AS by_employee,
         bool_or(certifier_role = 'SUPERVISOR')               AS by_supervisor,
         string_agg(DISTINCT signed_by, ', ')                 AS signed_by
    FROM labor_certification
   WHERE superseded_at IS NULL
   GROUP BY period, employee_key)
SELECT d.period, d.employee_key, d.employee_name, d.payroll_wages,
       d.objectives, d.reconstructed,
       c.signed_at, c.signed_by,
       COALESCE(c.by_employee, false)   AS by_employee,
       COALESCE(c.by_supervisor, false) AS by_supervisor,
       (c.signed_at IS NOT NULL)        AS certified,
       (c.signed_at IS NOT NULL AND c.signed_hash IS DISTINCT FROM d.current_hash)
                                        AS stale,
       -- Appended: see the note above the view.
       d.from_timesheet, d.weakest_grade
  FROM dist d LEFT JOIN cert c USING (period, employee_key);
