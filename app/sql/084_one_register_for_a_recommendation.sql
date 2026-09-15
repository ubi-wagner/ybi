-- 084: one register for a recommendation, whatever it is about.
--
-- `083` built *somebody who may read the cost record proposes a change, and
-- the controller disposes of it* and pointed it at classification, because
-- that is where the 757 working positions were. The same act is now wanted
-- for the two partitions the walk reports as NO DATA: **no building carries
-- square footage**, so the 200.465 carve-out cannot fire at all, and **no
-- asset carries a funding source**, so 200.436(b) cannot be answered on
-- $850,383 of depreciation. Heidi holds FACILITIES and INVENTORY and is the
-- person who will go and measure; Tom signs the rate those measurements feed.
--
-- The obvious build is `space_recommendation` and `asset_funding_
-- recommendation` beside `reclass_recommendation`. That is **three structures
-- describing one thing**, which is this repository's most expensive lesson in
-- somebody else's words — `project_wbs_nodes` beside `project_milestones`,
-- collapsed and dropped — and its own: `space_partition` beside `space_unit`,
-- 13.0% and 2.2% at the same moment, *the cost objective is the charge code
-- and there is deliberately no second register of codes*. Three registers
-- would also mean three review lists, and the whole point is that the
-- controller has **one** list.
--
-- So one register, carrying a **subject** and a **proposal**. Four subjects,
-- each mapping to exactly one register and exactly one door:
--
--     CLASSIFICATION   -> decision, through POST /api/classify/decide
--     FACILITY         -> facility, through PUT /api/facilities
--     SPACE_UNIT       -> space_unit, through PUT /api/facilities/space
--     ASSET_FUNDING    -> asset_funding, through PUT /api/facilities/asset-funding
--
-- **The proposal is `jsonb` and the schema still checks it.** A wide table
-- with four columns for one subject and five for another is sparse by
-- construction and every column is dead for three subjects out of four — the
-- shape `tests/test_no_register_is_dead.py` exists to catch. So the payload is
-- one column and `recommendation_is_well_formed()` validates it per subject,
-- **casting every enum to its real type** so a bad value fails in the
-- database rather than at the moment somebody accepts it. It re-checks the
-- target register's own invariants too — DIRECT names an objective, PROGRAM
-- space names an objective, OCCUPIED space names an occupant — because *a
-- recommendation the server would refuse is a screen offering what the API
-- will not take*, which this repository shipped once on 24 accounts.
--
-- **`saw` is a digest, not an id, and NULL is the interesting value.** `083`
-- stored the decision the recommendation was written against, so an overtaken
-- proposal says so rather than being applied to something it was never about.
-- The same guarantee is wanted for a square footage somebody has since
-- changed, and `subject_digest()` is that one definition for all four
-- subjects. NULL means **the row is not on the record at all** — which for
-- space and assets is not an edge case but the *normal* case, because both
-- registers are empty and Heidi's first act is to put a building on the
-- record rather than to amend one.

-- ------------------------------------------------------------- subjects ---

DO $$ BEGIN
  CREATE TYPE recommendation_subject AS ENUM
    ('CLASSIFICATION', 'FACILITY', 'SPACE_UNIT', 'ASSET_FUNDING');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMENT ON TYPE recommendation_subject IS
'What a recommendation is about. Each value names exactly one register and '
'exactly one route that writes it; accepting goes through that route, so '
'there is still one door to each register.';

-- What the record currently says about one subject, as one value.
--
-- The `project_claim.saw_*` idea, generalised: an approval has to be of
-- something specific or the record moves underneath it and the approval
-- silently comes to cover something else. NULL is honest and load-bearing —
-- it means the row is not there, which is the state both partitions are in.
CREATE OR REPLACE FUNCTION subject_digest(
    subj recommendation_subject, subj_id text, p text) RETURNS text AS $$
DECLARE d text;
BEGIN
  IF subj = 'CLASSIFICATION' THEN
    -- The live judgment itself. Superseding produces a new decision_id, which
    -- is exactly the change this has to notice.
    SELECT st.decision_id::text INTO d
      FROM v_classification_standing st
     WHERE st.period = p AND st.scope = subj_id;
  ELSIF subj = 'FACILITY' THEN
    SELECT md5(f.name || '|' || f.usable_sqft::text || '|'
               || COALESCE(f.rentable_sqft::text, '') || '|' || f.owned::text)
      INTO d FROM facility f
     WHERE f.facility_id = subj_id AND f.period = p;
  ELSIF subj = 'SPACE_UNIT' THEN
    SELECT md5(u.label || '|' || u.usable_sqft::text || '|' || u.use::text
               || '|' || u.status::text || '|' || COALESCE(u.objective_id, '')
               || '|' || u.occupant)
      INTO d FROM space_unit u
     WHERE u.unit_id = subj_id AND u.period = p;
  ELSIF subj = 'ASSET_FUNDING' THEN
    -- One asset's whole funding picture, because a proposal adds a source to
    -- a set and the question is whether the set has moved.
    SELECT md5(COALESCE(string_agg(af.kind::text || '|' || af.amount::text
                                   || '|' || af.award_reference, ','
                                   ORDER BY af.kind, af.award_reference), ''))
      INTO d FROM asset_funding af WHERE af.asset_id = subj_id;
    -- An asset with no funding rows and an asset that is not on the register
    -- are different facts, and md5('') cannot tell them apart.
    IF NOT EXISTS (SELECT 1 FROM asset a
                    WHERE a.asset_id = subj_id AND a.period = p) THEN
      d := NULL;
    END IF;
  END IF;
  RETURN d;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION subject_digest(recommendation_subject, text, text) IS
'What the record says about one subject right now, as one comparable value. '
'NULL means the row is not on the record — which for space and assets is the '
'normal case rather than an edge, both registers being empty.';

-- --------------------------------------- what would actually be written ---
--
-- A proposal names only what is changing, so what the target route receives
-- is the proposal laid over the row that is there — otherwise correcting a
-- square footage would blank the address. Two things went wrong with doing
-- that naively, and they point in opposite directions:
--
--   * **The merge can invent a combination nobody proposed.** The auditor
--     proposed `pool: G&A` on a group classified DIRECT to Xjet; the merge
--     carried the objective across and `direct_needs_objective` refused the
--     accept — a recommendation the register had already accepted, refused at
--     the last step, with nothing anywhere saying the objective was the
--     problem. On a classification the objective is not an independent field:
--     `direct_needs_objective` is an *equivalence*, so the objective is a
--     function of the pool and a pool that stops being DIRECT takes it with
--     it. That is the schema's rule, not a guess about what was meant.
--
--   * **Validating the proposal alone refuses legitimate partial changes.**
--     `status: OCCUPIED` on a space that already names its occupant is a
--     perfectly good one-field correction, and a check that reads the
--     proposal by itself sees no occupant and refuses it.
--
-- Both are the same mistake — checking something other than what would be
-- written. So there is one function that says what would be written, the
-- trigger validates *that*, and the accept handler reads *that* rather than
-- merging again in Python. A second copy of a merge rule is a second thing to
-- be wrong.

