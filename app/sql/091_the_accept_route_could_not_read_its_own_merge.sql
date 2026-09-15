-- 091 — v_recommendation lost the column the accept route reads
--
-- `POST /api/positions/recommendations/{id}/accept` answers **500 on every
-- FACILITY, SPACE_UNIT and ASSET_FUNDING recommendation** on every database
-- that has been running since `084`. `_merged(rec)` reads `rec["merged"]`,
-- `v_recommendation` has no such column, the dict comes back empty, and the
-- handler raises `KeyError: 'usable_sqft'`.
--
-- `084` declares the column. The deployed view does not have it, on the
-- reference record, on the publication clone and on the exam clone alike —
-- which can only mean the column was appended to `084` **after `084` had
-- already run**, and this repository has the lesson written down in as many
-- words:
--
--     Editing an applied migration file mutates nothing. Two of my four
--     mutation tests reported "no findings" because the change never reached
--     the database: the runner had already recorded `082` and skipped it.
--
-- It is worse here than in a mutation test, because the file and the comment
-- beside it both read as though the fix had shipped. `084`'s own comment
-- explains why the column is *appended* rather than inserted — "CREATE OR
-- REPLACE VIEW may add a column at the end and may not move one" — so the
-- author knew the constraint, wrote for it, and edited a file the runner was
-- never going to look at again.
--
-- Nothing caught it because the whole class was invisible: `pytest` builds
-- from the migrations, so CI has the column and every test passes, and
-- `drive_partitions` had not been run against a long-lived database since.
-- **A test that builds its own schema cannot see a schema that has drifted
-- from it.** `tests/test_the_schema_matches_the_migrations.py` is the other
-- half: it applies every migration to a scratch database and compares the
-- columns, so an edit to an applied file fails there instead of 500ing in
-- front of the controller.
--
-- Four objects drifted, not one: `enum_or_refuse` and `subject_merged` are
-- absent altogether, `recommendation_is_well_formed` is the older body that
-- validates the proposal rather than the merge, and the view is missing
-- `merged`. All four are lifted from `084` unchanged rather than retyped —
-- `070` records what retyping a definition costs — and every one of them is
-- `CREATE OR REPLACE`, so this is safe on a database that already has them.

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
  'Every recommendation with what the record says now, whether it has been '
  'overtaken, and what accepting it would write. `merged` is what the accept '
  'handler reads and what the validation trigger checks, so neither holds its '
  'own opinion about what a partial proposal means — it was declared in 084 '
  'after 084 had been applied, so it reached no running database and every '
  'FACILITY, SPACE_UNIT and ASSET_FUNDING accept answered 500 until 091.';

DROP TRIGGER IF EXISTS recommendation_well_formed ON recommendation;
CREATE TRIGGER recommendation_well_formed
  BEFORE INSERT OR UPDATE OF proposal ON recommendation
  FOR EACH ROW EXECUTE FUNCTION recommendation_is_well_formed();
