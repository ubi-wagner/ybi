-- =====================================================================
-- Account security: where a password came from, and how many tries
--
-- Seeding provisions every account with one bootstrap password. That is what
-- a bootstrap is, but it has to be visible until it is over: while four
-- people share a password, every signature the system holds in their names is
-- one any of them could have written, and a certification is only worth the
-- identity behind it.
--
-- So the origin of a password is recorded, not just its hash. SEED means
-- nobody has taken ownership of the account yet; ADMIN means it was reset for
-- someone; SELF is the only one that supports a signature.
-- =====================================================================

CREATE TYPE password_origin AS ENUM ('SEED', 'ADMIN', 'SELF');

ALTER TABLE actor
  ADD COLUMN password_set_by password_origin NOT NULL DEFAULT 'SEED',
  ADD COLUMN password_set_at timestamptz NOT NULL DEFAULT now();

COMMENT ON COLUMN actor.password_set_by IS
  'Who last set this password. SEED = still the shared bootstrap value, so '
  'the account does not yet identify one person.';


-- ── Throttling ───────────────────────────────────────────────────────
--
-- bcrypt makes each guess expensive but nothing made a series of them
-- expensive. A record whose accounts can be ground down by a script is not a
-- record. Attempts are kept for both halves of the pair — the email tried and
-- the address it came from — because locking only on email lets one attacker
-- lock every employee out of their own account.

CREATE TABLE login_attempt (
  attempt_id  bigserial PRIMARY KEY,
  email       text NOT NULL,
  ip          text NOT NULL DEFAULT '',
  succeeded   boolean NOT NULL,
  attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON login_attempt (email, attempted_at DESC);
CREATE INDEX ON login_attempt (ip, attempted_at DESC);

-- Failures since the last success, within the window. A successful sign-in
-- clears the count, so a person who mistypes four times and then gets it right
-- is not one failure away from a lockout tomorrow.
--
-- The count is per email and NOT per address. Locking on the address looks
-- like the stronger rule and is the wrong one here: everyone at YBI shares an
-- office connection, and behind Railway's proxy every request arrives from the
-- same peer, so one person mistyping their password eight times would lock out
-- the whole organisation — including the administrator who would have to undo
-- it. The address is recorded, because the record should say where a failed
-- attempt came from; it just does not gate anyone else's sign-in.
CREATE OR REPLACE FUNCTION recent_login_failures(p_email text,
                                                 p_window interval DEFAULT '15 minutes')
RETURNS integer LANGUAGE sql STABLE AS $$
  SELECT count(*)::integer FROM login_attempt a
   WHERE a.attempted_at > now() - p_window
     AND NOT a.succeeded
     AND a.email = p_email
     AND a.attempted_at > COALESCE(
           (SELECT max(s.attempted_at) FROM login_attempt s
             WHERE s.succeeded AND s.email = p_email
               AND s.attempted_at > now() - p_window),
           '-infinity'::timestamptz)
     -- Failures against the old password do not count against the new one.
     -- Without this the lockout survives the reset, and the message it shows
     -- — ask an administrator to reset your password — would be advice that
     -- does not work.
     AND a.attempted_at > COALESCE(
           (SELECT ac.password_set_at FROM actor ac WHERE ac.email = p_email),
           '-infinity'::timestamptz);
$$;


-- ── Who has not taken ownership of their account ─────────────────────

CREATE VIEW v_account_standing AS
SELECT a.actor_id, a.email, a.display_name, a.role, a.is_active,
       a.employee_key, a.created_at, a.last_login_at,
       a.password_set_by, a.password_set_at,
       (a.password_set_by = 'SEED')            AS holds_bootstrap_password,
       (SELECT count(*) FROM actor_session s
         WHERE s.actor_id = a.actor_id
           AND s.revoked_at IS NULL
           AND s.expires_at > now())           AS live_sessions,
       (SELECT count(*) FROM login_attempt l
         WHERE l.email = a.email AND NOT l.succeeded
           AND l.attempted_at > now() - interval '24 hours') AS failures_24h
  FROM actor a;

COMMENT ON VIEW v_account_standing IS
  'Account hygiene. holds_bootstrap_password means the seeded password has '
  'never been replaced, so the account does not yet identify one person and '
  'anything signed from it is correspondingly weak.';
