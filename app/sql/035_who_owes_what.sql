-- The worklist, routed to whoever can actually do something about it.
--
-- v_worklist knows what is outstanding and says nothing about whose job it
-- is, so every screen shows everybody the same list. That is fine for a
-- dashboard and useless as a morning. Heidi should open the application and
-- see that the buildings have no square footage against them; Stephanie
-- should see which of the people on her projects have not signed for their
-- own effort; Tom should see the queue. Nobody should have to read past four
-- items that belong to somebody else to find theirs.
--
-- The routing is by portfolio, because that is what the system already uses
-- to decide who may do a thing. An item nobody holds the portfolio for is
-- still shown — to the controller, who reaches everything — rather than
-- disappearing.

-- ── Things the worklist did not know to ask for ───────────────────────
--
-- Three additions, each one a question somebody has to answer before a rate
-- means anything, and each with an owner.
CREATE VIEW v_worklist_extra AS
-- No building on file at all. The facilities carve-out is the single largest
-- open judgment in the rate and it cannot start without one.
SELECT 'SPACE_UNMEASURED'                          AS kind,
       'BLOCKING'                                  AS severity,
       p.period,
       'No building has square footage on file'    AS label,
       'facility'                                  AS entity,
       ''                                          AS entity_id,
       NULL::numeric                               AS amount,
       'The facilities carve-out is sized by area. Without it the '
       'occupancy cost sitting in overhead cannot be split between the '
       'programme and the tenants, and 200.465 has nothing to work from.'
                                                   AS detail
  FROM fiscal_period p
 WHERE p.period = '2025'
   AND NOT EXISTS (SELECT 1 FROM facility f
                    WHERE f.period = p.period AND f.usable_sqft > 0)

UNION ALL
-- A building measured, but with nobody recorded as using it. Area alone does
-- not carve anything out; who occupies it is the driver.
SELECT 'SPACE_UNATTRIBUTED', 'HIGH', f.period, f.name, 'facility',
       f.facility_id, f.usable_sqft,
       'Measured at ' || f.usable_sqft::text || ' sq ft with no space '
       'partition saying who uses it. Area is not a driver until somebody '
       'is standing in it.'
  FROM facility f
 WHERE f.usable_sqft > 0
   AND NOT EXISTS (SELECT 1 FROM space_partition sp
                    WHERE sp.facility_id = f.facility_id)

UNION ALL
-- Hours booked to a code nobody was assigned to. Expected for 2025 and a
-- finding from 2026, which is why it names the year it is looking at.
SELECT 'CHARGE_CODE_UNASSIGNED', 'MEDIUM', c.period, c.objective_id,
       'cost_objective', c.objective_id, NULL::numeric,
       c.hours_charged::text || ' hours booked with nobody assigned to the '
       'code. Assign the people who work on it and the gate turns on.'
  FROM v_charge_code c
 WHERE c.hours_charged > 0 AND c.people_authorised = 0;


-- ── One worklist, with an owner on every row ──────────────────────────
CREATE VIEW v_worklist_owned AS
WITH all_items AS (
  SELECT kind, severity, period, label, entity, entity_id, amount, detail
    FROM v_worklist
  UNION ALL
  SELECT kind, severity, period, label, entity, entity_id, amount, detail
    FROM v_worklist_extra)
