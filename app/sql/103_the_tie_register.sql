-- 103 — one register saying whether every report ties to the financials
--
-- Twenty-two control-shaped views and nothing that collects them, so *does
-- everything we publish tie to the books* had twenty-two answers on
-- twenty-two screens and the reader kept the list. That is the hand-kept map
-- at its purest.
--
-- One row per report and anchor. **Each arm reads the control that already
-- owns the figure** — nothing here computes a tie, because a second
-- derivation of a control is one figure computed twice and the two can
-- disagree.
--
-- Three rules it keeps:
--
--   * **One vocabulary.** `v_labor_hours_check` answers `NO HOURS LOG` and
--     `HOURS WITHOUT WAGES`; `v_partition_coverage` answers TIES, OPEN and
--     NO DATA. `084` shipped a walk step that passed a view's own words
--     through and printed a state nothing renders. Every arm maps explicitly,
--     and `NO DATA` is never softened to a pass.
--   * **Name what it ties *to*.** A control that says TIES without saying
--     against which statement is the citation-with-no-document shape.
--   * **Carry the variance.** OPEN and not by how much is a dead end, which
--     is what `102` had to fix in the one report on this record that does not
--     tie.

CREATE OR REPLACE VIEW v_report_tie AS
WITH arms AS (
  -- The books, against themselves. Eleven cross-reference points, collapsed
  -- to the worst of them: a register of controls whose own row reported TIES
  -- while one of its eleven was open would be worse than no row.
  SELECT period, 10 AS seq, 'BOOKS' AS report,
         'The eleven cross-reference points' AS anchor,
         'the general ledger, the profit and loss, the balance sheet and the '
         'payroll register' AS ties_to,
         CASE WHEN count(*) FILTER (WHERE state = 'OPEN') > 0    THEN 'OPEN'
              WHEN count(*) FILTER (WHERE state = 'NO DATA') > 0 THEN 'NO DATA'
              WHEN count(*) = 0                                  THEN 'NO DATA'
              ELSE 'TIES' END AS state,
         NULL::numeric AS variance,
         COALESCE(string_agg(control, ', ')
                  FILTER (WHERE state <> 'TIES'), '') AS needs
    FROM v_statement_reconciliation GROUP BY period

  UNION ALL
  SELECT period, 20, 'BOOKS', 'The depreciation entry balances',
         'the balance sheet''s accumulated depreciation against the profit '
         'and loss''s depreciation expense',
         state, variance, needs
    FROM v_depreciation_posted_check

  UNION ALL
  SELECT period, 30, 'BOOKS', 'Every ledger line is accounted for',
         'the whole general ledger, in four buckets',
         state, dollar_difference,
         CASE WHEN state = 'TIES' THEN ''
              ELSE format('%s line(s) and %s fall between the four buckets.',
                          line_difference,
                          to_char(dollar_difference, 'FM999,999,999.00'))
         END FROM v_gl_accounted_check

  -- The rate.
  UNION ALL
  -- `note` rather than `needs`: the anchor register's own column name, read
  -- off the schema. Four views in this one view spell it differently.
  SELECT period, 40, 'RATE', control,
         'the ledger''s live judgments and the payroll register',
         state, variance,
         CASE WHEN state = 'TIES' THEN '' ELSE COALESCE(note, '') END
    FROM v_rate_anchor

  UNION ALL
  SELECT period, 50, 'RATE', 'Each rate''s pool is the ledger''s pool',
         'v_pool_balance, the live decisions over the ledger',
         CASE WHEN count(*) = 0                              THEN 'NO DATA'
              WHEN count(*) FILTER (WHERE NOT ties) > 0      THEN 'OPEN'
              ELSE 'TIES' END,
         sum(pool_variance),
         COALESCE(string_agg(kind, ', ') FILTER (WHERE NOT ties), '')
    FROM v_rate_buildup GROUP BY period

  UNION ALL
  SELECT period, 60, 'RATE', 'The carve-outs leave a pool to take a rate over',
         'the overhead pool the 200.465 and 200.436(b) adjustments come out of',
         state, NULL, needs
    FROM v_carve_out_check WHERE pool = 'OVERHEAD'

  -- The return.
  UNION ALL
  SELECT period, 70, 'FORM_990', 'Part IX adds back to the profit and loss',
         'the profit and loss''s Expense and COGS sections',
         state, variance, needs FROM v_form_990_line_check

  UNION ALL
  SELECT period, 80, 'FORM_990', 'Part VIII adds back to the profit and loss',
         'the profit and loss''s Income and Other Income sections',
         state, variance, needs FROM v_form_990_revenue_check

  UNION ALL
  SELECT period, 90, 'FORM_990', 'Part VII names everybody the register pays',
         'the payroll register', state, NULL, needs
    FROM v_form_990_officer_check

  -- The labour evidence.
  UNION ALL
  SELECT period, 100, 'TIMESHEET', 'The distribution is the payroll register',
         'the payroll register, which is the fringe denominator',
         state, variance, note
    FROM v_statement_reconciliation WHERE control = 'PAYROLL_REGISTER'

  UNION ALL
  SELECT period, 110, 'TIMESHEET', 'The hours account for the wages',
         'the hours log, against labor_allocation',
         -- Its own vocabulary, mapped. `NO HOURS LOG` is thirty-five people
         -- with one summary row and nothing to compare, which is NO DATA and
         -- not a pass; `HOURS WITHOUT WAGES` is effort on the record with no
         -- cost behind it, which is open.
         CASE WHEN count(*) FILTER (WHERE state = 'HOURS WITHOUT WAGES') > 0
                   OR count(*) FILTER (WHERE state = 'OPEN') > 0  THEN 'OPEN'
              WHEN count(*) FILTER (WHERE state = 'TIES') = 0     THEN 'NO DATA'
              ELSE 'TIES' END,
         NULL,
         COALESCE(string_agg(DISTINCT state, ', ')
                  FILTER (WHERE state <> 'TIES'), '')
    FROM v_labor_hours_check GROUP BY period

  -- The registers the rate rests on.
  UNION ALL
  SELECT period, 120, 'INVENTORY',
         'The asset register is the ledger''s depreciation',
         'the profit and loss''s depreciation expense, and the balance '
         'sheet''s accumulated depreciation',
         state, variance, needs FROM v_asset_control

  UNION ALL
  SELECT period, 130, 'INVOICES', 'The invoice register is the grant income',
         'account 3900 Grant Income, per objective',
         CASE WHEN count(*) = 0                             THEN 'NO DATA'
              WHEN count(*) FILTER (WHERE state = 'OPEN') > 0 THEN 'OPEN'
              ELSE 'TIES' END,
         sum(variance) FILTER (WHERE state = 'OPEN'),
         COALESCE(string_agg(objective_id || ' ' ||
                             to_char(variance, 'FM999,999,999.00'), '; ')
                  FILTER (WHERE state = 'OPEN'), '')
    FROM v_invoice_income_tie GROUP BY period

  UNION ALL
  SELECT period, 140, 'RESTATE',
         'Each claim still measures its own population',
         'the invoice register it was computed over',
         CASE WHEN count(*) = 0                                  THEN 'NO DATA'
              WHEN count(*) FILTER (WHERE NOT still_agrees) > 0  THEN 'OPEN'
              ELSE 'TIES' END,
         NULL,
         COALESCE(string_agg(objective_id, ', ')
                  FILTER (WHERE NOT still_agrees), '')
    FROM v_restatement
   WHERE status IN ('PROPOSED', 'SUBMITTED', 'ACCEPTED')
   GROUP BY period

  UNION ALL
  SELECT period, 150, 'PARTITIONS', partition || ' accounts for itself',
         'the register the partition divides',
         state, outstanding, needs FROM v_partition_coverage
)
SELECT a.period, a.seq, a.report, a.anchor, a.ties_to, a.state,
       a.variance, a.needs
  FROM arms a
 ORDER BY a.seq, a.anchor;