CREATE OR REPLACE FUNCTION subject_merged(
    subj recommendation_subject, subj_id text, p text, proposal jsonb)
RETURNS jsonb AS $$
DECLARE merged jsonb;
BEGIN
  merged := COALESCE(subject_current(subj, subj_id, p), '{}'::jsonb) || proposal;
  IF subj = 'CLASSIFICATION'
     AND COALESCE(merged->>'pool', '') <> 'DIRECT'
     AND NOT (proposal ? 'objective_id') THEN
    merged := merged - 'objective_id';
  END IF;
  RETURN merged;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION subject_merged(recommendation_subject, text, text, jsonb) IS
'What accepting this proposal would actually write: the proposal over the row '
'that is there. The one definition — the validation trigger checks it and the '
'accept handler reads it, so neither can hold its own opinion about what a '
'partial proposal means.';


-- ------------------------------------------------------- the register ------

CREATE TABLE IF NOT EXISTS recommendation (
    rec_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period          text NOT NULL REFERENCES fiscal_period(period),
    subject         recommendation_subject NOT NULL,
    subject_id      text NOT NULL,
    proposal        jsonb NOT NULL,
    note            text NOT NULL,
    recommended_by  uuid NOT NULL REFERENCES actor(actor_id),
    recommended_at  timestamptz NOT NULL DEFAULT now(),
    saw             text,
    disposition     text NOT NULL DEFAULT 'OPEN',
    disposed_by     uuid REFERENCES actor(actor_id),
    disposed_at     timestamptz,
    disposition_reason text,
    result_id       text,

    CONSTRAINT disposition_is_known
      CHECK (disposition IN ('OPEN', 'ACCEPTED', 'DECLINED', 'WITHDRAWN')),
    CONSTRAINT disposition_names_itself
      CHECK ((disposition = 'OPEN') = (disposed_at IS NULL)
         AND (disposed_at IS NULL) = (disposed_by IS NULL)),
    CONSTRAINT declining_says_why
      CHECK (disposition <> 'DECLINED'
             OR length(btrim(COALESCE(disposition_reason, ''))) >= 12),
    CONSTRAINT recommendation_says_why
      CHECK (length(btrim(note)) >= 12),
    CONSTRAINT subject_id_is_named
      CHECK (length(btrim(subject_id)) >= 1),
    CONSTRAINT proposal_is_an_object
      CHECK (jsonb_typeof(proposal) = 'object')
);

CREATE INDEX IF NOT EXISTS recommendation_subject_idx
  ON recommendation (period, subject, subject_id);

-- One open recommendation per person per subject. A second from the same
-- person is an amendment and supersedes; two different people each get one,
-- and the controller seeing both is information rather than noise — they may
-- disagree, and that is the most useful thing the register can tell him.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_recommendation_per_person
  ON recommendation (period, subject, subject_id, recommended_by)
  WHERE disposition = 'OPEN';

COMMENT ON TABLE recommendation IS
'Somebody who may read the cost record saying: this is wrong, here is what it '
'should be, and here is why. It is never a decision and never becomes one — '
'accepting records the change through the ordinary route for that register, '
'under the controller''s name, citing this row.';

-- A value the enum does not have is a *refusal*, not a fault.
--
-- `(p->>'use')::space_use` raises `invalid_text_representation`, which the
-- API's schema-gate handler does not recognise, so a typo in a space use
-- answered **500 Internal Server Error** — a person told the system broke
-- when what happened is that they picked something that does not exist. The
-- allowed values are read out of `pg_enum` rather than listed here, because
-- a hand-kept copy of an enum is the map this repository has been wrong about
-- four times in one run.
CREATE OR REPLACE FUNCTION enum_or_refuse(v text, type_name text, what text)
RETURNS text AS $$
DECLARE allowed text;
BEGIN
  EXECUTE format('SELECT $1::%I::text', type_name) INTO v USING v;
  RETURN v;
EXCEPTION WHEN invalid_text_representation OR null_value_not_allowed THEN
  SELECT string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) INTO allowed
    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
   WHERE t.typname = type_name;
  RAISE EXCEPTION '% is not a %. The register takes: %',
                  COALESCE(v, 'nothing'), what, allowed
    USING ERRCODE = 'raise_exception';
END;
$$ LANGUAGE plpgsql STABLE;

-- The payload, checked per subject. Every enum is cast to its real type, so a
-- value the target register would refuse fails here rather than at the moment
-- somebody presses Accept — *read the schema, never recall it*, enforced.
CREATE OR REPLACE FUNCTION recommendation_is_well_formed() RETURNS trigger AS $$
DECLARE
  p jsonb;
  pool_v        pool_type;
  fn_v          function_990;
  fed_v         federal_treatment;
  use_v         space_use;
  status_v      occupancy_status;
  kind_v        funding_kind;
  sqft_v        numeric;
  amount_v      numeric;
