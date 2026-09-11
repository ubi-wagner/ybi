-- An award with no ceiling on file is a question nobody was asking.
--
-- Last Tactical Mile carried a ceiling of zero for the whole engagement with
-- the citation "Ceiling not yet transcribed from the agreement". That was an
-- honest placeholder and it went quiet: the executed agreement had been on
-- file since September and §4.3 — $899,500 federal and $513,065 cost share —
-- had never been read into the record. It surfaced because somebody looked
-- at a screen and asked, which is not a control.
--
-- A ceiling is what a restatement is capped against and what tells anybody
-- whether a claim is within the contract, so an award without one cannot be
-- tested against anything. This puts it on the project manager's list, where
-- the placeholder has to be looked at rather than merely be true.
--
-- Cost share is the same question with higher stakes: the two obligations
-- nobody was tracking came to $617,065 between them, which is more than the
-- largest open classification judgment in the ledger.

CREATE OR REPLACE VIEW v_worklist_extra AS
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
SELECT 'CHARGE_CODE_UNASSIGNED', 'MEDIUM', c.period, c.objective_id,
       'cost_objective', c.objective_id, NULL::numeric,
       c.hours_charged::text || ' hours booked with nobody assigned to the '
       'code. Assign the people who work on it and the gate turns on.'
  FROM v_charge_code c
 WHERE c.hours_charged > 0 AND c.people_authorised = 0

UNION ALL
-- The one that would have caught Last Tactical Mile.
SELECT 'AWARD_NO_CEILING', 'HIGH', o.period, a.award_id, 'award', a.award_id,
       NULL::numeric,
       CASE WHEN EXISTS (SELECT 1 FROM evidence e
                          WHERE e.kind IN ('subrecipient-agreement',
                                           'award-agreement',
                                           'award-modification',
                                           'grant-agreement'))
            THEN 'No ceiling on file, and there are executed agreements in '
                 'the document register. Read the obligation clause into the '
                 'record — a claim cannot be tested against a ceiling that '
                 'is not there.'
            ELSE 'No ceiling on file and no executed agreement in the '
                 'register either. Get the agreement; what was invoiced is '
                 'not a ceiling.'
       END
  FROM award a
  JOIN cost_objective o ON o.objective_id = a.objective_id
 WHERE a.ceiling_federal = 0;


-- The new kind needs an owner and a destination like every other. Routed
-- here rather than by editing 035, which has already been applied.
CREATE OR REPLACE VIEW v_worklist_owned AS
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
         WHEN 'AWARD_NO_CEILING'       THEN 'PROJECT'
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
         WHEN 'AWARD_NO_CEILING'       THEN '/contracts'
         WHEN 'NEEDS_CERTIFICATION'    THEN '/contracts/people'
         WHEN 'EMPLOYMENT_UNKNOWN'     THEN '/timesheet'
         ELSE '/'
       END                                              AS goes_to
  FROM all_items a;
