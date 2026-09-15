-- 085: the asset partition was subtracting a count from a sum of money.
--
-- `v_partition_coverage` built the ASSETS row as
--
--     covered = a.gross_cost - a.funding_unknown
--
-- where `gross_cost` is $23,419,573.64 and `funding_unknown` is **263, the
-- number of assets nobody has answered for**. Dollars minus a count. It has
-- never shown, because `asset` has been empty for the life of the system and
-- `0 - 0` is 0 — `029`'s lesson once more, an empty register making a wrong
-- expression look right.
--
-- The moment the register is loaded it reads **$23,419,310.64 of
-- $23,419,573.64 covered — 100.0%**, on the partition screen and on the
-- walk, when the true answer is **nought**: not one asset carries a funding
-- source, which is 2 CFR 200.313(d)(1) unanswered and the reason 200.436(b)
-- cannot be settled on $850,382.89 of depreciation. A screen that says the
-- largest open question in the file is finished is worse than one that says
-- nothing, and this one would have said it on the first day anybody loaded
-- the schedule YBI has had all along.
--
-- Covered is the gross cost of the assets that **do** carry a funding source,
-- computed where the other asset figures are computed. Putting it here rather
-- than inside the partition view keeps one definition of every asset figure
-- in one place, which is what `v_asset_control` is for.
--
-- And **OPEN says what it needs.** `needs` was set only where the register is
-- absent, so the moment it landed the partition printed OPEN with an empty
-- reason — *cannot be classified with no reason is a dead end*, in a new
-- place. There are two different asks now and they lead to different work:
-- get the register, or answer the column the register does not have.

CREATE OR REPLACE VIEW v_asset_control AS
SELECT p.period,
       (SELECT count(*) FROM asset a WHERE a.period = p.period) AS assets,
       (SELECT count(*) FROM asset a
         WHERE a.period = p.period
           AND NOT EXISTS (SELECT 1 FROM asset_funding f
                            WHERE f.asset_id = a.asset_id)) AS funding_unknown,
       (SELECT COALESCE(sum(a.gross_cost), 0) FROM asset a
         WHERE a.period = p.period) AS gross_cost,
       (SELECT COALESCE(sum(a.depreciation), 0) FROM asset a
         WHERE a.period = p.period) AS register_depreciation,
       (SELECT COALESCE(sum(v.allowable_depreciation), 0)
          FROM v_asset_allowability v
         WHERE v.period = p.period) AS allowable_depreciation,
       (SELECT COALESCE(sum(l.amount), 0) FROM ledger_line l
         WHERE l.period = p.period AND l.account LIKE '%5010%')
         AS ledger_depreciation,
       (SELECT COALESCE(sum(a.depreciation), 0) FROM asset a
         WHERE a.period = p.period)
       - (SELECT COALESCE(sum(l.amount), 0) FROM ledger_line l
           WHERE l.period = p.period AND l.account LIKE '%5010%') AS variance,
       EXISTS (SELECT 1 FROM asset a WHERE a.period = p.period) AS evaluable,
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM asset a WHERE a.period = p.period)
           THEN 'NO DATA'
         WHEN (SELECT COALESCE(sum(a.depreciation), 0) FROM asset a
                WHERE a.period = p.period)
            - (SELECT COALESCE(sum(l.amount), 0) FROM ledger_line l
                WHERE l.period = p.period AND l.account LIKE '%5010%') = 0
           THEN 'TIES'
         ELSE 'OPEN'
       END AS state,
       -- Two asks, and they lead somewhere different.
       CASE
         WHEN NOT EXISTS (SELECT 1 FROM asset a WHERE a.period = p.period)
           THEN 'the asset register, with a funding source per asset'
         WHEN (SELECT count(*) FROM asset a
                WHERE a.period = p.period
                  AND NOT EXISTS (SELECT 1 FROM asset_funding f
                                   WHERE f.asset_id = a.asset_id)) > 0
           THEN 'the funding source per asset — the one column the schedule '
                'does not carry, and what 200.436(b) turns on'
         ELSE ''
       END AS needs,
       -- What the partition is actually measuring: the cost of the assets
       -- somebody has answered for. **Dollars, so it can be compared with
       -- dollars** — which is the whole of what `085` is about.
       (SELECT COALESCE(sum(a.gross_cost), 0) FROM asset a
         WHERE a.period = p.period
           AND EXISTS (SELECT 1 FROM asset_funding f
                        WHERE f.asset_id = a.asset_id)) AS funded_cost
  FROM fiscal_period p;

