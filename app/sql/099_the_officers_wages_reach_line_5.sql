-- 099 — the officers' wages come out of line 7 and onto line 5
--
-- `098` put the roster on the record and worked out who reaches line 5. This
-- is the view doing it.
--
-- **It is not a routing.** Every other line of this return is an account
-- prefix in `form_990_account_line`, and line 5 cannot be: the officers'
-- wages and everybody else's are the same account, because payroll posts as
-- two lump journal entries a pay period with no employee dimension. So line 5
-- is an amount lifted out of line 7 **by person**, from the payroll register,
-- and the two still add to the ledger's wage accounts — which is what
-- `test_line_5_comes_out_of_line_7` holds.
--
-- And the two lines are split by **different cohorts of the same effort
-- distribution**. `092` used the estate-wide share because the compensation
-- block is forty-three people; line 5 is one, and her own distribution is on
-- the record — 81.6% programme, 13.5% administration, 4.8% fundraising,
-- against the staff's 83.6 / 14.5 / 1.9. Lines 8, 9 and 10 keep the
-- estate-wide share, because benefits and payroll taxes are everybody's
-- including the officers' and the return leaves them there.

CREATE OR REPLACE VIEW v_form_990_part_ix AS
WITH cost AS (
  SELECT l.period, l.line_id AS ledger_line, l.account, l.amount
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Expense', 'COGS'))),
routed AS (
  SELECT DISTINCT ON (c.period, c.ledger_line)
         c.period, c.ledger_line, c.account, c.amount, m.line_id
    FROM cost c
    JOIN form_990_account_line m
      ON c.account = m.account_prefix
      OR c.account LIKE m.account_prefix || ':%'
   ORDER BY c.period, c.ledger_line, length(m.account_prefix) DESC),
judged AS (
  SELECT r.period, r.line_id, r.amount, r.ledger_line,
         COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED') AS function_990
    FROM routed r
    LEFT JOIN decision_line dl ON dl.line_id = r.ledger_line AND dl.live
    LEFT JOIN decision d ON d.decision_id = dl.decision_id
                        AND d.reversed_at IS NULL),
shares AS (
  SELECT period, 'ALL' AS cohort, function_990, share
    FROM v_labour_function_share
   UNION ALL
  SELECT period, cohort, function_990, share
    FROM v_labour_function_share_by_cohort),
officer AS (
  SELECT period, COALESCE(line_5_wages, 0) AS wages
    FROM v_form_990_officer_pay),
comp AS (
  SELECT period, line_id, sum(amount) AS amount, count(*) AS lines
    FROM judged
   WHERE function_990 = 'NOT_APPLICABLE' AND line_id IN ('7', '8', '9', '10')
   GROUP BY period, line_id),
-- Line 7 gives up the officers' wages; line 5 is what it gave up. Where no
-- roster is on the record the officer amount is zero and line 7 is unchanged,
-- which is exactly what the return said before `098`.
cohorts AS (
  SELECT c.period, c.line_id,
         CASE WHEN c.line_id = '7'
              THEN c.amount - COALESCE(o.wages, 0)
              ELSE c.amount END                            AS amount,
         c.lines,
         CASE WHEN c.line_id = '7' THEN 'STAFF' ELSE 'ALL' END AS cohort
    FROM comp c
    LEFT JOIN officer o ON o.period = c.period
   UNION ALL
  SELECT o.period, '5', o.wages, 0, 'OFFICER'
    FROM officer o WHERE o.wages > 0),
split AS (
  SELECT c.period, c.line_id, s.function_990,
         CASE s.function_990
           WHEN 'PROGRAM' THEN c.amount
             - round(c.amount * COALESCE((SELECT x.share FROM shares x
                  WHERE x.period = c.period AND x.cohort = c.cohort
                    AND x.function_990 = 'MANAGEMENT_AND_GENERAL'), 0), 2)
             - round(c.amount * COALESCE((SELECT x.share FROM shares x
                  WHERE x.period = c.period AND x.cohort = c.cohort
                    AND x.function_990 = 'FUNDRAISING'), 0), 2)
           ELSE round(c.amount * s.share, 2)
         END                                                     AS amount,
         CASE WHEN s.function_990 = 'PROGRAM' THEN c.lines ELSE 0 END AS lines
    FROM cohorts c
    JOIN shares s ON s.period = c.period AND s.cohort = c.cohort),
allocated AS (
  SELECT period, line_id, function_990, amount, 1 AS lines
    FROM judged
   WHERE NOT (function_990 = 'NOT_APPLICABLE' AND line_id IN ('7','8','9','10'))
  UNION ALL
  SELECT period, line_id, function_990, amount, lines FROM split),
by_line AS (
  SELECT period, line_id,
         sum(amount)                                                    AS total,
         sum(amount) FILTER (WHERE function_990 = 'PROGRAM')            AS program,
         sum(amount) FILTER (WHERE function_990 = 'MANAGEMENT_AND_GENERAL') AS management,
         sum(amount) FILTER (WHERE function_990 = 'FUNDRAISING')        AS fundraising,
         sum(amount) FILTER (WHERE function_990 = 'NOT_YET_CLASSIFIED') AS unjudged,
         sum(amount) FILTER (WHERE function_990 = 'NOT_APPLICABLE')     AS not_applicable,
         sum(lines)::bigint                                             AS lines
    FROM allocated GROUP BY period, line_id)
SELECT p.period, fl.line_id, fl.seq, fl.part, fl.label, fl.note,
       COALESCE(b.total, 0)          AS total,
       COALESCE(b.program, 0)        AS program,
       COALESCE(b.management, 0)     AS management,
       COALESCE(b.fundraising, 0)    AS fundraising,
       COALESCE(b.unjudged, 0)       AS unjudged,
       COALESCE(b.not_applicable, 0) AS not_applicable,
       COALESCE(b.lines, 0)          AS lines
  FROM fiscal_period p
 CROSS JOIN form_990_line fl
  LEFT JOIN by_line b ON b.period = p.period AND b.line_id = fl.line_id
 WHERE fl.part = 'IX' OR fl.line_id = '8b';

COMMENT ON VIEW v_form_990_part_ix IS
  'Form 990 Part IX on the return''s own numbered lines, with the one Part '
  'VIII line the form excludes from Part IX. Line 5 is lifted out of line 7 '
  'by person, from the payroll register, because the ledger has no employee '
  'dimension; the two still add to the wage accounts. Each is split by its '
  'own cohort of the effort distribution.';
