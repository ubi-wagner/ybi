-- 054: a P&L with no COGS line computed its net income as nought.
--
-- `PL_FOOTING` is the first of the eleven and it asks the plainest question
-- in the register: does net income as the profit and loss computes it equal
-- what the balance sheet carries in equity. It computed it as
--
--     sum(Income) - sum(Expense) - sum(COGS) + sum(Other Income)
--
-- with each term a `FILTER`ed aggregate and a single `COALESCE` around the
-- **whole** expression. A `FILTER` that matches no rows is NULL, and NULL
-- propagates through the arithmetic — so a period whose P&L has no COGS
-- section, or no Other Income section, produced NULL for the entire
-- calculation and the outer COALESCE turned it into **0.00**.
--
-- YBI's 2025 export happens to carry all four sections (COGS $37,261.00 in
-- two accounts, Other Income $116,948.46 in two), which is why this has
-- never shown. It was found by building a fixture period from the control
-- definitions rather than from what makes them pass — a small nonprofit P&L
-- with no cost of goods sold, which is an ordinary thing for a P&L to be.
--
-- ── Why it is worse than a wrong figure ──────────────────────────────
--
-- The variance would read as the whole of net income, which somebody would
-- notice. The dangerous case is quieter: a period whose sheet has no
-- printed "Net income" leaf either — an early import, a partial export —
-- compares **0 against 0 and ties**. That is the defect `029` was written to
-- close, living inside one of the eleven points `029` was checking.
--
-- `029` made each control say whether it could be *evaluated*, and
-- PL_FOOTING passes that test the moment a P&L and a sheet both exist. It
-- had no way of knowing that the arithmetic in between had collapsed.
--
-- The body below is lifted from `pg_get_viewdef` and one expression is
-- changed: each term carries its own COALESCE, so an absent section
-- contributes nothing instead of erasing the sum. Retyping a view body from
-- memory rewrote how every line of the 990 was categorised once already.

