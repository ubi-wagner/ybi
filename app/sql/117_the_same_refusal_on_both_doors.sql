-- 117 — The same refusal on both doors.
--
-- `116` put `unit_paid_program_names_its_agreement` on `space_unit`: space
-- somebody is charged rent for and which is nonetheless called programme
-- space has to name the agreement that says so. A tenancy reaching the
-- register through `PUT /api/facilities/space` meets it.
--
-- A tenancy reaching it through a **recommendation** would not, until the
-- moment Tom pressed Accept — which is `084`'s defect exactly: *a
-- recommendation the server would refuse is a screen offering what the API
-- will not take*, and that shipped once on twenty-four accounts. Worse here,
-- because the accept runs the dispatch: Heidi would be told her proposal was
-- fine and Tom would meet a raw constraint violation with her name on it.
--
-- So the validator asks the same question, of the **merged** row rather than
-- of the proposal — a proposal naming only `use` is laid over the tenancy
-- that is there, and whether that tenancy is charged for is on the row and
-- not in the proposal. `subject_current` therefore has to carry the two
-- columns the rule reads; it carried neither.
--
-- Both bodies are **lifted from the definitions in force** rather than
-- retyped. `070` records what retyping costs: a view rebuilt from the first
-- migration that declared it rather than the one that last changed it.

CREATE OR REPLACE FUNCTION public.subject_current(subj recommendation_subject, subj_id text, p text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
AS $function$
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
                              'occupant', u.occupant, 'floor', u.floor,
                              'actual_annual_charge',
                                COALESCE(u.actual_annual_charge, 0),
                              'occupancy_basis', u.occupancy_basis)
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
$function$;

CREATE OR REPLACE FUNCTION public.recommendation_is_well_formed()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
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
    IF use_v = 'PROGRAM'
       AND COALESCE((p->>'actual_annual_charge')::numeric, 0) > 0
       AND length(btrim(COALESCE(p->>'occupancy_basis', ''))) <= 10 THEN
      RAISE EXCEPTION 'space somebody is charged for and which is called '
                      'programme space names the agreement that says so — a '
                      'lease, or an incubation or residency agreement. This '
                      'is the reading that moves the rate, so it does not '
                      'rest on nobody''s document.'
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
$function$;
