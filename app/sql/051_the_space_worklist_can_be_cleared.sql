-- 051: the space worklist asks a question the space screen can answer.
--
-- `FACILITY_UNPARTITIONED` fired BLOCKING on Tech Block 5 while
-- `v_space_unit_control` reported 5,400 of 5,400 square feet accounted for
-- across three units. Doing the work it demanded could not clear it, because
-- it tested `NOT EXISTS (SELECT 1 FROM space_partition …)` and **nothing in
-- the system has ever written `space_partition`** — not a route, not a
-- script, not a migration. Migration `048` moved the occupancy carve-out off
-- that table for the same reason and said the worklist should follow; this
-- is that.
--
-- A BLOCKING item that cannot be cleared by doing what it asks is worse than
-- no item at all. It teaches the person reading the list that the list is
-- wrong, and the next one they dismiss will be real.
--
-- ── One question, not two ────────────────────────────────────────────
--
-- `FACILITY_UNPARTITIONED` (v_worklist, BLOCKING) and `SPACE_UNATTRIBUTED`
-- (v_worklist_extra, HIGH) asked the same thing. `SPACE_UNATTRIBUTED`
-- survives, because it guards on `usable_sqft > 0` and so reads as the
-- second half of a pair: `SPACE_UNMEASURED` says measure the building,
-- `SPACE_UNATTRIBUTED` says now say who is in it. The other fired on an
-- unmeasured building too, telling somebody to attribute square footage
-- that did not exist yet.
--
-- It keeps the BLOCKING severity rather than the HIGH one. Dropping the
-- stricter of two duplicate items and keeping the looser would be a quiet
-- downgrade, and the severity was right: `v_facility_occupancy` inner-joins
-- to its space totals, so a facility with no units does not appear in it at
-- all and every dollar of its occupancy cost reaches the federal pool
-- unchallenged. That is exactly what 200.465 is about.
--
-- ── And it reads the control, not an EXISTS ──────────────────────────
--
-- `space_partition` carried a deferred constraint trigger — space must
-- account for the facility in full, weighted by months. `space_unit` has no
-- such trigger and cannot have one: units are entered a suite at a time, so
-- a per-transaction constraint would refuse the first of three. The old
-- trigger was also comparing a months-weighted sum against the unweighted
-- usable figure, which would have raised on the record as it stands (4,800
-- weighted against 5,400 usable) — `020` was right to make this a control
-- rather than a constraint, and `v_space_unit_control` keeps the two sums
-- apart.
--
-- So the item reads `NOT c.ties` instead of `NOT EXISTS`. That covers the
-- case the trigger existed for and the EXISTS test never did: one suite
-- entered against a building of three leaves 3,600 sq ft unattributed, and
-- an existence test calls that done.
--
-- ── Two kinds were falling off the end ───────────────────────────────
--
-- Lifting `v_worklist` to edit it showed that `STALE_CERTIFICATION` and
-- `DONATION_RATE_MISSING` are emitted and were routed by neither CASE, so
-- both landed on the `ELSE` — owner CONTROLLER, destination `/`. The test
-- that is supposed to fail exactly this kept its list of kinds by hand, and
-- the hand-kept list was missing the same two. A hand-kept map of what the
-- code does was wrong four times in one run of the system review; it is
-- wrong here too, and the test now derives the kinds from the view.
--
-- `STALE_CERTIFICATION` goes where `NEEDS_CERTIFICATION` goes: a manager
-- cannot re-sign for somebody, so it is a list to go and ask, on
-- `/contracts/people`. `DONATION_RATE_MISSING` is a valuation and belongs to
-- the controller. Its destination is `/timesheet`, where the donated hours
-- are; **nothing in the application writes `donation_rate` yet**, which is
-- recorded in `docs/SWEEP.md` rather than left for somebody to discover by
-- clicking.
--
-- Every view body below is lifted from `pg_get_viewdef` and edited in place.
-- Retyping one from memory silently rewrote how every line of the 990 was
-- categorised once already.

