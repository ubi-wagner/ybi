-- =====================================================================
-- Who provisions whom, and who may judge what
--
-- Two axes, because the organisation has two different kinds of authority
-- and collapsing them is how a cost system ends up letting the person who
-- creates the accounts also sign the judgments.
--
--   The provisioning ladder is a hierarchy, and it only runs downward.
--   A system administrator sets up the organisation's administrator; the
--   organisation's administrator sets up controllers and employees. Nobody
--   provisions a peer or a superior, ever. That is the one lesson worth
--   carrying over from the govwin estate: no upward escalation.
--
--   Portfolios are not a hierarchy. They are a set, and a person holds the
--   union of the ones granted to them. The main controller holds
--   CONTROLLER. An inventory manager holds INVENTORY. Someone who is both
--   the facilities manager and the inventory manager holds both, and that
--   is an ordinary thing rather than a special case.
--
-- The reason portfolios are a set and not a ladder is the seal. Only
-- CONTROLLER seals a decision set, unseals one, or computes a rate. No
-- amount of other authority adds up to that, because the guarantee this
-- whole system rests on is that the classifications were fixed before any
-- rate existed, and a guarantee that several people can quietly satisfy is
-- not one an auditor can rely on.
--
-- Two further rules, both in the schema rather than in a handler:
--
--   Nobody grants themselves a portfolio. An administrator who needs one
--   asks the administrator above them. With one system administrator who
--   always exists, that is never a deadlock — and it means the grant trail
--   reads as two people rather than one.
--
--   Everybody in the organisation has a timesheet and a place to put
--   documents, whatever else they do. A controller is an employee too.
-- =====================================================================


-- ── The ladder ───────────────────────────────────────────────────────
--
-- Replacing the type rather than extending it: ALTER TYPE ... ADD VALUE
-- cannot be used in the same transaction that adds it, and every migration
-- here runs inside one. The two dependent views come down and go back up.

CREATE TYPE org_role AS ENUM (
  'SYSTEM_ADMIN',   -- provisions the organisation's administrator. Not staff.
  'ORG_ADMIN',      -- provisions controllers and employees. Not a judge.
  'CONTROLLER',     -- holds one or more portfolios; the work of the system
  'EMPLOYEE',       -- their own time, their own certification, their own uploads
  'AUDITOR'         -- reads everything, writes nothing
);

COMMENT ON TYPE org_role IS
  'The provisioning ladder. Rank is about who may create accounts, not '
  'about who may make cost judgments — that is what portfolios are for.';

DROP VIEW v_account_standing;
DROP VIEW v_actor_session_live;

ALTER TABLE actor DROP CONSTRAINT employee_needs_key;
ALTER TABLE actor ADD COLUMN org_role org_role;
UPDATE actor SET org_role = CASE role::text
    WHEN 'ADMIN'      THEN 'SYSTEM_ADMIN'
    WHEN 'CONTROLLER' THEN 'CONTROLLER'
    WHEN 'EMPLOYEE'   THEN 'EMPLOYEE'
    WHEN 'AUDITOR'    THEN 'AUDITOR'
  END::org_role;
ALTER TABLE actor DROP COLUMN role;
ALTER TABLE actor RENAME COLUMN org_role TO role;
ALTER TABLE actor ALTER COLUMN role SET NOT NULL;

-- Who provisioned this account. An account with no provisioner is a seed
-- account, and the roster says so rather than leaving a blank.
ALTER TABLE actor ADD COLUMN provisioned_by uuid REFERENCES actor(actor_id);

-- Anyone may have an employee key; an EMPLOYEE must. A controller who is
-- also on the payroll — which is all of them here — keeps a timesheet like
-- everybody else, and the key is what ties the two together.
ALTER TABLE actor ADD CONSTRAINT employee_needs_key
  CHECK (role <> 'EMPLOYEE' OR employee_key IS NOT NULL);

-- The ladder, in the schema. An account may only be provisioned by someone
-- strictly above it, so no administrator can mint a peer.
CREATE FUNCTION provisioning_rank(r org_role) RETURNS integer AS $$
  SELECT CASE r WHEN 'SYSTEM_ADMIN' THEN 0 WHEN 'ORG_ADMIN' THEN 1 ELSE 2 END
$$ LANGUAGE sql IMMUTABLE;

