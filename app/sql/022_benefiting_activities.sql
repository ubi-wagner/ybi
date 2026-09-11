-- =====================================================================
-- Unallowable activity is a cost objective
--
-- The rate engine models fundraising and unallowable activity as objectives
-- so that each bears its share of indirect cost. That is not a modelling
-- convenience: 2 CFR 200.413 and Appendix IV B.3.d say a benefiting activity
-- takes an allocation whether or not anything is recovered on it, and it is
-- precisely what stops the federal objectives absorbing cost that belongs to
-- lobbying or a gala.
--
-- FUNDRAISING was already in the chart. Its counterpart was not, so the
-- allocation the engine produced could not be written down — the foreign key
-- refused an objective the chart had never heard of. The engine was right and
-- the chart was short a row.
--
-- It is marked not-final: it is a terminal destination for cost, but it is
-- not a final cost objective in the sense the base uses, and nothing is ever
-- billed to it.
-- =====================================================================

INSERT INTO cost_objective (objective_id, period, label, objective_type,
                            is_federal, is_final, active)
VALUES ('UNALLOWABLE-ACTIVITY', '2025',
        'Unallowable activity (bears indirect, recovers nothing)',
        'UNALLOWABLE', false, false, true)
ON CONFLICT (objective_id) DO NOTHING;

COMMENT ON TABLE allocation IS
  'Where each allocable indirect dollar landed. Includes the benefiting '
  'activities — fundraising and unallowable — which bear their share under '
  '2 CFR 200.413 and recover none of it.';
