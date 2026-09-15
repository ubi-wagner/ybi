-- 107 — the register was speaking SQL on four of its twenty rows
--
-- `v_rate_anchor` names its four controls the way a database does —
-- `WAGE_BASE_IS_THE_REGISTER`, `FRINGE_POOL_IS_THE_PAYROLL_FRINGE` — and
-- `103` passed `control` straight into the `anchor` column, beside fourteen
-- rows reading *The depreciation entry balances* and *Part IX adds back to
-- the profit and loss*. **A screen that starts speaking SQL** is this file's
-- own phrase for it, written about `DONATION_RATE_MISSING` reaching the
-- controller with no destination, and it is the same defect on the panel a
-- reviewer reads first.
--
-- Worse in a second way that only showed with all four on one page: every one
-- of them said it ties to *the ledger's live judgments and the payroll
-- register*, because the arm carried one `ties_to` for four anchors that
-- answer to different things. `POOLS_ACCOUNT_FOR_JUDGMENTS` compares the
-- decision lines to the pools and touches no payroll at all. **Ties with the
-- wrong thing named is worse than a blank** — the blank is visibly missing,
-- and the wrong one is checkable, checks out, and is about something else.
--
-- The map is **data rather than a `CASE`**, which is what `065` chose for the
-- same reason, and it is a LEFT JOIN so a fifth anchor still reaches the
-- register rather than falling off the end. It reaches it speaking SQL, and
-- `test_every_report_ties_to_the_financials.py` fails on that — the
-- `worklistKinds.js` arrangement, where nothing is lost and nothing is
-- silent.
--
-- Lifted from `106` rather than retyped; only the RATE anchor arm moves.

CREATE OR REPLACE VIEW v_report_tie AS
WITH arms AS (
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

  UNION ALL
  SELECT a.period, 40, 'RATE',
         COALESCE(m.anchor, a.control),
         COALESCE(m.ties_to, ''),
         a.state, a.variance,
         CASE WHEN a.state = 'TIES' THEN '' ELSE COALESCE(a.note, '') END
    FROM v_rate_anchor a
    LEFT JOIN (VALUES
      ('POOLS_ACCOUNT_FOR_JUDGMENTS',
       'The pools account for every judgment',
       'the signed sum of the live decision lines over the ledger'),
      ('WAGE_BASE_IS_THE_REGISTER',
       'The wage base is the payroll register',
       'the payroll register, on the eleventh cross-reference point'),
      ('FRINGE_POOL_IS_THE_PAYROLL_FRINGE',
       'The fringe pool is the six accounts the P&L names',
       'the profit and loss''s six fringe accounts'),
      ('FRINGE_RATE_ON_THE_REGISTER',
       'The fringe rate falls out of its own two parts',
       'the fringe pool over the payroll register, both anchored to source '
       'documents')
    ) AS m(control, anchor, ties_to) ON m.control = a.control

  UNION ALL
  SELECT period, 50, 'RATE', 'Each rate''s pool is the ledger''s pool',
         'the live decisions over the ledger, pool by pool',
         CASE WHEN count(*) = 0                         THEN 'NO DATA'
              WHEN count(*) FILTER (WHERE NOT ties) > 0 THEN 'OPEN'
              ELSE 'TIES' END,
         sum(pool_variance),
         COALESCE(string_agg(kind, ', ') FILTER (WHERE NOT ties), '')
    FROM v_rate_buildup GROUP BY period

  UNION ALL
  SELECT period, 60, 'RATE', 'The carve-outs leave a pool to take a rate over',
         'the overhead pool the 200.465 and 200.436(b) adjustments come out of',
         state, NULL, needs
    FROM v_carve_out_check WHERE pool = 'OVERHEAD'

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

  UNION ALL
  SELECT period, 100, 'TIMESHEET', 'The distribution is the payroll register',
         'the payroll register, which is the fringe denominator',
         state, variance, note
    FROM v_statement_reconciliation WHERE control = 'PAYROLL_REGISTER'

  UNION ALL
  SELECT period, 110, 'TIMESHEET', 'The hours account for the wages',
         'the hours log, against the payroll distribution the rate rests on',
         CASE WHEN count(*) FILTER (WHERE state IN ('HOURS WITHOUT WAGES',
                                                    'OPEN')) > 0 THEN 'OPEN'
              WHEN count(*) FILTER (WHERE state = 'TIES') = 0     THEN 'NO DATA'
              ELSE 'TIES' END,
         NULL,
         trim(both ' ·' from
           COALESCE(CASE WHEN count(*) FILTER (WHERE state = 'EXPLAINED') > 0
                    THEN format('%s difference(s) named on the record: %s. ',
                         count(*) FILTER (WHERE state = 'EXPLAINED'),
                         string_agg(employee_key, ', ')
                           FILTER (WHERE state = 'EXPLAINED')) END, '')
           || COALESCE(CASE WHEN count(*) FILTER (WHERE state = 'NO HOURS LOG') > 0
                       THEN format('%s person(s) carry one summary row and '
                                   'there is nothing to compare.',
                            count(*) FILTER (WHERE state = 'NO HOURS LOG'))
                       END, ''))
    FROM v_labor_hours_check GROUP BY period

  UNION ALL
  SELECT period, 120, 'INVENTORY',
         'The asset register is the ledger''s depreciation',
         'the profit and loss''s depreciation expense, and the balance '
         'sheet''s accumulated depreciation',
         state, variance, tie_needs FROM v_asset_control

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
         CASE WHEN count(*) = 0                                 THEN 'NO DATA'
              WHEN count(*) FILTER (WHERE NOT still_agrees) > 0 THEN 'OPEN'
              ELSE 'TIES' END,
         NULL,
         COALESCE(string_agg(objective_id, ', ')
                  FILTER (WHERE NOT still_agrees), '')
    FROM v_restatement
   WHERE status IN ('PROPOSED', 'SUBMITTED', 'ACCEPTED')
   GROUP BY period

  UNION ALL
  SELECT period, 150, 'PARTITIONS', partition || ' accounts for itself',
         divides, state, outstanding, needs FROM v_partition_coverage
)
SELECT a.period, a.seq, a.report, a.anchor, a.ties_to, a.state,
       a.variance, a.needs
  FROM arms a
 ORDER BY a.seq, a.anchor;

COMMENT ON VIEW v_report_tie IS
  'Whether every report ties to the financials, in one place. Each row reads '
  'the control that already owns its figure rather than computing one. A '
  'view''s private vocabulary is mapped here explicitly — EXPLAINED is a '
  'difference contractor_identity names, and a named difference is closed.';