CREATE FUNCTION provisioning_runs_downward() RETURNS trigger AS $$
DECLARE by_role org_role;
BEGIN
  IF NEW.provisioned_by IS NULL THEN
    RETURN NEW;                       -- seeded; the roster shows it as such
  END IF;
  IF NEW.provisioned_by = NEW.actor_id THEN
    RAISE EXCEPTION 'an account cannot provision itself';
  END IF;
  SELECT role INTO by_role FROM actor WHERE actor_id = NEW.provisioned_by;
  IF provisioning_rank(by_role) >= provisioning_rank(NEW.role) THEN
    RAISE EXCEPTION
      '% may not provision % — an account is created by someone above it, '
      'never by a peer or a subordinate', by_role, NEW.role;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER actor_provisioning_ladder
  BEFORE INSERT OR UPDATE OF role, provisioned_by ON actor
  FOR EACH ROW EXECUTE FUNCTION provisioning_runs_downward();


-- The audit trail records the rank the actor held when they acted, so it
-- carries the type too. It has to move with the column it describes:
-- an entry written tomorrow by a SYSTEM_ADMIN cannot be stored in a type
-- that has never heard of one.

-- v_activity reads the audit log too, and it is a hundred lines of union
-- that has no business being restated here just to change a column's type.
-- Save what the database already has, put it back afterwards.
CREATE TEMP TABLE _saved_viewdef ON COMMIT DROP AS
SELECT c.relname::text AS name, pg_get_viewdef(c.oid, true) AS def
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = 'v_activity';

DROP VIEW v_activity;
DROP VIEW v_undoable;

ALTER TABLE audit_log ADD COLUMN role_new org_role;
UPDATE audit_log SET role_new = CASE actor_role::text
    WHEN 'ADMIN'      THEN 'SYSTEM_ADMIN'
    WHEN 'CONTROLLER' THEN 'CONTROLLER'
    WHEN 'EMPLOYEE'   THEN 'EMPLOYEE'
    WHEN 'AUDITOR'    THEN 'AUDITOR'
  END::org_role
 WHERE actor_role IS NOT NULL;
ALTER TABLE audit_log DROP COLUMN actor_role;
ALTER TABLE audit_log RENAME COLUMN role_new TO actor_role;

DO $restore$
DECLARE r record;
BEGIN
  FOR r IN SELECT name, def FROM _saved_viewdef LOOP
    EXECUTE format('CREATE VIEW %I AS %s', r.name, r.def);
  END LOOP;
END $restore$;

CREATE VIEW v_undoable AS
SELECT entry_id, occurred_at, action, actor, actor_id, actor_role,
       entity, entity_id, reason,
       CASE action
         WHEN 'CLASSIFY'        THEN 'Classification'
         WHEN 'SEGMENT'         THEN 'Split'
         WHEN 'NOTE'            THEN 'Note'
         WHEN 'TIME_ENTRY'      THEN 'Time entry'
         WHEN 'TIME_REMOVE'     THEN 'Time removed'
         WHEN 'TIME_SUBMIT'     THEN 'Timesheet submitted'
         WHEN 'CERTIFY'         THEN 'Certification'
         WHEN 'EMPLOYMENT'      THEN 'Employment terms'
         WHEN 'EVIDENCE_UPLOAD' THEN 'Document attached'
         WHEN 'DOCUMENT_UPLOAD' THEN 'Document sent in'
         WHEN 'EVIDENCE_ATTACH' THEN 'Document put to work'
         WHEN 'SEAL'            THEN 'Seal'
         ELSE action
       END AS label,
       action = ANY (ARRAY['CLASSIFY','SEGMENT','NOTE','TIME_ENTRY',
                           'TIME_REMOVE','TIME_SUBMIT','CERTIFY','EMPLOYMENT',
                           'EVIDENCE_UPLOAD','DOCUMENT_UPLOAD',
                           'EVIDENCE_ATTACH','SEAL']) AS reversible_action,
       EXISTS (SELECT 1 FROM audit_log u WHERE u.undoes_entry_id = al.entry_id)
         AS already_undone
  FROM audit_log al
 WHERE action <> ALL (ARRAY['SIGN_IN','SIGN_OUT','UNDO']);

DROP TYPE actor_role;


-- ── Portfolios ───────────────────────────────────────────────────────

CREATE TYPE portfolio AS ENUM (
  'CONTROLLER',   -- classify, import, reconcile, seal, unseal, rate, restate
  'INVENTORY',    -- the asset register, equipment, what it is worth by the hour
  'PROJECT',      -- awards and cost objectives, and what work belongs to them
  'FACILITIES',   -- buildings, space, occupancy, market rent
  'OFFICE'        -- the document library: matching evidence to what it supports
);

COMMENT ON TYPE portfolio IS
  'A set, not a ladder. A person holds the union of what they are granted. '
  'CONTROLLER is the only one that can seal, and nothing adds up to it.';

