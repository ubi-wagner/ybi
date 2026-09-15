-- 087 · The deployment bootstrap has no session, and that is the record
--
-- `drive_state_machine` and `drive_everyone` each assert that every audit
-- entry names an account and a session, and on a record built from nothing
-- both reported **24 violations** — 18 EVIDENCE_UPLOAD and 6 ACTOR_CREATE,
-- every one written by `app/foundation.py` at boot with
-- `actor = 'deployment bootstrap'` and no actor_id and no session.
--
-- The rows are right and the assertion is wrong. `077` opens the accounts
-- and files the eighteen documents when a Postgres service has been rebuilt
-- and nobody has signed in yet: there is no session because there was no
-- session, and there is no actor_id because the account being created does
-- not exist when the row is written. Naming a person there — Barb, say,
-- because she is the administrator — would be inventing a history, which is
-- exactly what `079` refused to do to 891 rows pointing at a retired
-- account. The honest record of a machine acting alone is a row that says
-- so, and it does.
--
-- So the rule is narrowed rather than relaxed, and it is narrowed **once**.
-- Three instruments held three copies of one predicate — `drive_state_
-- machine`, `drive_everyone` and `review_system` — which is the hand-kept
-- map this file is mostly about. They read this view now.
--
-- And the exemption is the *shape*, not a list of actors. A first draft
-- named `'deployment bootstrap'` literally and left three
-- `INVOICE_REPERIOD` rows on the live record still reported — written by
-- `load_invoices_2025.py (correction)`, which is the same case wearing a
-- different name, and a list of names is the defect one level up.
--
-- Two questions, and they are different:
--
--   * **Is anything named?** `actor` NULL is a change nobody can be held
--     to, and that is always a violation.
--   * **Does it claim a person?** `actor_id` is set only where a real
--     account made the change, and an account acts through a session. So
--     an entry carrying an actor_id and no session is a person's change
--     with no sign-in behind it, which is a violation — while a mechanism
--     that names itself and carries no actor_id had no session to record,
--     because nobody was signed in.
--
-- That leaves one row reported on the live record and it should be: `079`
-- deactivated the retired `tom@ybi.org` and recorded it under **Tom's own
-- name** with no session. The migration did it, not him. Naming a person
-- for an act a migration performed is the shape `079` itself refused when
-- it left 891 rows pointing where they pointed — and it is a finding to
-- answer rather than a predicate to widen.

DROP VIEW IF EXISTS v_audit_orphan;
CREATE VIEW v_audit_orphan AS
SELECT a.*
  FROM audit_log a
 WHERE a.actor IS NULL
    OR btrim(a.actor) = ''
    OR (a.session_id IS NULL AND a.actor_id IS NOT NULL);

COMMENT ON VIEW v_audit_orphan IS
'Audit entries that do not name who made the change and the session they '
'made it in. The deployment bootstrap is excluded because it acts when no '
'person is present and says so in `actor`; everything else with a missing '
'actor or session is a change nobody can be held to.';
