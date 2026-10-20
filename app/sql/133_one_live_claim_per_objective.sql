-- 133 · One standing claim per objective, and never two
--
-- **The register carried two live positions for one award, and every reader
-- added them together.** Recomputing DRIVE-AM on the locked rate left the
-- accepted $128,474.23 standing and wrote $136,534.61 beside it, so the
-- acceptance form NCDMM signs printed $265,008.84 — a figure YBI does not
-- owe, on the one page that goes to a sponsor.
--
-- `POST /api/restate` supersedes the prior restatement, and only
-- `WHERE status = 'PROPOSED'`. That narrowness is right about the thing it
-- was protecting: a position the sponsor has **accepted** must not be
-- replaced silently. What it does not do is refuse the act — it declines to
-- supersede and then writes the new row anyway, so the guard produces
-- exactly the state it exists to prevent.
--
-- **And the index that would have caught it is already there, on the right
-- columns, with the right predicate, and is not unique.**
-- `restatement_period_objective_id_idx` is `(period, objective_id) WHERE
-- status <> 'SUPERSEDED'` — written for lookups by somebody who had the
-- shape in mind. One word short of the invariant.
--
-- It is `one_live_decision_per_unit` in the last register that lacked it: a
-- ledger line carries one live decision, a ledger line carries one live
-- explanation (`125`), a charge code one live manager, a person one live
-- grant — and an objective now carries one live claim. `125` is the nearest
-- relative and its sentence is the same one: *over-explained reads exactly
-- like a plug and is worse, because each item is impeccable.*
--
-- The predicate is the `STANDING` set the routers already read — PROPOSED,
-- SUBMITTED, ACCEPTED — rather than `<> 'SUPERSEDED'`. **REJECTED is
-- deliberately not standing**: a sponsor saying no is the reason to measure
-- again, and an index that blocked that would be a control nobody can clear
-- by doing the work.

BEGIN;

-- ── 1 · the repair ───────────────────────────────────────────────────
--
-- Where an objective carries more than one standing claim, the **newest is
-- the position** and the rest are history. That is this system's model of
-- change everywhere else — a decision, a rate, a certification — and it
-- erases nothing: a superseded row keeps its `decided_at`, its
-- `decided_note` and its `modification_ref`, so *NCDMM accepted
-- $320,427.12 on 15 September* is still readable, and now carries a date
-- rather than standing as a claim YBI would bill on.
--
-- Nothing is deleted and nothing is chosen between: the later computation
-- is the one somebody asked for, and the earlier one is what it was meant
-- to replace.

CREATE TEMP TABLE overtaken ON COMMIT DROP AS
  SELECT r.restatement_id, r.period, r.objective_id, r.status::text AS was
    FROM restatement r
   WHERE r.status IN ('PROPOSED', 'SUBMITTED', 'ACCEPTED')
     AND EXISTS (SELECT 1 FROM restatement later
                  WHERE later.period = r.period
                    AND later.objective_id = r.objective_id
                    AND later.status IN ('PROPOSED', 'SUBMITTED', 'ACCEPTED')
                    AND (later.computed_at, later.restatement_id)
                        > (r.computed_at, r.restatement_id));

INSERT INTO audit_log (actor, action, entity, entity_id, before_state, reason)
  SELECT 'migration 133', 'RESTATEMENT_SUPERSEDE', 'restatement',
         o.restatement_id::text,
         jsonb_build_object('status', o.was, 'objective_id', o.objective_id,
                            'period', o.period),
         'A later computation stands for ' || o.objective_id || '. Two '
         'standing claims on one objective were added together by every '
         'reader, so the papers put the sum of a position and its own '
         'replacement in front of the sponsor. The later one is the '
         'position; this is history and keeps its dates.'
    FROM overtaken o;

UPDATE restatement SET status = 'SUPERSEDED'
 WHERE restatement_id IN (SELECT restatement_id FROM overtaken);

-- ── 2 · the invariant ────────────────────────────────────────────────

CREATE UNIQUE INDEX one_standing_restatement_per_objective
    ON restatement (period, objective_id)
 WHERE status IN ('PROPOSED', 'SUBMITTED', 'ACCEPTED');

COMMENT ON INDEX one_standing_restatement_per_objective IS
  'An objective carries one claim YBI would bill on. Recomputing supersedes '
  'a PROPOSED one; replacing a SUBMITTED or ACCEPTED one is two conscious '
  'acts, because taking back a position somebody agreed to is never '
  'automatic. REJECTED is not standing — being told no is a reason to '
  'measure again.';

COMMIT;
