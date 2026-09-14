-- 070 — adopting the reconstruction must not downgrade the record
--
-- `POST /api/timesheet/adopt` writes the controller's reconstruction onto the
-- employee's own sheet, which is what 2 CFR 200.430(i) asks for: a record
-- that reflects the work performed, supported, and **reviewed after the
-- fact**. It wrote `basis = 'RECALL'`, and `v_timesheet_entry` grades RECALL
-- `UNSUPPORTED` unconditionally.
--
-- So the act the whole certification exercise exists to produce made the
-- record **weaker**. Measured on the live record, one person:
--
--     before adopting   RECONSTRUCTION   MANAGEMENT_RECONSTRUCTION
--     after submitting  TIMESHEET        UNSUPPORTED
--
-- Same numbers, same provenance — the controller's rebuild from payroll and
-- hours logs — plus a signature, and the grade drops a rung. Across
-- forty-three people that is every workpaper reading `evidence_quality`
-- getting worse for doing the work, which is the shape this file keeps
-- finding: a control that punishes the person who clears it.
--
-- **`RECALL` is not wrong, it is the wrong question.** For an entry somebody
-- types from memory it is exactly right — *honest recollection with nothing
-- behind it*, and that stays true and stays UNSUPPORTED. What the enum could
-- not say is that these hours came from the organisation's reconstruction
-- and the person affirmed them. `ingest_channel = 'GENERATED'` in `038` is
-- the same move for the same reason: every other value meant the document
-- came from outside, and there was no value meaning *this system made it*.
--
-- The grade it earns is `MANAGEMENT_RECONSTRUCTION` — **carried across, not
-- raised**. It is literally the reconstruction, which already holds that
-- grade on `labor_allocation.evidence_quality`; adopting neither adds a
-- document nor takes one away. The strengthening that certification does
-- belongs on `v_certification_status`, where somebody's signature is
-- recorded, and not in a column about documentary support. Grading it
-- `CORROBORATED` would claim a contemporaneous record that does not exist.
--
-- Nobody can choose this basis. It is written only by the adopt route, and
-- `POST /api/timesheet/entry` refuses it — a person typing a day cannot
-- assert that the organisation reconstructed it for them.

ALTER TYPE time_basis ADD VALUE IF NOT EXISTS 'ADOPTED';

COMMENT ON TYPE time_basis IS
  'What a timesheet entry rests on. ADOPTED is written only by '
  'POST /api/timesheet/adopt and means the hours came from the controller''s '
  'reconstruction and the person whose work it was affirmed them; it carries '
  'that reconstruction''s grade rather than raising or lowering it.';


-- `CREATE OR REPLACE`, not `DROP ... CASCADE`: the column list is unchanged
-- and six views hang off this one, `v_labor_effective` among them. Dropping
-- it would take the whole timesheet stack down and rebuild it from memory.
--
-- Lifted from `019`, which is where this view is *currently* defined — the
-- copy in `017` says `SELECT e.*` and predates three columns, so replacing
-- with that body renames `lag_days` to `override_reason` and Postgres
-- refuses. Lift from the definition in force, not the first one written.
CREATE OR REPLACE VIEW v_timesheet_entry AS
SELECT e.entry_id, e.period, e.employee_key, e.work_date, e.objective_id,
       e.hours, e.basis, e.note, e.entered_by, e.entered_by_name, e.entered_at,
       e.superseded_at, e.superseded_by,
       (e.entered_at::date - e.work_date)              AS lag_days,
       CASE WHEN e.entered_at::date - e.work_date <= 7   THEN 'CONTEMPORANEOUS'
            WHEN e.entered_at::date - e.work_date <= 45  THEN 'NEAR_TERM'
            ELSE 'RECONSTRUCTED' END                   AS timing,
       -- `e.basis::text`, not a `'ADOPTED'::time_basis` literal: migrations
       -- run inside one transaction and PostgreSQL refuses a new enum label
       -- used in the transaction that added it.
       CASE WHEN e.basis::text = 'ADOPTED'  THEN 'MANAGEMENT_RECONSTRUCTION'
            WHEN e.basis = 'RECALL'                              THEN 'UNSUPPORTED'
            WHEN e.entered_at::date - e.work_date <= 7           THEN 'CORROBORATED'
            WHEN e.basis IN ('CALENDAR','PROJECT_RECORD','DELIVERABLE')
                                                                 THEN 'MANAGEMENT_RECONSTRUCTION'
            ELSE 'UNSUPPORTED' END::evidence_grade     AS entry_grade,
       o.label                                         AS objective_label,
       o.is_federal, o.is_final,
       e.override_reason, e.overrode, e.donated
  FROM timesheet_entry e
  JOIN cost_objective o USING (objective_id)
 WHERE e.superseded_at IS NULL;

COMMENT ON VIEW v_timesheet_entry IS
  'Live entries, with the grade the timing and the basis earn. A record made '
  'within the week of the work is contemporaneous; one made eight months '
  'later is a reconstruction however carefully it was built. An ADOPTED entry '
  'carries the controller''s reconstruction across rather than being regraded '
  'as a guess.';
