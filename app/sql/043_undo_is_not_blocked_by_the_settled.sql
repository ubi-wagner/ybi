-- 043 — an undo trail that cannot jam
--
-- Undo walks newest first, and that rule is right: undoing out of order puts
-- a value back that a later action had already moved on from. But there was
-- no way *past* an entry that can never be undone, and one of those sits in
-- the middle of the ordinary lifecycle.
--
-- Seal, compute a rate, unseal with a reason. Now the SEAL entry is still
-- offered as undoable — nothing has an `undoes_entry_id` pointing at it — and
-- undoing it answers "That set is not sealed", because the explicit unseal
-- already took care of that. Newest first means the chain stops there, so
-- every classification and every document upload older than the seal becomes
-- permanently unreachable. A state machine drive walked back forty times and
-- moved one thing.
--
-- The distinction the view was missing is between two very different reasons
-- an entry cannot be walked back:
--
--   it must not be     something later depends on it — a genuine blocker,
--                      and the chain is *supposed* to stop
--   it need not be     its effect is already gone, by another route — there
--                      is nothing to walk back and nothing to block
--
-- `already_undone` covered only "somebody pressed undo on it". It now covers
-- the second case too, so a settled entry is skipped rather than standing in
-- front of everything older than it.

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
       )                                                      AS already_undone
  FROM audit_log al
 WHERE al.action NOT IN ('SIGN_IN', 'SIGN_OUT', 'UNDO');

COMMENT ON VIEW v_undoable IS
  'The trail a person can walk back, newest first. already_undone covers both '
  '"somebody pressed undo on it" and "its effect is already gone by another '
  'route" — a seal whose set has since been unsealed, a classification a '
  'later judgment superseded. Without the second, one settled entry stands in '
  'front of everything older than it and the trail jams: a drive once walked '
  'back forty times and moved one thing.';
