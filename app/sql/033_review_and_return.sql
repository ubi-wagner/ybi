-- What a reviewer reads: the rate build-up, the functional allocation behind
-- the Form 990, and the documents each rests on.
--
-- Everything here is a view over judgments already recorded. Nothing computes
-- a new figure, because a figure that first appears on a review screen is a
-- figure that was never classified, sealed or controlled.

-- ── The rate, built up from the pools it came from ────────────────────
--
-- A rate on its own is a number somebody has to take on trust. The build-up
-- is the thing a reviewer actually asks for: what went into the pool, what
-- came out of it and under what authority, what the base was, and which
-- sealed set the whole thing hangs off.
--
-- Joined to the live rate rather than recomputed. Two numbers derived twice
-- are two numbers that can disagree, and the one on the workpaper would be
-- the one nobody could reproduce.
CREATE VIEW v_rate_buildup AS
SELECT r.period,
       r.rate_id,
       r.kind,
       r.pool_amount,
       r.base_type::text                                   AS base_type,
       r.base_amount,
       r.rate,
       r.status,
       r.seal_hash,
       r.computed_at,
       r.computed_by,
       ds.label                                            AS decision_set,
       ds.sealed_at,
       ds.sealed_by,
       -- The pool as the decisions leave it, before anything is carved out.
       -- FRINGE and the combined rate have no single pool of their own, so
       -- these are null rather than zero: zero is a measurement.
       pb.gross                                            AS pool_gross,
       pb.carved                                           AS pool_carved,
       pb.allocable                                        AS pool_allocable,
       (SELECT count(*) FROM carve_out c
         WHERE c.period = r.period
           AND c.pool::text = CASE r.kind WHEN 'G&A' THEN 'G&A'
                                          ELSE r.kind END) AS carve_outs
  FROM rate r
  JOIN decision_set ds ON ds.set_id = r.set_id
  LEFT JOIN v_pool_balance pb
         ON pb.period = r.period
        AND pb.pool::text = CASE r.kind WHEN 'G&A' THEN 'G&A' ELSE r.kind END
 -- `status`, not `superseded_by`. The column exists on the table and no code
 -- path has ever written it: recomputing and unsealing both express
 -- supersession by setting the status, and every other reader in the system
 -- (export, restate, /rates/current) filters on that. Filtering on the dead
 -- column returns superseded rates as live, which is how this view first
 -- showed four SUPERSEDED rates as the rate on file.
 WHERE r.status <> 'SUPERSEDED';

COMMENT ON VIEW v_rate_buildup IS
  'Each live rate with the pool it came from and the seal it hangs off. '
  'Read alongside v_classification_coverage: a rate over an unfinished '
  'classification reads high, which is honest, but it is not final.';


-- ── Form 990 Part IX, Statement of Functional Expenses ────────────────
--
-- The 990 asks for expense by natural category down the side and by function
-- across the top. The classification queue records the function on every
-- judgment, so the return is an aggregation of decisions rather than a
-- second exercise — which is the point of recording it there.
--
-- Two rules this view will not bend:
--
--   * Unclassified cost is a row, not a spread. 2 CFR 200 and the return
--     disagree about many things but not this: an allocation that quietly
--     distributes what nobody has judged is an allocation nobody can support.
--     It appears as NOT_YET_CLASSIFIED and the total is wrong on purpose
--     until it is empty.
--   * The natural category is the account's own parent, not a mapping
--     invented here. A crosswalk to the 990's printed line numbers is a
--     judgment with a preparer's name on it, and it belongs in a table
--     somebody signs rather than in a view.
CREATE VIEW v_form_990_functional AS
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
  LEFT JOIN decision_line dl ON dl.line_id = s.line_id
  LEFT JOIN decision d       ON d.decision_id = dl.decision_id
                            AND d.reversed_at IS NULL
 GROUP BY s.period, s.natural_category,
          COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED');

COMMENT ON VIEW v_form_990_functional IS
  'Part IX by natural category and function. NOT_YET_CLASSIFIED is a column '
  'in its own right: cost nobody has judged is never spread across the '
  'functions, so the return is visibly incomplete until the queue is empty.';


-- ── Is the return ready to file? ──────────────────────────────────────
--
-- The same rule the rate follows. A return assembled over an unfinished
-- classification is not a draft of the right answer, it is a different
-- answer, and saying so on the screen costs nothing.
CREATE VIEW v_form_990_readiness AS
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
                WHERE r.period = p.period AND r.superseded_by IS NULL) AS rate_on_file
  FROM fiscal_period p;

COMMENT ON VIEW v_form_990_readiness IS
  'What stands between the functional allocation and a return somebody '
  'signs. Every figure here is a count of work outstanding, not a score.';
