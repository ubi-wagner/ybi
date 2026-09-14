-- 069 — the distribution has to add back to the payroll register
--
-- `v_labor_effective.distributed_wages` was `round(payroll_wages * share, 2)`
-- computed **per row, independently**, so a person's distributed wages did
-- not have to add back to their payroll wages. The residual was simply lost
-- or gained, a cent at a time, per person.
--
-- Measured on the live 2025 record before any timesheet existed: **six of the
-- forty-three people already drifted** — JARIC and EWING a cent short, KALE,
-- POLITSKY and JADUE a cent over. The eleventh statement control tied anyway,
-- because the cents happened to net out. That is luck, not a control.
--
-- It matters because of *which* figure this is. The fringe base comes from
-- the effort distribution and is anchored to the payroll register — the
-- eleventh control, `WAGE_BASE_IS_THE_REGISTER`, and the whole argument that
-- 21.90% falls out rather than being asserted. A denominator that moves by
-- cents for reasons nobody chose is the register disagreeing with itself.
--
-- What exposed it was adopting a reconstruction as a timesheet. Submitting
-- one switches that person's distribution from reconstructed units to hours,
-- the shares move in the sixth decimal, the cents fall the other way, and
-- `PAYROLL_REGISTER` went OPEN by $0.01 — refusing `POST /api/rates/compute`
-- outright. Recommendation 1 asks forty-three people to do exactly that, so
-- this would have fired on the first one and gone on firing.
--
-- Largest remainder, then: floor every share to the cent and hand the spare
-- cents to the rows with the largest remainders, ties broken by objective so
-- the answer is deterministic. The person's wages are distributed in full by
-- construction, whatever the source and however the shares move.
--
-- **And the register was never $1,835,047.18.** That figure is in
-- `FOUNDATION.md`, `BASELINE_2025.md`, the fringe anchors of `067`, the
-- classification log and a memo — and it is this view's rounding, gained a
-- cent at a time. Read off the controller's workbook, column B, forty-three
-- employees, the register is **$1,835,047.17**, and `BASELINE_2025.md` also
-- carried $1,835,047.16 in one place: three readings of one document, which
-- is what per-row rounding produces when different things aggregate it.
--
-- The fringe rate is unmoved — 401,783.60 / 1,835,047.17 is 0.2190 to four
-- places, as it was — so nothing published changes. What moves is the cent:
-- the difference between the register and the ledger's wage accounts is
-- $45,053.23, not $45,053.24, and `reconcile.py` computes the ROUNDING item
-- from the live difference rather than a constant, so it lands at $53.23 on
-- its own and `PAYROLL_REGISTER` ties without being told to.
--
-- The rule this breaks is the one already written down: *figures in a
-- document for somebody else get read from the record, not recalled.* Here
-- the record itself was recalling an artefact.
--
-- `CREATE OR REPLACE` rather than `DROP ... CASCADE`: the column list is
-- unchanged and four views read this one. And the body below is **lifted**
-- from `017`, not retyped — one draft of `045` rewrote a view's scope from
-- memory and silently changed how every line was categorised.

CREATE OR REPLACE VIEW v_labor_effective AS

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
,
-- The share each row carries, and what it comes to before rounding.
based AS (
  SELECT m.period, m.employee_key, m.objective_id, m.source,
         m.original_units, m.reconstructed_units, m.effective_units,
         m.evidence_quality, m.rationale, m.is_reconstructed,
         COALESCE(w.employee_name, m.employee_key) AS employee_name,
         COALESCE(w.payroll_wages, 0)              AS payroll_wages,
         SUM(m.effective_units)
             OVER (PARTITION BY m.period, m.employee_key) AS employee_units
    FROM merged m
    LEFT JOIN wages w USING (period, employee_key)),
exact AS (
  SELECT b.*,
         CASE WHEN b.employee_units > 0
              THEN b.payroll_wages * b.effective_units / b.employee_units
              ELSE 0 END AS exact_wages
    FROM based b),
floored AS (
  -- floor() rather than round(): a floor can only ever be short, so the
  -- spare is always a non-negative number of cents to hand out. Rounding to
  -- nearest makes it signed, and a negative spare is the shape that silently
  -- dropped a line when the adopt route first tried this arithmetic.
  SELECT e.*, floor(e.exact_wages * 100) / 100 AS floor_wages FROM exact e),
shared_out AS (
  SELECT f.*,
         round((f.payroll_wages
                - SUM(f.floor_wages)
                    OVER (PARTITION BY f.period, f.employee_key)) * 100)::int
                                                          AS spare_cents,
         row_number() OVER (PARTITION BY f.period, f.employee_key
                            ORDER BY (f.exact_wages - f.floor_wages) DESC,
                                     f.objective_id)       AS remainder_rank
    FROM floored f)
SELECT s.period, s.employee_key, s.employee_name,
       s.objective_id, s.source, s.payroll_wages,
       s.original_units, s.reconstructed_units, s.effective_units,
       s.evidence_quality, s.rationale, s.is_reconstructed,
       s.employee_units,
       CASE WHEN s.employee_units > 0
            THEN round(s.effective_units / s.employee_units, 6)
            ELSE 0 END                                AS share,
       s.floor_wages
         + CASE WHEN s.remainder_rank <= s.spare_cents
                THEN 0.01 ELSE 0 END                  AS distributed_wages
  FROM shared_out s;

COMMENT ON VIEW v_labor_effective IS
  'The distribution that speaks for each employee: their own timesheet once '
  'they have submitted it as complete, the controller''s reconstruction until '
  'then. Firsthand outranks secondhand — but only a finished record counts '
  'as firsthand for a whole period. `distributed_wages` allocates the whole '
  'of the person''s payroll wages by largest remainder, so it adds back to '
  'the register by construction rather than by how the cents happen to fall.';
