-- 045 — one rule, no exceptions: a join to decision_line filters live
--
-- Three more views join `decision_line` by `line_id` without `dl.live`, and
-- all three are safe — each inner-joins to a decision filtered on
-- `reversed_at IS NULL`, so a superseded row is dropped by the decision join
-- before it can multiply anything.
--
-- Safe by luck, though, not by intent. The rule that protects this system is
-- "every join to decision_line by line_id says dl.live", and a rule with an
-- exception for "unless the next join happens to be inner" is one somebody
-- gets wrong the day they turn one of these into a LEFT JOIN to show a zero.
-- Three views already had this defect for real; these three are one edit away
-- from being the fourth.
--
-- So the filter goes on, redundantly, and `tests/test_supersession.py` sweeps
-- for the pattern with no exceptions to remember.
--
-- Only the join conditions change. Every other character is the existing
-- definition, lifted rather than retyped — one migration in this series
-- rewrote a view body from memory and silently changed how the Form 990
-- categorises every line, and the first draft of this one ran a view body
-- into the next view's CREATE and failed the boot.


CREATE OR REPLACE VIEW v_evidence_coverage AS
SELECT l.period,
       d.pool,
       sum(abs(l.amount))                                        AS dollars,
       sum(abs(l.amount)) FILTER (WHERE a.attachment_id IS NOT NULL) AS documented,
       round(100.0 * sum(abs(l.amount)) FILTER (WHERE a.attachment_id IS NOT NULL)
             / nullif(sum(abs(l.amount)), 0), 1)                 AS pct_documented
  FROM ledger_line l
  JOIN decision_line dl ON dl.line_id = l.line_id
                   AND dl.live
  JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
  LEFT JOIN attachment a
         ON a.target_type = 'LEDGER_LINE' AND a.target_id = l.line_id
        AND a.detached_at IS NULL
 GROUP BY l.period, d.pool;


CREATE OR REPLACE VIEW v_charge_code AS
SELECT o.period, o.objective_id, o.label, o.objective_type, o.is_federal,
       o.is_final, o.active, o.cfda,
       a.award_id, a.sponsor, a.instrument, a.ceiling_federal,
       a.period_start, a.period_end,
       (SELECT count(*) FROM charge_authority ca
         WHERE ca.objective_id = o.objective_id AND ca.period = o.period
           AND ca.revoked_at IS NULL)                        AS people_authorised,
       (SELECT COALESCE(sum(t.hours), 0) FROM timesheet_entry t
         WHERE t.objective_id = o.objective_id AND t.period = o.period
           AND t.superseded_at IS NULL)                      AS hours_charged,
       (SELECT count(DISTINCT t.employee_key) FROM timesheet_entry t
         WHERE t.objective_id = o.objective_id AND t.period = o.period
           AND t.superseded_at IS NULL)                      AS people_charging,
       (SELECT COALESCE(sum(la.reconstructed_units), 0)
          FROM labor_allocation la
         WHERE la.objective_id = o.objective_id AND la.period = o.period) AS wages_distributed,
       (SELECT COALESCE(sum(l.amount), 0) FROM ledger_line l
          JOIN decision_line dl ON dl.line_id = l.line_id
                   AND dl.live
          JOIN decision d ON d.decision_id = dl.decision_id
                         AND d.reversed_at IS NULL
         WHERE d.objective_id = o.objective_id AND l.period = o.period) AS cost_classified
  FROM cost_objective o
  LEFT JOIN award a ON a.objective_id = o.objective_id;


CREATE OR REPLACE VIEW v_award_performance AS
SELECT a.award_id, a.objective_id, a.sponsor, a.instrument,
       a.ceiling_federal, a.cost_share_required,
       a.period_start, a.period_end,
       o.period, o.label AS objective_label, o.is_federal, o.cfda,
       (SELECT count(*) FROM milestone m WHERE m.award_id = a.award_id) AS milestones,
       (SELECT count(*) FROM milestone m WHERE m.award_id = a.award_id
          AND m.state IN ('DELIVERED','ACCEPTED','INVOICED','PAID'))    AS milestones_done,
       (SELECT count(*) FROM award_term t WHERE t.award_id = a.award_id) AS terms,
       COALESCE((SELECT sum(i.direct_claimed + i.indirect_claimed)
                   FROM invoice i WHERE i.award_id = a.award_id), 0)    AS invoiced,
       COALESCE((SELECT sum(r.amount) FROM receipt r
                   JOIN invoice i ON i.invoice_id = r.invoice_id
                  WHERE i.award_id = a.award_id), 0)                    AS received,
       COALESCE((SELECT sum(l.amount) FROM ledger_line l
                   JOIN decision_line dl ON dl.line_id = l.line_id
                   AND dl.live
                   JOIN decision d ON d.decision_id = dl.decision_id
                                  AND d.reversed_at IS NULL
                  WHERE d.objective_id = a.objective_id
                    AND l.period = o.period), 0)                        AS cost_classified,
       COALESCE((SELECT sum(la.reconstructed_units) FROM labor_allocation la
                  WHERE la.objective_id = a.objective_id
                    AND la.period = o.period), 0)                       AS labor_distributed
  FROM award a
  JOIN cost_objective o ON o.objective_id = a.objective_id;
