-- 068 — administrative labour: in the base, or in the G&A pool
--
-- `YBI-GA` carries $264,444.90 of wages ($322,358.33 with fringe) and the
-- model treats it as a **cost objective**, so it takes a $100,013.06
-- allocation of indirect rather than forming part of it. Appendix IV B puts
-- the director's office, accounting and personnel administration *in* the G&A
-- pool, and the YBI-GA distribution is Kelly, Ruby, Shaulis, Jaric, Politsky
-- and Ewing — the administrator herself. Modelling that as an objective
-- allocates the indirect pool to its own administration, which recovers from
-- nobody.
--
-- The counter-argument is real and does not apply here: FUNDRAISING and
-- UNALLOWABLE-ACTIVITY *are* deliberately benefiting objectives, because
-- 200.413 and Appendix IV B.3.d say they bear indirect while recovering
-- nothing. General administration is the opposite case — it **is** the
-- indirect.
--
-- It is worth 34.82% against 43.99% on the same sealed judgments, which is
-- ~$463,907 a year on a $5.06m direct base. That is too large to be a
-- property of the code, and it is a judgment rather than arithmetic: whether
-- YBI-GA is genuinely general administration, or the bucket unattributable
-- time went into, is something only the person who built the reconstruction
-- can say.
--
-- So this migration does not change any rate. It makes the treatment a
-- **recorded choice on the rate**, the way `base_type` already records which
-- base a rate was taken over. A rate that does not say which basis produced
-- it is one a reviewer cannot reproduce, and until now nothing said.

ALTER TABLE rate
    ADD COLUMN IF NOT EXISTS admin_labour_basis text NOT NULL DEFAULT 'OBJECTIVE';

ALTER TABLE rate
    DROP CONSTRAINT IF EXISTS rate_admin_labour_basis_check;
ALTER TABLE rate
    ADD CONSTRAINT rate_admin_labour_basis_check
    CHECK (admin_labour_basis IN ('OBJECTIVE', 'POOL'));

COMMENT ON COLUMN rate.admin_labour_basis IS
    'How general-administration labour was treated when this rate was '
    'computed. OBJECTIVE: YBI-GA is a cost objective in the base and takes '
    'an allocation of indirect. POOL: its wages and fringe form part of the '
    'G&A pool, per 2 CFR 200 Appendix IV B. The default is OBJECTIVE, which '
    'is what every rate before migration 068 used — stated rather than '
    'assumed, so an old rate is not silently relabelled.';


-- What the choice is worth, read off the record rather than recalculated by
-- whoever is asking. Both figures on one row, so the decision is taken with
-- the alternative visible instead of against a number somebody remembers.
--
-- It reports on the rate *as computed* and never changes it. The comparison
-- is arithmetic on figures already recorded: the administrative objective's
-- own base amount moves from the denominator to the G&A numerator, which is
-- the whole of the difference between the two treatments.
DROP VIEW IF EXISTS v_admin_labour_decision;
CREATE VIEW v_admin_labour_decision AS
WITH live AS (
    SELECT r.period, r.kind, r.rate, r.pool_amount, r.base_amount,
           r.admin_labour_basis, r.rate_id
      FROM rate r
     WHERE r.status <> 'SUPERSEDED'
),
combined AS (
    SELECT period, rate_id, rate, pool_amount, base_amount, admin_labour_basis
      FROM live WHERE kind = 'INDIRECT_COMBINED'
),
admin AS (
    -- What the administrative objective carries in the base. NULL where it
    -- has no allocation row at all, which is a different fact from zero and
    -- is reported as such below.
    SELECT c.period, c.rate_id, sum(a.base_amount) AS admin_in_base
      FROM combined c
      JOIN allocation a ON a.rate_id = c.rate_id
     WHERE a.objective_id = 'YBI-GA'
     GROUP BY c.period, c.rate_id
)
SELECT c.period,
       c.admin_labour_basis                                   AS basis_used,
       c.rate                                                 AS rate_as_computed,
       c.pool_amount                                          AS pool_as_computed,
       c.base_amount                                          AS base_as_computed,
       a.admin_in_base,
       CASE WHEN a.admin_in_base IS NULL THEN NULL
            WHEN c.base_amount - a.admin_in_base <= 0 THEN NULL
            ELSE round((c.pool_amount + a.admin_in_base)
                       / (c.base_amount - a.admin_in_base), 6)
       END                                                    AS rate_if_pooled,
       CASE WHEN a.admin_in_base IS NULL THEN NULL
            WHEN c.base_amount - a.admin_in_base <= 0 THEN NULL
            ELSE round((c.pool_amount + a.admin_in_base)
                       / (c.base_amount - a.admin_in_base), 6) - c.rate
       END                                                    AS movement,
       CASE
           WHEN c.admin_labour_basis = 'POOL'   THEN 'DECIDED — in the pool'
           WHEN a.admin_in_base IS NULL         THEN 'NO DATA'
           ELSE 'OPEN — administration is an objective'
       END                                                    AS state,
       'Appendix IV B puts the director''s office, accounting and personnel '
       'administration in the G&A pool. Modelling it as an objective '
       'allocates the pool to its own administration. FUNDRAISING and '
       'UNALLOWABLE-ACTIVITY stay objectives on purpose — 200.413 makes them '
       'bear indirect while recovering nothing, which is the opposite case.'
                                                              AS note
  FROM combined c
  LEFT JOIN admin a USING (period, rate_id);

COMMENT ON VIEW v_admin_labour_decision IS
    'The administrative-labour question with both answers on one row. '
    'NO DATA where the rate has no YBI-GA allocation to move, because a '
    'choice that cannot be evaluated has not been made — the same '
    'three-state rule the statement register follows.';


