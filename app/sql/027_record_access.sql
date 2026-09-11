-- =====================================================================
-- Reading the cost record, as a grant rather than a side effect of rank
--
-- The previous migration took SYSTEM_ADMIN out of the readers, on the
-- grounds that standing the software up is not a reason to read every
-- employee's timesheet. That reasoning holds. What it did not account for
-- is the ordinary case where the person running the system is also the
-- engagement lead, under an agreement with the organisation, and does need
-- to read the record.
--
-- The answer is not to put rank back. It is to say so out loud: access to
-- the record is a grant, it names who gave it and why, and it appears on
-- the roster where anybody can see it.
--
-- Note which direction it runs. The organisation's own administrator grants
-- it — including to the system administrator above them in rank. That is
-- backwards for provisioning and exactly right here: the data belongs to
-- YBI, so YBI is who lets somebody read it. An outside consultant's access
-- to a client's books is granted by the client, not assumed by the
-- consultant, and an auditor asking "who authorised this person to see the
-- payroll" should find a row rather than an inference about job titles.
-- =====================================================================

ALTER TABLE actor
  ADD COLUMN record_access            boolean NOT NULL DEFAULT false,
  ADD COLUMN record_access_reason     text,
  ADD COLUMN record_access_granted_by uuid REFERENCES actor(actor_id),
  ADD COLUMN record_access_granted_at  timestamptz;

ALTER TABLE actor ADD CONSTRAINT record_access_names_its_reason
  CHECK (record_access = (record_access_reason IS NOT NULL
                          AND length(btrim(record_access_reason)) >= 20));

COMMENT ON COLUMN actor.record_access IS
  'Explicitly granted permission to read the cost record, for accounts whose '
  'rank does not carry it. Always names a grantor and a reason.';

-- Nobody lets themselves into the books.
CREATE FUNCTION record_access_is_granted_by_somebody_else() RETURNS trigger
AS $$
BEGIN
  IF NEW.record_access AND NEW.record_access_granted_by = NEW.actor_id THEN
    RAISE EXCEPTION
      'an account cannot grant itself access to the cost record — the '
      'organisation grants it, and the trail should show two people';
  END IF;
  IF NEW.record_access AND NEW.record_access_granted_by IS NULL THEN
    RAISE EXCEPTION 'access to the cost record has to name who granted it';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER actor_record_access_grantor
  BEFORE INSERT OR UPDATE OF record_access, record_access_granted_by ON actor
  FOR EACH ROW EXECUTE FUNCTION record_access_is_granted_by_somebody_else();


-- ── Correcting an account ────────────────────────────────────────────
--
-- Seeding the payroll produces accounts whose email addresses were derived
-- from a naming convention rather than looked up, and a person who cannot
-- sign in also cannot have their account replaced — the employee key is
-- unique, so the wrong account squats the right one's place. Correcting the
-- address in place is the only way out that does not involve deleting an
-- account, which is never right here: every judgment points at one.

ALTER TABLE actor ADD COLUMN email_confirmed boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN actor.email_confirmed IS
  'False where the address was derived from a naming convention rather than '
  'known. Such an account cannot be signed into until somebody who knows the '
  'address corrects it, and the roster says which ones those are.';


-- ── The roster, with both ────────────────────────────────────────────

DROP VIEW v_account_standing;
DROP VIEW v_actor_access;

CREATE VIEW v_actor_access AS
SELECT a.actor_id, a.email, a.display_name, a.role, a.is_active,
       a.employee_key, a.created_at, a.last_login_at,
       a.password_set_by, a.password_set_at,
       (a.password_set_by = 'SEED')                        AS holds_bootstrap_password,
       (a.password_set_by <> 'SELF')                       AS must_set_password,
       a.email_confirmed,
       a.record_access, a.record_access_reason,
       g.display_name                                      AS record_access_granted_by_name,
       a.record_access_granted_at,
       -- What this account may actually read. Rank carries it for the
       -- controller, the auditor and the organisation's own administrator;
       -- anybody else needs the grant above.
       (a.role IN ('CONTROLLER', 'AUDITOR', 'ORG_ADMIN') OR a.record_access)
                                                           AS may_read_record,
       p.display_name                                      AS provisioned_by_name,
       a.provisioned_by,
       COALESCE(
         (SELECT array_agg(ap.portfolio ORDER BY ap.portfolio)
            FROM actor_portfolio ap
           WHERE ap.actor_id = a.actor_id AND ap.revoked_at IS NULL),
         '{}')                                             AS portfolios,
       EXISTS (SELECT 1 FROM actor_portfolio ap
                WHERE ap.actor_id = a.actor_id AND ap.revoked_at IS NULL
                  AND ap.portfolio = 'CONTROLLER')         AS may_seal,
       (SELECT count(*) FROM actor_session s
         WHERE s.actor_id = a.actor_id AND s.revoked_at IS NULL
           AND s.expires_at > now())                       AS live_sessions,
       (SELECT count(*) FROM login_attempt l
         WHERE l.email = a.email AND NOT l.succeeded
           AND l.attempted_at > now() - interval '24 hours') AS failures_24h
  FROM actor a
  LEFT JOIN actor p ON p.actor_id = a.provisioned_by
  LEFT JOIN actor g ON g.actor_id = a.record_access_granted_by;

COMMENT ON VIEW v_actor_access IS
  'The roster as an administrator needs to read it: who they are, who let '
  'them in, what they may judge, what they may read and on whose authority, '
  'and whether their password and address still identify one person.';

CREATE VIEW v_account_standing AS
SELECT actor_id, email, display_name, role, is_active, employee_key,
       created_at, last_login_at, password_set_by, password_set_at,
       holds_bootstrap_password, must_set_password, email_confirmed,
       live_sessions, failures_24h, portfolios, may_seal, may_read_record,
       record_access, record_access_reason, record_access_granted_by_name,
       provisioned_by, provisioned_by_name
  FROM v_actor_access;