BEGIN
  p := subject_merged(NEW.subject, NEW.subject_id, NEW.period, NEW.proposal);

  IF NEW.subject = 'CLASSIFICATION' THEN
    IF NOT (p ? 'pool' AND p ? 'function_990' AND p ? 'federal') THEN
      RAISE EXCEPTION 'a classification proposal names a pool, a 990 function '
                      'and a federal treatment' USING ERRCODE='raise_exception';
    END IF;
    pool_v := enum_or_refuse(p->>'pool', 'pool_type', 'cost pool')::pool_type;
    fn_v   := enum_or_refuse(p->>'function_990', 'function_990',
                             '990 function')::function_990;
    fed_v  := enum_or_refuse(p->>'federal', 'federal_treatment',
                             'federal treatment')::federal_treatment;
    IF (pool_v = 'DIRECT') <> (COALESCE(p->>'objective_id', '') <> '') THEN
      RAISE EXCEPTION 'direct cost names a cost objective; pooled cost must '
                      'not carry one' USING ERRCODE='raise_exception';
    END IF;
    IF fed_v = 'ALLOWABLE' AND pool_v IN ('FUNDRAISING', 'UNALLOWABLE') THEN
      RAISE EXCEPTION 'fundraising and unallowable cost is not federally '
                      'allowable' USING ERRCODE='raise_exception';
    END IF;

  ELSIF NEW.subject = 'FACILITY' THEN
    IF COALESCE(btrim(p->>'name'), '') = '' THEN
      RAISE EXCEPTION 'a building proposal names the building'
        USING ERRCODE='raise_exception';
    END IF;
    sqft_v := (p->>'usable_sqft')::numeric;
    IF sqft_v IS NULL OR sqft_v <= 0 THEN
      RAISE EXCEPTION 'a building proposal carries its usable square footage, '
                      'which is what the 200.465 carve-out is sized by'
        USING ERRCODE='raise_exception';
    END IF;
    IF COALESCE(p->>'rentable_sqft', '') <> ''
       AND (p->>'rentable_sqft')::numeric < sqft_v THEN
      RAISE EXCEPTION 'rentable area cannot be smaller than usable area'
        USING ERRCODE='raise_exception';
    END IF;

  ELSIF NEW.subject = 'SPACE_UNIT' THEN
    IF COALESCE(btrim(p->>'facility_id'), '') = ''
       OR COALESCE(btrim(p->>'label'), '') = '' THEN
      RAISE EXCEPTION 'a space proposal names its building and what the space '
                      'is called' USING ERRCODE='raise_exception';
    END IF;
    sqft_v   := (p->>'usable_sqft')::numeric;
    use_v    := enum_or_refuse(p->>'use', 'space_use', 'space use')::space_use;
    status_v := enum_or_refuse(p->>'status', 'occupancy_status',
                               'occupancy status')::occupancy_status;
    IF sqft_v IS NULL OR sqft_v <= 0 THEN
      RAISE EXCEPTION 'a space proposal carries its square footage'
        USING ERRCODE='raise_exception';
    END IF;
    IF use_v = 'PROGRAM' AND COALESCE(p->>'objective_id', '') = '' THEN
      RAISE EXCEPTION 'programme space names the cost objective it serves'
        USING ERRCODE='raise_exception';
    END IF;
    IF status_v = 'OCCUPIED' AND COALESCE(btrim(p->>'occupant'), '') = '' THEN
      RAISE EXCEPTION 'occupied space names who is in it'
        USING ERRCODE='raise_exception';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM facility f
                    WHERE f.facility_id = p->>'facility_id'
                      AND f.period = NEW.period)
       AND NOT EXISTS (SELECT 1 FROM recommendation r
                        WHERE r.subject = 'FACILITY'
                          AND r.subject_id = p->>'facility_id'
                          AND r.period = NEW.period
                          AND r.disposition = 'OPEN') THEN
      RAISE EXCEPTION 'no building % is on the record or proposed. Put the '
                      'building up first — its area is what the space inside '
                      'it has to account for.', p->>'facility_id'
        USING ERRCODE='raise_exception';
    END IF;

  ELSIF NEW.subject = 'ASSET_FUNDING' THEN
    kind_v   := enum_or_refuse(p->>'kind', 'funding_kind',
                               'funding source')::funding_kind;
    amount_v := (p->>'amount')::numeric;
    IF amount_v IS NULL OR amount_v < 0 THEN
      RAISE EXCEPTION 'a funding proposal carries the amount that source paid'
        USING ERRCODE='raise_exception';
    END IF;
    IF kind_v = 'FEDERAL'
       AND COALESCE(btrim(p->>'award_reference'), '') = '' THEN
      RAISE EXCEPTION 'federal money names the award it came from — 200.313'
                      '(d)(1) requires it, and an unnamed federal source is '
                      'the gap this register exists to close'
        USING ERRCODE='raise_exception';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM asset a
                    WHERE a.asset_id = NEW.subject_id
                      AND a.period = NEW.period) THEN
      RAISE EXCEPTION 'asset % is not on the register. The register arrives '
                      'whole from the fixed-asset schedule — ask for it on '
                      'the Requests screen — and the funding source is the '
                      'one column it does not carry.', NEW.subject_id
        USING ERRCODE='raise_exception';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS recommendation_well_formed ON recommendation;
CREATE TRIGGER recommendation_well_formed
  BEFORE INSERT OR UPDATE ON recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_is_well_formed();

-- Nobody disposes of their own recommendation. `062`'s rule — handing
-- yourself a job is taking one, and it reads differently on the record.
CREATE OR REPLACE FUNCTION recommendation_disposed_by_another_fn() RETURNS trigger AS $$
BEGIN
  IF NEW.disposition IN ('ACCEPTED', 'DECLINED')
     AND NEW.disposed_by = NEW.recommended_by THEN
    RAISE EXCEPTION 'a recommendation is somebody asking somebody else to look '
                    'at it. Withdraw your own instead — that is the act you '
                    'are actually performing.' USING ERRCODE='raise_exception';
  END IF;
  IF NEW.disposition = 'WITHDRAWN'
     AND NEW.disposed_by IS DISTINCT FROM NEW.recommended_by THEN
    RAISE EXCEPTION 'only the person who made a recommendation withdraws it. '
                    'Decline it, and say why.' USING ERRCODE='raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS recommendation_disposed_by_another ON recommendation;
CREATE TRIGGER recommendation_disposed_by_another
  BEFORE UPDATE ON recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_disposed_by_another_fn();

-- ------------------------------------ and it has to propose a change ------

-- The current state of a subject, shaped like a proposal, so the two can be
-- compared key by key. Returns NULL where the row is not on the record, in
-- which case any proposal at all is a change.
CREATE OR REPLACE FUNCTION subject_current(
    subj recommendation_subject, subj_id text, p text) RETURNS jsonb AS $$
