-- 046: the seal freezes the set, and the schema is what says so.
--
-- Sealing is the moment the whole engagement rests on: the hash is taken
-- across every live judgment in the set, and a rate carries it. So a judgment
-- that changes afterwards leaves a stored hash that no longer recomputes —
-- and nothing recomputes it until somebody unseals, which may be months away
-- or never.
--
-- Two routes could do that, both found by driving the system as two people at
-- once rather than by anything failing:
--
--   * `POST /api/classify/decide` read "which set is open" on its own
--     connection before taking the period lock, so seven requests all read
--     the same open set, the seal froze it, and the four judgments still
--     queued behind the seal inserted into it afterwards. The stored hash
--     covered two judgments; the set held six.
--
--   * `POST /api/undo` reverses a classification by setting `reversed_at`,
--     with nothing stopping it doing so inside a sealed set.
--
-- The handlers are fixed. This is the invariant underneath them, so it holds
-- when a handler is wrong or a new one is written next year by somebody who
-- has not read this file.

CREATE OR REPLACE FUNCTION decision_set_is_frozen() RETURNS trigger AS $$
DECLARE
  sealed boolean;
BEGIN
  SELECT s.seal_hash IS NOT NULL INTO sealed
    FROM decision_set s WHERE s.set_id = NEW.set_id;
  IF NOT COALESCE(sealed, false) THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    RAISE EXCEPTION 'decision set % is sealed; a judgment cannot be added to '
                    'it. Unseal it, with a written reason — which supersedes '
                    'any rate computed from it.', NEW.set_id
      USING ERRCODE = 'raise_exception';
  END IF;

  -- An UPDATE only matters where it changes something the seal hashed, or
  -- reverses the judgment out of the set. Anything else — a note, a citation
  -- corrected for spelling — leaves the hash reproducing exactly as stored.
  IF NEW.reversed_at IS DISTINCT FROM OLD.reversed_at
     OR NEW.pool         IS DISTINCT FROM OLD.pool
     OR NEW.function_990 IS DISTINCT FROM OLD.function_990
     OR NEW.federal      IS DISTINCT FROM OLD.federal
     OR NEW.objective_id IS DISTINCT FROM OLD.objective_id
     OR NEW.grade        IS DISTINCT FROM OLD.grade THEN
    RAISE EXCEPTION 'decision % belongs to a sealed set; changing it would '
                    'leave the seal hashing to something the set no longer '
                    'says. Unseal first.', NEW.decision_id
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decision_respects_the_seal ON decision;
CREATE TRIGGER decision_respects_the_seal
  BEFORE INSERT OR UPDATE ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_set_is_frozen();

COMMENT ON FUNCTION decision_set_is_frozen() IS
  'A sealed decision set takes no new judgments and lets none of its own '
  'change. The seal is a hash across the set; a judgment that moves under it '
  'leaves a stored hash that no longer recomputes, and nothing recomputes it '
  'until somebody unseals.';

CREATE OR REPLACE VIEW v_undoable AS
SELECT al.entry_id, al.occurred_at, al.action, al.actor, al.actor_id,
       al.actor_role, al.entity, al.entity_id, al.reason,
       CASE al.action
         WHEN 'CLASSIFY'      THEN 'Classification'
         WHEN 'SEGMENT'       THEN 'Split'
         WHEN 'NOTE'          THEN 'Note'
         WHEN 'TIME_ENTRY'    THEN 'Time entry'
         WHEN 'TIME_REMOVE'   THEN 'Time removed'
         WHEN 'TIME_SUBMIT'   THEN 'Timesheet submitted'
         WHEN 'CERTIFY'       THEN 'Certification'
         WHEN 'EMPLOYMENT'    THEN 'Employment terms'
         WHEN 'EVIDENCE_UPLOAD' THEN 'Document attached'
         WHEN 'SEAL'          THEN 'Seal'
         ELSE al.action
       END                                                   AS label,
       (al.action IN ('CLASSIFY','SEGMENT','NOTE','TIME_ENTRY','TIME_REMOVE',
                      'TIME_SUBMIT','CERTIFY','EMPLOYMENT','EVIDENCE_UPLOAD',
                      'SEAL'))                               AS reversible_action,
       (
         EXISTS (SELECT 1 FROM audit_log u
                  WHERE u.undoes_entry_id = al.entry_id)
         OR
         -- Settled by another route, so there is nothing left to walk back.
         -- Each of these is "the thing this entry did is already not the
         -- case", never "it would be inconvenient to undo".
         CASE al.action
           -- The set this sealed is open again. `unsealed_reason` is what
           -- separates "somebody unsealed it deliberately" from a set that
           -- was never sealed at all.
           WHEN 'SEAL' THEN NOT EXISTS (
                SELECT 1 FROM decision_set s
                 WHERE s.set_id::text = al.entity_id
                   AND s.seal_hash IS NOT NULL)
           -- The judgment was already reversed — by a later judgment of the
           -- same group, which supersedes, or by anything else.
           WHEN 'CLASSIFY' THEN EXISTS (
                SELECT 1 FROM decision d
                 WHERE d.decision_id::text = al.entity_id
                   AND d.reversed_at IS NOT NULL)
           ELSE false
         END
       )                                                      AS already_undone,
       -- A judgment inside a sealed set is not undoable, and the reason is
       -- not that it has been settled — it is that the seal depends on it.
       -- The seal is a hash across every live judgment in the set, so
       -- reversing one underneath it leaves a stored hash that no longer
       -- recomputes, which is the one failure this system cannot detect
       -- later. `already_undone` would be the wrong column: there is
       -- something left to walk back, and the way to reach it is to unseal.
       (al.action = 'CLASSIFY' AND EXISTS (
            SELECT 1 FROM decision d
              JOIN decision_set s USING (set_id)
             WHERE d.decision_id::text = al.entity_id
               AND s.seal_hash IS NOT NULL))               AS blocked_by_seal
  FROM audit_log al
 WHERE al.action NOT IN ('SIGN_IN', 'SIGN_OUT', 'UNDO');

COMMENT ON VIEW v_undoable IS
  'The trail a person can walk back, newest first. already_undone covers both '
  '"somebody pressed undo on it" and "its effect is already gone by another '
  'route". blocked_by_seal is the other kind of stop: a judgment inside a '
  'sealed set has something depending on it, and the way past it is to unseal '
  'rather than to walk it back.';
