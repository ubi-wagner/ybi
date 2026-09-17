-- One person, one account.
--
-- The roster said `tom@ybi.org`, which was the naming convention rather than a
-- lookup; his own email of 10 September 2026 carries the four real YBI
-- addresses and he is `tmetzinger@`. The bootstrap in `077` will not touch an
-- account that exists, so it correctly opened the right address *beside* the
-- wrong one — and left two active accounts for one person, which is how a
-- timesheet and a certification come apart, and how "who classified this"
-- gains two answers.
--
-- He has now signed in as `tmetzinger@ybi.org`. The old address is retired.
--
-- **Retired, not removed.** 891 audit rows and all eighteen foundational
-- documents point at that actor row: it is the provenance of the entire 2025
-- classification. Deleting it would orphan the record it authorised, which is
-- the opposite of what the record is for — the same rule
-- `POST /api/actors/{id}/active` states in its own docstring, and the same
-- reason `027` corrects an address in place rather than deleting an account.
-- Those 891 rows keep pointing where they point, because those acts *were*
-- performed on that account and rewriting them would be inventing a history.
--
-- Three fences, and the first is the one that matters:
--
--   * it fires only where the replacement exists and is active. A recovery
--     that restored the old row and not the new one would otherwise leave
--     the controller with no way in at all — a migration that can lock
--     somebody out is worse than the duplicate it tidies.
--   * it revokes that account's live sessions in the same statement that
--     turns it off, because `app/auth.py` requires `a.is_active` to resolve a
--     token but a revoked session is the honest record of the sign-out.
--   * it is idempotent: run twice it changes nothing the second time, and it
--     writes no second audit row.
--
-- It does **not** move the portfolio grant. Both rows already hold CONTROLLER
-- in their own right, so there is nothing to carry across, and a grant history
-- that gained a row nobody made would be a worse record than one that did not.

WITH replacement AS (
    SELECT actor_id FROM actor
     WHERE email = 'tmetzinger@ybi.org' AND is_active
), retired AS (
    UPDATE actor a
       SET is_active = false
      FROM replacement r
     WHERE a.email = 'tom@ybi.org'
       AND a.is_active
       AND r.actor_id <> a.actor_id
    RETURNING a.actor_id, a.display_name
), sessions AS (
    UPDATE actor_session s SET revoked_at = now()
      FROM retired t
     WHERE s.actor_id = t.actor_id AND s.revoked_at IS NULL
    RETURNING s.session_id
)
INSERT INTO audit_log (actor, actor_id, actor_role, action, entity, entity_id,
                       before_state, after_state, reason)
SELECT t.display_name, t.actor_id, 'CONTROLLER', 'ACTOR_ACTIVE', 'actor',
       t.actor_id::text,
       jsonb_build_object('is_active', true,  'email', 'tom@ybi.org'),
       jsonb_build_object('is_active', false, 'email', 'tom@ybi.org',
                          'superseded_by', 'tmetzinger@ybi.org',
                          'live_sessions_revoked',
                          (SELECT count(*) FROM sessions)),
       'Superseded address. tom@ybi.org was the naming convention rather '
       || 'than a lookup; the controller signs in as tmetzinger@ybi.org. '
       || 'Retired rather than deleted: this account authorised the 2025 '
       || 'classification and every audit row under it stands.'
  FROM retired t;
