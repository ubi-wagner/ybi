-- 042 — coverage counts a line once, however often it has been judged
--
-- `v_classification_coverage` starts from `ledger_line` and LEFT JOINs
-- `decision_line`, which is right — it has to count cost nobody has judged,
-- and an inner join would drop exactly that. But it joined on `line_id`
-- alone, so a line carrying more than one `decision_line` row produced more
-- than one row of output, and the sums multiplied.
--
-- That was harmless for as long as a line could only ever have one. It is not
-- harmless now: reclassifying supersedes, which leaves the old
-- `decision_line` in place with `live = false`, so every reclassified line
-- was counted twice. One reclassification took `classified` from
-- 2,219,105.55 to 4,438,211.10 — exactly double — and coverage from 13.0% to
-- 23.0% over cost that had not changed at all. The scope itself grew, which
-- is the tell: there is no judgment anybody can make that changes how much
-- there is to judge.
--
-- Found by the propagation drive, which asserts that a reclassification moves
-- the pools and moves nothing else. Nothing on a screen would have shown it —
-- coverage would simply have read high, in the direction that flatters, and
-- the more work Tom did the further out it would have drifted.
--
-- `dl.live` is the fix and it is the same filter every other view that joins
-- from the ledger side already had. This one was written before anything
-- superseded and never needed it until now.

CREATE OR REPLACE VIEW v_classification_coverage AS
WITH scope AS (
  SELECT l.line_id, l.period, l.account, l.payee, l.amount,
         (dl.decision_id IS NOT NULL) AS decided
    FROM ledger_line l
    -- `dl.live` is load-bearing. Without it a superseded line joins twice
    -- and every sum below doubles for it.
    LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
    LEFT JOIN decision d ON d.decision_id = dl.decision_id
                        AND d.reversed_at IS NULL
   -- Cost, and only cost.
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
  'the P&L scope. Joins decision_line on dl.live, so a line superseded by a '
  'reclassification is counted once rather than once per judgment it has '
  'ever carried. classified + unclassified = scope_dollars and the '
  'percentage reproduces from them, so a reader can check the row.';
