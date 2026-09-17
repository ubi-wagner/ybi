-- 106 — one column was answering two questions
--
-- `v_asset_control` serves two readers and they ask different things.
-- `v_partition_coverage` reads `needs` for **the partition's** ask — *does
-- every asset name where its money came from* — and `v_report_tie` reads it
-- for **the tie's** — *does the register's depreciation equal the ledger's*.
-- The view's `state` was always the second and its `needs` was always the
-- first, and nothing showed while the funding column was unanswered, because
-- then both asks happened to be the same sentence.
--
-- `102` filled in the third branch and the collision arrived: the close
-- answered all 263 funding sources, the partition went `TIES`, and it went on
-- printing *the register carries 872,811.91 and the ledger charged
-- 850,382.89* — **a finished partition asking for something it already has**,
-- which is `093` in as many words, one view along.
--
-- Found by `test_worklist_product.py`, which asserts exactly that and has
-- failed for this shape once before. A test that has caught a rule twice is
-- the rule being kept.
--
-- So the two asks get two columns. `needs` is the partition's and is left
-- exactly as `085` and `086` built it; `tie_needs` is the difference, and
-- `v_report_tie`'s INVENTORY arm reads that. Neither reader now has to know
-- which question the other was asking.
--
-- Lifted from the definition in force rather than retyped.

CREATE OR REPLACE VIEW v_asset_control AS
 SELECT period,
    ( SELECT count(*) AS count
           FROM asset a
          WHERE a.period = p.period) AS assets,
    ( SELECT count(*) AS count
           FROM asset a
          WHERE a.period = p.period AND NOT (EXISTS ( SELECT 1
                   FROM asset_funding f
                  WHERE f.asset_id = a.asset_id))) AS funding_unknown,
    ( SELECT COALESCE(sum(a.gross_cost), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.period = p.period) AS gross_cost,
    ( SELECT COALESCE(sum(a.depreciation), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.period = p.period) AS register_depreciation,
    ( SELECT COALESCE(sum(v.allowable_depreciation), 0::numeric) AS "coalesce"
           FROM v_asset_allowability v
          WHERE v.period = p.period) AS allowable_depreciation,
    ( SELECT COALESCE(sum(l.amount), 0::numeric) AS "coalesce"
           FROM ledger_line l
          WHERE l.period = p.period AND l.account ~~ '%5010%'::text) AS ledger_depreciation,
    (( SELECT COALESCE(sum(a.depreciation), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.period = p.period)) - (( SELECT COALESCE(sum(l.amount), 0::numeric) AS "coalesce"
           FROM ledger_line l
          WHERE l.period = p.period AND l.account ~~ '%5010%'::text)) AS variance,
    (EXISTS ( SELECT 1
           FROM asset a
          WHERE a.period = p.period)) AS evaluable,
        CASE
            WHEN NOT (EXISTS ( SELECT 1
               FROM asset a
              WHERE a.period = p.period)) THEN 'NO DATA'::text
            WHEN ((( SELECT COALESCE(sum(a.depreciation), 0::numeric) AS "coalesce"
               FROM asset a
              WHERE a.period = p.period)) - (( SELECT COALESCE(sum(l.amount), 0::numeric) AS "coalesce"
               FROM ledger_line l
              WHERE l.period = p.period AND l.account ~~ '%5010%'::text))) = 0::numeric THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
        CASE
            WHEN NOT (EXISTS ( SELECT 1
               FROM asset a
              WHERE a.period = p.period)) THEN 'the asset register, with a funding source per asset'::text
            WHEN (( SELECT count(*) AS count
               FROM asset a
              WHERE a.period = p.period AND NOT (EXISTS ( SELECT 1
                       FROM asset_funding f
                      WHERE f.asset_id = a.asset_id)))) > 0 THEN 'the funding source per asset — the one column the schedule does not carry, and what 200.436(b) turns on'::text
            ELSE ''::text
        END AS needs,
    ( SELECT COALESCE(sum(a.gross_cost), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.period = p.period AND (EXISTS ( SELECT 1
                   FROM asset_funding f
                  WHERE f.asset_id = a.asset_id))) AS funded_cost,
    CASE
        WHEN NOT (EXISTS ( SELECT 1 FROM asset a
                            WHERE a.period = p.period))
          THEN 'the asset register, so the depreciation it carries can be compared to the ledger''s'::text
            WHEN (( SELECT COALESCE(sum(a.depreciation), 0::numeric)
               FROM asset a WHERE a.period = p.period))
                 - (( SELECT COALESCE(sum(l.amount), 0::numeric)
               FROM ledger_line l
              WHERE l.period = p.period AND l.account ~~ '%5010%'::text))
                 <> 0::numeric
              THEN format('The register carries %s of depreciation and the '
                          'ledger charged %s, a difference of %s. '
                          'It is named per cost account on the inventory '
                          'screen: '
                          'buildings agree to the cent and the rest is the '
                          '2026 print of the schedule carrying assets placed '
                          'in service after the year end, plus four '
                          'per-class differences somebody has to attribute.',
                          to_char((SELECT COALESCE(sum(a.depreciation), 0)
                                     FROM asset a WHERE a.period = p.period),
                                  'FM999,999,999.00'),
                          to_char((SELECT COALESCE(sum(l.amount), 0)
                                     FROM ledger_line l
                                    WHERE l.period = p.period
                                      AND l.account ~~ '%5010%'),
                                  'FM999,999,999.00'),
                          to_char((SELECT COALESCE(sum(a.depreciation), 0)
                                     FROM asset a WHERE a.period = p.period)
                                  - (SELECT COALESCE(sum(l.amount), 0)
                                       FROM ledger_line l
                                      WHERE l.period = p.period
                                        AND l.account ~~ '%5010%'),
                                  'FM999,999,999.00'))
        ELSE ''::text
    END AS tie_needs
   FROM fiscal_period p;

COMMENT ON VIEW v_asset_control IS
  'The fixed-asset register: what it carries, how much of it names a funding '
  'source, and whether its depreciation is the ledger''s. Two questions and '
  'two asks — `needs` is the partition''s and `tie_needs` is the '
  'difference''s, because one column answering both printed a sentence about '
  'depreciation on a partition that was finished.';

-- The INVENTORY arm now reads the ask that belongs to it. Lifted from `105`;
-- only that arm moves.
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
  SELECT period, 40, 'RATE', control,
         'the ledger''s live judgments and the payroll register',
         state, variance,
         CASE WHEN state = 'TIES' THEN '' ELSE COALESCE(note, '') END
    FROM v_rate_anchor

  UNION ALL
  SELECT period, 50, 'RATE', 'Each rate''s pool is the ledger''s pool',
         'v_pool_balance, the live decisions over the ledger',
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
         'the hours log, against labor_allocation',
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
         'the register the partition divides',
         state, outstanding, needs FROM v_partition_coverage
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
