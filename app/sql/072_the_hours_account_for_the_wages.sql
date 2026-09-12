-- 072 — the hours the distribution was built from, against the distribution
--
-- `071` loaded the hours log. This is the control it makes possible, and
-- until now there was nothing to build it from: `labor_allocation` carried a
-- wage distribution with **no independent source in the database to check it
-- against**, so every downstream tie — the fringe base, the eleventh
-- statement control, `WAGE_BASE_IS_THE_REGISTER` — proved that the wages
-- added up, and none of them could ask whether the wages were split the way
-- the hours were.
--
-- They were. Measured across the eight people with a full-year hours log,
-- the largest difference between a person's share of adjusted hours and
-- their share of distributed wages is **0.000013** — thirteen millionths,
-- which is the source's own two-decimal rounding and nothing else. That is
-- worth recording as a control rather than as a paragraph: it is the
-- evidence that the distribution is the hours log and not somebody's
-- allocation of it.
--
-- **Three states, because thirty-six of the forty-five have no hours log.**
-- They carry one summary row, so there is nothing to compare and saying
-- `TIES` over it would be the empty set matching the empty set — `029` in
-- the newest place in the system. `NO HOURS LOG` is not a pass.
--
-- The tolerance is one basis point on a share. Below that is the rounding
-- of a two-decimal hours column; above it, somebody has redistributed
-- something and the objective it moved between is on the row.

-- Dropped and recreated rather than replaced: the column list gains
-- `rounding_bound`, and `CREATE OR REPLACE` cannot reorder columns.
DROP VIEW IF EXISTS v_labor_hours_check;
CREATE VIEW v_labor_hours_check AS
WITH hours AS (
    SELECT period, employee_key, objective_id,
           sum(adjusted_hours) AS adjusted,
           count(*)            AS roundings
      FROM labor_month
     GROUP BY period, employee_key, objective_id
    HAVING sum(adjusted_hours) > 0
),
person AS (
    SELECT period, employee_key, sum(adjusted) AS total,
           sum(roundings) AS roundings
      FROM hours GROUP BY period, employee_key
),
-- What the calendar says those months held, so a person's log can be read
-- against their capacity as well as against their wages.
capacity AS (
    SELECT m.period, m.employee_key, sum(w.available_hours) AS available
      FROM (SELECT DISTINCT period, employee_key, month_start
              FROM labor_month) m
      JOIN work_month w ON w.period = m.period
                       AND w.month_start = m.month_start
     GROUP BY m.period, m.employee_key
),
compared AS (
    SELECT h.period, h.employee_key,
           count(*)                                           AS objectives,
           max(abs(round(h.adjusted / p.total, 6) - e.share))  AS worst_gap,
           count(*) FILTER (WHERE e.share IS NULL)             AS unmatched
      FROM hours h
      JOIN person p USING (period, employee_key)
      LEFT JOIN v_labor_effective e
             ON e.period = h.period AND e.employee_key = h.employee_key
            AND e.objective_id = h.objective_id
     GROUP BY h.period, h.employee_key
),
-- Everybody on either side. Starting from the distribution alone hid the
-- person who has hours and no wages, which is the finding this view exists
-- to surface.
everybody AS (
    SELECT period, employee_key FROM labor_allocation
    UNION
    SELECT period, employee_key FROM labor_month
)
SELECT l.period, l.employee_key,
       COALESCE(c.objectives, 0)                           AS objectives,
       p.total                                             AS adjusted_hours,
       cap.available                                       AS available_hours,
       p.total - cap.available                             AS capacity_gap,
       -- **The tolerance is derived, not chosen.** Each row of the log is
       -- recorded to the cent of an hour, so a sum of `n` of them carries
       -- up to n/200 of rounding and nothing more. Picking a round number
       -- instead would be a tolerance that quietly swallows a real
       -- difference on a person with few rows and flags one on a person
       -- with many.
       round(p.roundings / 200.0, 4)                       AS rounding_bound,
       c.worst_gap,
       c.unmatched,
       CASE
           WHEN p.total IS NULL                  THEN 'NO HOURS LOG'
           WHEN NOT EXISTS (SELECT 1 FROM labor_allocation a
                             WHERE a.period = l.period
                               AND a.employee_key = l.employee_key)
                                                 THEN 'HOURS WITHOUT WAGES'
           WHEN c.unmatched > 0                  THEN 'OPEN'
           WHEN c.worst_gap IS NULL              THEN 'NO HOURS LOG'
           WHEN c.worst_gap <= 0.0001            THEN 'TIES'
           ELSE 'OPEN'
       END                                                 AS state,
       CASE
           WHEN p.total IS NULL                  THEN 'NO HOURS LOG'
           WHEN cap.available IS NULL            THEN 'NO CALENDAR'
           WHEN abs(p.total - cap.available) <= p.roundings / 200.0
                                                 THEN 'TIES'
           ELSE 'OPEN'
       END                                                 AS capacity_state
  FROM everybody l
  LEFT JOIN person   p   USING (period, employee_key)
  LEFT JOIN capacity cap USING (period, employee_key)
  LEFT JOIN compared c   USING (period, employee_key);

COMMENT ON VIEW v_labor_hours_check IS
    'Each person''s share of adjusted hours against their share of '
    'distributed wages — the hours log against the distribution built from '
    'it. Three things it can say that nothing else could: NO HOURS LOG, '
    'because thirty-six of the forty-five carry one summary row and an '
    'empty comparison is not a pass; HOURS WITHOUT WAGES, for effort on the '
    'record with no labour cost behind it; and whether a person''s log adds '
    'to what the calendar says their months held.';
