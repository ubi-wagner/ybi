-- 102 — the asset control was OPEN and said nothing about why
--
-- `085` gave `v_asset_control.needs` a branch for a register nobody had
-- answered the funding source on, because until then that was the only way it
-- could be open. `098`'s run answered all 263, the branch fell through to the
-- empty string, and the control went on reporting **OPEN** with nothing
-- saying what it wanted — on the one figure that feeds the 200.436(b)
-- carve-out and therefore the rate.
--
-- It is `086` and `093` for the third time in the same family, and it is why
-- `101` exists: a control that says OPEN and not by how much is a dead end,
-- and a register of controls that collects dead ends is a longer dead end.
--
-- The state was right the whole time. The register carries $872,811.91 of
-- depreciation and the ledger charged $850,382.89, and the difference is not
-- one thing: `v_asset_register_tie` shows buildings agreeing **to the cent**,
-- the 2026 print of the schedule carrying $10,916.17 of assets placed in
-- service after the year end, and four per-class differences somebody has to
-- attribute. Naming it is what closes it, which is the rule the reconciling
-- register has always followed.
--
-- Lifted from the definition in force rather than retyped — `070` records
-- what retyping a view body costs.

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
            WHEN (( SELECT COALESCE(sum(a.depreciation), 0::numeric)
               FROM asset a WHERE a.period = p.period))
                 - (( SELECT COALESCE(sum(l.amount), 0::numeric)
               FROM ledger_line l
              WHERE l.period = p.period AND l.account ~~ '%5010%'::text))
                 <> 0::numeric
              THEN format('The register carries %s of depreciation and the '
                          'ledger charged %s, a difference of %s. '
                          'v_asset_register_tie names it per cost account: '
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
        END AS needs,
    ( SELECT COALESCE(sum(a.gross_cost), 0::numeric) AS "coalesce"
           FROM asset a
          WHERE a.period = p.period AND (EXISTS ( SELECT 1
                   FROM asset_funding f
                  WHERE f.asset_id = a.asset_id))) AS funded_cost
   FROM fiscal_period p;

COMMENT ON VIEW v_asset_control IS
  'The fixed-asset register against the ledger, and how much of it names '
  'a funding source. OPEN now says which of the two it is and by how '
  'much — it reported OPEN with a blank reason for as long as the funding '
  'question was answered and the depreciation one was not.';