DECLARE j jsonb;
BEGIN
  IF subj = 'CLASSIFICATION' THEN
    SELECT jsonb_build_object('pool', st.pool, 'function_990', st.function_990,
                              'federal', st.federal,
                              'objective_id', COALESCE(st.objective_id, ''),
                              'grade', st.grade)
      INTO j FROM v_classification_standing st
     WHERE st.period = p AND st.scope = subj_id;
  ELSIF subj = 'FACILITY' THEN
    SELECT jsonb_build_object('name', f.name, 'usable_sqft', f.usable_sqft,
                              'rentable_sqft', f.rentable_sqft,
                              'owned', f.owned, 'address', f.address,
                              'landlord', f.landlord)
      INTO j FROM facility f
     WHERE f.facility_id = subj_id AND f.period = p;
  ELSIF subj = 'SPACE_UNIT' THEN
    SELECT jsonb_build_object('facility_id', u.facility_id, 'label', u.label,
                              'usable_sqft', u.usable_sqft, 'use', u.use,
                              'status', u.status,
                              'objective_id', COALESCE(u.objective_id, ''),
                              'occupant', u.occupant, 'floor', u.floor)
      INTO j FROM space_unit u
     WHERE u.unit_id = subj_id AND u.period = p;
  ELSIF subj = 'ASSET_FUNDING' THEN
    -- Keyed on the source being proposed, because adding a second source to
    -- an asset is a change even where the first is unchanged.
    SELECT jsonb_build_object('kind', af.kind, 'amount', af.amount,
                              'award_reference', af.award_reference,
                              'funder', af.funder)
      INTO j FROM asset_funding af
     WHERE af.asset_id = subj_id;
    IF NOT EXISTS (SELECT 1 FROM asset a
                    WHERE a.asset_id = subj_id AND a.period = p) THEN
      j := NULL;
    END IF;
  END IF;
  RETURN j;
END;
$$ LANGUAGE plpgsql STABLE;

-- Two values are the same where they are numerically equal, or equal as text.
-- "5400" and "5400.00" are one square footage, and a proposal that only
-- restates the record is not a recommendation however it was spelled.
CREATE OR REPLACE FUNCTION same_value(a text, b text) RETURNS boolean AS $$
BEGIN
  BEGIN
    RETURN a::numeric = b::numeric;
  EXCEPTION WHEN others THEN
    RETURN COALESCE(a, '') = COALESCE(b, '');
  END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION recommendation_proposes_a_change_fn() RETURNS trigger AS $$
DECLARE cur jsonb; k text; v text; c text;
BEGIN
  IF NEW.disposition <> 'OPEN' THEN RETURN NEW; END IF;
  cur := subject_current(NEW.subject, NEW.subject_id, NEW.period);
  IF cur IS NULL THEN RETURN NEW; END IF;
  FOR k, v IN SELECT key, value FROM jsonb_each_text(NEW.proposal) LOOP
    c := cur->>k;
    IF c IS NULL OR NOT same_value(v, c) THEN RETURN NEW; END IF;
  END LOOP;
  RAISE EXCEPTION 'that is what the record already says. A recommendation has '
                  'to propose a change; to say you agree with it, write a note.'
    USING ERRCODE = 'raise_exception';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS recommendation_is_a_change ON recommendation;
CREATE TRIGGER recommendation_is_a_change
  BEFORE INSERT ON recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_proposes_a_change_fn();

-- --------------------------------------------------------- the notes ------

DO $$ BEGIN
  ALTER TABLE classification_note RENAME TO record_note;
EXCEPTION WHEN undefined_table THEN NULL; END $$;

ALTER TABLE record_note
  ADD COLUMN IF NOT EXISTS subject recommendation_subject
      NOT NULL DEFAULT 'CLASSIFICATION';

-- `scope` was the classification group key and is now one subject's id among
-- four. Renamed rather than duplicated: a second column holding the same fact
-- is how the two come apart.
DO $$ BEGIN
  ALTER TABLE record_note RENAME COLUMN scope TO subject_id;
EXCEPTION WHEN undefined_column THEN NULL; END $$;

DROP INDEX IF EXISTS classification_note_scope;
CREATE INDEX IF NOT EXISTS record_note_subject
  ON record_note (period, subject, subject_id);

COMMENT ON TABLE record_note IS
'A note against one subject of the cost record — a classification group, a '
'building, a space, an asset''s funding. Two kinds, and the kind is the '
'visibility: a RECORD note travels in the audit package and a WORKING note '
'does not, while the count of both is disclosed to every reader.';

-- The append-only trigger named the old column.
CREATE OR REPLACE FUNCTION note_body_is_written_once() RETURNS trigger AS $$
BEGIN
  IF NEW.body IS DISTINCT FROM OLD.body
     OR NEW.written_by IS DISTINCT FROM OLD.written_by
     OR NEW.subject IS DISTINCT FROM OLD.subject
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id THEN
    RAISE EXCEPTION 'a note is not edited. Write another one; both stand, and '
                    'the record shows the order they were written in.'
      USING ERRCODE = 'raise_exception';
  END IF;
  IF NEW.kind IS DISTINCT FROM OLD.kind
     AND NEW.redesignated_at IS NOT DISTINCT FROM OLD.redesignated_at THEN
    RAISE EXCEPTION 'changing what a note discloses is an act. Record who did '
                    'it and why.' USING ERRCODE = 'raise_exception';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------- the rows 083 already held ----

-- `083` shipped one commit ago and its register is superseded rather than
-- edited, which is this system's own model of change. The rows move across
-- with their disposition and their reasons intact; nothing is rewritten.
-- Guarded on the table still being there, so the file can be replayed. `083`
-- learned this one file ago: a migration that cannot be applied twice fails
-- the first time somebody replays it.
DO $migrate$ BEGIN
IF to_regclass('public.reclass_recommendation') IS NOT NULL THEN
INSERT INTO recommendation
    (rec_id, period, subject, subject_id, proposal, note, recommended_by,
     recommended_at, saw, disposition, disposed_by, disposed_at,
     disposition_reason, result_id)
SELECT r.rec_id, r.period, 'CLASSIFICATION', r.scope,
       jsonb_strip_nulls(jsonb_build_object(
           'pool', r.pool::text, 'function_990', r.function_990::text,
           'federal', r.federal::text, 'objective_id', r.objective_id)),
       r.note, r.recommended_by, r.recommended_at, r.saw_decision::text,
       r.disposition, r.disposed_by, r.disposed_at, r.disposition_reason,
       r.resulting_decision::text
  FROM reclass_recommendation r
 WHERE NOT EXISTS (SELECT 1 FROM recommendation x WHERE x.rec_id = r.rec_id);
END IF; END $migrate$;

-- Three views read the table on the way out. They are lifted from the
-- definition in force and recreated at the foot of this file — `070` records
-- what retyping one costs.
DROP VIEW IF EXISTS v_worklist_covered;
DROP VIEW IF EXISTS v_worklist_owned;
DROP VIEW IF EXISTS v_worklist_extra;
DROP VIEW IF EXISTS v_controller_review;

