-- 039 — one definition of coverage
--
-- "How much of the cost has been classified" had two answers in the running
-- system, at the same moment, over the same single decision:
--
--     the classification screen   13.0%   5,096 lines, $17,057,405.96 in scope
--     the auditor's report         2.2%  15,500 lines, $99,281,655.58 in scope
--
-- Same question, same instant, and the controller's screen and the reviewer's
-- report disagreed by a factor of six. Worse, the *classified* figure
-- differed too — $2,219,105.55 against $1,678,057.27 — because one measures
-- a group by what it moved and the other by its net position.
--
-- Worse again, this view disagreed with itself. It printed `classified` and
-- `unclassified` as net sums over every ledger line, and a percentage over
-- *absolute* sums over the same lines: 1,678,057.27 against 12,693,242.03 is
-- 11.7%, and the column beside them said 2.2%. A reader checking the
-- arithmetic on one row could not make it come out.
--
-- `classify.py::coverage` is the one that is right, and it says why in a
-- comment this view predates: balance sheet accounts are not cost, and
-- including them makes the measure that gates sealing meaningless. A journal
-- entry moving money between two accounts is not a cost to classify, and
-- counting both sides of it inflates the denominator until progress reads as
-- a fraction of what it is.
--
-- So the definition moves here, once, and the route reads it. A figure
-- derived twice is one that can disagree with itself, and the workpaper
-- carries the version nobody can reproduce.
--
-- The columns are now all measured the same way — absolute dollars over the
-- P&L scope — so `classified + unclassified = scope_dollars` and the
-- percentage reproduces from the two figures printed beside it. That is the
-- property the old view lacked and the only one that makes a row checkable.

DROP VIEW IF EXISTS v_classification_coverage;

CREATE VIEW v_classification_coverage AS
WITH scope AS (
  SELECT l.line_id, l.period, l.account, l.payee, l.amount,
         (dl.decision_id IS NOT NULL) AS decided
    FROM ledger_line l
    LEFT JOIN decision_line dl ON dl.line_id = l.line_id
    LEFT JOIN decision d ON d.decision_id = dl.decision_id
                        AND d.reversed_at IS NULL
   -- Cost, and only cost. The comment this replaces lived in a handler.
   WHERE l.statement = 'P&L'
)
SELECT period,
       count(*)                                                 AS total_lines,
       count(*) FILTER (WHERE decided)                          AS decided_lines,
       count(DISTINCT (account, payee))                         AS groups_total,
       count(DISTINCT (account, payee)) FILTER (WHERE decided)  AS groups_decided,
       coalesce(sum(abs(amount)), 0)                            AS scope_dollars,
       coalesce(sum(abs(amount)) FILTER (WHERE decided), 0)     AS classified,
       coalesce(sum(abs(amount)) FILTER (WHERE NOT decided), 0) AS unclassified,
       round(100.0 * coalesce(sum(abs(amount)) FILTER (WHERE decided), 0)
             / nullif(sum(abs(amount)), 0), 1)                  AS pct_dollars_covered
  FROM scope
 GROUP BY period;

COMMENT ON VIEW v_classification_coverage IS
  'The one definition of classification coverage, in absolute dollars over '
  'the P&L scope — balance sheet movements are not cost to classify, and '
  'counting both sides of a transfer makes the measure that gates sealing '
  'meaningless. classified + unclassified = scope_dollars and the percentage '
  'reproduces from them, so a reader can check the row. Both the '
  'classification screen and the review screens read this; the two used to '
  'compute it separately and answered 13.0% and 2.2% at the same moment.';