COMMENT ON VIEW v_report_tie IS
  'Whether every report ties to the financials, in one place. Each row reads '
  'the control that already owns its figure rather than computing one — a '
  'second derivation of a control is one figure computed twice. The states '
  'are the register''s own three and a view''s private vocabulary is mapped '
  'rather than passed through, which 084 shipped once.';


CREATE OR REPLACE VIEW v_report_tie_summary AS
SELECT period,
       count(*)                                      AS anchors,
       count(*) FILTER (WHERE state = 'TIES')        AS ties,
       count(*) FILTER (WHERE state = 'OPEN')        AS open,
       count(*) FILTER (WHERE state = 'NO DATA')     AS no_data,
       CASE WHEN count(*) FILTER (WHERE state = 'OPEN') > 0    THEN 'OPEN'
            WHEN count(*) FILTER (WHERE state = 'NO DATA') > 0 THEN 'NO DATA'
            WHEN count(*) = 0                                  THEN 'NO DATA'
            ELSE 'TIES' END                          AS state,
       COALESCE(string_agg(report || ' · ' || anchor, '; ')
                FILTER (WHERE state = 'OPEN'), '')   AS open_anchors
  FROM v_report_tie GROUP BY period;

COMMENT ON VIEW v_report_tie_summary IS
  'The one line. TIES only when every anchor does, because a summary that '
  'rounded a NO DATA up to a pass is the shape 029 exists for.';
