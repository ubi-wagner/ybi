-- 083: a working position is not a judgment, and the record has to say which.
--
-- All 757 live 2025 decisions read `decided_by = 'Tom Metzinger'` and were
-- recorded across **six seconds**, because `scripts/classification_log.py
-- --apply` writes them through the real API signed in as the controller. That
-- is the right way for a script to write — every judgment carries a person's
-- name and an audit row, and there is no path in it that writes behind the
-- API's back. What it cannot do is tell the truth about what kind of act it
-- was. An auditor reading the timestamps finds seven hundred judgments a
-- minute and stops reading anything else in the file.
--
-- The fix is not to rewrite `decided_by`. That column says who the API call
-- was made as, the audit rows say the same, and editing it would be inventing
-- a history — which is what `079` refused to do to 891 audit rows pointing at
-- a retired account. What is missing is a *value for the kind of act*, exactly
-- as `038` found that `ingest_channel` had no value meaning *this system made
-- it* and `070` found that `basis` had no value meaning *the organisation
-- reconstructed it and the person affirmed it*. Third instance, same shape.
--
-- So `decision.origin` is `CONTROLLER` or `MACHINE_PROPOSAL`, defaulting to
-- CONTROLLER — **nothing changes by default**, the `077` rule — and the 757
-- are marked from what the record already says about them rather than from an
-- assertion here: every one of their rationales names the script that wrote
-- it.
--
-- A MACHINE_PROPOSAL is then adopted by the person whose judgment it has to
-- be, which is `POST /api/timesheet/adopt` one level up: the controller's
-- reconstruction shown to the person whose work it was, read, corrected and
-- signed. And it has that route's load-bearing property — **confirming moves
-- no figure.** The rate holds throughout, whatever order people review in;
-- if it did not, the rate would depend on who had got round to reviewing.
--
-- Two facts underneath that, and they are worth keeping apart because the
-- first draft of this header ran them together. **Confirming never reaches
-- the seal trigger at all**: it writes `position_confirmation`, a different
-- table, and touches no judgment. **`origin` does reach it** — it is a
-- column of `decision`, and the backfill below is an UPDATE against rows in
-- a sealed set, permitted only because `decision_set_is_frozen` compares the
-- six columns the hash is taken over and `origin` is not one of them. Put it
-- in that list and the migration is refused by the seal, which is how that
-- sentence was checked rather than reasoned about.
--
-- Three registers hang off that, and each is the house pattern in a new place:
--
--   * `position_confirmation`, shaped like `rate_certification` — a signature,
--     withdrawable with a reason, one live per decision, and liveness read
--     from one view because `082` found two handlers each carrying their own
--     `withdrawn_at IS NULL` and answering 200 to a withdrawal of the dead one.
--
--   * `classification_note`, on the *group key* rather than the decision id,
--     so a note survives the supersession it is usually about. Two kinds, and
--     the kind is the visibility: a RECORD note is part of the cost record and
--     every reader of the record sees it; a WORKING note is deliberative and
--     stays out of the audit package. **A WORKING note is undisclosed, never
--     concealed** — `v_classification_standing` carries the count of them to
--     every reader, so the paper says three exist and does not say what they
--     say. Re-designating one is a recorded act with a reason, because a
--     visibility switch that can be flipped silently after a question is asked
--     is worse than no note at all.
--
--   * `reclass_recommendation`, which is what `062` could not carry. That
--     migration was right to refuse a `PROPOSED` decision row — `PROPOSED`
--     already means *YBI has put this to a sponsor and they have not answered*
--     and a second meaning in one word leaves a reviewer unable to tell the
--     two apart. A `todo` carries the reason and cannot carry the *proposed
--     classification*, which is the thing Tom has to look at. So: its own
--     register, holding the proposal, the person, the note, and Tom's
--     disposition — and `saw_decision_id`, the `project_claim.saw_*` seal, so
--     a recommendation made against a position that has since moved says so
--     rather than being applied to something it was never about.
--
-- Who may do what, and one departure from `062` with a reason. Recommending
-- and noting take **`require_reader`** — the cost-record grant, the library's
-- gate — which admits the auditor, who holds no portfolio. `062` offered its
-- Recommend button only to portfolio holders because a worklist item is work
-- to *do* and the auditor does none of it. A reclassification recommendation
-- is the opposite case: *the auditor requiring a new classification out of a
-- sealed account is the whole exercise*, and a system where the auditor cannot
-- record the ask has put it back in an email. Confirming, deciding and
-- disposing stay `CONTROLLER`. Nobody disposes of their own recommendation.


-- ---------------------------------------------------------------- origin ---