CREATE OR REPLACE VIEW v_worklist AS
 SELECT 'UNCLASSIFIED'::text AS kind,
    'BLOCKING'::text AS severity,
    l.period,
    l.account || COALESCE(NULLIF(' / '::text || l.payee, ' / '::text), ''::text) AS label,
    'ledger_group'::text AS entity,
    (l.account || chr(31)) || COALESCE(l.payee, ''::text) AS entity_id,
    sum(abs(l.amount)) AS amount,
    count(*)::text || ' lines, no decision'::text AS detail
   FROM ledger_line l
     LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
  WHERE l.period = '2025'::text AND l.statement = 'P&L'::text AND dl.line_id IS NULL
  GROUP BY l.period, l.account, l.payee
UNION ALL
 SELECT 'BLOCKS_SEAL'::text AS kind,
    'BLOCKING'::text AS severity,
    '2025'::text AS period,
    d.scope AS label,
    'decision'::text AS entity,
    d.decision_id::text AS entity_id,
    ( SELECT sum(abs(l.amount)) AS sum
           FROM decision_line dl
             JOIN ledger_line l USING (line_id)
          WHERE dl.decision_id = d.decision_id) AS amount,
    'graded '::text || d.grade::text AS detail
   FROM decision d
  WHERE d.reversed_at IS NULL AND (d.grade = ANY (ARRAY['UNSUPPORTED'::evidence_grade, 'TEST_ASSUMPTION'::evidence_grade]))
UNION ALL
 SELECT 'NEEDS_EVIDENCE'::text AS kind,
    'HIGH'::text AS severity,
    '2025'::text AS period,
    d.scope AS label,
    'decision'::text AS entity,
    d.decision_id::text AS entity_id,
    ( SELECT sum(abs(l.amount)) AS sum
           FROM decision_line dl
             JOIN ledger_line l USING (line_id)
          WHERE dl.decision_id = d.decision_id) AS amount,
    'no document cited on the judgment'::text AS detail
   FROM decision d
  WHERE d.reversed_at IS NULL AND (d.federal = ANY (ARRAY['ALLOWABLE'::federal_treatment, 'PENDING'::federal_treatment])) AND NOT (EXISTS ( SELECT 1
           FROM decision_evidence de
          WHERE de.decision_id = d.decision_id))
UNION ALL
 SELECT 'NEEDS_CERTIFICATION'::text AS kind,
    'BLOCKING'::text AS severity,
    c.period,
    COALESCE(NULLIF(c.employee_name, ''::text), c.employee_key) AS label,
    'employee'::text AS entity,
    c.employee_key AS entity_id,
    c.payroll_wages AS amount,
        CASE
            WHEN c.reconstructed THEN 'reconstructed distribution, unsigned'::text
            ELSE 'distribution unsigned'::text
        END AS detail
   FROM v_certification_status c
  WHERE NOT c.certified
UNION ALL
 SELECT 'STALE_CERTIFICATION'::text AS kind,
    'BLOCKING'::text AS severity,
    c.period,
    COALESCE(NULLIF(c.employee_name, ''::text), c.employee_key) AS label,
    'employee'::text AS entity,
    c.employee_key AS entity_id,
    c.payroll_wages AS amount,
    ('signed '::text || to_char(c.signed_at, 'DD Mon YYYY'::text)) || ', distribution changed since'::text AS detail
   FROM v_certification_status c
  WHERE c.certified AND c.stale
UNION ALL
 SELECT 'ASSET_FUNDING_UNKNOWN'::text AS kind,
    'BLOCKING'::text AS severity,
    a.period,
    a.description AS label,
    'asset'::text AS entity,
    a.asset_id AS entity_id,
    a.depreciation AS amount,
    'depreciation currently treated as fully allowable'::text AS detail
   FROM asset a
  WHERE NOT (EXISTS ( SELECT 1
           FROM asset_funding f
          WHERE f.asset_id = a.asset_id))
