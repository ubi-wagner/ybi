-- The rate build-up has to tie to the pool it was built from, and say so.
--
-- `063` gave `carve_out` the writer it never had, and the reason that defect
-- survived the life of the system is here: **nothing ever compared the rate
-- to the pool underneath it.** `rate.pool_amount` is what the computation
-- used. `v_pool_balance.allocable` is what the ledger says is left after
-- carve-outs. They were $932,254.78 apart, on the build-up screen, in
-- adjacent columns, and no control looked at the difference.
--
-- Every derived figure ties to a control. This is the one for the rate.
--
-- Two other things the build-up could not say, both visible the moment the
-- carve-out started being written:
--
--   * **INDIRECT_COMBINED had no pool at all.** The join was
--     `pb.pool = r.kind`, and there is no pool named INDIRECT_COMBINED — it
--     is OVERHEAD plus G&A. So the rate that is actually applied to a
--     restatement showed blank gross, blank carved, blank allocable and zero
--     carve-outs, while the OVERHEAD row beside it showed all four. The one
--     figure that leaves the building was the one with nothing behind it.
--   * **A pool nobody has classified into reads NULL, not 0.** FRINGE and
--     G&A show `pool_amount = 0.00` from the computation and NULL from the
--     LEFT JOIN, side by side, meaning the same thing in two spellings. A
--     reader cannot tell "nothing is in this pool" from "this did not join".
--
-- Dropped and recreated rather than replaced: this adds columns and changes
-- the join. The body is lifted from the live definition.
DROP VIEW v_rate_buildup;

CREATE VIEW v_rate_buildup AS
WITH pool_for_kind AS (
    -- Which pools stand behind each kind of rate. One row per pool for the
    -- single-pool kinds; two for INDIRECT_COMBINED, which is the sum of the
    -- two it combines. Written as data rather than as a CASE so the combined
    -- rate cannot go on being the one with nothing behind it.
    SELECT 'FRINGE'::text AS kind,   'FRINGE'::text   AS pool
    UNION ALL SELECT 'OVERHEAD',          'OVERHEAD'
    UNION ALL SELECT 'G&A',               'G&A'
    UNION ALL SELECT 'INDIRECT_COMBINED', 'OVERHEAD'
    UNION ALL SELECT 'INDIRECT_COMBINED', 'G&A'
), rolled AS (
    SELECT r.rate_id,
           -- COALESCE to 0, not NULL: a pool nobody has classified into
           -- holds nothing, which is a figure. The rate says 0.00 and the
           -- pool must say the same thing in the same spelling or the tie
           -- below cannot be evaluated.
           COALESCE(sum(pb.gross), 0)     AS pool_gross,
           COALESCE(sum(pb.carved), 0)    AS pool_carved,
           COALESCE(sum(pb.allocable), 0) AS pool_allocable,
           COALESCE(sum(c.n), 0)          AS carve_outs
      FROM rate r
      JOIN pool_for_kind pk ON pk.kind = r.kind
      LEFT JOIN v_pool_balance pb
             ON pb.period = r.period AND pb.pool::text = pk.pool
      LEFT JOIN LATERAL (
            SELECT count(*) AS n FROM carve_out co
             WHERE co.period = r.period AND co.pool::text = pk.pool) c ON true
     GROUP BY r.rate_id
)
SELECT r.period,
       r.rate_id,
       r.kind,
       r.pool_amount,
       r.base_type::text AS base_type,
       r.base_amount,
       r.rate,
       r.status,
       r.seal_hash,
       r.computed_at,
       r.computed_by,
       ds.label AS decision_set,
       ds.sealed_at,
       ds.sealed_by,
       b.pool_gross,
       b.pool_carved,
       b.pool_allocable,
       b.carve_outs,
       -- The control. What the rate was computed on, against what the ledger
       -- says is left after the carve-outs somebody recorded.
       (r.pool_amount - b.pool_allocable) AS pool_variance,
       (r.pool_amount = b.pool_allocable) AS ties
  FROM rate r
  JOIN decision_set ds ON ds.set_id = r.set_id
  JOIN rolled b ON b.rate_id = r.rate_id
 WHERE r.status <> 'SUPERSEDED'::text;

COMMENT ON VIEW v_rate_buildup IS
  'Each live rate against the pool it was built from. `ties` is the control '
  'that was missing: rate.pool_amount is what the computation used and '
  'pool_allocable is what the ledger says is left after recorded carve-outs, '
  'and they sat $932,254.78 apart in adjacent columns for the life of the '
  'system because nothing compared them. INDIRECT_COMBINED rolls up the two '
  'pools it combines rather than joining to a pool of that name, which does '
  'not exist — the rate that is actually applied to a restatement used to be '
  'the one row with nothing behind it.';
