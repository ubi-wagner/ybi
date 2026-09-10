-- =====================================================================
-- Profit and loss scope
--
-- The general ledger export carries every account, balance sheet included.
-- Without a scope the classification queue asks the controller to classify
-- bank accounts, receivables and payables — 2,479 groups and $99M of absolute
-- movement against $6.7M of actual 2025 cost. That is not a cosmetic problem:
-- dollar coverage, the measure that gates sealing, becomes meaningless.
--
-- Scope comes from the P&L report rather than from account numbers. YBI's
-- 2025 chart has revenue in the 5xxx expense range (5107 Interest Income,
-- 5108 Other Income) and income in the net-assets range (3991 MBAC), so
-- number-based inference gives the wrong answer on real data.
-- =====================================================================

CREATE TABLE pl_account (
  period          text NOT NULL REFERENCES fiscal_period,
  account         text NOT NULL,               -- qualified path as printed
  leaf            text NOT NULL,               -- last path segment, for GL matching
  section         text NOT NULL,               -- Income | COGS | Expense | Other Income
  amount          numeric(14,2) NOT NULL,
  import_id       uuid REFERENCES ledger_import,
  loaded_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (period, account),
  CONSTRAINT pl_section_known
    CHECK (section IN ('Income','COGS','Expense','Other Income'))
);
CREATE INDEX ON pl_account (period, leaf);

-- A ledger line is in P&L scope when its leaf account appears on the P&L.
CREATE VIEW v_ledger_scope AS
SELECT l.line_id,
       l.period,
       l.account,
       split_part(l.account, ':', array_length(string_to_array(l.account, ':'), 1))
         AS leaf,
       p.section,
       (p.section IS NOT NULL) AS in_pl_scope
  FROM ledger_line l
  LEFT JOIN pl_account p
         ON p.period = l.period
        AND p.leaf = split_part(l.account, ':',
              array_length(string_to_array(l.account, ':'), 1));
