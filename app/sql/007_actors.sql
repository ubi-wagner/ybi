-- =====================================================================
-- Actors
--
-- Until now the system took an actor's name as a parameter. That is right
-- for one trusted operator and wrong the moment an employee signs a
-- certification of their own hours or the auditor is given read access:
-- "decided_by = 'Tom Metzinger'" is a claim anyone can make.
--
-- Four roles, because four different people touch this system and they are
-- not interchangeable:
--
--   CONTROLLER  imports, classifies, seals, restates. The daily operator.
--   EMPLOYEE    certifies their OWN effort distribution and nothing else.
--               This is the 2 CFR 200.430(i) signature; it has to be theirs.
--   AUDITOR     reads everything, writes nothing. Not a courtesy — a reviewer
--               who can alter the record cannot attest to it.
--   ADMIN       provisions actors. Deliberately not a superset of CONTROLLER:
--               administering people and making cost judgments are different
--               jobs and separating them is what makes the audit trail mean
--               something.
--
-- Enforcement is app-layer here, with the actor resolved from a signed
-- session rather than from a request field. Row-level security is the
-- defence-in-depth layer on top and is a separate migration: the app-layer
-- predicate has to be right first, because RLS underneath a wrong predicate
-- just fails closed in ways nobody can debug.
-- =====================================================================

CREATE TYPE actor_role AS ENUM ('CONTROLLER', 'EMPLOYEE', 'AUDITOR', 'ADMIN');

CREATE TABLE actor (
  actor_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email           text NOT NULL,
  display_name    text NOT NULL,
  role            actor_role NOT NULL,
  password_hash   text NOT NULL,
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_login_at   timestamptz,

  -- An EMPLOYEE actor is the person whose effort is being certified, so the
  -- account has to name them in the labour records. Nobody else needs it.
  employee_key    text,

  CONSTRAINT actor_email_lower CHECK (email = lower(email)),
  CONSTRAINT employee_needs_key
    CHECK (role <> 'EMPLOYEE' OR employee_key IS NOT NULL)
);

-- Case-insensitive uniqueness on the login identifier.
CREATE UNIQUE INDEX actor_email_key ON actor (email);

-- One EMPLOYEE account per person. Two accounts certifying the same hours is
-- not a feature.
CREATE UNIQUE INDEX actor_employee_key
  ON actor (employee_key) WHERE employee_key IS NOT NULL;

-- Sessions are recorded so a login can be revoked and so the audit log can
-- say which session an action came from, not merely which name was typed.
CREATE TABLE actor_session (
  session_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        uuid NOT NULL REFERENCES actor,
  issued_at       timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  revoked_at      timestamptz,
  user_agent      text NOT NULL DEFAULT '',
  CHECK (expires_at > issued_at)
);
CREATE INDEX ON actor_session (actor_id, issued_at DESC);

-- Sessions are evidence of who did what. They may be revoked, never removed.
CREATE TRIGGER actor_session_immutable
  BEFORE DELETE ON actor_session
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

-- Live sessions, for the "who is signed in" view and for revocation.
CREATE VIEW v_actor_session_live AS
SELECT s.session_id, s.actor_id, a.email, a.display_name, a.role,
       s.issued_at, s.expires_at, s.user_agent
  FROM actor_session s
  JOIN actor a USING (actor_id)
 WHERE s.revoked_at IS NULL
   AND s.expires_at > now();
