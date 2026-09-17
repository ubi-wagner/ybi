-- 104 — the control never read the register built to explain it
--
-- `072` added `v_labor_hours_check` and it reported one person as **HOURS
-- WITHOUT WAGES**: 781 hours across all twelve months, no payroll row, and no
-- payment anywhere in the ledger under that surname. `073` answered it — he
-- is 1099, paid as `Metz Consulting, LLC.`, $73,024.44 over 25 lines, and
-- `contractor_identity` is the register that holds the link with the note
-- reconciling both differences exactly.
--
-- **And the control has gone on reporting HOURS WITHOUT WAGES ever since.**
-- The register exists, the answer is in it, and the thing that asks the
-- question never learned to read it. That is the dead-register shape pointed
-- the other way: not a table nothing writes, but a table nothing *reads* —
-- and `test_no_register_is_dead.py` cannot see it, because `contractor_
-- identity` does have a reader in `v_contractor_effort_check`.
--
-- It surfaced from `103`, which is the argument for collecting controls into
-- one register: a difference that has been explained for months reads as
-- untied until something asks *all* of them at once.
--
-- `EXPLAINED` is a fourth state and not a pass dressed up. The hours genuinely
-- do not tie to wages — they tie to a contractor payment — and `explained_by`
-- carries the payee and the note, so the state is never the whole answer.
-- *A difference is closed by naming it*, which is the reconciling register's
-- own rule in a second place.
--
-- Lifted from the definition in force rather than retyped.

CREATE OR REPLACE VIEW v_labor_hours_check AS
 WITH hours AS (
         SELECT labor_month.period,
            labor_month.employee_key,
            labor_month.objective_id,
            sum(labor_month.adjusted_hours) AS adjusted,
            count(*) AS roundings
           FROM labor_month
          GROUP BY labor_month.period, labor_month.employee_key, labor_month.objective_id
         HAVING sum(labor_month.adjusted_hours) > 0::numeric
        ), person AS (
         SELECT hours.period,
            hours.employee_key,
            sum(hours.adjusted) AS total,
            sum(hours.roundings) AS roundings
           FROM hours
          GROUP BY hours.period, hours.employee_key
        ), capacity AS (
         SELECT m.period,
            m.employee_key,
            sum(w.available_hours) AS available
           FROM ( SELECT DISTINCT labor_month.period,
                    labor_month.employee_key,
                    labor_month.month_start
                   FROM labor_month) m
             JOIN work_month w ON w.period = m.period AND w.month_start = m.month_start
          GROUP BY m.period, m.employee_key
        ), compared AS (
         SELECT h.period,
            h.employee_key,
            count(*) AS objectives,
            max(abs(round(h.adjusted / p_1.total, 6) - e.share)) AS worst_gap,
            count(*) FILTER (WHERE e.share IS NULL) AS unmatched
           FROM hours h
             JOIN person p_1 USING (period, employee_key)
             LEFT JOIN v_labor_effective e ON e.period = h.period AND e.employee_key = h.employee_key AND e.objective_id = h.objective_id
          GROUP BY h.period, h.employee_key
        ), everybody AS (
         SELECT labor_allocation.period,
            labor_allocation.employee_key
           FROM labor_allocation
        UNION
         SELECT labor_month.period,
            labor_month.employee_key
           FROM labor_month
        )
 SELECT l.period,
    l.employee_key,
    COALESCE(c.objectives, 0::bigint) AS objectives,
    p.total AS adjusted_hours,
    cap.available AS available_hours,
    p.total - cap.available AS capacity_gap,
    round(p.roundings / 200.0, 4) AS rounding_bound,
    c.worst_gap,
    c.unmatched,
        CASE
            WHEN p.total IS NULL THEN 'NO HOURS LOG'::text
            WHEN NOT (EXISTS ( SELECT 1
               FROM labor_allocation a
              WHERE a.period = l.period AND a.employee_key = l.employee_key))
              THEN CASE WHEN EXISTS ( SELECT 1
                     FROM contractor_identity ci
                    WHERE ci.period = l.period
                      AND ci.employee_key = l.employee_key)
                        THEN 'EXPLAINED'::text
                   ELSE 'HOURS WITHOUT WAGES'::text END
            WHEN c.unmatched > 0 THEN 'OPEN'::text
            WHEN c.worst_gap IS NULL THEN 'NO HOURS LOG'::text
            WHEN c.worst_gap <= 0.0001 THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
        CASE
            WHEN p.total IS NULL THEN 'NO HOURS LOG'::text
            WHEN cap.available IS NULL THEN 'NO CALENDAR'::text
            WHEN abs(p.total - cap.available) <= (p.roundings / 200.0) THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS capacity_state,
    ( SELECT ci.payee || ' — ' || ci.note FROM contractor_identity ci
       WHERE ci.period = l.period AND ci.employee_key = l.employee_key)
        AS explained_by
   FROM everybody l
     LEFT JOIN person p USING (period, employee_key)
     LEFT JOIN capacity cap USING (period, employee_key)
     LEFT JOIN compared c USING (period, employee_key);

COMMENT ON VIEW v_labor_hours_check IS
  'Whether each person''s hours account for their wages. EXPLAINED is somebody '
  'with hours and no payroll row whom contractor_identity names — the 1099 '
  'case 073 recorded and this control did not read until 104. NO HOURS LOG '
  'is not a pass: thirty-five people carry one summary row and there is '
  'nothing to compare.';
