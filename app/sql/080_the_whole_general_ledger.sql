-- Every dollar of the general ledger, accounted for.
--
-- `v_classification_coverage` answers *how much of the cost has been judged*,
-- scoped to cost by `v_cost_line` since `064`. That is the right denominator
-- for a rate and the wrong one for the question a controller is actually
-- asked, which is **"have you been through the whole book?"** Measured on the
-- live record the two are 100.0% and 59.7% of very different things: the
-- ledger is 15,500 lines, 5,096 on the profit and loss and 10,404 on the
-- balance sheet, and only 4,038 of them are cost to classify.
--
-- Taking income out of scope in `064` was correct and it also took income out
-- of *view* — the same move this repository has already recorded costing it
-- the America Makes billing, which sat in the Income section for a year one
-- join away from every figure computed without it. A screen that shows only
-- what is in scope cannot be checked against the general ledger it came from.
--
-- So every line lands in exactly one bucket and the buckets add to the book.
-- Two are in scope and two are not, and **the two that are not say why**:
-- "cannot be classified" on its own is the dead end this file keeps finding,
-- and out-of-scope with no reason is that in a new place.
--
-- Absolute dollars, because `039` chose that for coverage deliberately — a
-- group counts by what it moved — and a screen that put a signed figure beside
-- a coverage percentage taken over absolute ones would not add up on its face.

CREATE VIEW v_gl_accounted AS
-- The four buckets, declared once and independently of what is in them.
--
-- A first draft built this list with `SELECT DISTINCT seq FROM buckets`, which
-- is circular: an empty bucket contributes no row, so it is absent from the
-- list of buckets, so it is absent from the answer. The live record printed
-- three rows and *the queue is empty* was indistinguishable from *there is no
-- queue* — `029` reproduced inside the fix written for it.
WITH kinds (seq, bucket, in_scope, why, goes_to) AS (
    VALUES
    (1, 'CLASSIFIED', true,
     'Judged into a cost pool with a reason on the record.',
     '/classify'),
    (2, 'IN THE QUEUE', true,
     'Cost nobody has judged yet. It is never defaulted into a pool, which '
     || 'is why the rate reads high while this is outstanding.',
     '/classify'),
    (3, 'NOT COST — INCOME', false,
     'Grant income and programme fees. A cost pool is for cost, so there is '
     || 'no answer to give these; 2 CFR 200 allocates cost, not revenue. The '
     || 'America Makes billing is in here, which is why it is shown rather '
     || 'than dropped.',
     '/books'),
    (4, 'NOT COST — BALANCE SHEET', false,
     'Movements between accounts, not cost incurred. Both sides of a '
     || 'transfer are here, which is why counting them would make the '
     || 'measure that gates sealing meaningless.',
     '/books')
),
scoped AS (
    SELECT cl.line_id, cl.account, cl.payee, cl.amount, cl.period,
           (dl.decision_id IS NOT NULL) AS decided
      FROM v_cost_line cl
      -- `AND dl.live`: superseding leaves the old row behind, and without this
      -- a reclassified line is counted once per judgment it has ever carried.
      LEFT JOIN decision_line dl ON dl.line_id = cl.line_id AND dl.live
),
lines AS (
    SELECT period, CASE WHEN decided THEN 1 ELSE 2 END AS seq,
           account, payee, amount
      FROM scoped
    UNION ALL
    SELECT period, 3, account, payee, amount
      FROM ledger_line
     WHERE statement = 'P&L' AND section = 'Income'
    UNION ALL
    SELECT period, 4, account, payee, amount
      FROM ledger_line
     WHERE statement = 'BALANCE_SHEET'
),
periods AS (SELECT DISTINCT period FROM ledger_line)
SELECT p.period, k.seq, k.bucket, k.in_scope, k.why, k.goes_to,
       count(l.*)                                            AS lines,
       count(DISTINCT l.account || COALESCE(l.payee, ''))    AS groups,
       COALESCE(sum(abs(l.amount)), 0)                       AS dollars
  FROM periods p
  CROSS JOIN kinds k
  LEFT JOIN lines l ON l.period = p.period AND l.seq = k.seq
 GROUP BY p.period, k.seq, k.bucket, k.in_scope, k.why, k.goes_to;

COMMENT ON VIEW v_gl_accounted IS
'Every general-ledger line in exactly one bucket, so the classification screen '
'can show that the whole book has been accounted for rather than only the part '
'that is in scope. Two buckets are in scope and two are not, and the two that '
'are not carry the reason.';


-- And the control that says the buckets are the book.
--
-- Four buckets that add to something other than the ledger is the shape where
-- a line falls between two `WHERE` clauses and nobody notices — which is what
-- `v_cost_line`'s `section <> 'Income'` would do to a NULL section, if
-- `ledger_line.section` were not NOT NULL DEFAULT ''. It is, so a blank
-- section reads as '' and stays in scope, which is what the intake rule wants:
-- not knowing what something is is a reason to look at it. This holds that,
-- rather than trusting that the next person reads the default the same way.
CREATE VIEW v_gl_accounted_check AS
SELECT b.period,
       b.accounted_lines,
       g.ledger_lines,
       b.accounted_dollars,
       g.ledger_dollars,
       g.ledger_lines - b.accounted_lines       AS line_difference,
       g.ledger_dollars - b.accounted_dollars   AS dollar_difference,
       CASE WHEN g.ledger_lines = 0 THEN 'NO DATA'
            WHEN g.ledger_lines = b.accounted_lines
             AND g.ledger_dollars = b.accounted_dollars THEN 'TIES'
            ELSE 'OPEN' END                     AS state
  FROM (SELECT period, sum(lines) AS accounted_lines,
               sum(dollars) AS accounted_dollars
          FROM v_gl_accounted GROUP BY period) b
  FULL JOIN (SELECT period, count(*) AS ledger_lines,
                    sum(abs(amount)) AS ledger_dollars
               FROM ledger_line GROUP BY period) g USING (period);

COMMENT ON VIEW v_gl_accounted_check IS
'The four buckets against the ledger they came from. NO DATA where no ledger '
'is loaded, because an empty set matching an empty set perfectly is not a pass.';
