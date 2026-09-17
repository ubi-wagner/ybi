-- 090 — a carve-out cannot exceed the pool it comes out of
--
-- `POST /api/rates/compute` built the 2 CFR 200.465 facilities carve-out one
-- facility at a time as `overhead_gross * (excluded_f / usable_f)` and summed
-- the rows. With one building that is exactly right. With five it carves five
-- shares of the *whole* pool: an estate half let building by building would
-- have removed 250% of overhead and left the rate negative.
--
-- **Nothing could have caught it.** The pool ties to itself whatever the
-- carve-outs say — `v_pool_balance.allocable` is gross less carved and
-- `rate.pool_amount` is what the computation used, so `v_rate_buildup`
-- reports TIES on both sides of a wrong answer. And the reference record has
-- carried exactly one building for the life of the rate engine, so the shape
-- had no instance to be wrong in. It is `029` in the largest adjustment in
-- the model: a control that is green because the population is degenerate.
--
-- The handler weights each building by the estate's usable square footage
-- now, which reduces to the old arithmetic exactly when there is one
-- building — so nothing published moves. This is the control that says so
-- when it does not.
--
-- Three states, because a control that cannot be evaluated has not passed:
--
--   NO DATA   nothing has been carved out of this pool at all. That is the
--             normal state of every pool but OVERHEAD, and of OVERHEAD until
--             a building is measured — and it is not a pass, because it is
--             also what a carve-out that failed to fire looks like.
--   TIES      something was carved and what is left is a figure a rate can
--             honestly be taken over.
--   OPEN      the carve-out meets or exceeds the pool. There is no allocable
--             cost left, so any rate over it is meaningless.

CREATE OR REPLACE VIEW v_carve_out_check AS
SELECT pb.period,
       pb.pool,
       pb.gross,
       pb.carved,
       pb.allocable,
       (SELECT count(*) FROM carve_out c
         WHERE c.pool = pb.pool AND c.period = pb.period)  AS carve_outs,
       CASE WHEN pb.carved = 0            THEN 'NO DATA'
            WHEN pb.gross <= 0            THEN 'NO DATA'
            WHEN pb.allocable <= 0        THEN 'OPEN'
            ELSE 'TIES' END                                AS state,
       CASE WHEN pb.carved = 0
              THEN 'Nothing has been carved out of this pool.'
            WHEN pb.gross <= 0
              THEN 'The pool holds nothing, so there is nothing to carve.'
            WHEN pb.allocable <= 0
              THEN format('Carve-outs of %s meet or exceed the pool''s %s, '
                          'so nothing is left to take a rate over.',
                          to_char(pb.carved, 'FM999,999,999.00'),
                          to_char(pb.gross, 'FM999,999,999.00'))
            ELSE format('%s carved from %s leaves %s allocable.',
                        to_char(pb.carved, 'FM999,999,999.00'),
                        to_char(pb.gross, 'FM999,999,999.00'),
                        to_char(pb.allocable, 'FM999,999,999.00'))
       END                                                 AS needs
  FROM v_pool_balance pb;

COMMENT ON VIEW v_carve_out_check IS
  'Whether what was carved out of a pool leaves a figure a rate can be taken '
  'over. Nothing had ever compared the two: v_pool_balance computes allocable '
  'as gross less carved and v_rate_buildup ties rate.pool_amount to that, so '
  'both sides agree however large the carve-out is. NO DATA is not a pass — '
  'an unfired carve-out and a building with no rental space look identical '
  'from here, which is why the state is three-valued.';
