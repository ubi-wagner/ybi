-- 050: the readiness flag could never turn red.
--
-- `v_form_990_readiness.rate_on_file` asked whether a rate exists whose
-- `superseded_by` is null. **No code path has ever written that column.**
-- Recomputing and unsealing both express supersession through `status`, and
-- every other reader filters on that — which is written out in a comment
-- thirty lines above this one, in the same migration, because the same
-- mistake had just been found in `v_rate_buildup` and presented four
-- SUPERSEDED rates as the rate on file.
--
-- So the flag went true the moment any rate existed and stayed true after an
-- unseal superseded every one of them. On the screen that says whether a tax
-- return can be filed, that is a green light with no way of going out.
--
-- The first instance was fixed with a test scoped to the view it was found
-- in — `test_the_rate_buildup_reads_the_column_the_system_maintains` — which
-- is why the second survived thirty lines away. That test now sweeps every
-- view in every migration.
--
-- And the column goes. Two ways to express one fact is what produced this
-- twice; `status` is the way, and a dead column that looks usable is an
-- invitation. Nothing reads it after the view above is corrected and nothing
-- has ever written it, so there is nothing to migrate.

CREATE OR REPLACE VIEW v_form_990_readiness AS
SELECT p.period,
       COALESCE((SELECT sum(amount) FROM v_form_990_functional f
                  WHERE f.period = p.period
                    AND f.function_990 <> 'NOT_YET_CLASSIFIED'), 0)  AS allocated,
       COALESCE((SELECT sum(amount) FROM v_form_990_functional f
                  WHERE f.period = p.period
                    AND f.function_990 = 'NOT_YET_CLASSIFIED'), 0)   AS unallocated,
       COALESCE((SELECT count(*) FROM v_statement_reconciliation v
                  WHERE v.period = p.period AND NOT v.ties), 0)      AS controls_open,
       COALESCE((SELECT count(*) FROM labor_allocation la
                  WHERE la.period = p.period
                    AND NOT EXISTS (SELECT 1 FROM labor_certification lc
                                     WHERE lc.period = la.period
                                       AND lc.employee_key = la.employee_key)),
                0)                                                   AS uncertified_allocations,
       EXISTS (SELECT 1 FROM rate r
                WHERE r.period = p.period
                  AND r.status <> 'SUPERSEDED')                        AS rate_on_file
  FROM fiscal_period p;

COMMENT ON VIEW v_form_990_readiness IS
  'What stands between the functional allocation and a return somebody '
  'signs. Every figure here is a count of work outstanding, not a score. '
  'rate_on_file reads status, never superseded_by, which nothing writes.';


-- Dropped last, so the view above no longer depends on it.
ALTER TABLE rate DROP COLUMN superseded_by;