-- And the control has to know the choice was made.
--
-- `v_rate_buildup` compares `rate.pool_amount` against what the ledger
-- classification puts in that pool. Under `admin_labour_basis = 'POOL'` the
-- G&A pool deliberately carries $322,358.33 that came from the effort
-- distribution rather than from a classification decision, so the comparison
-- reported **OPEN by exactly that amount** the moment the choice was made.
--
-- That is the `FACILITY_UNPARTITIONED` shape: a control nobody can clear by
-- doing the work teaches the reader the list is wrong, and the next real
-- failure they see they will dismiss. The expected pool is read against the
-- basis the rate was computed on, the way `pool_state` is already read
-- against the completion of the classification rather than against the pool
-- alone.
--
-- The administrative labour it adds back is read from the rate's own
-- allocation rows under the other basis — no, it cannot be: under POOL the
-- objective has gone. So it comes from `v_labor_effective`, which is where
-- the figure came from in the first place, plus fringe at the rate this same
-- computation produced. One source, not a second copy.
DROP VIEW IF EXISTS v_rate_buildup;
CREATE VIEW v_rate_buildup AS
WITH pool_for_kind AS (
    SELECT 'FRINGE'::text AS kind, 'FRINGE'::text AS pool
    UNION ALL SELECT 'OVERHEAD',          'OVERHEAD'
    UNION ALL SELECT 'G&A',               'G&A'
    UNION ALL SELECT 'INDIRECT_COMBINED', 'OVERHEAD'
    UNION ALL SELECT 'INDIRECT_COMBINED', 'G&A'
),
-- **One row per rate, and deliberately not joined to `pool_for_kind`.**
-- The first draft did join it, so INDIRECT_COMBINED — which is two rows of
-- that table — multiplied the G&A pool and the build-up reported OPEN by
-- exactly the G&A gross. Aggregate first, add this once afterwards.
admin_pooled AS (
    SELECT r.rate_id,
           CASE WHEN r.admin_labour_basis = 'POOL'
                THEN round(COALESCE(le.wages, 0) * (1 + COALESCE(fr.rate, 0)), 2)
                ELSE 0 END AS amount
      FROM rate r
      LEFT JOIN LATERAL (
          SELECT sum(distributed_wages) AS wages
            FROM v_labor_effective
           WHERE period = r.period AND objective_id = 'YBI-GA') le ON true
      LEFT JOIN LATERAL (
          SELECT f.rate FROM rate f
           WHERE f.period = r.period AND f.kind = 'FRINGE'
             AND f.set_id = r.set_id AND f.status <> 'SUPERSEDED'
           ORDER BY f.computed_at DESC LIMIT 1) fr ON true
),
rolled AS (
    SELECT r.rate_id,
           COALESCE(sum(pb.gross), 0)     AS pool_gross,
           COALESCE(sum(pb.carved), 0)    AS pool_carved,
           COALESCE(sum(pb.allocable), 0) AS pool_allocable,
           COALESCE(sum(c.n), 0)          AS carve_outs
      FROM rate r
      JOIN pool_for_kind pk ON pk.kind = r.kind
      LEFT JOIN v_pool_balance pb
             ON pb.period = r.period AND pb.pool::text = pk.pool
      LEFT JOIN LATERAL (SELECT count(*) AS n FROM carve_out co
                          WHERE co.period = r.period
                            AND co.pool::text = pk.pool) c ON true
     GROUP BY r.rate_id
)
SELECT r.period, r.rate_id, r.kind, r.pool_amount,
       r.base_type::text AS base_type, r.base_amount, r.rate, r.status,
       r.seal_hash, r.computed_at, r.computed_by,
       r.admin_labour_basis,
       ds.label AS decision_set, ds.sealed_at, ds.sealed_by,
       -- Administrative labour reaches only the pools that contain G&A.
       b.pool_gross     + adm.extra AS pool_gross,
       b.pool_carved                AS pool_carved,
       b.pool_allocable + adm.extra AS pool_allocable,
       b.carve_outs,
       adm.extra                    AS pool_admin_labour,
       r.pool_amount - (b.pool_allocable + adm.extra) AS pool_variance,
       CASE
           WHEN r.pool_amount <> b.pool_allocable + adm.extra THEN 'OPEN'
           WHEN r.pool_amount = 0 AND b.pool_gross + adm.extra = 0
                AND COALESCE(cov.unclassified, 0) > 0 THEN 'NO DATA'
           ELSE 'TIES'
       END AS pool_state,
       CASE
           WHEN r.pool_amount <> b.pool_allocable + adm.extra THEN false
           WHEN r.pool_amount = 0 AND b.pool_gross + adm.extra = 0
                AND COALESCE(cov.unclassified, 0) > 0 THEN false
           ELSE true
       END AS ties
  FROM rate r
  JOIN decision_set ds ON ds.set_id = r.set_id
  JOIN rolled b ON b.rate_id = r.rate_id
  JOIN LATERAL (
      SELECT CASE WHEN r.kind IN ('G&A', 'INDIRECT_COMBINED')
                  THEN COALESCE(ap.amount, 0) ELSE 0 END AS extra
        FROM (SELECT 1) _
        LEFT JOIN admin_pooled ap ON ap.rate_id = r.rate_id) adm ON true
  LEFT JOIN v_classification_coverage cov ON cov.period = r.period
 WHERE r.status <> 'SUPERSEDED';

COMMENT ON VIEW v_rate_buildup IS
    'The rate against the pool underneath it. `pool_admin_labour` is what '
    'the administrative-labour decision added to G&A — zero under the '
    'OBJECTIVE basis, and read from the effort distribution rather than '
    'from a classification under POOL, because that is where the figure '
    'comes from.';
