-- The tie points anchor at the completion of the classification.
--
-- `065` gave the rate build-up a control: `rate.pool_amount` against
-- `v_pool_balance.allocable`, which is what caught the $932,254.78 carve-out
-- that had been missing from the workpaper for the life of the system. It
-- then reported **TIES on FRINGE and on G&A over nothing at all** — an empty
-- pool holds 0.00, the ledger says 0, and `0 = 0` is green.
--
-- That is `029` again, in the control written to catch the last one. *An
-- empty period compares zero against zero and looks green.* A control that
-- cannot be evaluated has not passed.
--
-- Two things here, and they are the same idea at two scales.

-- ── 1. A pool with nothing in it is NO DATA until the queue is empty ──
--
-- While anything is unjudged, an empty pool means *nobody has judged any of
-- this yet*. Once `unclassified` reaches zero it means *there is none of
-- this*, which is a figure and ties honestly. The state is read against the
-- completion of the classification rather than against the pool alone.
-- Dropped and recreated rather than replaced: `pool_state` goes in beside
-- `pool_variance`, and CREATE OR REPLACE can only add a column at the end.
DROP VIEW v_rate_buildup;
CREATE VIEW v_rate_buildup AS
 WITH pool_for_kind AS (
         SELECT 'FRINGE'::text AS kind,
            'FRINGE'::text AS pool
        UNION ALL
         SELECT 'OVERHEAD'::text,
            'OVERHEAD'::text
        UNION ALL
         SELECT 'G&A'::text,
            'G&A'::text
        UNION ALL
         SELECT 'INDIRECT_COMBINED'::text,
            'OVERHEAD'::text
        UNION ALL
         SELECT 'INDIRECT_COMBINED'::text,
            'G&A'::text
        ), rolled AS (
         SELECT r_1.rate_id,
            COALESCE(sum(pb.gross), 0::numeric) AS pool_gross,
            COALESCE(sum(pb.carved), 0::numeric) AS pool_carved,
            COALESCE(sum(pb.allocable), 0::numeric) AS pool_allocable,
            COALESCE(sum(c.n), 0::numeric) AS carve_outs
           FROM rate r_1
             JOIN pool_for_kind pk ON pk.kind = r_1.kind
             LEFT JOIN v_pool_balance pb ON pb.period = r_1.period AND pb.pool::text = pk.pool
             LEFT JOIN LATERAL ( SELECT count(*) AS n
                   FROM carve_out co
                  WHERE co.period = r_1.period AND co.pool::text = pk.pool) c ON true
          GROUP BY r_1.rate_id
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
    r.pool_amount - b.pool_allocable AS pool_variance,
    -- Three states, not a boolean, and the middle one is the point.
    --
    -- A pool nobody has classified into holds 0.00, the ledger says 0, and
    -- `0 = 0` reported `ties = true`. That is the defect migration `029`
    -- fixed for the eleven statement controls — *an empty period compares
    -- zero against zero and looks green* — reproduced in the control written
    -- to catch it. FRINGE and G&A were both reading TIES over nothing at all.
    --
    -- **And the way out is completion.** While anything is still unjudged, an
    -- empty pool means *nobody has judged any of this yet*, which is NO DATA:
    -- a control that cannot be evaluated has not passed. Once the queue is
    -- empty an empty pool is a real zero and ties honestly. So the tie points
    -- anchor at the completion of the classification, and say so before it.
    CASE
        WHEN r.pool_amount <> b.pool_allocable            THEN 'OPEN'
        WHEN r.pool_amount = 0 AND b.pool_gross = 0
         AND COALESCE(cov.unclassified, 0) > 0            THEN 'NO DATA'
        ELSE 'TIES'
    END AS pool_state,
    (CASE
        WHEN r.pool_amount <> b.pool_allocable            THEN false
        WHEN r.pool_amount = 0 AND b.pool_gross = 0
         AND COALESCE(cov.unclassified, 0) > 0            THEN false
        ELSE true
     END) AS ties
   FROM rate r
     JOIN decision_set ds ON ds.set_id = r.set_id
     JOIN rolled b ON b.rate_id = r.rate_id
   LEFT JOIN v_classification_coverage cov ON cov.period = r.period
 WHERE r.status <> 'SUPERSEDED'::text;

COMMENT ON VIEW v_rate_buildup IS
  'Each live rate against the pool it was built from. pool_state is TIES, '
  'OPEN or NO DATA — a pool nobody has classified into cannot be said to tie '
  'until the queue is empty, which is the 029 rule applied to this control '
  'rather than to the statement register.';

-- ── 2. And the anchors for the rate as a whole ───────────────────────
--
-- A rate is a pool over a base, and `065` anchored only the numerator. Two
-- more comparisons, and each is the one thing a control needs: **two
-- independent sources for one figure.**
--
--   * **Every classified dollar is in exactly one pool.** The signed sum of
--     the live decision lines against the sum of every pool's gross. Nothing
--     has ever compared them, so cost could go missing between the queue and
--     the pools and each pool would still tie to itself perfectly. They agree
--     today at $1,678,057.27 and nothing in the system knew it.
--
--     Signed on both sides deliberately. `v_classification_coverage` measures
--     in **absolute** dollars — 039 chose that so a group is counted by what
--     it moved — and the pools carry the signed position, so the same
--     judgments read $2,219,105.55 and $1,678,057.27. Both are right and
--     comparing them would be a false alarm every time a credit is judged.
--
--   * **The wage base is the payroll register.** The fringe denominator is
--     `SALARIES_WAGES` at $1,835,047.17, and that figure is `register_wages`
--     on the eleventh statement control — *the fringe base comes from the
--     effort distribution, not from the ledger's wage accounts*. The anchor
--     existed and the build-up never pointed at it, so a reviewer reading the
--     rate saw a denominator with nothing behind it.
--
-- What is deliberately **not** anchored here is MTDC. It is labour plus
-- fringe plus direct non-labour less the 200.1 exclusions, and every one of
-- those comes from the model — so a second derivation in SQL would be the
-- same figure computed twice, which is the thing that can disagree with
-- itself. It is anchored through its parts: the labour in it is the wage
-- base below, and the non-labour in it is the DIRECT pool, which point 1
-- covers.
--
-- Read-side only. `POST /api/rates/compute` gates on the statement register
-- because a rate over books that disagree is a rate over the wrong numbers;
-- these are checks *on* the rate it produced, and gating a computation on a
-- control derived from its own output would be circular.
CREATE VIEW v_rate_anchor AS
WITH cov AS (
    SELECT period, unclassified, scope_dollars, pct_dollars_covered
      FROM v_classification_coverage
), judged AS (
    SELECT l.period, COALESCE(sum(l.amount), 0) AS classified_signed
      FROM decision d
      JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
      JOIN ledger_line l ON l.line_id = dl.line_id
     WHERE d.reversed_at IS NULL
     GROUP BY l.period
), pooled AS (
    SELECT period, COALESCE(sum(gross), 0) AS pools_total
      FROM v_pool_balance GROUP BY period
), wage AS (
    SELECT period, max(base_amount) AS wage_base
      FROM rate
     WHERE status <> 'SUPERSEDED' AND base_type = 'SALARIES_WAGES'
     GROUP BY period
)
SELECT p.period, 1 AS seq,
       'POOLS_ACCOUNT_FOR_JUDGMENTS'::text AS control,
       'Every classified dollar lands in exactly one pool'::text AS description,
       COALESCE(j.classified_signed, 0)                     AS expected,
       COALESCE(pl.pools_total, 0)                          AS actual,
       COALESCE(j.classified_signed, 0)
         - COALESCE(pl.pools_total, 0)                      AS variance,
       CASE
           WHEN j.classified_signed IS NULL                 THEN 'NO DATA'
           WHEN COALESCE(j.classified_signed, 0)
                = COALESCE(pl.pools_total, 0)               THEN 'TIES'
           ELSE 'OPEN'
       END                                                  AS state,
       'Signed on both sides: coverage counts absolute dollars by design, '
       'so it is not the figure to compare against a pool.'::text AS note,
       (c.unclassified = 0)                                 AS classification_complete,
       c.pct_dollars_covered
  FROM fiscal_period p
  LEFT JOIN cov c    ON c.period = p.period
  LEFT JOIN judged j ON j.period = p.period
  LEFT JOIN pooled pl ON pl.period = p.period
UNION ALL
SELECT p.period, 2 AS seq,
       'WAGE_BASE_IS_THE_REGISTER'::text,
       'The fringe denominator is the payroll register, not the ledger'::text,
       COALESCE(pr.register_wages, 0),
       COALESCE(w.wage_base, 0),
       COALESCE(pr.register_wages, 0) - COALESCE(w.wage_base, 0),
       CASE
           WHEN w.wage_base IS NULL                         THEN 'NO DATA'
           WHEN pr.register_wages IS NULL                   THEN 'NO DATA'
           WHEN pr.register_wages = w.wage_base             THEN 'TIES'
           ELSE 'OPEN'
       END,
       'The eleventh statement control reconciles the register to the '
       'ledger''s wage accounts; this is the other half — that the rate '
       'actually used it.'::text,
       (c.unclassified = 0),
       c.pct_dollars_covered
  FROM fiscal_period p
  LEFT JOIN cov c ON c.period = p.period
  LEFT JOIN wage w ON w.period = p.period
  LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period;

COMMENT ON VIEW v_rate_anchor IS
  'What the rate is anchored to, beyond each pool tying to itself: that the '
  'pools account for every judgment made, and that the fringe denominator is '
  'the payroll register. NO DATA is not a pass. classification_complete says '
  'whether the anchors are over a finished queue or a partial one.';