UNION ALL
 SELECT 'INVOICE_NO_INDIRECT'::text AS kind,
    'HIGH'::text AS severity,
    v.period,
    (('Invoice '::text || COALESCE(v.invoice_number, ''::text)) || ' '::text) || COALESCE(v.objective_id, ''::text) AS label,
    'invoice'::text AS entity,
    v.invoice_id::text AS entity_id,
    v.mtdc_as_billed AS amount,
    'no indirect billed on a base of '::text || v.mtdc_as_billed::text AS detail
   FROM v_invoice_category v
  WHERE v.no_indirect_billed AND v.mtdc_as_billed > 0::numeric
UNION ALL
 SELECT 'INVOICE_NO_AWARD'::text AS kind,
    'MEDIUM'::text AS severity,
    i.period,
    'Invoice '::text || COALESCE(i.invoice_number, i.seq::text) AS label,
    'invoice'::text AS entity,
    i.invoice_id::text AS entity_id,
    i.total AS amount,
    'not linked to an award'::text AS detail
   FROM invoice i
  WHERE i.award_id IS NULL
UNION ALL
 SELECT 'STALE_DECISION'::text AS kind,
    'HIGH'::text AS severity,
    l.period,
    d.scope AS label,
    'decision'::text AS entity,
    d.decision_id::text AS entity_id,
    abs(l.amount) AS amount,
    ('source line '::text || r.change) || ' after the decision'::text AS detail
   FROM ledger_revision r
     JOIN ledger_line l USING (line_id)
     JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
     JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
  WHERE r.detected_at > d.decided_at
UNION ALL
 SELECT 'EMPLOYMENT_UNKNOWN'::text AS kind,
    'HIGH'::text AS severity,
    a.period,
    COALESCE(NULLIF(max(a.employee_name), ''::text), a.employee_key) AS label,
    'employee'::text AS entity,
    a.employee_key AS entity_id,
    max(a.payroll_wages) AS amount,
    'no employment terms recorded, so no timesheet of theirs can be tested'::text AS detail
   FROM labor_allocation a
  WHERE NOT (EXISTS ( SELECT 1
           FROM employment e
          WHERE e.period = a.period AND e.employee_key = a.employee_key AND e.superseded_at IS NULL))
  GROUP BY a.period, a.employee_key
UNION ALL
 SELECT 'DONATION_RATE_MISSING'::text AS kind,
    'MEDIUM'::text AS severity,
    d.period,
    (d.employee_key || ' — '::text) || d.objective_id AS label,
    'employee'::text AS entity,
    d.employee_key AS entity_id,
    d.hours AS amount,
    d.hours::text || ' donated hours with no documented rate'::text AS detail
   FROM v_donated_time d
  WHERE d.rate_missing;;

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
    CASE WHEN c.units = 0
         THEN 'Measured at ' || c.usable_sqft::text || ' sq ft with no space units saying who uses it. Area is not a driver until somebody is standing in it.'
         ELSE c.units::text || ' space units accounting for ' || c.unit_sqft::text
              || ' sq ft against ' || c.usable_sqft::text || ' measured, a difference of '
              || c.variance::text || '. Space must be accounted for in full, including what is common and what is vacant.'
    END::text AS detail
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
  WHERE a.ceiling_federal = 0::numeric;
;

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
        END AS goes_to
   FROM all_items a;
;

COMMENT ON VIEW v_worklist_extra IS
  'The worklist items added after 011. SPACE_UNATTRIBUTED reads '
  'v_space_unit_control rather than testing existence, so a building with '
  'one suite entered of three is still outstanding — which is what the '
  'constraint trigger on the dead space_partition table was for.';

COMMENT ON VIEW v_worklist_owned IS
  'Every outstanding item with the portfolio that can act on it and the '
  'screen it is dealt with on. The CONTROLLER sees all of it, which is what '
  'the portfolio means. Nothing should reach the ELSE: a kind that does is '
  'owned by the controller and pointed at the root by accident rather than '
  'by decision, which tests/test_worklist_ownership.py now derives from '
  'these views rather than from a list kept by hand.';


-- The table nothing ever wrote, and the trigger that guarded it.
DROP TABLE space_partition;
DROP FUNCTION space_must_account_for_facility();
