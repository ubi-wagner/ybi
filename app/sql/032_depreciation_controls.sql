-- Two defects the 2025 baseline run found by cross-tying depreciation.
--
-- ── 1. depreciation_expensed counted the contra-asset as expense ──────
--
-- v_depreciation_basis read depreciation expense as
--
--     sum(abs(amount)) WHERE account ILIKE '%depreciation%'
--
-- with no scope. Two ledger accounts match that pattern in 2025:
--
--     5010 Depreciation Expense                        850,382.89
--     1570 TBB5:1502 TBB5 Accumulated Depreciation    -438,873.05
--
-- The second is the contra-asset on the balance sheet — the credit side of
-- part of the first. abs() turned that credit into an addition, so the view
-- reported 1,289,255.94 of depreciation expense against a ledger that
-- expensed 850,382.89. It overstated by 51.6%, and it did so on a figure that
-- feeds the 200.436(b) analysis.
--
-- It matched exactly one of the six accumulated-depreciation accounts because
-- that one spells the word out; the other five say "Accum. Depr." or "A/D"
-- and were silently excluded. A pattern that catches one sixth of a class is
-- worse than one that catches none, because the total looks plausible.
--
-- This is the defect CLAUDE.md names: never join on a name where a key
-- exists. The scope is the profit and loss, and pl_account already carries
-- it, so ask that instead of asking the spelling.
--
-- The ledger proves the right answer on both sides. The six accumulated
-- depreciation accounts moved as follows in 2025:
--
--     1502 TBB5                    438,873.05
--     1512 Buildings               224,524.44
--     1522 Capital Improvements    102,820.79
--     1523 Capital Leases                0.00
--     1526 Computer Equipment       77,597.49
--     1528 Equipment-Other           6,567.12
--                                  ----------
--                                  850,382.89   = 5010 Depreciation Expense

CREATE OR REPLACE VIEW v_depreciation_basis AS
SELECT b.period, b.asset_class, b.gross_cost, b.depreciable_cost,
       b.accumulated_depreciation, b.net_book_value,
       (SELECT COALESCE(sum(a.gross_cost), 0) FROM asset a
         WHERE a.period = b.period)                        AS register_cost,
       (SELECT count(*) FROM asset a
         WHERE a.period = b.period
           AND NOT EXISTS (SELECT 1 FROM asset_funding f
                            WHERE f.asset_id = a.asset_id)) AS assets_without_funding,
       -- Expense, not the contra-asset behind it. Scoped by what the profit
       -- and loss says is an expense account rather than by how the account
       -- happens to be spelled, and signed rather than absolute: a credit to
       -- depreciation expense is a reduction of it, not more of it.
       (SELECT COALESCE(sum(l.amount), 0)
          FROM ledger_line l
         WHERE l.period = b.period
           AND EXISTS (SELECT 1 FROM pl_account p
                        WHERE p.period = l.period
                          AND p.account = l.account
                          AND p.section IN ('Expense', 'COGS'))
           AND l.account ILIKE '%depreciation%')           AS depreciation_expensed
  FROM v_fixed_asset_basis b;

COMMENT ON VIEW v_depreciation_basis IS
  'What the books say the basis is, against what the register says about how '
  'it was funded. 2 CFR 200.436(b): depreciation on a federally funded asset '
  'is unallowable, so the second half decides the first half''s treatment. '
  'Depreciation expense is scoped to P&L expense accounts — the contra-asset '
  'accounts carry the same word and are not expense.';


-- ── 2. ASSET_REGISTER reported a variance where it had no data ────────
--
-- Migration 029 established the rule for the eleven cross-reference points:
-- a control that cannot be evaluated has not passed, and must say NO DATA
-- rather than compare zero against something and call the difference a
-- variance. ASSET_REGISTER lives outside that view, in the audit package, and
-- never got the treatment.
--
-- With no register loaded it reported:
--
--     register_depreciation        0.00
--     ledger_depreciation    850,382.89
--     variance              -850,382.89
--
-- which reads as "the register disagrees with the ledger by 850,382.89". The
-- register does not disagree. There is no register. Those are different
-- findings and only one of them is true, and a reviewer handed the first one
-- goes looking for an error that does not exist.

CREATE OR REPLACE VIEW v_asset_control AS
SELECT p.period,
       (SELECT count(*) FROM asset WHERE period = p.period)              AS assets,
       (SELECT count(*) FROM asset a WHERE a.period = p.period
          AND NOT EXISTS (SELECT 1 FROM asset_funding f
                           WHERE f.asset_id = a.asset_id))               AS funding_unknown,
       (SELECT COALESCE(sum(gross_cost), 0) FROM asset
         WHERE period = p.period)                                        AS gross_cost,
       (SELECT COALESCE(sum(depreciation), 0) FROM asset
         WHERE period = p.period)                                        AS register_depreciation,
       (SELECT COALESCE(sum(allowable_depreciation), 0)
          FROM v_asset_allowability WHERE period = p.period)             AS allowable_depreciation,
       (SELECT COALESCE(sum(amount), 0) FROM ledger_line
         WHERE period = p.period AND account LIKE '%5010%')              AS ledger_depreciation,
       (SELECT COALESCE(sum(depreciation), 0) FROM asset
         WHERE period = p.period)
       - (SELECT COALESCE(sum(amount), 0) FROM ledger_line
           WHERE period = p.period AND account LIKE '%5010%')            AS variance,
       -- There has to be a register before it can agree with anything.
       EXISTS (SELECT 1 FROM asset WHERE period = p.period)              AS evaluable,
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM asset WHERE period = p.period)
           THEN 'NO DATA'
         WHEN (SELECT COALESCE(sum(depreciation), 0) FROM asset
                WHERE period = p.period)
            - (SELECT COALESCE(sum(amount), 0) FROM ledger_line
                WHERE period = p.period AND account LIKE '%5010%') = 0
           THEN 'TIES'
         ELSE 'OPEN'
       END                                                               AS state,
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM asset WHERE period = p.period)
           THEN 'the asset register, with a funding source per asset'
         ELSE ''
       END                                                               AS needs
  FROM fiscal_period p;

COMMENT ON VIEW v_asset_control IS
  'The register against the ledger. Reports NO DATA rather than a variance '
  'when no register has been loaded — an absent register is a missing '
  'document, not a disagreement.';
