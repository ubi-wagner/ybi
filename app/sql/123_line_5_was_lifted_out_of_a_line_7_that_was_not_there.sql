-- 123 — line 5 was lifted out of a line 7 that was not there
--
-- **Part IX over-reported by $192,087.13 on every record that has a ledger
-- and no classifications** — the chief executive's 2025 compensation, to the
-- cent. Line 7 read 1,789,993.94 against the reference record's 1,597,906.81
-- and the difference is line 5 exactly, so the return did not cross-foot: its
-- lines added to 6,812,635.68 against a profit and loss of 6,775,212.18.
--
-- `098` is right about the rule — *line 5 is an amount lifted out of line 7
-- by person, and the two still add to the wage accounts*. What `099` did not
-- hold is that the two halves of that one act could happen separately. The
-- subtraction lives inside `comp`, which is `WHERE function_990 =
-- 'NOT_APPLICABLE'` — the compensation block, and that exists only once
-- somebody has judged the wage accounts. The addition was `FROM officer o
-- WHERE o.wages > 0`, which needs nothing at all. **The lift was conditional
-- and what it lifted was not.**
--
-- `099`'s own comment shows where the reasoning stopped: *"where no roster is
-- on the record the officer amount is zero and line 7 is unchanged"*. It
-- anticipated a missing **roster** — `096` seeds that, so it is never missing
-- — and not a missing **block**, which is the state every record passes
-- through between the ledger landing and the first judgment.
--
-- **And the second half is worse than the arithmetic.** Line 5 splits by the
-- OFFICER cohort's own effort shares, so on a record where nothing has been
-- judged it was the one line claiming a function allocation — 81.6%
-- programme, 13.5% administration — while every other dollar on the return
-- sat in `NOT_YET_CLASSIFIED`. *That is a column of the 990, not a rounding*,
-- and line 5 was jumping the queue out of it.
--
-- So line 5 appears with the block it is carved out of. On the reference
-- record `comp` carries line 7 and **nothing moves**: the same 192,087.13 on
-- line 5, the same 1,597,906.81 on line 7, the same function columns. On a
-- record nobody has classified, the whole of the payroll is on line 7 under
-- *not yet classified*, which is what is true, and the return foots.
--
-- Found by seeding from an empty database rather than by reading. The
-- reference record has been classified since before `098` existed, so this
-- state had never once been looked at — and four tests that assert the
-- return foots were passing on the only record anybody ran them against.
--
-- The body is lifted from `099`, which is the definition in force; `070`
-- records what retyping one costs. Lifted **by line range**, because `099`
-- carries a semicolon inside a comment — *"Line 7 gives up the officers'
-- wages; line 5 is what it gave up"* — and the extractor I reached for first
-- stopped there and produced half a view. That is written down in CLAUDE.md
-- about this exact shape, and I walked into it anyway.

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
  -- Line 5 belongs to the compensation block and appears with it. It was
  -- emitted whether or not the block existed, so on a record whose payroll
  -- nobody has judged the return added the officers' wages without taking
  -- them off line 7, and Part IX over-reported by exactly one salary.
  SELECT o.period, '5', o.wages, 0, 'OFFICER'
    FROM officer o
   WHERE o.wages > 0
     AND EXISTS (SELECT 1 FROM comp c
                  WHERE c.period = o.period AND c.line_id = '7')),
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

-- The note says the rule and not the state. `100` exists because `094` wrote
-- line 5's note about a state the record then moved out of, so this sentence
-- is written to be true in both: it says when the line appears rather than
-- asserting whether it has.

UPDATE form_990_line
   SET note = note || ' It is carved out of the compensation block, so it '
              'appears once the wage accounts have been judged; until then '
              'the whole of the payroll is on line 7 under *not yet '
              'classified*.'
 WHERE line_id = '5'
   AND note NOT LIKE '%carved out of the compensation block%';
