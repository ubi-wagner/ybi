-- 093 — a partition that ties still asked for the thing it already had
--
-- With the estate measured and every asset answered, `v_partition_coverage`
-- read:
--
--     SPACE   TIES  100.0  the square footage per building, and what each
--                          part is used for
--     COST    TIES  100.0  the general ledger and the profit and loss
--     ASSETS  TIES  100.0
--
-- Two of the three go on naming what is missing after nothing is. `needs` is
-- a constant on the COST and SPACE arms — written when neither partition had
-- ever been finished, so the state it is wrong in had never occurred. It is
-- `086` one view along: *the step whose whole job is to say what is
-- unfinished must not assert something untrue about it*, and the same defect
-- wearing the opposite sign.
--
-- ASSETS was already right, because `085` had to give it a second branch when
-- the register was loaded and the reason went blank. **A rule fixed in one
-- arm is one somebody gets wrong in the other two** — which is the sentence
-- `086` closes on, about these same three partitions.
--
-- So `needs` is empty when the partition ties, on all three, and
-- `tests/test_worklist_product.py` asks for a sentence only where there is
-- something outstanding. That test asserted one unconditionally and therefore
-- failed the moment a partition was finished — a test that cannot pass for
-- the state it is about, which is the mirror of a test that cannot fail for
-- the thing it names.

CREATE OR REPLACE VIEW v_partition_coverage AS
WITH cost AS (
  SELECT c.period, 'COST' AS partition,
         'The 2025 profit and loss, into cost pools' AS divides,
         'dollars' AS unit,
         c.classified AS covered, c.scope_dollars AS whole,
         c.groups_decided AS parts_done, c.groups_total AS parts,
         c.scope_dollars > 0 AS evaluable,
         CASE WHEN c.classified >= c.scope_dollars THEN ''
              ELSE 'the general ledger and the profit and loss' END AS needs,
         '/classify' AS goes_to
    FROM v_classification_coverage c),
space AS (
  SELECT p.period, 'SPACE',
         'Each building, into tenant, programme and vacant space',
         'square feet',
         COALESCE(s.unit_sqft, 0), COALESCE(s.usable_sqft, 0),
         COALESCE(s.units, 0), (SELECT count(*) FROM facility),
         COALESCE(s.usable_sqft, 0) > 0,
         CASE WHEN COALESCE(s.usable_sqft, 0) > 0
                   AND COALESCE(s.unit_sqft, 0) >= COALESCE(s.usable_sqft, 0)
              THEN ''
              ELSE 'the square footage per building, and what each part is '
                   'used for' END,
         '/classify/space'
    FROM fiscal_period p
    LEFT JOIN (SELECT period, sum(usable_sqft) AS usable_sqft,
                      sum(unit_sqft) AS unit_sqft, sum(units) AS units
                 FROM v_space_unit_control GROUP BY period) s
      ON s.period = p.period),
assets AS (
  SELECT a.period, 'ASSETS',
         'The fixed-asset register, into funding sources',
         'dollars',
         a.funded_cost, a.gross_cost,
         a.assets - a.funding_unknown, a.assets,
         a.evaluable, a.needs, '/classify/assets'
    FROM v_asset_control a)
SELECT period, partition, divides, unit, covered, whole, parts_done, parts,
       evaluable, needs, goes_to,
       CASE WHEN whole > 0 THEN round(100.0 * covered / whole, 1) END AS pct,
       CASE WHEN NOT evaluable         THEN 'NO DATA'
            WHEN covered = whole       THEN 'TIES'
            ELSE 'OPEN' END                                        AS state,
       whole - covered                                             AS outstanding
  FROM (SELECT * FROM cost UNION ALL SELECT * FROM space
        UNION ALL SELECT * FROM assets) x;

COMMENT ON VIEW v_partition_coverage IS
  'The three partitions the year is closed by — cost into pools, space into '
  'uses, assets into funding sources — each with what is outstanding and '
  'where it is dealt with. `needs` is empty once the partition ties: a '
  'finished partition asking for the thing it already has is the defect 086 '
  'fixed on the walk, in the view the walk reads.';