-- The notes CTE now has three other subjects to ignore. Without the filter a
-- note against a building would count against a classification group that
-- happened to share its id — unlikely on these keys and wrong in principle,
-- which is the same thing one refactor later.
CREATE OR REPLACE VIEW v_classification_standing AS
WITH live AS (
         SELECT d.decision_id,
            d.scope,
            s.period,
            d.pool,
            d.function_990,
            d.federal,
            d.objective_id,
            d.grade,
            d.rationale,
            d.citation,
            d.decided_by,
            d.decided_at,
            d.origin
           FROM decision d
             JOIN decision_set s ON s.set_id = d.set_id
          WHERE d.reversed_at IS NULL
        ), grp AS (
         SELECT DISTINCT ON (dl.decision_id) dl.decision_id,
            l_1.account,
            l_1.payee
           FROM decision_line dl
             JOIN ledger_line l_1 ON l_1.line_id = dl.line_id
          WHERE dl.live
        ), conf AS (
         SELECT v_position_confirmed.decision_id,
            v_position_confirmed.confirmed_by,
            v_position_confirmed.confirmed_at,
            v_position_confirmed.note
           FROM v_position_confirmed
          WHERE v_position_confirmed.live
        ), notes AS (
         SELECT record_note.period,
            record_note.subject_id AS scope,
            count(*) FILTER (WHERE record_note.kind = 'RECORD'::note_kind) AS record_notes,
            count(*) FILTER (WHERE record_note.kind = 'WORKING'::note_kind) AS working_notes,
            max(record_note.written_at) AS last_note_at
           FROM record_note
          WHERE record_note.subject = 'CLASSIFICATION'::recommendation_subject
          GROUP BY record_note.period, record_note.subject_id
        ), recs AS (
         SELECT recommendation.period,
            recommendation.subject_id AS scope,
            count(*) FILTER (WHERE recommendation.disposition = 'OPEN'::text) AS open_recs,
            count(*) FILTER (WHERE recommendation.disposition = 'ACCEPTED'::text) AS accepted_recs,
            count(*) FILTER (WHERE recommendation.disposition = 'DECLINED'::text) AS declined_recs
           FROM recommendation
          WHERE recommendation.subject = 'CLASSIFICATION'::recommendation_subject
          GROUP BY recommendation.period, recommendation.subject_id
        )
 SELECT l.period,
    l.scope,
    g.account,
    COALESCE(g.payee, ''::text) AS payee,
    l.decision_id,
    l.pool,
    l.function_990,
    l.federal,
    l.objective_id,
    l.grade,
    l.rationale,
    l.citation,
    l.decided_by,
    l.decided_at,
    l.origin,
    l.origin = 'MACHINE_PROPOSAL'::decision_origin AS is_working_position,
    c.confirmed_by,
    c.confirmed_at,
    c.note AS confirmation_note,
    l.origin = 'CONTROLLER'::decision_origin OR c.confirmed_at IS NOT NULL AS adopted,
    COALESCE(n.record_notes, 0::bigint) AS record_notes,
    COALESCE(n.working_notes, 0::bigint) AS working_notes,
    n.last_note_at,
    COALESCE(r.open_recs, 0::bigint) AS open_recommendations,
    COALESCE(r.accepted_recs, 0::bigint) AS accepted_recommendations,
    COALESCE(r.declined_recs, 0::bigint) AS declined_recommendations
   FROM live l
     LEFT JOIN grp g ON g.decision_id = l.decision_id
     LEFT JOIN conf c ON c.decision_id = l.decision_id
     LEFT JOIN notes n ON n.period = l.period AND n.scope = l.scope
     LEFT JOIN recs r ON r.period = l.period AND r.scope = l.scope;

-- The old register has no readers left.
DROP TABLE IF EXISTS reclass_recommendation;

-- ------------------------------------------------------------- reading ----

CREATE OR REPLACE VIEW v_recommendation AS
SELECT r.rec_id, r.period, r.subject, r.subject_id, r.proposal, r.note,
       a.display_name AS raised_by, r.recommended_by AS raised_by_actor,
       r.recommended_at AS raised_at, r.disposition,
       d.display_name AS disposed_by, r.disposed_at, r.disposition_reason,
       r.result_id,
       subject_current(r.subject, r.subject_id, r.period) AS current,
       subject_digest(r.subject, r.subject_id, r.period)
         IS NOT DISTINCT FROM r.saw                       AS still_agrees,
       subject_current(r.subject, r.subject_id, r.period) IS NULL AS is_new,
       -- Appended, not inserted. CREATE OR REPLACE VIEW may add a column at
       -- the end and may not move one, so a tidier position for this costs a
       -- DROP — and two views read this one, so a DROP cascades. The column
       -- order of a view is not worth a cascade.
       subject_merged(r.subject, r.subject_id, r.period, r.proposal) AS merged
  FROM recommendation r
  JOIN actor a ON a.actor_id = r.recommended_by
  LEFT JOIN actor d ON d.actor_id = r.disposed_by;

COMMENT ON VIEW v_recommendation IS
'Every recommendation with the record beside it: what is there now, whether '
'that has moved since the recommendation was written, and whether the row '
'exists at all.';

-- A human name for whatever a recommendation is about, read from the register
-- that owns it rather than stored on the recommendation. A label copied at
-- the moment of writing is a second copy of a fact, free to go stale.
CREATE OR REPLACE VIEW v_subject_label AS
SELECT 'CLASSIFICATION'::recommendation_subject AS subject,
       st.period, st.scope AS subject_id,
       st.account AS title,
       NULLIF(st.payee, '') AS detail
  FROM v_classification_standing st
UNION ALL
SELECT 'FACILITY', f.period, f.facility_id, f.name,
       NULLIF(f.address, '')
  FROM facility f
UNION ALL
SELECT 'SPACE_UNIT', u.period, u.unit_id, u.label,
       f.name || ' · ' || u.use::text
  FROM space_unit u JOIN facility f ON f.facility_id = u.facility_id
UNION ALL
SELECT 'ASSET_FUNDING', a.period, a.asset_id, a.description,
       NULLIF(a.serial_number, '')
  FROM asset a;

