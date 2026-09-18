-- A partition at 101.8%, counting rooms against buildings, saying nothing.
--
-- The controller reached the Classify screen with cost at 100.0% and the
-- asset register tying, and stopped at:
--
--     Space   Each building, into tenant, programme and vacant space
--             101.8%   155,913 square feet   38 / 5   OPEN
--
-- Three things wrong with one row, and none of them is the estate.
--
-- **`parts_done` and `parts` are different populations.** `sum(units)` is
-- space units — rooms — and `count(*) FROM facility` is buildings, so the
-- fraction read 38 of 5. It is `085`'s unit confusion exactly, where the
-- ASSETS arm subtracted a count of assets from a sum of dollars; that one
-- was caught because it read 100% over a register nobody had answered, and
-- this one hid until an estate was entered. Both sides are buildings now:
-- how many account for themselves, of how many there are.
--
-- **`needs` was blank.** Its branch is `unit_sqft >= usable_sqft`, so an
-- estate attributing MORE floor area than it has satisfies it and the step
-- printed nothing about what was wrong. That is the third appearance of
-- `086`'s defect in this family after `093` and `106` — OPEN with nothing
-- saying why — and the first in the *over* direction, which nobody had seen
-- because until an estate was entered a partition could only be short. It
-- names the buildings now, and by how much.
--
-- **And nothing said this does not block the seal.** `state` is right:
-- covered = whole ties, anything else is open, and over-attribution is a
-- real finding — `v_facility_occupancy` inner-joins to its space totals, so
-- a building that does not add up drops out of the 200.465 carve-out
-- entirely and every dollar of its occupancy cost stays in the federal
-- pool. What the card could not say is that the seal waits on the
-- classification and on nothing else (`081` step 7), which `082` settled
-- for everything downstream: nothing is blocked, the paper says what is
-- unfinished. A reader who cannot tell a wall from a caveat treats both as
-- walls.
--
-- Lifted from `119`, which is the definition in force, and only the SPACE
-- arm moves. COST and ASSETS are reproduced exactly.

CREATE OR REPLACE VIEW v_partition_coverage AS
WITH cost AS (
  SELECT p.period, 'COST' AS partition,
         'The 2025 profit and loss, into cost pools' AS divides,
         'dollars' AS unit,
         COALESCE(c.classified, 0) AS covered,
         COALESCE(c.scope_dollars, 0) AS whole,
         COALESCE(c.groups_decided, 0)::numeric AS parts_done,
         COALESCE(c.groups_total, 0) AS parts,
         COALESCE(c.scope_dollars, 0) > 0 AS evaluable,
         CASE WHEN COALESCE(c.scope_dollars, 0) > 0
                   AND COALESCE(c.classified, 0) >= c.scope_dollars THEN ''
              ELSE 'the general ledger and the profit and loss' END AS needs,
         '/classify' AS goes_to
    FROM fiscal_period p
    LEFT JOIN v_classification_coverage c ON c.period = p.period),
space AS (
  SELECT p.period, 'SPACE',
         'Each building, into tenant, programme and vacant space',
         'square feet',
         COALESCE(s.unit_sqft, 0), COALESCE(s.usable_sqft, 0),
         -- Buildings on both sides of the fraction, not rooms over buildings.
         COALESCE(s.tying, 0)::numeric, (SELECT count(*) FROM facility),
         COALESCE(s.usable_sqft, 0) > 0,
         CASE
           WHEN COALESCE(s.usable_sqft, 0) = 0 THEN
                'the square footage per building, and what each part is used for'
           WHEN COALESCE(s.unit_sqft, 0) = COALESCE(s.usable_sqft, 0) THEN ''
           -- Over-attribution and under-attribution are different errors and
           -- lead to different work, so the sentence says which, names the
           -- buildings, and says what it costs. A building that does not add
           -- up leaves the carve-out altogether.
           WHEN COALESCE(s.unit_sqft, 0) > COALESCE(s.usable_sqft, 0) THEN
                format('%s %s %s sq ft more than %s. A building whose parts do '
                       'not add up drops out of the 200.465 carve-out, so its '
                       'occupancy cost stays in the federal pool.',
                       s.off_names,
                       CASE WHEN s.off = 1 THEN 'attributes' ELSE 'attribute' END,
                       trim(trailing '.' FROM
                            to_char(s.unit_sqft - s.usable_sqft, 'FM999,999,999.9')),
                       CASE WHEN s.off = 1 THEN 'the building holds'
                            ELSE 'those buildings hold' END)
           ELSE format('%s sq ft not yet attributed, in %s.',
                       trim(trailing '.' FROM
                            to_char(s.usable_sqft - s.unit_sqft, 'FM999,999,999.9')),
                       s.off_names)
         END,
         '/classify/space'
    FROM fiscal_period p
    LEFT JOIN (SELECT period,
                      sum(usable_sqft) AS usable_sqft,
                      sum(unit_sqft) AS unit_sqft,
                      count(*) FILTER (WHERE ties) AS tying,
                      count(*) FILTER (WHERE NOT ties) AS off,
                      string_agg(name, ', ' ORDER BY abs(variance) DESC)
                        FILTER (WHERE NOT ties) AS off_names
                 FROM v_space_unit_control GROUP BY period) s
      ON s.period = p.period),
assets AS (
  SELECT a.period, 'ASSETS',
         'The fixed-asset register, into funding sources',
         'dollars',
         a.funded_cost, a.gross_cost,
         (a.assets - a.funding_unknown)::numeric, a.assets,
         a.evaluable, a.needs, '/classify/assets'
    FROM v_asset_control a)
SELECT period, partition, divides, unit, covered, whole, parts_done, parts,
       evaluable, needs, goes_to,
       CASE WHEN whole > 0 THEN round(100.0 * covered / whole, 1) END AS pct,
       CASE WHEN NOT evaluable THEN 'NO DATA'
            WHEN covered = whole THEN 'TIES'
            ELSE 'OPEN' END AS state,
       whole - covered AS outstanding
  FROM (SELECT * FROM cost UNION ALL SELECT * FROM space
        UNION ALL SELECT * FROM assets) x;
