-- 092 — Form 990 Part IX reported no salaries in any function
--
-- Part IX printed **$2,191,777.54 of payroll with nothing in any of the three
-- columns the return prints** — $1,789,993.94 of wages and $401,783.60 of
-- fringe, the whole of YBI's compensation, filed under `NOT_APPLICABLE`.
-- Programme, management and general, and fundraising added to $4,583,434.64
-- against a printed total of $6,775,212.18, so the row did not cross-foot on
-- a tax return and a reader adding the columns could not find out why.
--
-- It is one word answering two questions. `EXCLUDED` is a *rate* judgment and
-- it is right: `compute` feeds `v_labor_effective.distributed_wages` into
-- `add_labor()`, so a DIRECT judgment on `5140 Employee Wages` would put the
-- payroll in MTDC twice — which `CLAUDE.md` records in as many words. But
-- the classification log set the 990 function from the same judgment, and
-- **which column of the return a salary goes in is a different question from
-- which pool carries it.** Nothing about 200.430 says a wage that must stay
-- out of a cost pool is also outside the Statement of Functional Expenses.
--
-- The driver is the one the eleventh control already insists on: *the fringe
-- base comes from the effort distribution, not from the ledger's wage
-- accounts.* The same distribution says which function the effort served.
-- On the live record it is 83.40% programme, 14.41% management and general,
-- 2.18% fundraising — read from `v_labor_effective` through
-- `cost_objective.objective_type`, which already carries what each objective
-- is for. A second map of that in this view would be free to drift from it;
-- `073` records the cost of writing `'YBI-GA'` as a literal in three places.
--
-- Two things it deliberately does not do:
--
--   * **It splits nothing else.** `5107 Interest Income` and `5108 Other
--     Income` stay `NOT_APPLICABLE`: they are contra-income sitting in the
--     expense section, they are not compensation, and no effort distribution
--     describes them.
--   * **It invents no precision.** The split is largest-remainder against the
--     category total — two functions rounded and the third the residual — so
--     the three add back to what the ledger holds to the cent. `069` is the
--     record of what per-row rounding costs.
--
-- The line count rides on the programme row alone, because the count belongs
-- to the natural category rather than to the split, and the reader who wants
-- it wants one number.

CREATE OR REPLACE VIEW v_labour_function_share AS
WITH effort AS (
  SELECT le.period,
         CASE o.objective_type
           WHEN 'ADMINISTRATION'  THEN 'MANAGEMENT_AND_GENERAL'
           WHEN 'FUNDRAISING/B&P' THEN 'FUNDRAISING'
           -- 200.413 and Appendix IV B.3.d make unallowable activity bear
           -- indirect while recovering nothing; on the return it is somebody
           -- administering the organisation, not delivering a programme.
           WHEN 'UNALLOWABLE'     THEN 'MANAGEMENT_AND_GENERAL'
           ELSE 'PROGRAM'
         END                                            AS function_990,
         le.distributed_wages                           AS wages
    FROM v_labor_effective le
    JOIN cost_objective o ON o.objective_id = le.objective_id)
SELECT period, function_990,
       sum(wages)                                       AS wages,
       round(sum(wages) / NULLIF(sum(sum(wages)) OVER (PARTITION BY period),
                                 0), 6)                 AS share
  FROM effort
 GROUP BY period, function_990;

COMMENT ON VIEW v_labour_function_share IS
  'How the effort distribution divides between the three functions Form 990 '
  'Part IX prints, read through cost_objective.objective_type. It is the '
  'driver for the compensation rows of the return, which carried no function '
  'at all until 092 — the pool judgment said EXCLUDED, which is right about '
  'the rate and says nothing about the column.';


CREATE OR REPLACE VIEW v_form_990_functional AS
WITH scope AS (
  SELECT l.period, l.line_id, l.amount,
         split_part(l.account, ':', 1) AS natural_category,
         l.account
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Expense', 'COGS'))),
judged AS (
  SELECT s.period, s.natural_category, s.account, s.amount, s.line_id,
         COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED') AS function_990
    FROM scope s
    LEFT JOIN decision_line dl ON dl.line_id = s.line_id AND dl.live
    LEFT JOIN decision d ON d.decision_id = dl.decision_id
                        AND d.reversed_at IS NULL),
-- Compensation the pools must not carry, which the return must. The
-- discriminator is the bookkeeper's own top-level grouping rather than a list
-- of account numbers kept here: a hand-kept map of which accounts are payroll
-- is the shape this file has been wrong about four times in one run.
compensation AS (
  SELECT period, natural_category,
         sum(amount) AS amount, count(*) AS lines,
         count(DISTINCT account) AS accounts
    FROM judged
   WHERE function_990 = 'NOT_APPLICABLE'
     AND natural_category = '5129 Payroll Expenses'
   GROUP BY period, natural_category),
split AS (
  SELECT c.period, c.natural_category, f.function_990,
         CASE f.function_990
           WHEN 'PROGRAM' THEN c.amount
             - round(c.amount * COALESCE(
                 (SELECT share FROM v_labour_function_share x
                   WHERE x.period = c.period
                     AND x.function_990 = 'MANAGEMENT_AND_GENERAL'), 0), 2)
             - round(c.amount * COALESCE(
                 (SELECT share FROM v_labour_function_share x
                   WHERE x.period = c.period
                     AND x.function_990 = 'FUNDRAISING'), 0), 2)
           ELSE round(c.amount * f.share, 2)
         END                                            AS amount,
         CASE WHEN f.function_990 = 'PROGRAM' THEN c.lines ELSE 0 END
                                                        AS lines,
         CASE WHEN f.function_990 = 'PROGRAM' THEN c.accounts ELSE 0 END
                                                        AS accounts
    FROM compensation c
    JOIN v_labour_function_share f ON f.period = c.period)
SELECT period, natural_category, function_990,
       sum(amount)             AS amount,
       sum(lines)::bigint      AS lines,
       sum(accounts)::bigint   AS accounts
  FROM (
    SELECT period, natural_category, function_990, amount,
           1 AS lines, 0 AS accounts
      FROM judged
     WHERE NOT (function_990 = 'NOT_APPLICABLE'
                AND natural_category = '5129 Payroll Expenses')
    UNION ALL
    SELECT period, natural_category, function_990, amount, lines, accounts
      FROM split) x
 GROUP BY period, natural_category, function_990;

COMMENT ON VIEW v_form_990_functional IS
  'Form 990 Part IX: natural category down the side, function across the '
  'top. Compensation is split by the effort distribution rather than by the '
  'pool judgment — EXCLUDED keeps the wage accounts out of the cost pools, '
  'which is right, and says nothing about which column of the return they '
  'belong in. Until 092 the whole payroll printed as NOT_APPLICABLE and the '
  'rows did not cross-foot.';
