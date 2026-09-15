-- 097 — v_form_990_part_ix emitted Part VIII's revenue lines, at zero
--
-- `094` built the view as `fiscal_period CROSS JOIN form_990_line`, so that
-- **every line of Part IX prints whether or not it carries anything** — an
-- empty line is a fact about the year and a `SELECT DISTINCT` over the ledger
-- cannot say it. That is right and it is why the cross join is there.
--
-- `095` then put Part VIII's eight revenue lines into the same
-- `form_990_line` table, because they are lines of the same return. The cross
-- join picked them up, and the expense view began answering with eight
-- revenue lines carrying 0.00 — a shape that reads perfectly and is not true:
-- `V1` is $5,866,141.77 of contributions and grants, reported by the view
-- next to it as nothing.
--
-- Nothing refused it, and the first reader was the comparison report, which
-- printed **total revenue of −154,663.63** — the netted fundraising expense
-- with no revenue behind it. A figure so wrong it could only be a join, which
-- is the good case; the bad case is the one where zero is plausible.
--
-- The view is Part IX plus the one Part VIII line the form *takes out* of
-- Part IX, which is what its own comment already said it was.

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
compensation AS (
  SELECT period, line_id, sum(amount) AS amount, count(*) AS lines
    FROM judged
   WHERE function_990 = 'NOT_APPLICABLE' AND line_id IN ('7', '8', '9', '10')
   GROUP BY period, line_id),
split AS (
  SELECT c.period, c.line_id, f.function_990,
         CASE f.function_990
           WHEN 'PROGRAM' THEN c.amount
             - round(c.amount * COALESCE((SELECT share
                  FROM v_labour_function_share x
                 WHERE x.period = c.period
                   AND x.function_990 = 'MANAGEMENT_AND_GENERAL'), 0), 2)
             - round(c.amount * COALESCE((SELECT share
                  FROM v_labour_function_share x
                 WHERE x.period = c.period
                   AND x.function_990 = 'FUNDRAISING'), 0), 2)
           ELSE round(c.amount * f.share, 2)
         END                                                     AS amount,
         CASE WHEN f.function_990 = 'PROGRAM' THEN c.lines ELSE 0 END AS lines
    FROM compensation c
    JOIN v_labour_function_share f ON f.period = c.period),
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
SELECT p.period,
       fl.line_id,
       fl.seq,
       fl.part,
       fl.label,
       fl.note,
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
  'VIII line whose amounts the form excludes from Part IX. Every Part IX line '
  'prints whether or not it carries anything, because an empty line is a fact '
  'about the year — and no line of Part VIII prints here at all, which 094 '
  'got wrong the moment 095 put the revenue lines in the same table.';