CREATE OR REPLACE VIEW v_statement_reconciliation_core AS
 WITH p AS (
         SELECT fiscal_period.period
           FROM fiscal_period
        ), reg AS (
         SELECT p.period,
            10 AS seq,
            'PL_FOOTING'::text AS control,
            'VARIANCE'::text AS basis,
            'Profit and loss foots to the net income the sheet carries'::text AS description,
            'P&L sections'::text AS left_label,
            COALESCE(( SELECT COALESCE(sum(a.amount) FILTER (WHERE a.section = 'Income'::text), 0)
                            - COALESCE(sum(a.amount) FILTER (WHERE a.section = 'Expense'::text), 0)
                            - COALESCE(sum(a.amount) FILTER (WHERE a.section = 'COGS'::text), 0)
                            + COALESCE(sum(a.amount) FILTER (WHERE a.section = 'Other Income'::text), 0)
                   FROM pl_account a
                  WHERE a.period = p.period), 0::numeric) AS left_value,
            'Balance sheet net income'::text AS right_label,
            COALESCE(( SELECT b.amount
                   FROM bs_account b
                  WHERE b.period = p.period AND b.leaf ~~* 'net income%'::text AND NOT b.is_rollup
                 LIMIT 1), 0::numeric) AS right_value,
            0::numeric AS exceptions,
            'Net income as the P&L computes it must equal what the sheet carries in equity. Two exports that disagree are two different moments in the same books, and everything built on either is suspect.'::text AS note
           FROM p
        UNION ALL
         SELECT p.period,
            20,
            'BS_FOOTING'::text,
            'VARIANCE'::text,
            'Balance sheet balances'::text,
            'Assets'::text,
            COALESCE(( SELECT sum(b.amount) AS sum
                   FROM bs_account b
                  WHERE b.period = p.period AND b.side = 'ASSET'::text AND NOT b.is_rollup), 0::numeric) AS "coalesce",
            'Liabilities and equity'::text,
            COALESCE(( SELECT sum(b.amount) AS sum
                   FROM bs_account b
                  WHERE b.period = p.period AND (b.side = ANY (ARRAY['LIABILITY'::text, 'EQUITY'::text])) AND NOT b.is_rollup), 0::numeric) AS "coalesce",
            0,
            'Assets less liabilities and equity.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            30,
            'GL_PROMOTE_COMPLETE'::text,
            'VARIANCE'::text,
            'Every staged line reached the ledger'::text,
            'Dated lines staged'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM staging_line s
                     JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'::source_report AND b.status = 'ACCEPTED'::import_status AND s.txn_date IS NOT NULL), 0::bigint) AS "coalesce",
            'Lines in the ledger'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM ledger_line l
                  WHERE l.period = p.period), 0::bigint) AS "coalesce",
            0,
            'The promote path dedupes on each line''s natural key. When two genuinely different lines hash alike one is dropped and nothing raises: 71 lines carrying $24,082.67 went that way before the key learned to number repeats. This counts them.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            40,
            'GL_SUBTOTALS'::text,
            'VARIANCE'::text,
            'Printed account totals agree with the parsed lines'::text,
            'Printed'::text,
            COALESCE(( SELECT sum(s.printed_total) AS sum
                   FROM staging_subtotal s
                     JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'::source_report AND b.status = 'ACCEPTED'::import_status), 0::numeric) AS "coalesce",
            'Parsed'::text,
            COALESCE(( SELECT sum(s.parsed_total) AS sum
                   FROM staging_subtotal s
                     JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'::source_report AND b.status = 'ACCEPTED'::import_status), 0::numeric) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM staging_subtotal s
                     JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'::source_report AND b.status = 'ACCEPTED'::import_status AND abs(s.parsed_total - s.printed_total) > 0.005), 0::bigint) AS "coalesce",
            'QuickBooks prints its own account totals. Reconciling against them catches almost every parsing mistake and costs nothing.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            50,
            'GL_PL_SECTION'::text,
            'VARIANCE'::text,
            'Ledger P&L-scope activity agrees with the P&L by section'::text,
            'Ledger'::text,
            COALESCE(( SELECT sum(l.amount) AS sum
                   FROM ledger_line l
                  WHERE l.period = p.period AND l.statement = 'P&L'::text), 0::numeric) AS "coalesce",
            'P&L'::text,
            COALESCE(( SELECT sum(a.amount) AS sum
                   FROM pl_account a
                  WHERE a.period = p.period), 0::numeric) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM ( SELECT COALESCE(g.section, a.section) AS section
                           FROM ( SELECT ledger_line.section,
                                    sum(ledger_line.amount) AS amt
                                   FROM ledger_line
                                  WHERE ledger_line.period = p.period AND ledger_line.statement = 'P&L'::text
                                  GROUP BY ledger_line.section) g
                             FULL JOIN ( SELECT pl_account.section,
                                    sum(pl_account.amount) AS amt
                                   FROM pl_account
                                  WHERE pl_account.period = p.period
                                  GROUP BY pl_account.section) a ON a.section = g.section
                          WHERE round(COALESCE(g.amt, 0::numeric) - COALESCE(a.amt, 0::numeric), 2) <> 0::numeric) x), 0::bigint) AS "coalesce",
            'Section totals are where a mis-sectioned account shows: four leaves in this chart sit under both an income and an expense parent, and reading an expense as revenue moves the section without moving the grand total.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            60,
            'GL_PL_ACCOUNT'::text,
            'EXCEPTIONS'::text,
            'Ledger agrees with the P&L account by account'::text,
            'Gross difference'::text,
            COALESCE(( SELECT sum(abs(v.gross_variance)) AS sum
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period), 0::numeric) AS "coalesce",
            'Left unexplained'::text,
            COALESCE(( SELECT sum(abs(v.unexplained)) AS sum
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period), 0::numeric) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.unexplained <> 0::numeric), 0::bigint) AS "coalesce",
            'Sections can tie while accounts do not: money moved between two expense accounts nets to nothing at the section line. Each account that differs is either a named reconciling item with the ledger lines behind it, or it is unexplained.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            70,
            'GL_PL_COVERAGE'::text,
            'EXCEPTIONS'::text,
            'Every P&L account exists on both sides'::text,
            'Ledger accounts absent from the P&L'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.gl_lines > 0 AND v.pl_amount = 0::numeric AND v.section IS NULL), 0::bigint) AS "coalesce",
            'P&L accounts with no ledger lines'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.gl_lines = 0 AND v.pl_amount <> 0::numeric), 0::bigint) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_pl_account v
                  WHERE v.period = p.period AND (v.gl_lines > 0 AND v.pl_amount = 0::numeric AND v.section IS NULL OR v.gl_lines = 0 AND v.pl_amount <> 0::numeric)), 0::bigint) AS "coalesce",
            'A P&L account with no ledger behind it cannot be classified, and a ledger account off the P&L is cost with nowhere to land.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            80,
            'GL_BS_ACCOUNT'::text,
            'EXCEPTIONS'::text,
            'Opening balance plus the year''s movement equals the sheet'::text,
            'Accounts tied'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet AND v.variance = 0::numeric), 0::bigint) AS "coalesce",
            'Accounts off'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet AND v.variance <> 0::numeric), 0::bigint) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet AND v.variance <> 0::numeric), 0::bigint) AS "coalesce",
            'The tie the system could not make until the ledger''s opening balances were kept. It proves the sheet off the ledger rather than trusting two exports to agree.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            90,
            'GL_BS_COVERAGE'::text,
            'EXCEPTIONS'::text,
            'Accounts absent from the sheet closed at zero'::text,
            'Absent, closing at zero'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet AND v.absent_because_zero), 0::bigint) AS "coalesce",
            'Absent, carrying a balance'::text,
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet AND NOT v.absent_because_zero), 0::bigint) AS "coalesce",
            COALESCE(( SELECT count(*) AS count
                   FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet AND NOT v.absent_because_zero), 0::bigint) AS "coalesce",
            'QuickBooks omits an account that ends at zero, which is a complete explanation and a checkable one. An absent account still carrying a balance is a hole in the sheet.'::text
           FROM p
        UNION ALL
         SELECT p.period,
            100,
            'SEGMENTATION'::text,
            'VARIANCE'::text,
            'Split lines still sum to the lines they came from'::text,
            'Ledger'::text,
            COALESCE(( SELECT s.source_total
                   FROM v_segmentation_control s
                  WHERE s.period = p.period), 0::numeric) AS "coalesce",
            'Analytical'::text,
            COALESCE(( SELECT s.analytical_total
                   FROM v_segmentation_control s
                  WHERE s.period = p.period), 0::numeric) AS "coalesce",
            0,
            'Splitting a line for classification is an analytical act on the same money. It must not change what there is.'::text
           FROM p
        )
 SELECT period,
    seq,
    control,
    basis,
    description,
    left_label,
    left_value,
    right_label,
    right_value,
    round(left_value - right_value, 2) AS variance,
    exceptions,
        CASE basis
            WHEN 'VARIANCE'::text THEN round(left_value - right_value, 2) = 0::numeric AND exceptions = 0::numeric
            WHEN 'EXCEPTIONS'::text THEN exceptions = 0::numeric
            ELSE NULL::boolean
        END AS ties,
    note
   FROM reg;
;

COMMENT ON VIEW v_statement_reconciliation_core IS
  'The eleven cross-reference points, before the evaluability guard in 029 '
  'is applied. PL_FOOTING coalesces each section term separately: a FILTER '
  'over no rows is NULL, and one COALESCE around the whole expression let a '
  'P&L with no COGS compute its net income as nought — which ties against a '
  'sheet that has no net income line either.';
