-- The cost partition disappeared where there was no ledger.
--
-- `078` built `v_partition_coverage` as three arms and the COST arm reads
-- `FROM v_classification_coverage`, which returns **no row at all** for a
-- period with no ledger. So on a record with no books the view answers with
-- two partitions where there are three, and the missing one is the cost
-- classification — the partition this repository calls the one that matters.
--
-- An absent row is not `NO DATA`; it is worse. `NO DATA` says *nobody has
-- measured this*, which is `029`'s whole point. A row that is simply not
-- there reads as *this partition does not apply here*, and the reader has no
-- way to tell the two apart. `v_report_tie` passes the state straight
-- through, so the tie register loses the anchor as well.
--
-- **SPACE was fixed for exactly this and ASSETS never had it**: SPACE drives
-- from `fiscal_period` and LEFT JOINs its totals, `v_asset_control` is built
-- per period and answers `evaluable = false` over an empty register. COST is
-- the third arm and kept the defect — which is `086`'s own closing sentence
-- about these same three partitions: *a rule fixed in one arm is one somebody
-- gets wrong in the other two.*
--
-- It is visible on the live record too, not only on an empty one: 2021–2024
-- and 2026 each print SPACE and ASSETS at `NO DATA` and no COST row at all.
--
-- **Nothing on 2025 moves.** The COST row already exists there and already
-- reads TIES; this adds the five periods that had no row and the empty-record
-- case. `needs` gains the guard `093` gave the other arms — a partition that
-- cannot be evaluated still says what it wants, rather than falling through
-- the `classified >= scope_dollars` branch that `0 >= 0` satisfies and
-- printing nothing at all.
--
-- Lifted from `093`, which is the definition in force; only the COST arm
-- changes.

CREATE OR REPLACE VIEW v_partition_coverage AS
WITH cost AS (
  SELECT p.period, 'COST' AS partition,
         'The 2025 profit and loss, into cost pools' AS divides,
         'dollars' AS unit,
         COALESCE(c.classified, 0) AS covered,
         COALESCE(c.scope_dollars, 0) AS whole,
         COALESCE(c.groups_decided, 0) AS parts_done,
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
  'where it is dealt with. All three are driven from fiscal_period, so a '
  'partition nobody has measured answers NO DATA rather than falling off the '
  'result: an absent row reads as not applicable, which is the one thing it '
  'never means. `needs` is empty only once the partition ties.';
