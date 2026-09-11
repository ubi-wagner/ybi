-- =====================================================================
-- The balance sheet, and the asset basis it carries
--
-- The one report that was never imported, and the one that answers the
-- question the rate has been waiting on. 2 CFR 200.436(b) makes depreciation
-- on a federally funded asset unallowable, so $850,383 of 2025 depreciation
-- sits at TEST_ASSUMPTION and blocks the seal until the basis and its funding
-- source are known. The sheet gives the basis. The funding source still has
-- to come from the asset register, and this makes the gap explicit rather
-- than leaving it implied.
--
-- It also brings two controls the system did not have:
--
--   The sheet must balance. Assets less liabilities and equity, zero.
--
--   Net income on the balance sheet must equal net income on the profit and
--   loss. Two exports that disagree are two different moments in the same
--   books, and everything built on either is suspect. This is the first
--   control that spans two reports.
-- =====================================================================

CREATE TABLE bs_account (
  period        text NOT NULL REFERENCES fiscal_period,
  account       text NOT NULL,                 -- qualified path
  leaf          text NOT NULL,
  side          text NOT NULL CHECK (side IN ('ASSET', 'LIABILITY', 'EQUITY')),
  amount        numeric(16,2) NOT NULL,
  is_rollup     boolean NOT NULL DEFAULT false,
  depth         integer NOT NULL DEFAULT 0,
  PRIMARY KEY (period, account, is_rollup)
);
CREATE INDEX ON bs_account (period, side);

COMMENT ON TABLE bs_account IS
  'The balance sheet as exported, accounts and the totals printed over them, '
  'with the qualified path so a contra account stays beside what it offsets.';


-- ── The asset basis, as the books hold it ────────────────────────────
--
-- Cost paired with the accumulated depreciation that reduces it. Land and
-- construction in progress carry no contra account, correctly — neither is
-- depreciated — which is exactly why they have to come out of any depreciable
-- basis rather than being netted in silently.

CREATE VIEW v_fixed_asset_basis AS
WITH fixed AS (
  SELECT account, leaf, amount,
         -- The group a cost and its contra share: everything up to the last
         -- path segment.
         COALESCE(NULLIF(regexp_replace(account, ':[^:]+$', ''), account),
                  'Assets:Fixed Assets')                      AS group_path,
         (leaf ~* 'accum|a/d')                                AS is_contra,
         (leaf ~* '^1500 |land|construction in progress')      AS not_depreciable,
         period
    FROM bs_account
   WHERE NOT is_rollup AND account LIKE 'Assets:Fixed Assets%')
SELECT period,
       group_path,
       -- Accounts hanging directly off Fixed Assets — land and construction
       -- in progress — have no sub-group, and a blank label in a workpaper is
       -- an invitation to misread it.
       COALESCE(NULLIF(regexp_replace(group_path, '^Assets:Fixed Assets:?', ''), ''),
                'Fixed Assets (no sub-account)')                   AS asset_class,
       sum(amount) FILTER (WHERE NOT is_contra)                  AS gross_cost,
       sum(amount) FILTER (WHERE is_contra)                      AS accumulated_depreciation,
       sum(amount)                                               AS net_book_value,
       sum(amount) FILTER (WHERE NOT is_contra AND NOT not_depreciable)
                                                                 AS depreciable_cost,
       bool_or(not_depreciable)                                  AS holds_non_depreciable,
       count(*)                                                  AS accounts
  FROM fixed
 GROUP BY period, group_path;

COMMENT ON VIEW v_fixed_asset_basis IS
  'Gross cost against accumulated depreciation by asset class. '
  'depreciable_cost excludes land and construction in progress, which carry '
  'no contra account because neither is depreciated.';


-- ── Controls ─────────────────────────────────────────────────────────

CREATE VIEW v_balance_sheet_control AS
WITH t AS (
  SELECT period,
         sum(amount) FILTER (WHERE side = 'ASSET'     AND NOT is_rollup) AS assets,
         sum(amount) FILTER (WHERE side = 'LIABILITY' AND NOT is_rollup) AS liabilities,
         sum(amount) FILTER (WHERE side = 'EQUITY'    AND NOT is_rollup) AS equity
    FROM bs_account GROUP BY period)
SELECT t.period,
       t.assets, t.liabilities, t.equity,
       round(t.assets - t.liabilities - t.equity, 2)              AS variance,
       (round(t.assets - t.liabilities - t.equity, 2) = 0)        AS ties,
       -- The cross-statement tie. bs_account holds net income as an equity
       -- account; pl_account holds the sections it comes from.
       (SELECT amount FROM bs_account b
         WHERE b.period = t.period AND b.leaf ILIKE 'net income%'
           AND NOT b.is_rollup LIMIT 1)                           AS bs_net_income,
       (SELECT COALESCE(sum(amount) FILTER (WHERE section = 'Income'), 0)
             - COALESCE(sum(amount) FILTER (WHERE section = 'Expense'), 0)
             - COALESCE(sum(amount) FILTER (WHERE section = 'COGS'), 0)
             + COALESCE(sum(amount) FILTER (WHERE section = 'Other Income'), 0)
          FROM pl_account p WHERE p.period = t.period)            AS pl_net_income
  FROM t;

COMMENT ON VIEW v_balance_sheet_control IS
  'The sheet balances, and its net income is the P&L''s. The second is the '
  'first control in this system that spans two reports: two exports that '
  'disagree are two different moments in the same books.';


-- ── The depreciation question, stated ────────────────────────────────
--
-- Basis by class from the sheet, against the funding source from the asset
-- register. Where the register is silent the basis is known and the
-- allowability is not, which is a different and more useful thing to say than
-- "no evidence".

CREATE VIEW v_depreciation_basis AS
SELECT b.period, b.asset_class, b.gross_cost, b.depreciable_cost,
       b.accumulated_depreciation, b.net_book_value,
       (SELECT COALESCE(sum(a.gross_cost), 0) FROM asset a
         WHERE a.period = b.period)                        AS register_cost,
       (SELECT count(*) FROM asset a
         WHERE a.period = b.period
           AND NOT EXISTS (SELECT 1 FROM asset_funding f
                            WHERE f.asset_id = a.asset_id)) AS assets_without_funding,
       (SELECT COALESCE(sum(abs(l.amount)), 0)
          FROM ledger_line l
         WHERE l.period = b.period
           AND l.account ILIKE '%depreciation%')           AS depreciation_expensed
  FROM v_fixed_asset_basis b;

COMMENT ON VIEW v_depreciation_basis IS
  'What the books say the basis is, against what the register says about how '
  'it was funded. 2 CFR 200.436(b): depreciation on a federally funded asset '
  'is unallowable, so the second half decides the first half''s treatment.';
