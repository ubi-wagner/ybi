-- 121 · The door the 200.331 register never had.
--
-- `115` opened a determination for every party the 200.1 cap could bite and
-- said, in its own words, that the register would be *"recorded with the route
-- and screen it stands in for"*. That route and that screen were never built.
-- So six determinations worth **$313,605.35 of MTDC** were answerable only by
-- somebody writing SQL against the table — which is the capability-with-no-door
-- shape this repository has now paid for five times: the restatement had five
-- complete routes and no page, the timesheet draft had two and no card, the
-- lane comparison had an API that could only answer zeroes, and
-- `POST /api/rates/compute` was called by nothing in the SPA for the life of
-- the rate engine.
--
-- Three things this migration adds, and the third is the one that matters.
--
-- **The kind on the worklist.** `v_worklist` has always known what is
-- outstanding and `v_worklist_owned` which portfolio can act on it, and an
-- UNDETERMINED party reached neither — so the only place it surfaced was
-- `scripts/readiness.py`, which is a script somebody runs. It is
-- `PARTY_UNDETERMINED`, owned by CONTROLLER because 200.331 turns on the
-- substance of a contractual relationship and that is the controller's
-- judgment, and it goes to `/classify/parties`, which is where the door now
-- is. One kind and not two — `SUBAWARD_OVER_CAP` beside it would be a second
-- copy of one fact, which `084` refused for the same reason.
--
-- **The amount is `at_stake`, not the payment.** The payment is what the
-- party was paid; what is outstanding is the part of it MTDC may or may not
-- take, which is everything above the cap. A worklist row carrying the gross
-- would say $463,605.35 is in question when $313,605.35 is — and the first
-- $25,000 is in the base under either determination, so it is not in question
-- at all.
--
-- **And the entity id is composite, deliberately.** `party_determination` is
-- keyed on (period, objective_id, payee) and there is no surrogate on the
-- worklist side. A group key is an account and a payee joined by a separator
-- elsewhere in this system and that has already cost a URL refusal, so this
-- one is joined by a printable `|` and is never put in a path: the screen
-- takes both halves as query parameters. `060`'s rule holds — the worklist
-- carries no foreign key, because its entity ids are computed and a
-- constraint would have to re-derive the whole view on every insert.

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
  WHERE r.item = 'RECOMMENDATION'::text
UNION ALL
 SELECT 'PARTY_UNDETERMINED'::text AS kind,
    'HIGH'::text AS severity,
    x.period,
    COALESCE(NULLIF(x.payee, ''), '(no payee on the ledger line)') AS label,
    'party_determination'::text AS entity,
    (x.objective_id || '|' || x.payee)::text AS entity_id,
    x.at_stake AS amount,
    ('Paid ' || to_char(x.amount, 'FM999,999,990.00') || ' on ' ||
     x.objective_id || '. 2 CFR 200.1 takes the first 25,000.00 of a '
     '**subaward** into MTDC and a contract for services whole, so '
     || to_char(x.at_stake, 'FM999,999,990.00') || ' of the base turns on '
     'the 200.331 determination. The substance of the relationship governs '
     'and not what the invoice called it.')::text AS detail
   FROM v_subaward_exposure x
  WHERE x.determination = 'UNDETERMINED'::text;

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
            WHEN 'RECOMMENDATION_OPEN'::text THEN 'CONTROLLER'::text
            WHEN 'PARTY_UNDETERMINED'::text THEN 'CONTROLLER'::text
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
            WHEN 'PARTY_UNDETERMINED'::text THEN '/classify/parties'::text
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
            WHEN 'PARTY_UNDETERMINED'::text THEN 'audit'::text
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