SELECT a.*,
       -- Who can do something about it. CONTROLLER reaches everything, so
       -- an item owned by a narrow portfolio is still the controller's to
       -- see; that is handled where this is read, not here.
       CASE a.kind
         WHEN 'UNCLASSIFIED'           THEN 'CONTROLLER'
         WHEN 'BLOCKS_SEAL'            THEN 'CONTROLLER'
         WHEN 'STALE_DECISION'         THEN 'CONTROLLER'
         WHEN 'NEEDS_EVIDENCE'         THEN 'OFFICE'
         WHEN 'FACILITY_UNPARTITIONED' THEN 'FACILITIES'
         WHEN 'SPACE_UNMEASURED'       THEN 'FACILITIES'
         WHEN 'SPACE_UNATTRIBUTED'     THEN 'FACILITIES'
         WHEN 'ASSET_FUNDING_UNKNOWN'  THEN 'INVENTORY'
         WHEN 'INVOICE_NO_INDIRECT'    THEN 'PROJECT'
         WHEN 'INVOICE_NO_AWARD'       THEN 'PROJECT'
         WHEN 'CHARGE_CODE_UNASSIGNED' THEN 'PROJECT'
         WHEN 'NEEDS_CERTIFICATION'    THEN 'PROJECT'
         WHEN 'EMPLOYMENT_UNKNOWN'     THEN 'PROJECT'
         ELSE 'CONTROLLER'
       END                                              AS owner_portfolio,
       -- Where the person goes to deal with it. A worklist that says what is
       -- wrong and not where to fix it makes somebody hunt through the nav.
       CASE a.kind
         WHEN 'UNCLASSIFIED'           THEN '/classify'
         WHEN 'BLOCKS_SEAL'            THEN '/classify'
         WHEN 'STALE_DECISION'         THEN '/classify'
         WHEN 'NEEDS_EVIDENCE'         THEN '/evidence'
         WHEN 'FACILITY_UNPARTITIONED' THEN '/space'
         WHEN 'SPACE_UNMEASURED'       THEN '/space'
         WHEN 'SPACE_UNATTRIBUTED'     THEN '/space'
         WHEN 'ASSET_FUNDING_UNKNOWN'  THEN '/inventory'
         WHEN 'INVOICE_NO_INDIRECT'    THEN '/contracts'
         WHEN 'INVOICE_NO_AWARD'       THEN '/contracts'
         WHEN 'CHARGE_CODE_UNASSIGNED' THEN '/contracts/codes'
         WHEN 'NEEDS_CERTIFICATION'    THEN '/contracts/people'
         WHEN 'EMPLOYMENT_UNKNOWN'     THEN '/timesheet'
         ELSE '/'
       END                                              AS goes_to
  FROM all_items a;

COMMENT ON VIEW v_worklist_owned IS
  'Everything outstanding, with the portfolio that can act on it and the '
  'screen it is dealt with on. Read it filtered by what somebody holds.';


-- ── Who has not signed for their own effort, and on whose projects ────
--
-- The project manager's version of the certification question. 200.430(i)
-- wants the signature of the person whose effort it was, so a manager cannot
-- sign it for them — what they can do is see who has not, on the work they
-- are responsible for, and go and ask.
--
-- "Their projects" is read from the assignments they made. Somebody who put
-- people on a charge code is managing that code; that is a fact already on
-- the record rather than a new field to maintain. A project manager who has
-- made no assignments sees the award-backed objectives instead, which is the
-- honest fallback for a year that was worked before assignment existed.
CREATE VIEW v_certification_chase AS
SELECT la.period,
       la.objective_id,
       o.label                                          AS objective_label,
       aw.award_id,
       la.employee_key,
       la.employee_name,
       la.reconstructed_units                           AS wages,
       la.evidence_quality::text                        AS grade,
       cs.certified,
       cs.stale,
       cs.signed_at,
       -- Who assigned this person to this code, where anybody did. That is
       -- the manager to chase, and it is null for every 2025 row because
       -- the mechanism did not exist while the year was worked.
       (SELECT ca.granted_by FROM charge_authority ca
         WHERE ca.period = la.period
           AND ca.objective_id = la.objective_id
           AND ca.employee_key = la.employee_key
           AND ca.revoked_at IS NULL)                   AS assigned_by
  FROM labor_allocation la
  JOIN cost_objective o ON o.objective_id = la.objective_id
  LEFT JOIN award aw    ON aw.objective_id = la.objective_id
  LEFT JOIN v_certification_status cs
         ON cs.period = la.period AND cs.employee_key = la.employee_key
 WHERE COALESCE(cs.certified, false) = false OR COALESCE(cs.stale, false);

COMMENT ON VIEW v_certification_chase IS
  'Effort distributed to somebody who has not signed for it, by objective. '
  'A manager cannot sign on their behalf — 200.430(i) wants the person '
  'whose effort it was — so this is a list to chase, not to action.';