CREATE OR REPLACE VIEW v_controller_review AS
SELECT r.period,
       'RECOMMENDATION'::text  AS item,
       r.rec_id::text          AS item_id,
       r.subject::text         AS subject,
       r.subject_id,
       -- A proposal for a row that does not exist yet has no label in any
       -- register, so it falls back to what the proposal calls itself and
       -- then to the id. "Not on the record" must never read as blank.
       COALESCE(l.title, r.proposal->>'name', r.proposal->>'label',
                r.proposal->>'description', r.subject_id) AS title,
       l.detail,
       r.raised_by,
       r.raised_at,
       r.note,
       r.proposal,
       r.current,
       r.still_agrees,
       r.is_new,
       NULL::uuid              AS decision_id
  FROM v_recommendation r
  LEFT JOIN v_subject_label l
         ON l.subject = r.subject AND l.period = r.period
        AND l.subject_id = r.subject_id
 WHERE r.disposition = 'OPEN'
UNION ALL
SELECT st.period,
       'UNCONFIRMED',
       st.decision_id::text,
       'CLASSIFICATION',
       st.scope,
       st.account,
       NULLIF(st.payee, ''),
       st.decided_by,
       st.decided_at,
       st.rationale,
       jsonb_build_object('pool', st.pool::text,
                          'function_990', st.function_990::text,
                          'federal', st.federal::text,
                          'objective_id', COALESCE(st.objective_id, '')),
       jsonb_build_object('pool', st.pool::text,
                          'function_990', st.function_990::text,
                          'federal', st.federal::text,
                          'objective_id', COALESCE(st.objective_id, '')),
       true,
       false,
       st.decision_id
  FROM v_classification_standing st
 WHERE st.is_working_position AND NOT st.adopted;

COMMENT ON VIEW v_controller_review IS
'The controller''s one list: every working position nobody has adopted, and '
'every open recommendation anybody has raised about any part of the cost '
'record, with the proposal beside what is there now so the comparison is on '
'the page rather than in his head.';


-- ------------------------------------------------------- on the worklist ---
--
-- **One kind, not three.** `083` added `RECLASS_RECOMMENDED`; the obvious
-- extension is `SPACE_RECOMMENDED` and `ASSET_RECOMMENDED` beside it, and
-- that would be three kinds with one owner and one destination — three copies
-- of one fact, in the map this repository has already been wrong about four
-- times in one run. What differs between them is the *subject*, which is on
-- the row. `RECOMMENDATION_OPEN` replaces it, and
-- `tests/test_worklist_labels.py` fails a kind the one map does not describe.

CREATE VIEW v_worklist_extra AS
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
    'A working position a script proposed and nobody has adopted. It is '::text || 'classified, and it is not yet anybody''s judgment.'::text AS detail
   FROM v_classification_standing st
  WHERE st.is_working_position AND NOT st.adopted
UNION ALL
 SELECT 'RECOMMENDATION_OPEN'::text AS kind,
    'HIGH'::text AS severity,
    r.period,
    r.title AS label,
    'recommendation'::text AS entity,
    r.item_id AS entity_id,
    NULL::numeric AS amount,
    (r.raised_by || ' recommends a change to ' || lower(replace(r.subject, '_', ' ')) || ': ' || r.note)::text AS detail
   FROM v_controller_review r
  WHERE r.item = 'RECOMMENDATION'::text;

CREATE VIEW v_worklist_owned AS
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
            WHEN 'RECOMMENDATION_OPEN'::text THEN 'CONTROLLER'::text
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
            WHEN 'RECOMMENDATION_OPEN'::text THEN '/classify/review'::text
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
            WHEN 'RECOMMENDATION_OPEN'::text THEN 'audit'::text
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

CREATE VIEW v_worklist_covered AS
SELECT w.kind,
    w.severity,
    w.period,
    w.label,
    w.entity,
    w.entity_id,
    w.amount,
    w.detail,
    w.owner_portfolio,
    w.goes_to,
    t.todo_id,
    t.assignee,
    t.due_on,
    t.status AS todo_status,
    t.todo_id IS NOT NULL AS taken,
    t.todo_id IS NOT NULL AND t.assignee IS NULL AS taken_by_nobody,
    t.opened_by
   FROM v_worklist_owned w
     LEFT JOIN LATERAL ( SELECT tt.todo_id,
            who.display_name AS assignee,
            tt.due_on,
            tt.status,
            tt.opened_by
           FROM todo tt
             LEFT JOIN actor who ON who.actor_id = tt.assignee_actor
          WHERE tt.worklist_kind = w.kind AND tt.worklist_entity_id = w.entity_id AND tt.period = w.period AND tt.status <> 'DONE'::text
          ORDER BY tt.opened_at DESC
         LIMIT 1) t ON true;


-- ------------------------------------ the walk speaks its own language ----
--
-- Step 4 read `v_partition_coverage.state` straight through, and that view's
-- vocabulary is the control register's — **TIES**, OPEN, NO DATA. The walk's
-- is DONE, OPEN, NO DATA, WAITING. Nobody had ever seen the difference,
-- because with no building on the record the partition was NO DATA in every
-- run there has ever been; the first square footage anybody entered made the
-- walk print a word nothing on the screen renders.
--
-- Found by `tests/test_the_walk.py`, which asserts the four states against the
-- view rather than against a list of its own — so the moment a fifth appeared
-- it failed, on a change three files away from the walk.

DROP VIEW v_audit_walk;