CREATE TABLE actor_portfolio (
  actor_id        uuid NOT NULL REFERENCES actor(actor_id),
  portfolio       portfolio NOT NULL,
  granted_by      uuid NOT NULL REFERENCES actor(actor_id),
  granted_at      timestamptz NOT NULL DEFAULT now(),
  reason          text NOT NULL CHECK (length(btrim(reason)) >= 10),
  revoked_at      timestamptz,
  revoked_by      uuid REFERENCES actor(actor_id),
  revoked_reason  text,
  PRIMARY KEY (actor_id, portfolio, granted_at),
  CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL)),
  -- Nobody grants themselves authority. An administrator who needs a
  -- portfolio asks the one above them, and the trail then reads as two
  -- people agreeing rather than one person deciding.
  CHECK (actor_id <> granted_by)
);

CREATE UNIQUE INDEX one_live_grant_per_portfolio
  ON actor_portfolio (actor_id, portfolio) WHERE revoked_at IS NULL;

COMMENT ON TABLE actor_portfolio IS
  'Append-only grants of authority, each with a reason and a grantor who is '
  'not the recipient. Revoking is a second row''s worth of writing, not a '
  'delete: who could do what, when, is part of the audit file.';


-- ── What an actor may actually do ────────────────────────────────────

CREATE VIEW v_actor_access AS
SELECT a.actor_id, a.email, a.display_name, a.role, a.is_active,
       a.employee_key, a.created_at, a.last_login_at,
       a.password_set_by, a.password_set_at,
       (a.password_set_by = 'SEED')                        AS holds_bootstrap_password,
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
  LEFT JOIN actor p ON p.actor_id = a.provisioned_by;

COMMENT ON VIEW v_actor_access IS
  'The roster as an administrator needs to read it: who they are, who let '
  'them in, what they may judge, and whether their password still '
  'identifies one person.';

-- Kept under its old name because the manual, the admin API and the drive
-- scripts all name it.
CREATE VIEW v_account_standing AS
SELECT actor_id, email, display_name, role, is_active, employee_key,
       created_at, last_login_at, password_set_by, password_set_at,
       holds_bootstrap_password, live_sessions, failures_24h,
       portfolios, may_seal, provisioned_by, provisioned_by_name
  FROM v_actor_access;

CREATE VIEW v_actor_session_live AS
SELECT s.session_id, s.actor_id, a.email, a.display_name, a.role,
       s.issued_at, s.expires_at, s.user_agent
  FROM actor_session s JOIN actor a USING (actor_id)
 WHERE s.revoked_at IS NULL AND s.expires_at > now();


-- ── The document inbox ───────────────────────────────────────────────
--
-- Everybody in the organisation can put a document into the system. Almost
-- nobody should be deciding what it proves.
--
-- A receipt, an invoice, a project plan, a photograph of a nameplate — the
-- person who has it is the person who was there, and making them route it
-- through the controller is how it ends up in a drawer instead. So the
-- upload is open to anyone signed in, and the *judgment* — this document
-- supports that cost, to this standard — stays with whoever holds the
-- portfolio it belongs to.
--
-- Which makes an uploaded, unattached document a queue rather than a loose
-- end, and v_evidence_inbox is that queue.

ALTER TABLE evidence ADD COLUMN uploaded_by uuid REFERENCES actor(actor_id);
ALTER TABLE evidence ADD COLUMN note text NOT NULL DEFAULT '';
ALTER TABLE evidence ADD COLUMN suggested_for text NOT NULL DEFAULT '';

COMMENT ON COLUMN evidence.uploaded_by IS
  'The account that put this document in, resolved from the session. '
  'received_from stays a label — it can name somebody who is not a user.';
COMMENT ON COLUMN evidence.suggested_for IS
  'What the uploader says it relates to, in their words. A hint for whoever '
  'attaches it, never a claim that it has been attached.';

CREATE VIEW v_evidence_inbox AS
SELECT e.evidence_id, e.period, e.kind, e.received_at, e.received_from,
       e.byte_size, e.mime_type, e.doc_date, e.doc_amount, e.vendor_name,
       e.note, e.suggested_for, e.uploaded_by,
       a.display_name                                   AS uploaded_by_name,
       a.employee_key                                   AS uploaded_by_employee,
       (SELECT count(*) FROM attachment t
         WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL) AS attachments,
       EXISTS (SELECT 1 FROM attachment t
                WHERE t.evidence_id = e.evidence_id AND t.detached_at IS NULL) AS is_attached
  FROM evidence e
  LEFT JOIN actor a ON a.actor_id = e.uploaded_by;

COMMENT ON VIEW v_evidence_inbox IS
  'Every document, with who put it there and whether anyone has yet said '
  'what it supports. The unattached ones are a queue, not a mess.';
