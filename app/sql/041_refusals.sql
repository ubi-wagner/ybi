-- 041 — what was tried and refused
--
-- `audit_log` records changes. By construction it records nothing when a
-- change does not happen, which leaves the most frustrating case on the
-- record nowhere at all: somebody pressed a button, the system said no, and
-- the trail is silent about it.
--
-- That gap is not academic. A controller who tries to compute a rate six
-- times while a control is open, an administrator whose account creation is
-- refused by the provisioning ladder, an employee whose timesheet entry hits
-- a constraint — none of it existed anywhere afterwards. The person knows
-- something went wrong and nobody else can see what, which is the opposite of
-- what this system is for.
--
-- So a refusal is an event, in its own table rather than in `audit_log`.
-- Three reasons to keep them apart:
--
--   * `audit_log` means "this changed". Mixing in attempts that changed
--     nothing would make every count and every feed wrong.
--   * An audit entry must name an account and a session, and the review
--     asserts there are no orphans. A refusal can be anonymous — a 401 is
--     exactly the case where there is nobody to name.
--   * Refusals are noisier and shorter-lived. They can be trimmed without
--     touching the record of what actually happened.

CREATE TABLE refusal (
  refusal_id    bigserial PRIMARY KEY,
  occurred_at   timestamptz NOT NULL DEFAULT now(),
  actor_id      uuid REFERENCES actor(actor_id),
  actor         text NOT NULL DEFAULT '',      -- label, may be 'anonymous'
  method        text NOT NULL,
  path          text NOT NULL,
  status        integer NOT NULL,
  detail        text NOT NULL DEFAULT '',
  -- What the person was trying to do, in the words the API uses. A status
  -- code alone tells a reader that something was refused and not what.
  CONSTRAINT refusal_is_a_refusal CHECK (status >= 400)
);

CREATE INDEX ON refusal (occurred_at DESC);
CREATE INDEX ON refusal (actor_id, occurred_at DESC);

COMMENT ON TABLE refusal IS
  'Mutating requests the system declined, with the reason it gave. Kept '
  'apart from audit_log because that table means "this changed" and these '
  'changed nothing — and because a refusal can be anonymous, which an audit '
  'entry may never be.';


-- What somebody is being stopped from doing, and how often. The shape a
-- person actually needs: not a log to scroll, but "you have tried this four
-- times and here is what it keeps saying".
CREATE VIEW v_refusals_recent AS
SELECT r.refusal_id,
       r.occurred_at,
       r.actor,
       r.actor_id,
       r.method,
       r.path,
       r.status,
       r.detail,
       CASE r.status
         WHEN 401 THEN 'Not signed in'
         WHEN 403 THEN 'Not permitted'
         WHEN 404 THEN 'Not found'
         WHEN 409 THEN 'Refused by a rule'
         WHEN 410 THEN 'Gone'
         WHEN 413 THEN 'Too large'
         WHEN 422 THEN 'Rejected as written'
         ELSE CASE WHEN r.status >= 500 THEN 'The system failed'
                   ELSE 'Refused' END
       END                                              AS what_happened,
       -- A fault is ours; everything else is the system doing its job. The
       -- distinction is what stops a screen full of correct 403s burying the
       -- one 500 that matters.
       r.status >= 500                                  AS is_a_fault
  FROM refusal r
 ORDER BY r.occurred_at DESC;

COMMENT ON VIEW v_refusals_recent IS
  'Refused writes, newest first, with the status turned into a sentence. '
  'is_a_fault separates the system failing from the system correctly saying '
  'no — a screen full of correct 403s would otherwise bury the one 500.';
