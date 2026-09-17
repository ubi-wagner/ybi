-- 101 — one register saying whether every report ties to the financials
--
-- The system has twenty-two control-shaped views and **nothing that collects
-- them**. So *does everything we publish tie to the books* had no answer: it
-- had twenty-two answers, on twenty-two screens, and a reader had to know
-- which ones mattered and go and look at each. That is the hand-kept map at
-- its purest — the reader keeps the list.
--
-- `v_report_tie` is one row per report and anchor, each **reading the control
-- that already owns the figure**. Nothing here computes a tie; a second
-- derivation of a control is one figure computed twice, which is the thing
-- that can disagree with itself.
--
-- Three things it has to do that a list of views would not:
--
--   * **Speak one vocabulary.** `v_labor_hours_check` answers `NO HOURS LOG`
--     and `HOURS WITHOUT WAGES`; `v_partition_coverage` answers TIES, OPEN
--     and NO DATA. `084` shipped a walk step that passed a view's own words
--     straight through and printed a state nothing renders. Every arm maps
--     explicitly.
--   * **Name the financial statement each report answers to**, because
--     *ties* with nothing said about *to what* is the citation-with-no-
--     document shape.
--   * **Carry the variance where there is one.** A control that says OPEN and
--     not by how much is a dead end, which is what `v_asset_control` did: it
--     is the one report on this record that does not tie, by $22,429.02, and
--     its `needs` was **blank** — `085` gave it a branch for a register with
--     no funding source and `098`'s work filled that in, so the reason went
--     blank while the state stayed OPEN for a different cause. `086` and
--     `093` are the same defect in the walk and the partitions; this is the
--     third arm of the same rule.

-- ── The depreciation entry balances ──────────────────────────────────
--
-- Nothing had ever compared these, and they are the anchor the asset
-- register should be measured against: the balance sheet's accumulated
-- depreciation moved by 850,382.89 in 2025 across five contra accounts, and
-- the profit and loss charged 850,382.89. To the cent, which is what says the
-- depreciation entry is complete and balanced on both statements.

CREATE OR REPLACE VIEW v_depreciation_posted_check AS
WITH pl AS (
  SELECT period, sum(amount) AS amount FROM ledger_line
   WHERE account LIKE '5010%' GROUP BY period),
bs AS (
  SELECT period, -sum(amount) AS amount, count(DISTINCT account) AS accounts
    FROM ledger_line
   WHERE statement = 'BALANCE_SHEET'
     AND (account ILIKE '%A/D%' OR account ILIKE '%Accum%')
   GROUP BY period)
SELECT p.period,
       COALESCE(pl.amount, 0)                       AS profit_and_loss,
       COALESCE(bs.amount, 0)                       AS balance_sheet,
       COALESCE(bs.accounts, 0)                     AS contra_accounts,
       COALESCE(pl.amount, 0) - COALESCE(bs.amount, 0) AS variance,
       CASE WHEN COALESCE(pl.amount, 0) = 0
                 AND COALESCE(bs.amount, 0) = 0        THEN 'NO DATA'
            WHEN COALESCE(pl.amount, 0) = COALESCE(bs.amount, 0) THEN 'TIES'
            ELSE 'OPEN' END                          AS state,
       CASE WHEN COALESCE(pl.amount, 0) = 0 AND COALESCE(bs.amount, 0) = 0
              THEN 'the general ledger, imported'
            WHEN COALESCE(pl.amount, 0) <> COALESCE(bs.amount, 0)
              THEN format('The depreciation charged to the profit and loss '
                          'is %s and accumulated depreciation moved %s. One '
                          'of the two entries is incomplete.',
                          to_char(COALESCE(pl.amount, 0), 'FM999,999,999.00'),
                          to_char(COALESCE(bs.amount, 0), 'FM999,999,999.00'))
            ELSE '' END                              AS needs
  FROM fiscal_period p
  LEFT JOIN pl ON pl.period = p.period
  LEFT JOIN bs ON bs.period = p.period;

COMMENT ON VIEW v_depreciation_posted_check IS
  'The balance sheet''s accumulated depreciation movement against the profit '
  'and loss''s depreciation expense. Nothing had ever compared them, and it '
  'is what says the entry is complete on both statements — and it is the '
  'anchor the fixed-asset register is measured against, rather than the '
  'expense account alone.';


-- ── The asset register, named per class ──────────────────────────────
--
-- One number for a 22,429.02 difference is a dead end. Per GL account it is
-- four differences with four causes, and the largest single class — buildings
-- at 224,524.44 — agrees **to the cent**.