DO $$ BEGIN
  CREATE TYPE decision_origin AS ENUM ('CONTROLLER', 'MACHINE_PROPOSAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE decision
  ADD COLUMN IF NOT EXISTS origin decision_origin NOT NULL DEFAULT 'CONTROLLER';

COMMENT ON COLUMN decision.origin IS
'What kind of act made this row. CONTROLLER is a person judging; '
'MACHINE_PROPOSAL is a working position a script proposed and recorded under '
'the operator''s credentials, which is not the same claim and must not read '
'like one. Write-once: a judgment cannot be disowned after the fact.';

-- ------------------------------------------------------------ the 757 -----
--
-- Read from what the record already says about these rows rather than
-- asserted here: `scripts/classification_log.py --apply` stamps its own name
-- into every rationale it writes, so the ledger of judgments carries the
-- evidence of which act made each one. On a database the log has never run
-- against — CI, a fresh clone — this marks nothing, which is correct.
--
-- It runs **before** the write-once trigger below, and that is the only place
-- it can: these rows predate the column, so what is being corrected is the
-- default ALTER TABLE gave them rather than a fact anybody recorded. After
-- this point the column never moves again. The DROP is what makes that true
-- on a re-run as well — a judgment the log wrote *after* the first run would
-- otherwise meet a trigger that refuses it, and a migration that cannot be
-- applied twice is one that fails the first time somebody replays the file.

DROP TRIGGER IF EXISTS decision_origin_write_once ON decision;

UPDATE decision
   SET origin = 'MACHINE_PROPOSAL'
 WHERE origin = 'CONTROLLER'
   AND rationale LIKE '%scripts/classification_log.py%';

-- Write-once. Without this, `origin` is outside the seal hash and so an UPDATE
-- under a seal could turn a controller's own judgment into a machine proposal
-- — disowning it without superseding it, which is the one thing this column
-- must never make possible.
CREATE OR REPLACE FUNCTION decision_origin_is_write_once() RETURNS trigger AS $$
BEGIN
  IF NEW.origin IS DISTINCT FROM OLD.origin THEN
    RAISE EXCEPTION 'decision % was recorded as %; what kind of act made a '
                    'judgment is not something that can change afterwards. '
                    'Correct it by superseding the judgment, with a reason.',
                    OLD.decision_id, OLD.origin
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decision_origin_write_once ON decision;
CREATE TRIGGER decision_origin_write_once
  BEFORE UPDATE ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_origin_is_write_once();

-- ------------------------------------------------- the confirmation -------

CREATE TABLE IF NOT EXISTS position_confirmation (
    confirmation_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id      uuid NOT NULL REFERENCES decision(decision_id),
    confirmed_by     uuid NOT NULL REFERENCES actor(actor_id),
    confirmed_at     timestamptz NOT NULL DEFAULT now(),
    note             text NOT NULL DEFAULT '',
    withdrawn_at     timestamptz,
    withdrawn_by     uuid REFERENCES actor(actor_id),
    withdrawn_reason text,
    CONSTRAINT withdrawal_names_itself
      CHECK ((withdrawn_at IS NULL) = (withdrawn_by IS NULL)
         AND (withdrawn_at IS NULL) = (withdrawn_reason IS NULL)),
    CONSTRAINT withdrawal_says_why
      CHECK (withdrawn_reason IS NULL OR length(btrim(withdrawn_reason)) >= 12)
);

CREATE INDEX IF NOT EXISTS position_confirmation_decision
  ON position_confirmation (decision_id);

COMMENT ON TABLE position_confirmation IS
'The controller adopting a working position as his own judgment. Shaped like '
'rate_certification because it is the same act one level down: a signature, '
'withdrawable with a reason, and append-only — re-confirming after a '
'withdrawal is a new row, not an edit of the old one.';

CREATE OR REPLACE VIEW v_position_confirmed AS
SELECT c.confirmation_id,
       c.decision_id,
       c.confirmed_at,
       c.note,
       a.display_name       AS confirmed_by,
       c.confirmed_by       AS confirmed_by_actor,
       c.withdrawn_at,
       w.display_name       AS withdrawn_by,
       c.withdrawn_reason,
       c.withdrawn_at IS NULL AS live
  FROM position_confirmation c
  JOIN actor a ON a.actor_id = c.confirmed_by
  LEFT JOIN actor w ON w.actor_id = c.withdrawn_by;

COMMENT ON VIEW v_position_confirmed IS
'The one definition of whether a confirmation stands. 082 found two handlers '
'each carrying their own withdrawn_at IS NULL test and disagreeing about which '
'signature was live; there is one reading of it and everything reads it here.';

-- One live confirmation per decision. A second is two signatures on one
-- judgment, which reads as two people having reviewed it when one did.
CREATE OR REPLACE FUNCTION one_live_confirmation() RETURNS trigger AS $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM v_position_confirmed
   WHERE decision_id = NEW.decision_id AND live
     AND confirmation_id <> NEW.confirmation_id;
  IF n > 0 THEN
    RAISE EXCEPTION 'that position is already confirmed. Withdraw the '
                    'signature on it first, and say why.'
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS position_confirmation_is_singular ON position_confirmation;
CREATE TRIGGER position_confirmation_is_singular
  AFTER INSERT OR UPDATE ON position_confirmation
  FOR EACH ROW EXECUTE FUNCTION one_live_confirmation();

-- A CONTROLLER-origin decision is the controller's judgment already. Signing
-- your own judgment a second time is a second spelling of making it, and on a
-- screen it would read as independent review.
CREATE OR REPLACE FUNCTION confirmation_is_of_a_proposal() RETURNS trigger AS $$
DECLARE o decision_origin;
BEGIN
  SELECT origin INTO o FROM decision WHERE decision_id = NEW.decision_id;
  IF o <> 'MACHINE_PROPOSAL' THEN
    RAISE EXCEPTION 'decision % was judged by a person, not proposed. There is '
                    'nothing to adopt; the judgment already carries a name.',
                    NEW.decision_id
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS confirmation_adopts_a_proposal ON position_confirmation;
CREATE TRIGGER confirmation_adopts_a_proposal
  BEFORE INSERT ON position_confirmation
  FOR EACH ROW EXECUTE FUNCTION confirmation_is_of_a_proposal();


-- ------------------------------------------------------------- the notes ---

DO $$ BEGIN
  CREATE TYPE note_kind AS ENUM ('RECORD', 'WORKING');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMENT ON TYPE note_kind IS
'RECORD: part of the cost record, read by everybody who may read the record, '
'and it travels in the audit package. WORKING: deliberative, and it does not. '
'The count of WORKING notes is disclosed to every reader regardless — '
'undisclosed is a position anybody can take, concealed is not one.';

CREATE TABLE IF NOT EXISTS classification_note (
    note_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period         text NOT NULL REFERENCES fiscal_period(period),
    scope          text NOT NULL,
    kind           note_kind NOT NULL,
    body           text NOT NULL,
    written_by     uuid NOT NULL REFERENCES actor(actor_id),
    written_at     timestamptz NOT NULL DEFAULT now(),
    -- the position the note was written against, so a note that predates a
    -- reclassification reads as being about what was there at the time.
    about_decision uuid REFERENCES decision(decision_id),
    redesignated_at     timestamptz,
    redesignated_by     uuid REFERENCES actor(actor_id),
    redesignated_reason text,
    CONSTRAINT note_says_something CHECK (length(btrim(body)) >= 12),
    CONSTRAINT redesignation_names_itself
      CHECK ((redesignated_at IS NULL) = (redesignated_by IS NULL)
         AND (redesignated_at IS NULL) = (redesignated_reason IS NULL)),
    CONSTRAINT redesignation_says_why
      CHECK (redesignated_reason IS NULL
             OR length(btrim(redesignated_reason)) >= 12)
);

CREATE INDEX IF NOT EXISTS classification_note_scope
  ON classification_note (period, scope);

COMMENT ON TABLE classification_note IS
'A note against a classification group. It hangs off the group key rather than '
'a decision id, because the thing worth saying is nearly always about the '
'group and has to survive the supersession it is usually about.';

COMMENT ON COLUMN classification_note.scope IS
'The group key as `decision.scope` writes it: account=<account>|payee=<payee>. '
'Never the 0x1f wire form — a composite key never goes in a URL path, and '
'these two encodings of one key are already one decoder short.';

-- A note is never deleted and never rewritten; changing its kind is a
-- recorded act with a reason, and audit_log holds the history of them. A
-- visibility setting that can be flipped silently the day after somebody asks
-- for the file is the one shape this must not have.
CREATE OR REPLACE FUNCTION note_body_is_written_once() RETURNS trigger AS $$
BEGIN
  IF NEW.body IS DISTINCT FROM OLD.body
     OR NEW.written_by IS DISTINCT FROM OLD.written_by
     OR NEW.scope IS DISTINCT FROM OLD.scope THEN
    RAISE EXCEPTION 'a note is not edited. Write another one; both stand, and '
                    'the record shows the order they were written in.'
      USING ERRCODE = 'raise_exception';
  END IF;
  IF NEW.kind IS DISTINCT FROM OLD.kind
     AND NEW.redesignated_at IS NOT DISTINCT FROM OLD.redesignated_at THEN
    RAISE EXCEPTION 'changing what a note discloses is an act. Record who did '
                    'it and why.'
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS note_is_append_only ON classification_note;
CREATE TRIGGER note_is_append_only
  BEFORE UPDATE ON classification_note
  FOR EACH ROW EXECUTE FUNCTION note_body_is_written_once();

CREATE OR REPLACE FUNCTION note_no_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'a note is part of the record of how a judgment was reached. '
                  'It is not deleted.'
    USING ERRCODE = 'raise_exception';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS note_is_never_deleted ON classification_note;
CREATE TRIGGER note_is_never_deleted
  BEFORE DELETE ON classification_note
  FOR EACH ROW EXECUTE FUNCTION note_no_delete();

-- --------------------------------------------- the recommendation ----------

CREATE TABLE IF NOT EXISTS reclass_recommendation (
    rec_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period          text NOT NULL REFERENCES fiscal_period(period),
    scope           text NOT NULL,

    -- what is being proposed. The same four dimensions a decision records,
    -- because a recommendation Tom cannot accept with one keystroke is a
    -- recommendation that has to be retyped, and retyping is where a judgment
    -- quietly becomes a different one.
    pool            pool_type NOT NULL,
    function_990    function_990 NOT NULL,
    federal         federal_treatment NOT NULL,
    objective_id    text REFERENCES cost_objective(objective_id),

    note            text NOT NULL,
    recommended_by  uuid NOT NULL REFERENCES actor(actor_id),
    recommended_at  timestamptz NOT NULL DEFAULT now(),

    -- the seal, in the sense project_claim.saw_* is one: the position this was
    -- recommended against. If Tom has reclassified since, the recommendation
    -- is about something that is no longer there and must say so rather than
    -- being applied to whatever is there now.
    saw_decision    uuid REFERENCES decision(decision_id),

    disposition     text NOT NULL DEFAULT 'OPEN',
    disposed_by     uuid REFERENCES actor(actor_id),
    disposed_at     timestamptz,
    disposition_reason text,
    resulting_decision uuid REFERENCES decision(decision_id),

    CONSTRAINT disposition_is_known
      CHECK (disposition IN ('OPEN', 'ACCEPTED', 'DECLINED', 'WITHDRAWN')),
    CONSTRAINT disposition_names_itself
      CHECK ((disposition = 'OPEN') = (disposed_at IS NULL)
         AND (disposed_at IS NULL) = (disposed_by IS NULL)),
    -- Declining is the one that has to say why. Accepting says why by
    -- producing a decision whose own rationale carries it.
    CONSTRAINT declining_says_why
      CHECK (disposition <> 'DECLINED'
             OR length(btrim(COALESCE(disposition_reason, ''))) >= 12),
    CONSTRAINT recommendation_says_why
      CHECK (length(btrim(note)) >= 12),
    -- The same rule the queue's own answer has to satisfy. A recommendation
    -- the server would refuse is a screen offering what the API will not take.
    CONSTRAINT recommended_direct_needs_objective
      CHECK ((pool = 'DIRECT') = (objective_id IS NOT NULL)),
    CONSTRAINT recommended_unallowable_not_allowable
      CHECK (NOT (federal = 'ALLOWABLE'
                  AND pool IN ('FUNDRAISING', 'UNALLOWABLE')))
);

CREATE INDEX IF NOT EXISTS reclass_recommendation_scope
  ON reclass_recommendation (period, scope);

-- One open recommendation per person per group. A second from the same person
-- is an amendment and supersedes; two different people each get one, and Tom
-- seeing both is information rather than noise — they may disagree, and that
-- is the most useful thing the register can tell him.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_recommendation_per_person
  ON reclass_recommendation (period, scope, recommended_by)
  WHERE disposition = 'OPEN';

COMMENT ON TABLE reclass_recommendation IS
'Somebody who may read the cost record saying: this group is classified wrong, '
'here is what it should be, and here is why. It is not a decision and never '
'becomes one — accepting it records a fresh judgment through the ordinary '
'route, under the controller''s name, citing this row.';

-- A recommendation that proposes the position already on the record is a
-- no-op wearing a recommendation's clothes: it costs Tom a review and can
-- change nothing.
CREATE OR REPLACE FUNCTION recommendation_proposes_a_change() RETURNS trigger AS $$
DECLARE d record;
BEGIN
  IF NEW.disposition <> 'OPEN' THEN RETURN NEW; END IF;
  SELECT dd.pool, dd.function_990, dd.federal, dd.objective_id INTO d
    FROM decision dd
   WHERE dd.decision_id = NEW.saw_decision;
  IF FOUND
     AND d.pool = NEW.pool
     AND d.function_990 = NEW.function_990
     AND d.federal = NEW.federal
     AND d.objective_id IS NOT DISTINCT FROM NEW.objective_id THEN
    RAISE EXCEPTION 'that is the classification already on the record. A '
                    'recommendation has to propose a change; to say you agree '
                    'with it, write a note.'
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS recommendation_is_a_change ON reclass_recommendation;
CREATE TRIGGER recommendation_is_a_change
  BEFORE INSERT ON reclass_recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_proposes_a_change();

-- Nobody disposes of their own recommendation. 062's rule — handing yourself
-- a job is taking one, and it reads differently on the record — pointed at
-- the other end of the same act.
CREATE OR REPLACE FUNCTION recommendation_is_disposed_by_another() RETURNS trigger AS $$
BEGIN
  IF NEW.disposition IN ('ACCEPTED', 'DECLINED')
     AND NEW.disposed_by = NEW.recommended_by THEN
    RAISE EXCEPTION 'a recommendation is somebody asking somebody else to look '
                    'at it. Withdraw your own instead — that is the act you '
                    'are actually performing.'
      USING ERRCODE = 'raise_exception';
  END IF;
  IF NEW.disposition = 'WITHDRAWN'
     AND NEW.disposed_by IS DISTINCT FROM NEW.recommended_by THEN
    RAISE EXCEPTION 'only the person who made a recommendation withdraws it. '
                    'Decline it, and say why.'
      USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS recommendation_disposed_by_another ON reclass_recommendation;
CREATE TRIGGER recommendation_disposed_by_another
  BEFORE UPDATE ON reclass_recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_is_disposed_by_another();

-- ------------------------------------------------------------ standing ----

CREATE OR REPLACE VIEW v_classification_standing AS
WITH live AS (
    SELECT d.decision_id, d.scope, s.period, d.pool, d.function_990,
           d.federal, d.objective_id, d.grade, d.rationale, d.citation,
           d.decided_by, d.decided_at, d.origin
      FROM decision d
      JOIN decision_set s ON s.set_id = d.set_id
     WHERE d.reversed_at IS NULL
),
-- The group a judgment covers, read back through the lines it covers. That is
-- deliberately the long way round: `decision.scope` and the queue's group_key
-- are two encodings of one key with an encoder at the point of writing and no
-- decoder anywhere, and an account name carrying the separator would make a
-- parse of the scope string silently wrong. decision_line -> ledger_line is
-- the only route that cannot be.
grp AS (
    SELECT DISTINCT ON (dl.decision_id)
           dl.decision_id, l.account, l.payee
      FROM decision_line dl
      JOIN ledger_line l ON l.line_id = dl.line_id
     WHERE dl.live
),
conf AS (
    SELECT decision_id, confirmed_by, confirmed_at, note
      FROM v_position_confirmed WHERE live
),
notes AS (
    SELECT period, scope,
           count(*) FILTER (WHERE kind = 'RECORD')  AS record_notes,
           count(*) FILTER (WHERE kind = 'WORKING') AS working_notes,
           max(written_at)                          AS last_note_at
      FROM classification_note
     GROUP BY period, scope
),
recs AS (
    SELECT period, scope,
           count(*) FILTER (WHERE disposition = 'OPEN')     AS open_recs,
           count(*) FILTER (WHERE disposition = 'ACCEPTED') AS accepted_recs,
           count(*) FILTER (WHERE disposition = 'DECLINED') AS declined_recs
      FROM reclass_recommendation
     GROUP BY period, scope
)
SELECT l.period,
       l.scope,
       g.account,
       COALESCE(g.payee, '') AS payee,
       l.decision_id,
       l.pool, l.function_990, l.federal, l.objective_id, l.grade,
       l.rationale, l.citation, l.decided_by, l.decided_at,
       l.origin,
       (l.origin = 'MACHINE_PROPOSAL') AS is_working_position,
       c.confirmed_by,
       c.confirmed_at,
       c.note AS confirmation_note,
       -- A judgment stands as somebody's own when a person made it, or when
       -- the person whose it has to be has adopted what the machine proposed.
       (l.origin = 'CONTROLLER' OR c.confirmed_at IS NOT NULL) AS adopted,
       COALESCE(n.record_notes, 0)  AS record_notes,
       COALESCE(n.working_notes, 0) AS working_notes,
       n.last_note_at,
       COALESCE(r.open_recs, 0)     AS open_recommendations,
       COALESCE(r.accepted_recs, 0) AS accepted_recommendations,
       COALESCE(r.declined_recs, 0) AS declined_recommendations
  FROM live l
  LEFT JOIN grp   g ON g.decision_id = l.decision_id
  LEFT JOIN conf  c ON c.decision_id = l.decision_id
  LEFT JOIN notes n ON n.period = l.period AND n.scope = l.scope
  LEFT JOIN recs  r ON r.period = l.period AND r.scope = l.scope;

COMMENT ON VIEW v_classification_standing IS
'Where each classification group stands: what it says, whether a person or a '
'script put it there, whether the controller has adopted it, and what has been '
'written against it. The WORKING note count is here rather than hidden, '
'because a reader entitled to the record is entitled to know a note exists '
'even where they are not shown what it says.';

-- What the controller has in front of him, one row per thing to look at.
CREATE OR REPLACE VIEW v_controller_review AS
SELECT r.period,
       'RECOMMENDATION'::text AS item,
       r.rec_id::text         AS item_id,
       r.scope,
       st.account,
       st.payee,
       st.decision_id,
       a.display_name         AS raised_by,
       r.recommended_at       AS raised_at,
       r.note,
       r.pool::text           AS proposed_pool,
       r.function_990::text   AS proposed_function,
       r.federal::text        AS proposed_federal,
       r.objective_id         AS proposed_objective,
       st.pool::text          AS current_pool,
       st.function_990::text  AS current_function,
       st.federal::text       AS current_federal,
       st.objective_id        AS current_objective,
       -- False is not a defect. It is the one thing the controller needs to
       -- know before acting: the position has moved since this was written.
       (r.saw_decision IS NOT DISTINCT FROM st.decision_id) AS still_agrees
  FROM reclass_recommendation r
  LEFT JOIN v_classification_standing st
         ON st.period = r.period AND st.scope = r.scope
  JOIN actor a ON a.actor_id = r.recommended_by
 WHERE r.disposition = 'OPEN'
UNION ALL
SELECT st.period,
       'UNCONFIRMED',
       st.decision_id::text,
       st.scope,
       st.account,
       st.payee,
       st.decision_id,
       st.decided_by,
       st.decided_at,
       st.rationale,
       NULL, NULL, NULL, NULL,
       st.pool::text, st.function_990::text, st.federal::text, st.objective_id,
       true
  FROM v_classification_standing st
 WHERE st.is_working_position AND NOT st.adopted;

COMMENT ON VIEW v_controller_review IS
'The controller''s list: every working position nobody has adopted, and every '
'open recommendation somebody has raised, with the proposal beside what is '
'there now so the comparison is on the page rather than in his head.';

-- ------------------------------------------------------- on the worklist ---
--
-- Both views are **lifted from the definition in force** and not retyped:
-- `070` records what retyping one costs, and `v_worklist_owned` carries three
-- parallel CASE arms where a kind missing from any one of them falls silently
-- onto an ELSE. Every kind is routed explicitly; a kind that reaches the ELSE
-- by accident fails `tests/test_worklist_ownership.py`.

CREATE OR REPLACE VIEW v_worklist_extra AS
SELECT 'SPACE_UNMEASURED'::text AS kind,
    'BLOCKING'::text AS severity,
    p.period,
    'No building has square footage on file'::text AS label,
    'facility'::text AS entity,
    ''::text AS entity_id,
    NULL::numeric AS amount,
    'The facilities carve-out is sized by area. Without it the occupancy cost sitting in overhead cannot be split between the programme and the tenants, and 200.465 has nothing to work from.'::text AS detail
   FROM fiscal_period p
  WHERE p.period = '2025'::text AND NOT (EXISTS ( SELECT 1
           FROM facility f
          WHERE f.period = p.period AND f.usable_sqft > 0::numeric))
UNION ALL
 SELECT 'SPACE_UNATTRIBUTED'::text AS kind,
    'BLOCKING'::text AS severity,
    c.period,
    c.name AS label,
    'facility'::text AS entity,
    c.facility_id AS entity_id,
    c.usable_sqft AS amount,
        CASE
            WHEN c.units = 0 THEN ('Measured at '::text || c.usable_sqft::text) || ' sq ft with no space units saying who uses it. Area is not a driver until somebody is standing in it.'::text
            ELSE ((((((c.units::text || ' space units accounting for '::text) || c.unit_sqft::text) || ' sq ft against '::text) || c.usable_sqft::text) || ' measured, a difference of '::text) || c.variance::text) || '. Space must be accounted for in full, including what is common and what is vacant.'::text
        END AS detail
   FROM v_space_unit_control c
  WHERE c.usable_sqft > 0::numeric AND NOT c.ties
UNION ALL
 SELECT 'CHARGE_CODE_UNASSIGNED'::text AS kind,
    'MEDIUM'::text AS severity,
    c.period,
    c.objective_id AS label,
    'cost_objective'::text AS entity,
    c.objective_id AS entity_id,
    NULL::numeric AS amount,
    c.hours_charged::text || ' hours booked with nobody assigned to the code. Assign the people who work on it and the gate turns on.'::text AS detail
   FROM v_charge_code c
  WHERE c.hours_charged > 0::numeric AND c.people_authorised = 0
UNION ALL
 SELECT 'AWARD_NO_CEILING'::text AS kind,
    'HIGH'::text AS severity,
    o.period,
    a.award_id AS label,
    'award'::text AS entity,
    a.award_id AS entity_id,
    NULL::numeric AS amount,
        CASE
            WHEN (EXISTS ( SELECT 1
               FROM evidence e
              WHERE e.kind = ANY (ARRAY['subrecipient-agreement'::text, 'award-agreement'::text, 'award-modification'::text, 'grant-agreement'::text]))) THEN 'No ceiling on file, and there are executed agreements in the document register. Read the obligation clause into the record — a claim cannot be tested against a ceiling that is not there.'::text
            ELSE 'No ceiling on file and no executed agreement in the register either. Get the agreement; what was invoiced is not a ceiling.'::text
        END AS detail
   FROM award a
     JOIN cost_objective o ON o.objective_id = a.objective_id
  WHERE a.ceiling_federal = 0::numeric
UNION ALL
 SELECT 'POSITION_UNCONFIRMED'::text AS kind,
    'HIGH'::text AS severity,
    st.period,
    st.scope AS label,
    'decision'::text AS entity,
    st.decision_id::text AS entity_id,
    NULL::numeric AS amount,
    'A working position a script proposed and nobody has adopted. It is '
    || 'classified, and it is not yet anybody''s judgment.'::text AS detail
   FROM v_classification_standing st
  WHERE st.is_working_position AND NOT st.adopted
UNION ALL
 SELECT 'RECLASS_RECOMMENDED'::text AS kind,
    'HIGH'::text AS severity,
    r.period,
    r.scope AS label,
    'reclass_recommendation'::text AS entity,
    r.rec_id::text AS entity_id,
    NULL::numeric AS amount,
    (a.display_name || ' recommends ' || r.pool::text || ': ' || r.note)::text
      AS detail
   FROM reclass_recommendation r
   JOIN actor a ON a.actor_id = r.recommended_by
  WHERE r.disposition = 'OPEN';

CREATE OR REPLACE VIEW v_worklist_owned AS
WITH all_items AS (
         SELECT v_worklist.kind,
            v_worklist.severity,
            v_worklist.period,
            v_worklist.label,
            v_worklist.entity,
            v_worklist.entity_id,
            v_worklist.amount,
            v_worklist.detail
           FROM v_worklist
        UNION ALL
         SELECT v_worklist_extra.kind,
            v_worklist_extra.severity,
            v_worklist_extra.period,
            v_worklist_extra.label,
            v_worklist_extra.entity,
            v_worklist_extra.entity_id,
            v_worklist_extra.amount,
            v_worklist_extra.detail
           FROM v_worklist_extra
        )
 SELECT kind,
    severity,
    period,
    label,
    entity,
    entity_id,
    amount,
    detail,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN 'CONTROLLER'::text
            WHEN 'BLOCKS_SEAL'::text THEN 'CONTROLLER'::text
            WHEN 'STALE_DECISION'::text THEN 'CONTROLLER'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN 'CONTROLLER'::text
            WHEN 'POSITION_UNCONFIRMED'::text THEN 'CONTROLLER'::text
            WHEN 'RECLASS_RECOMMENDED'::text THEN 'CONTROLLER'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN 'OFFICE'::text
            WHEN 'SPACE_UNMEASURED'::text THEN 'FACILITIES'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN 'FACILITIES'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN 'INVENTORY'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN 'PROJECT'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN 'PROJECT'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN 'PROJECT'::text
            WHEN 'AWARD_NO_CEILING'::text THEN 'PROJECT'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN 'PROJECT'::text
            WHEN 'STALE_CERTIFICATION'::text THEN 'PROJECT'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN 'PROJECT'::text
            ELSE 'CONTROLLER'::text
        END AS owner_portfolio,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN '/classify'::text
            WHEN 'BLOCKS_SEAL'::text THEN '/classify'::text
            WHEN 'STALE_DECISION'::text THEN '/classify'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN '/timesheet'::text
            WHEN 'POSITION_UNCONFIRMED'::text THEN '/classify/review'::text
            WHEN 'RECLASS_RECOMMENDED'::text THEN '/classify/review'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN '/evidence'::text
            WHEN 'SPACE_UNMEASURED'::text THEN '/space'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN '/space'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN '/inventory'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN '/contracts'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN '/contracts'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN '/contracts/codes'::text
            WHEN 'AWARD_NO_CEILING'::text THEN '/contracts'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN '/contracts/people'::text
            WHEN 'STALE_CERTIFICATION'::text THEN '/contracts/people'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN '/timesheet'::text
            ELSE '/'::text
        END AS goes_to,
        CASE kind
            WHEN 'UNCLASSIFIED'::text THEN 'audit'::text
            WHEN 'BLOCKS_SEAL'::text THEN 'audit'::text
            WHEN 'STALE_DECISION'::text THEN 'audit'::text
            WHEN 'POSITION_UNCONFIRMED'::text THEN 'audit'::text
            WHEN 'RECLASS_RECOMMENDED'::text THEN 'audit'::text
            WHEN 'NEEDS_EVIDENCE'::text THEN 'audit'::text
            WHEN 'SPACE_UNMEASURED'::text THEN 'audit'::text
            WHEN 'SPACE_UNATTRIBUTED'::text THEN 'audit'::text
            WHEN 'ASSET_FUNDING_UNKNOWN'::text THEN 'audit'::text
            WHEN 'INVOICE_NO_INDIRECT'::text THEN 'audit'::text
            WHEN 'INVOICE_NO_AWARD'::text THEN 'audit'::text
            WHEN 'AWARD_NO_CEILING'::text THEN 'audit'::text
            WHEN 'DONATION_RATE_MISSING'::text THEN 'fcs'::text
            WHEN 'CHARGE_CODE_UNASSIGNED'::text THEN 'fcs'::text
            WHEN 'NEEDS_CERTIFICATION'::text THEN 'fcs'::text
            WHEN 'STALE_CERTIFICATION'::text THEN 'fcs'::text
            WHEN 'EMPLOYMENT_UNKNOWN'::text THEN 'fcs'::text
            ELSE 'audit'::text
        END AS owner_product
   FROM all_items a;

-- ---------------------------------------------------------- and the walk ---
--
-- Step 3 has said 'Every cost judged' and read coverage, which answers whether
-- every dollar carries a position. On a restaged year every dollar does and
-- **none of it is anybody's judgment yet**, so the step would have read DONE
-- over 757 rows nobody has looked at — the walk making the exact claim this
-- migration exists to stop the record making. Lifted from 082 and given the
-- second half of its own question.

DROP VIEW v_audit_walk;

CREATE VIEW v_audit_walk AS
WITH
period AS (SELECT period FROM fiscal_period),
ledger AS (
    SELECT p.period,
           (SELECT count(*) FROM ledger_line l WHERE l.period = p.period) AS lines
      FROM period p
),
recon AS (
    SELECT p.period,
           count(r.*)                             AS points,
           count(r.*) FILTER (WHERE r.ties)       AS tying,
           count(r.*) FILTER (WHERE r.state = 'NO DATA') AS blind
      FROM period p
      LEFT JOIN v_statement_reconciliation r ON r.period = p.period
     GROUP BY p.period
),
cover AS (
    SELECT p.period, c.groups_total, c.groups_decided,
           c.scope_dollars, c.classified, c.unclassified, c.pct_dollars_covered
      FROM period p
      LEFT JOIN v_classification_coverage c ON c.period = p.period
),
part AS (
    SELECT p.period,
           max(pc.state) FILTER (WHERE pc.partition = 'SPACE')  AS space_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'SPACE')  AS space_needs,
           max(pc.state) FILTER (WHERE pc.partition = 'ASSETS') AS asset_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'ASSETS') AS asset_needs
      FROM period p
      LEFT JOIN v_partition_coverage pc ON pc.period = p.period
     GROUP BY p.period
),
adopt AS (
    SELECT p.period,
           count(*) FILTER (WHERE st.is_working_position AND NOT st.adopted)
             AS unadopted
      FROM period p
      LEFT JOIN v_classification_standing st ON st.period = p.period
     GROUP BY p.period
),
cited AS (
    -- A judgment that names the paper it rests on. Attaching is not citing:
    -- `decision_verified_check` counts `decision_evidence`, and that is the
    -- difference between *this paper is about that money* and *this paper is
    -- why I judged it the way I did*.
    -- The period comes through `decision_set`, not off the decision.
    -- `decision.scope` is the **group key** — `account=…|payee=…` — and a
    -- first draft grouped by it, which produced one row per group and made
    -- this step report "nothing has been judged yet" over 757 judgments.
    -- That is the name-written-from-memory defect this file lists by name,
    -- committed by somebody who had just read the list.
    -- Scoped to the judgments the worklist's NEEDS_EVIDENCE scopes to —
    -- federally chargeable, ALLOWABLE or PENDING — because both appear on
    -- this one page and a first draft counted all 757 live judgments beside
    -- a worklist row saying 363. Two true figures about "judgments with no
    -- document", at the same moment, which a reader has to reconcile in
    -- their head. That is 13.0% and 2.2% in its presentation form.
    SELECT ds.period,
           count(DISTINCT d.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS live,
           count(DISTINCT de.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS with_citation,
           count(DISTINCT d.decision_id)                           AS all_live
      FROM decision d
      JOIN decision_set ds ON ds.set_id = d.set_id
      LEFT JOIN decision_evidence de ON de.decision_id = d.decision_id
     WHERE d.reversed_at IS NULL
     GROUP BY ds.period
),
sealed AS (
    SELECT p.period,
           bool_or(ds.sealed_at IS NOT NULL)      AS is_sealed,
           max(ds.sealed_at)                      AS at,
           max(left(ds.seal_hash, 12))            AS hash
      FROM period p
      LEFT JOIN decision_set ds ON ds.period = p.period
     GROUP BY p.period
),
rated AS (
    SELECT p.period,
           count(r.*) FILTER (WHERE r.status <> 'SUPERSEDED')  AS live,
           max(r.rate) FILTER (WHERE r.kind = 'INDIRECT_COMBINED'
                                 AND r.status <> 'SUPERSEDED') AS combined,
           max(r.admin_labour_basis) FILTER (WHERE r.status <> 'SUPERSEDED')
                                                               AS basis
      FROM period p
      LEFT JOIN rate r ON r.period = p.period
     GROUP BY p.period
),
restated AS (
    SELECT p.period,
           count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED') AS standing
      FROM period p
      LEFT JOIN restatement rs ON rs.period = p.period
     GROUP BY p.period
)
SELECT * FROM (
    SELECT l.period, 1 AS seq, 'The books are in' AS step,
           'LEDGER' AS key,
           'The QuickBooks exports, as received' AS what,
           CASE WHEN l.lines = 0 THEN 'NO DATA' ELSE 'DONE' END AS state,
           CASE WHEN l.lines = 0
                THEN 'No ledger has been loaded for this period.'
                -- Grouped in the database because this sentence is built
                -- here: `api.js::money()` and `count()` are the one formatter
                -- for a figure the screen renders, and they cannot reach
                -- inside a string the view composed. 15500 read as a part
                -- number rather than a count.
                ELSE to_char(l.lines, 'FM999,999,999')
                     || ' general-ledger lines on file.' END AS detail,
           '/books/import' AS goes_to
      FROM ledger l

    UNION ALL
    SELECT r.period, 2, 'The books agree with themselves',
           'RECONCILE',
           'Ledger, profit and loss, balance sheet, payroll register',
           CASE WHEN r.points = 0 THEN 'NO DATA'
                WHEN r.blind > 0 THEN 'NO DATA'
                WHEN r.tying = r.points THEN 'DONE'
                ELSE 'OPEN' END,
           CASE WHEN r.points = 0
                THEN 'No control has been evaluated.'
                WHEN r.blind > 0
                THEN r.blind || ' of ' || r.points || ' points cannot be '
                     || 'evaluated, which is not the same as tying.'
                ELSE r.tying || ' of ' || r.points || ' cross-reference '
                     || 'points tie. A rate is refused while any is open.'
           END,
           '/books'
      FROM recon r

    UNION ALL
    SELECT c.period, 3, 'Every cost judged',
           'CLASSIFY',
           'The profit and loss, less income, into 2 CFR 200 pools',
           -- Judged and *adopted* are two questions, and this step is only
           -- done when both answer yes. A working position a script proposed
           -- is a classification and is not yet anybody's judgment; a walk
           -- that called this step DONE over 757 of them would be the screen
           -- making a claim the record does not support.
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'NO DATA'
                WHEN c.unclassified = 0 AND COALESCE(ad.unadopted, 0) = 0
                THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0
                THEN 'There is no cost to classify yet.'
                WHEN c.unclassified > 0
                THEN to_char(c.groups_decided, 'FM999,999') || ' of '
                     || to_char(c.groups_total, 'FM999,999')
                     || ' groups, ' || c.pct_dollars_covered || '% of dollars.'
                WHEN COALESCE(ad.unadopted, 0) > 0
                THEN 'Every group carries a position. '
                     || to_char(ad.unadopted, 'FM999,999') || ' of '
                     || to_char(c.groups_total, 'FM999,999')
                     || ' are working positions a script proposed and nobody '
                     || 'has adopted — classified, and not yet a judgment.'
                ELSE to_char(c.groups_decided, 'FM999,999') || ' of '
                     || to_char(c.groups_total, 'FM999,999')
                     || ' groups, ' || c.pct_dollars_covered || '% of dollars.'
           END,
           '/classify'
      FROM cover c LEFT JOIN adopt ad ON ad.period = c.period

    UNION ALL
    SELECT pt.period, 4, 'Every square foot accounted for',
           'SPACE',
           'Each building, into tenant, programme and vacant space',
           COALESCE(pt.space_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.space_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.space_needs, 'the square footage')
                     || '. Until it lands the 200.465 carve-out cannot be '
                     || 'computed at all, and every dollar of tenant and '
                     || 'vacant occupancy cost sits in the federal pool.'
                ELSE 'The space accounts for itself.' END,
           '/classify/space'
      FROM part pt

    UNION ALL
    SELECT pt.period, 5, 'Every asset''s funding source',
           'ASSETS',
           'The fixed-asset register, into funding sources',
           COALESCE(pt.asset_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.asset_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.asset_needs, 'the asset register')
                     || '. 200.436(b) makes depreciation on a federally '
                     || 'funded asset unallowable and the schedule has no '
                     || 'such column, which 200.313(d)(1) requires.'
                ELSE 'Every asset names where its money came from.' END,
           '/classify/assets'
      FROM part pt

    UNION ALL
    SELECT c.period, 6, 'The paper behind the judgments',
           'EVIDENCE',
           'A judgment that cites the document it rests on',
           CASE WHEN COALESCE(ct.all_live, 0) = 0 THEN 'WAITING'
                WHEN COALESCE(ct.live, 0) = 0 THEN 'DONE'
                WHEN ct.with_citation = ct.live THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN COALESCE(ct.all_live, 0) = 0
                THEN 'Nothing has been judged yet, so there is nothing to cite.'
                WHEN COALESCE(ct.live, 0) = 0
                THEN 'No judgment is federally chargeable, so none needs a '
                     || 'citation for 2 CFR 200.'
                ELSE to_char(COALESCE(ct.with_citation, 0), 'FM999,999')
                     || ' of ' || to_char(ct.live, 'FM999,999')
                     || ' federally chargeable judgments cite a document, of '
                     || to_char(ct.all_live, 'FM999,999') || ' live. '
                     || 'Attaching is not citing: a citation is why the '
                     || 'judgment was made, and it is what VERIFIED requires.'
           END,
           '/evidence'
      FROM cover c LEFT JOIN cited ct ON ct.period = c.period

    UNION ALL
    SELECT s.period, 7, 'The classifications sealed',
           'SEAL',
           'Hashed across every judgment, before any rate exists',
           CASE WHEN s.is_sealed THEN 'DONE'
                WHEN COALESCE(c.unclassified, 1) <> 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN s.is_sealed
                THEN 'Sealed ' || to_char(s.at, 'DD Mon YYYY') || ' · '
                     || s.hash || '…'
                WHEN COALESCE(c.unclassified, 1) <> 0
                THEN 'Cost is still outstanding. Sealing an incomplete set '
                     || 'is allowed and makes the rate read high, which is '
                     || 'the honest direction to err.'
                ELSE 'Every group is judged. Sealing is the assertion that '
                     || 'the rate was not reverse-engineered, and it is '
                     || 'yours to make.'
           END,
           '/review/rate'
      FROM sealed s LEFT JOIN cover c ON c.period = s.period

    UNION ALL
    SELECT rt.period, 8, 'The rate computed',
           'RATE',
           'A pool over a base, carrying the seal',
           CASE WHEN COALESCE(rt.live, 0) > 0 THEN 'DONE'
                WHEN NOT COALESCE(s.is_sealed, false) THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rt.live, 0) > 0
                THEN 'Indirect, combined: '
                     || round(rt.combined * 100, 2) || '% on the '
                     || rt.basis || ' basis.'
                WHEN NOT COALESCE(s.is_sealed, false)
                THEN 'No rate can exist until the set is sealed — the '
                     || 'database refuses one whose seal does not match.'
                ELSE 'The set is sealed. Computing is arithmetic from here.'
           END,
           '/review/rate'
      FROM rated rt LEFT JOIN sealed s ON s.period = rt.period

    UNION ALL
    SELECT rt.period, 9, 'The rate certified',
           'CERTIFY',
           'The controller''s signature on the build-up',
           CASE WHEN cert.certified THEN 'DONE'
                WHEN COALESCE(rt.live, 0) = 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN cert.certified
                THEN 'Signed by ' || cert.certified_by || ' on '
                     || to_char(cert.certified_at, 'DD Mon YYYY') || '. '
                     || 'Anything issued from here says so.'
                ELSE COALESCE(cert.why_not, 'Nobody has signed the rate.')
                     || ' Nothing is blocked by this — an invoice or a '
                     || 'workbook produced now simply carries NOT CERTIFIED.'
           END,
           '/review/rate'
      FROM rated rt
      LEFT JOIN v_rate_certified cert ON cert.period = rt.period

    UNION ALL
    SELECT rs.period, 10, 'The position on each invoice',
           'RESTATE',
           'What was billed, against what the rate supports',
           CASE WHEN COALESCE(rs.standing, 0) > 0 THEN 'DONE'
                WHEN COALESCE(rt.live, 0) = 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rs.standing, 0) > 0
                THEN rs.standing || ' restatement(s) standing as a claim. '
                     || 'Everything is PROPOSED until a sponsor says '
                     || 'otherwise in writing.'
                WHEN COALESCE(rt.live, 0) = 0
                THEN 'Needs a rate to measure against.'
                ELSE 'Nothing has been put to a sponsor yet.'
           END,
           '/restate'
      FROM restated rs LEFT JOIN rated rt ON rt.period = rs.period

    UNION ALL
    SELECT p.period, 11, 'The papers that leave the building',
           'REPORT',
           'The auditor''s report, Form 990, the workbooks',
           'DONE',
           'Read from the rows they were recorded in. Each states what is '
           || 'unfinished above its figures, and the workbooks repeat it on '
           || 'the first sheet because a workbook travels.',
           '/reports'
      FROM period p
) w
ORDER BY period, seq;

COMMENT ON VIEW v_audit_walk IS
'The 2025 audit as the one ordered journey it is, eleven steps, each reading '
'the view that already owns its figure. WAITING is a step whose predecessor is '
'not done — printing it as OPEN would offer work the system would refuse. '
'Step 3 is done when every dollar is judged and every working position has '
'been adopted; those are two questions and one of them is about a person.';