COMMENT ON VIEW v_asset_control IS
'The fixed-asset register against the ledger it depreciates into, and against '
'the funding question 200.313(d)(1) asks of it. `funded_cost` is the cost of '
'the assets somebody has answered for, in dollars — the partition view '
'subtracted the *count* of unanswered ones from the gross cost instead, which '
'read as 100% covered over a register where nothing had been answered.';


-- Lifted from the definition in force and given the dollars it was asking
-- for. `070` records what retyping a view body costs.

CREATE OR REPLACE VIEW v_partition_coverage AS
WITH cost AS (
         SELECT c.period,
            'COST'::text AS partition,
            'The 2025 profit and loss, into cost pools'::text AS divides,
            'dollars'::text AS unit,
            c.classified AS covered,
            c.scope_dollars AS whole,
            c.groups_decided AS parts_done,
            c.groups_total AS parts,
            c.scope_dollars > 0::numeric AS evaluable,
            'the general ledger and the profit and loss'::text AS needs,
            '/classify'::text AS goes_to
           FROM v_classification_coverage c
        ), space AS (
         SELECT p.period,
            'SPACE'::text AS text,
            'Each building, into tenant, programme and vacant space'::text AS "?column?",
            'square feet'::text AS text,
            COALESCE(s.unit_sqft, 0::numeric) AS "coalesce",
            COALESCE(s.usable_sqft, 0::numeric) AS "coalesce",
            COALESCE(s.units, 0::numeric) AS "coalesce",
            ( SELECT count(*) AS count
                   FROM facility) AS count,
            COALESCE(s.usable_sqft, 0::numeric) > 0::numeric AS "?column?",
            'the square footage per building, and what each part is used for'::text AS text,
            '/classify/space'::text AS text
           FROM fiscal_period p
             LEFT JOIN ( SELECT v_space_unit_control.period,
                    sum(v_space_unit_control.usable_sqft) AS usable_sqft,
                    sum(v_space_unit_control.unit_sqft) AS unit_sqft,
                    sum(v_space_unit_control.units) AS units
                   FROM v_space_unit_control
                  GROUP BY v_space_unit_control.period) s ON s.period = p.period
        ), assets AS (
         SELECT a.period,
            'ASSETS'::text AS text,
            'The fixed-asset register, into funding sources'::text AS "?column?",
            'dollars'::text AS text,
            a.funded_cost AS "?column?",
            a.gross_cost,
            a.assets - a.funding_unknown AS int8,
            a.assets,
            a.evaluable,
            a.needs,
            '/classify/assets'::text AS text
           FROM v_asset_control a
        )
 SELECT period,
    partition,
    divides,
    unit,
    covered,
    whole,
    parts_done,
    parts,
    evaluable,
    needs,
    goes_to,
        CASE
            WHEN whole > 0::numeric THEN round(100.0 * covered / whole, 1)
            ELSE NULL::numeric
        END AS pct,
        CASE
            WHEN NOT evaluable THEN 'NO DATA'::text
            WHEN covered = whole THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
    whole - covered AS outstanding
   FROM ( SELECT cost.period,
            cost.partition,
            cost.divides,
            cost.unit,
            cost.covered,
            cost.whole,
            cost.parts_done,
            cost.parts,
            cost.evaluable,
            cost.needs,
            cost.goes_to
           FROM cost
        UNION ALL
         SELECT space.period,
            space.text,
            space."?column?",
            space.text_1 AS text,
            space."coalesce",
            space.coalesce_1 AS "coalesce",
            space.coalesce_2 AS "coalesce",
            space.count,
            space."?column?_1" AS "?column?",
            space.text_2 AS text,
            space.text_3 AS text
           FROM space space(period, text, "?column?", text_1, "coalesce", coalesce_1, coalesce_2, count, "?column?_1", text_2, text_3)
        UNION ALL
         SELECT assets.period,
            assets.text,
            assets."?column?",
            assets.text_1 AS text,
            assets."?column?_1" AS "?column?",
            assets.gross_cost,
            assets.int8,
            assets.assets,
            assets.evaluable,
            assets.needs,
            assets.text_2 AS text
           FROM assets assets(period, text, "?column?", text_1, "?column?_1", gross_cost, int8, assets, evaluable, needs, text_2)) x;