CREATE OR REPLACE VIEW v_asset_register_tie AS
WITH reg AS (
  SELECT period, gl_account,
         sum(depreciation) FILTER (
           WHERE in_service_on < date_trunc('year',
                   (period || '-01-01')::date) + interval '1 year')
                                                     AS in_period,
         sum(depreciation) FILTER (
           WHERE in_service_on >= date_trunc('year',
                   (period || '-01-01')::date) + interval '1 year')
                                                     AS after_period,
         sum(depreciation)                           AS register,
         count(*)                                    AS assets
    FROM asset GROUP BY period, gl_account),
-- The depreciation software numbers an asset within its cost account; the
-- ledger accumulates it in the paired contra account. `asset_schedule.py`
-- already carries that pairing — "BLDG5-1501-1502 is cost in 1501 and
-- accumulated depreciation in 1502" — so the map is the schedule's own.
paired AS (
  SELECT * FROM (VALUES
    ('1501', '1502'), ('1511', '1512'), ('1521', '1522'),
    ('1525', '1526'), ('1527', '1528')
  ) AS t(cost_account, contra_account)),
led AS (
  SELECT l.period, p.cost_account, -sum(l.amount) AS ledger
    FROM ledger_line l
    JOIN paired p ON l.account LIKE '%' || p.contra_account || '%'
   WHERE l.statement = 'BALANCE_SHEET'
   GROUP BY l.period, p.cost_account)
SELECT COALESCE(r.period, l.period)           AS period,
       COALESCE(r.gl_account, l.cost_account) AS gl_account,
       COALESCE(r.assets, 0)                  AS assets,
       COALESCE(l.ledger, 0)                  AS ledger,
       COALESCE(r.in_period, 0)               AS register_in_period,
       COALESCE(r.after_period, 0)            AS register_after_period,
       COALESCE(r.register, 0)                AS register,
       COALESCE(r.register, 0) - COALESCE(l.ledger, 0)    AS variance,
       COALESCE(r.in_period, 0) - COALESCE(l.ledger, 0)   AS variance_in_period,
       CASE WHEN COALESCE(r.register, 0) = 0
                 AND COALESCE(l.ledger, 0) = 0             THEN 'NO DATA'
            WHEN COALESCE(r.register, 0) = COALESCE(l.ledger, 0) THEN 'TIES'
            ELSE 'OPEN' END                                AS state
  FROM reg r
  FULL JOIN led l ON l.period = r.period AND l.cost_account = r.gl_account;

COMMENT ON VIEW v_asset_register_tie IS
  'The fixed-asset register against the ledger, per cost account, with the '
  'assets placed in service after the year end shown separately — the '
  'register on file is the 2026 print of the schedule and carries them. One '
  'figure for the whole difference is a dead end; per class it is four '
  'differences with four causes, and buildings agree to the cent.';


-- ── The invoice register against the income it recognises ────────────

CREATE OR REPLACE VIEW v_invoice_income_tie AS
WITH billed AS (
  SELECT to_char(invoice_date, 'YYYY') AS period, objective_id,
         count(*) AS invoices, sum(total) AS billed
    FROM invoice WHERE status <> 'WITHDRAWN' AND objective_id IS NOT NULL
   GROUP BY 1, 2),
recognised AS (
  SELECT l.period, m.objective_id, sum(l.amount) AS income
    FROM ledger_line l
    JOIN (VALUES
      ('%Drive AM%', 'DRIVE-AM'), ('%Last Tactical Mile%', 'LTM'),
      ('%Hybrid Energy%', 'HYBRID-II'), ('%Digital Engineering%', 'DIG-ENG'),
      ('%Rising Tides%', 'RISING-TIDES'), ('%AAMEN%', 'AAMEN')
    ) AS m(pattern, objective_id) ON l.account LIKE m.pattern
   WHERE l.account LIKE '3900 Grant Income%'
   GROUP BY l.period, m.objective_id)
SELECT COALESCE(b.period, r.period)         AS period,
       COALESCE(b.objective_id, r.objective_id) AS objective_id,
       COALESCE(b.invoices, 0)              AS invoices,
       COALESCE(b.billed, 0)                AS billed,
       COALESCE(r.income, 0)                AS grant_income,
       COALESCE(b.billed, 0) - COALESCE(r.income, 0) AS variance,
       CASE WHEN COALESCE(b.billed, 0) = 0 AND COALESCE(r.income, 0) = 0
              THEN 'NO DATA'
            WHEN COALESCE(b.billed, 0) = COALESCE(r.income, 0) THEN 'TIES'
            ELSE 'OPEN' END                 AS state
  FROM billed b
  FULL JOIN recognised r
    ON r.period = b.period AND r.objective_id = b.objective_id;

COMMENT ON VIEW v_invoice_income_tie IS
  'The invoice register against the grant income the ledger recognises, per '
  'objective, on the invoice''s own date rather than its period column — the '
  'discipline that stops the next loader writing a year as a constant. A '
  'difference is a timing question for the controller and is named rather '
  'than netted.';