CREATE VIEW v_audit_walk AS
WITH period AS (
         SELECT fiscal_period.period
           FROM fiscal_period
        ), ledger AS (
         SELECT p.period,
            ( SELECT count(*) AS count
                   FROM ledger_line l
                  WHERE l.period = p.period) AS lines
           FROM period p
        ), recon AS (
         SELECT p.period,
            count(r.*) AS points,
            count(r.*) FILTER (WHERE r.ties) AS tying,
            count(r.*) FILTER (WHERE r.state = 'NO DATA'::text) AS blind
           FROM period p
             LEFT JOIN v_statement_reconciliation r ON r.period = p.period
          GROUP BY p.period
        ), cover AS (
         SELECT p.period,
            c.groups_total,
            c.groups_decided,
            c.scope_dollars,
            c.classified,
            c.unclassified,
            c.pct_dollars_covered
           FROM period p
             LEFT JOIN v_classification_coverage c ON c.period = p.period
        ), part AS (
         SELECT p.period,
            max(pc.state) FILTER (WHERE pc.partition = 'SPACE'::text) AS space_state,
            max(pc.needs) FILTER (WHERE pc.partition = 'SPACE'::text) AS space_needs,
            max(pc.state) FILTER (WHERE pc.partition = 'ASSETS'::text) AS asset_state,
            max(pc.needs) FILTER (WHERE pc.partition = 'ASSETS'::text) AS asset_needs
           FROM period p
             LEFT JOIN v_partition_coverage pc ON pc.period = p.period
          GROUP BY p.period
        ), adopt AS (
         SELECT p.period,
            count(*) FILTER (WHERE st.is_working_position AND NOT st.adopted) AS unadopted
           FROM period p
             LEFT JOIN v_classification_standing st ON st.period = p.period
          GROUP BY p.period
        ), cited AS (
         SELECT ds.period,
            count(DISTINCT d.decision_id) FILTER (WHERE d.federal = ANY (ARRAY['ALLOWABLE'::federal_treatment, 'PENDING'::federal_treatment])) AS live,
            count(DISTINCT de.decision_id) FILTER (WHERE d.federal = ANY (ARRAY['ALLOWABLE'::federal_treatment, 'PENDING'::federal_treatment])) AS with_citation,
            count(DISTINCT d.decision_id) AS all_live
           FROM decision d
             JOIN decision_set ds ON ds.set_id = d.set_id
             LEFT JOIN decision_evidence de ON de.decision_id = d.decision_id
          WHERE d.reversed_at IS NULL
          GROUP BY ds.period
        ), sealed AS (
         SELECT p.period,
            bool_or(ds.sealed_at IS NOT NULL) AS is_sealed,
            max(ds.sealed_at) AS at,
            max("left"(ds.seal_hash, 12)) AS hash
           FROM period p
             LEFT JOIN decision_set ds ON ds.period = p.period
          GROUP BY p.period
        ), rated AS (
         SELECT p.period,
            count(r.*) FILTER (WHERE r.status <> 'SUPERSEDED'::text) AS live,
            max(r.rate) FILTER (WHERE r.kind = 'INDIRECT_COMBINED'::text AND r.status <> 'SUPERSEDED'::text) AS combined,
            max(r.admin_labour_basis) FILTER (WHERE r.status <> 'SUPERSEDED'::text) AS basis
           FROM period p
             LEFT JOIN rate r ON r.period = p.period
          GROUP BY p.period
        ), restated AS (
         SELECT p.period,
            count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED'::restatement_status) AS standing
           FROM period p
             LEFT JOIN restatement rs ON rs.period = p.period
          GROUP BY p.period
        )
 SELECT period,
    seq,
    step,
    key,
    what,
    state,
    detail,
    goes_to
   FROM ( SELECT l.period,
            1 AS seq,
            'The books are in'::text AS step,
            'LEDGER'::text AS key,
            'The QuickBooks exports, as received'::text AS what,
                CASE
                    WHEN l.lines = 0 THEN 'NO DATA'::text
                    ELSE 'DONE'::text
                END AS state,
                CASE
                    WHEN l.lines = 0 THEN 'No ledger has been loaded for this period.'::text
                    ELSE to_char(l.lines, 'FM999,999,999'::text) || ' general-ledger lines on file.'::text
                END AS detail,
            '/books/import'::text AS goes_to
           FROM ledger l
        UNION ALL
         SELECT r.period,
            2,
            'The books agree with themselves'::text AS text,
            'RECONCILE'::text AS text,
            'Ledger, profit and loss, balance sheet, payroll register'::text AS text,
                CASE
                    WHEN r.points = 0 THEN 'NO DATA'::text
                    WHEN r.blind > 0 THEN 'NO DATA'::text
                    WHEN r.tying = r.points THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN r.points = 0 THEN 'No control has been evaluated.'::text
                    WHEN r.blind > 0 THEN (((r.blind || ' of '::text) || r.points) || ' points cannot be '::text) || 'evaluated, which is not the same as tying.'::text
                    ELSE (((r.tying || ' of '::text) || r.points) || ' cross-reference '::text) || 'points tie. A rate is refused while any is open.'::text
                END AS "case",
            '/books'::text AS text
           FROM recon r
        UNION ALL
         SELECT c.period,
            3,
            'Every cost judged'::text AS text,
            'CLASSIFY'::text AS text,
            'The profit and loss, less income, into 2 CFR 200 pools'::text AS text,
                CASE
                    WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'NO DATA'::text
                    WHEN c.unclassified = 0::numeric AND COALESCE(ad.unadopted, 0::bigint) = 0 THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'There is no cost to classify yet.'::text
                    WHEN c.unclassified > 0::numeric THEN ((((to_char(c.groups_decided, 'FM999,999'::text) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' groups, '::text) || c.pct_dollars_covered) || '% of dollars.'::text
                    WHEN COALESCE(ad.unadopted, 0::bigint) > 0 THEN (((('Every group carries a position. '::text || to_char(ad.unadopted, 'FM999,999'::text)) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' are working positions a script proposed and nobody '::text) || 'has adopted — classified, and not yet a judgment.'::text
                    ELSE ((((to_char(c.groups_decided, 'FM999,999'::text) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' groups, '::text) || c.pct_dollars_covered) || '% of dollars.'::text
                END AS "case",
            '/classify'::text AS text
           FROM cover c
             LEFT JOIN adopt ad ON ad.period = c.period
        UNION ALL
         SELECT pt.period,
            4,
            'Every square foot accounted for'::text AS text,
            'SPACE'::text AS text,
            'Each building, into tenant, programme and vacant space'::text AS text,
            CASE COALESCE(pt.space_state, 'NO DATA'::text) WHEN 'TIES'::text THEN 'DONE'::text ELSE COALESCE(pt.space_state, 'NO DATA'::text) END AS "coalesce",
                CASE
                    WHEN CASE COALESCE(pt.space_state, 'NO DATA'::text) WHEN 'TIES'::text THEN 'DONE'::text ELSE COALESCE(pt.space_state, 'NO DATA'::text) END = 'NO DATA'::text THEN ((('Needs '::text || COALESCE(pt.space_needs, 'the square footage'::text)) || '. Until it lands the 200.465 carve-out cannot be '::text) || 'computed at all, and every dollar of tenant and '::text) || 'vacant occupancy cost sits in the federal pool.'::text
                    ELSE 'The space accounts for itself.'::text
                END AS "case",
            '/classify/space'::text AS text
           FROM part pt
        UNION ALL
         SELECT pt.period,
            5,
            'Every asset''s funding source'::text AS text,
            'ASSETS'::text AS text,
            'The fixed-asset register, into funding sources'::text AS text,
            CASE COALESCE(pt.asset_state, 'NO DATA'::text) WHEN 'TIES'::text THEN 'DONE'::text ELSE COALESCE(pt.asset_state, 'NO DATA'::text) END AS "coalesce",
                CASE
                    WHEN CASE COALESCE(pt.asset_state, 'NO DATA'::text) WHEN 'TIES'::text THEN 'DONE'::text ELSE COALESCE(pt.asset_state, 'NO DATA'::text) END = 'NO DATA'::text THEN ((('Needs '::text || COALESCE(pt.asset_needs, 'the asset register'::text)) || '. 200.436(b) makes depreciation on a federally '::text) || 'funded asset unallowable and the schedule has no '::text) || 'such column, which 200.313(d)(1) requires.'::text
                    ELSE 'Every asset names where its money came from.'::text
                END AS "case",
            '/classify/assets'::text AS text
           FROM part pt
        UNION ALL
         SELECT c.period,
            6,
            'The paper behind the judgments'::text AS text,
            'EVIDENCE'::text AS text,
            'A judgment that cites the document it rests on'::text AS text,
                CASE
                    WHEN COALESCE(ct.all_live, 0::bigint) = 0 THEN 'WAITING'::text
                    WHEN COALESCE(ct.live, 0::bigint) = 0 THEN 'DONE'::text
                    WHEN ct.with_citation = ct.live THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(ct.all_live, 0::bigint) = 0 THEN 'Nothing has been judged yet, so there is nothing to cite.'::text
                    WHEN COALESCE(ct.live, 0::bigint) = 0 THEN 'No judgment is federally chargeable, so none needs a '::text || 'citation for 2 CFR 200.'::text
                    ELSE ((((((to_char(COALESCE(ct.with_citation, 0::bigint), 'FM999,999'::text) || ' of '::text) || to_char(ct.live, 'FM999,999'::text)) || ' federally chargeable judgments cite a document, of '::text) || to_char(ct.all_live, 'FM999,999'::text)) || ' live. '::text) || 'Attaching is not citing: a citation is why the '::text) || 'judgment was made, and it is what VERIFIED requires.'::text
                END AS "case",
            '/evidence'::text AS text
           FROM cover c
             LEFT JOIN cited ct ON ct.period = c.period
        UNION ALL
         SELECT s.period,
            7,
            'The classifications sealed'::text AS text,
            'SEAL'::text AS text,
            'Hashed across every judgment, before any rate exists'::text AS text,
                CASE
                    WHEN s.is_sealed THEN 'DONE'::text
                    WHEN COALESCE(c.unclassified, 1::numeric) <> 0::numeric THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN s.is_sealed THEN ((('Sealed '::text || to_char(s.at, 'DD Mon YYYY'::text)) || ' · '::text) || s.hash) || '…'::text
                    WHEN COALESCE(c.unclassified, 1::numeric) <> 0::numeric THEN ('Cost is still outstanding. Sealing an incomplete set '::text || 'is allowed and makes the rate read high, which is '::text) || 'the honest direction to err.'::text
                    ELSE ('Every group is judged. Sealing is the assertion that '::text || 'the rate was not reverse-engineered, and it is '::text) || 'yours to make.'::text
                END AS "case",
            '/review/rate'::text AS text
           FROM sealed s
             LEFT JOIN cover c ON c.period = s.period
        UNION ALL
         SELECT rt.period,
            8,
            'The rate computed'::text AS text,
            'RATE'::text AS text,
            'A pool over a base, carrying the seal'::text AS text,
                CASE
                    WHEN COALESCE(rt.live, 0::bigint) > 0 THEN 'DONE'::text
                    WHEN NOT COALESCE(s.is_sealed, false) THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(rt.live, 0::bigint) > 0 THEN ((('Indirect, combined: '::text || round(rt.combined * 100::numeric, 2)) || '% on the '::text) || rt.basis) || ' basis.'::text
                    WHEN NOT COALESCE(s.is_sealed, false) THEN 'No rate can exist until the set is sealed — the '::text || 'database refuses one whose seal does not match.'::text
                    ELSE 'The set is sealed. Computing is arithmetic from here.'::text
                END AS "case",
            '/review/rate'::text AS text
           FROM rated rt
             LEFT JOIN sealed s ON s.period = rt.period
        UNION ALL
         SELECT rt.period,
            9,
            'The rate certified'::text AS text,
            'CERTIFY'::text AS text,
            'The controller''s signature on the build-up'::text AS text,
                CASE
                    WHEN cert.certified THEN 'DONE'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN cert.certified THEN (((('Signed by '::text || cert.certified_by) || ' on '::text) || to_char(cert.certified_at, 'DD Mon YYYY'::text)) || '. '::text) || 'Anything issued from here says so.'::text
                    ELSE (COALESCE(cert.why_not, 'Nobody has signed the rate.'::text) || ' Nothing is blocked by this — an invoice or a '::text) || 'workbook produced now simply carries NOT CERTIFIED.'::text
                END AS "case",
            '/review/rate'::text AS text
           FROM rated rt
             LEFT JOIN v_rate_certified cert ON cert.period = rt.period
        UNION ALL
         SELECT rs.period,
            10,
            'The position on each invoice'::text AS text,
            'RESTATE'::text AS text,
            'What was billed, against what the rate supports'::text AS text,
                CASE
                    WHEN COALESCE(rs.standing, 0::bigint) > 0 THEN 'DONE'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(rs.standing, 0::bigint) > 0 THEN ((rs.standing || ' restatement(s) standing as a claim. '::text) || 'Everything is PROPOSED until a sponsor says '::text) || 'otherwise in writing.'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'Needs a rate to measure against.'::text
                    ELSE 'Nothing has been put to a sponsor yet.'::text
                END AS "case",
            '/restate'::text AS text
           FROM restated rs
             LEFT JOIN rated rt ON rt.period = rs.period
        UNION ALL
         SELECT p.period,
            11,
            'The papers that leave the building'::text AS text,
            'REPORT'::text AS text,
            'The auditor''s report, Form 990, the workbooks'::text AS text,
            'DONE'::text AS text,
            ('Read from the rows they were recorded in. Each states what is '::text || 'unfinished above its figures, and the workbooks repeat it on '::text) || 'the first sheet because a workbook travels.'::text,
            '/reports'::text AS text
           FROM period p) w
  ORDER BY period, seq;

COMMENT ON VIEW v_audit_walk IS
'The 2025 audit as the one ordered journey it is, eleven steps, each reading '
'the view that already owns its figure. WAITING is a step whose predecessor is '
'not done — printing it as OPEN would offer work the system would refuse. '
'Step 3 is done when every dollar is judged and every working position has '
'been adopted; those are two questions and one of them is about a person.';
