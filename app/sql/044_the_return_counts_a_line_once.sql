-- 044 — the return counts a line once, however often it was judged
--
-- `v_form_990_functional` prints Part IX by natural category and function,
-- with `NOT_YET_CLASSIFIED` as a column in its own right. It joined
-- `decision_line` on `line_id` alone, so a line that had been reclassified
-- produced two rows: one under the function its live judgment gives it, and
-- one under NOT_YET_CLASSIFIED, because the reversed `decision_line` survives
-- the join and its decision does not.
--
-- The same cost would have appeared twice on a tax return — once judged and
-- once as unjudged — and the total would have been over by the amount of
-- everything anybody had ever changed their mind about. Nothing would have
-- shown it: the return is *supposed* to carry a NOT_YET_CLASSIFIED column
-- while work is open, so the extra figure would have looked like work
-- remaining rather than like the same dollars counted twice.
--
-- Third time for this exact shape. `v_classification_coverage` (042) and the
-- classification queue had it too, and all three were written before anything
-- could supersede. `tests/test_supersession.py` sweeps for the pattern now
-- rather than waiting for the next one to be found by hand.
--
-- Only the join changes. Everything else is 033's definition verbatim — the
-- first draft of this migration rewrote the scope CTE from memory and got
-- the natural category wrong, which would have silently recategorised every
-- line on the return.

CREATE OR REPLACE VIEW v_form_990_functional AS
WITH scope AS (
  SELECT l.period, l.line_id, l.amount,
         -- The top of the account path: "Management & Administrative
         -- Expenses:5205 Travel:5206 Travel" is Travel's natural home and
         -- the first segment is what the reader recognises.
         split_part(l.account, ':', 1)                     AS natural_category,
         l.account
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Expense', 'COGS')))
SELECT s.period,
       s.natural_category,
       COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED')  AS function_990,
       sum(s.amount)                                         AS amount,
       count(*)                                              AS lines,
       count(DISTINCT s.account)                             AS accounts
  FROM scope s
  -- `dl.live`: without it a reclassified line lands in its function
  -- *and* in NOT_YET_CLASSIFIED, and the return is over by the amount
  -- of everything anybody ever changed their mind about.
  LEFT JOIN decision_line dl ON dl.line_id = s.line_id AND dl.live
  LEFT JOIN decision d       ON d.decision_id = dl.decision_id
                            AND d.reversed_at IS NULL
 GROUP BY s.period, s.natural_category,
          COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED');

COMMENT ON VIEW v_form_990_functional IS
  'Part IX by natural category and function. NOT_YET_CLASSIFIED is a column '
  'in its own right: cost nobody has judged is never spread across the '
  'functions, so the return is visibly incomplete until the queue is empty. '
  'Joins decision_line on dl.live, so a reclassified line appears once — it '
  'used to appear twice, in its function and as unjudged.';
