-- =====================================================================
-- Walking an action back, guardrails, and time nobody was paid for
--
-- Three things that all turn on the same principle: nothing is deleted and
-- nothing is edited in place, so every correction is a new record that says
-- what it corrected and why.
--
-- 1. UNDO. A fat finger and a mass reclassification are the same accident at
--    different scales, and until now the queue's Undo button showed a message
--    saying a reversal had been recorded while recording nothing. An undo is
--    a forward act: it supersedes or reverses through the same paths a person
--    would use by hand, writes its own audit entry, and names the entry it
--    walked back.
--
-- 2. GUARDRAILS. A day over eight hours or a week over forty is usually a
--    typo and occasionally the truth, so it is a question rather than a
--    refusal — answered with a reason, which is then part of the record.
--
-- 3. DONATED TIME. Hours nobody was paid for are not part of a paid
--    distribution and must never dilute one. They are recorded separately,
--    valued at a rate the controller sets and can defend, and reported where
--    they are worth something: cost share under 2 CFR 200.306, and the story
--    the organisation tells about itself.
-- =====================================================================

-- ── The breadcrumb ───────────────────────────────────────────────────
--
-- An undo names what it undid. Without the link the log holds two entries
-- that happen to be about the same row and no statement that one answers the
-- other.

ALTER TABLE audit_log ADD COLUMN undoes_entry_id bigint REFERENCES audit_log;
CREATE INDEX ON audit_log (undoes_entry_id) WHERE undoes_entry_id IS NOT NULL;

COMMENT ON COLUMN audit_log.undoes_entry_id IS
  'The entry this one walks back. An undo is a forward record, never an '
  'erasure of the thing it reverses.';


-- Notes had no way back at all: written, and then permanent whatever they
-- said. Retraction keeps the text and marks it withdrawn, which is what a
-- workpaper does with a note somebody thought better of.
ALTER TABLE note
  ADD COLUMN retracted_at timestamptz,
  ADD COLUMN retracted_by text,
  ADD COLUMN retraction_reason text,
  ADD CONSTRAINT note_retraction_complete
    CHECK (num_nonnulls(retracted_at, retracted_by, retraction_reason) IN (0, 3));


-- What can be walked back, by whom, and whether it still can be.
--
-- Reversibility is a property of the action and of the world since: a
-- classification somebody else has already superseded is not yours to undo,
-- and neither is a sign-in.
CREATE VIEW v_undoable AS
SELECT al.entry_id, al.occurred_at, al.action, al.actor, al.actor_id,
       al.actor_role, al.entity, al.entity_id, al.reason,
       CASE al.action
         WHEN 'CLASSIFY'      THEN 'Classification'
         WHEN 'SEGMENT'       THEN 'Split'
         WHEN 'NOTE'          THEN 'Note'
         WHEN 'TIME_ENTRY'    THEN 'Time entry'
         WHEN 'TIME_REMOVE'   THEN 'Time removed'
         WHEN 'TIME_SUBMIT'   THEN 'Timesheet submitted'
         WHEN 'CERTIFY'       THEN 'Certification'
         WHEN 'EMPLOYMENT'    THEN 'Employment terms'
         WHEN 'EVIDENCE_UPLOAD' THEN 'Document attached'
         WHEN 'SEAL'          THEN 'Seal'
         ELSE al.action
       END                                                   AS label,
       (al.action IN ('CLASSIFY','SEGMENT','NOTE','TIME_ENTRY','TIME_REMOVE',
                      'TIME_SUBMIT','CERTIFY','EMPLOYMENT','EVIDENCE_UPLOAD',
                      'SEAL'))                               AS reversible_action,
       EXISTS (SELECT 1 FROM audit_log u
                WHERE u.undoes_entry_id = al.entry_id)       AS already_undone
  FROM audit_log al
 WHERE al.action NOT IN ('SIGN_IN', 'SIGN_OUT', 'UNDO');

COMMENT ON VIEW v_undoable IS
  'The trail a person can walk back. reversible_action says the kind of thing '
  'it is; whether this particular one still stands is settled when the undo '
  'is attempted, because the world moves between looking and acting.';


-- ── Guardrails on a day ──────────────────────────────────────────────
--
-- Eight hours is the shape of a normal day and forty of a normal week. Over
-- either is usually a slip and sometimes a genuinely long week, so the system
-- asks rather than refuses — and keeps the answer, because "why is there a
-- fourteen-hour day in March" is exactly what a reviewer asks.

ALTER TABLE timesheet_entry
  ADD COLUMN override_reason text,
  ADD COLUMN overrode text[] NOT NULL DEFAULT '{}',
  ADD CONSTRAINT override_needs_reason
    CHECK (cardinality(overrode) = 0
           OR length(btrim(COALESCE(override_reason, ''))) > 0);

COMMENT ON COLUMN timesheet_entry.overrode IS
  'Which soft limits this entry was allowed past — DAY_OVER_8, WEEK_OVER_40 — '
  'with override_reason saying why. A hard limit (24 hours in a day) has no '
  'override and is refused by a trigger.';



-- ── Donated time ─────────────────────────────────────────────────────
--
-- Volunteer effort is potentially cost share under 2 CFR 200.306(e)-(h),
-- which asks for the same documentation as paid staff and a rate consistent
-- with what the organisation pays for similar work. It is a different
-- question from whether the same hours are recognisable in the financial
-- statements under ASC 958-605, which turns on specialised skills. Both
-- start from a contemporaneous record of who did what, and neither survives
-- an estimate made at year end.
--
-- Donated hours are kept out of the paid distribution entirely. Letting them
-- in would move every paid share and misstate the wages allocated to every
-- objective — the most expensive kind of quiet error.

ALTER TABLE timesheet_entry
  ADD COLUMN donated boolean NOT NULL DEFAULT false;

CREATE INDEX ON timesheet_entry (period, employee_key)
  WHERE donated AND superseded_at IS NULL;

COMMENT ON COLUMN timesheet_entry.donated IS
  'Hours given rather than paid. Never enters the paid labour distribution: '
  'it would move every other share.';


-- The rate donated hours are valued at. The controller sets it and says what
-- it rests on, because a volunteer valuing their own time is the whole
-- problem 200.306(e) is guarding against.
CREATE TABLE donation_rate (
  rate_id       bigserial PRIMARY KEY,
  period        text NOT NULL REFERENCES fiscal_period,
  employee_key  text NOT NULL,
  hourly_rate   numeric(10,2) NOT NULL,
  basis         text NOT NULL,
  source_document text NOT NULL DEFAULT '',
  set_by        uuid NOT NULL REFERENCES actor,
  set_by_name   text NOT NULL DEFAULT '',
  set_at        timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,

  CONSTRAINT donation_rate_positive CHECK (hourly_rate > 0),
  CONSTRAINT donation_rate_needs_basis CHECK (length(btrim(basis)) > 10)
);
CREATE UNIQUE INDEX one_live_donation_rate
  ON donation_rate (period, employee_key) WHERE superseded_at IS NULL;

CREATE TRIGGER donation_rate_immutable
  BEFORE UPDATE OF period, employee_key, hourly_rate, basis, set_by, set_at
  ON donation_rate FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER donation_rate_no_delete
  BEFORE DELETE ON donation_rate FOR EACH ROW EXECUTE FUNCTION refuse_mutation();





-- Donated hours must not reach the paid distribution. The views that feed the
-- rate and the certification read v_timesheet_entry, so the exclusion belongs
-- there — one place, rather than a WHERE clause every caller has to remember.
-- Written out column by column rather than as e.*, with the three new columns
-- last. A view's column list is fixed when the view is created, so the old
-- one never saw override_reason, overrode or donated however they were added
-- to the table underneath it — and CREATE OR REPLACE can only append, never
-- insert. Naming them in order is what lets this replace the view instead of
-- dropping half the schema that depends on it.
CREATE OR REPLACE VIEW v_timesheet_entry AS
SELECT e.entry_id, e.period, e.employee_key, e.work_date, e.objective_id,
       e.hours, e.basis, e.note, e.entered_by, e.entered_by_name, e.entered_at,
       e.superseded_at, e.superseded_by,
       (e.entered_at::date - e.work_date)              AS lag_days,
       CASE WHEN e.entered_at::date - e.work_date <= 7   THEN 'CONTEMPORANEOUS'
            WHEN e.entered_at::date - e.work_date <= 45  THEN 'NEAR_TERM'
            ELSE 'RECONSTRUCTED' END                   AS timing,
       CASE WHEN e.basis = 'RECALL'                              THEN 'UNSUPPORTED'
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


CREATE VIEW v_timesheet_overrides AS
SELECT e.period, e.employee_key, e.work_date, e.objective_id, e.hours,
       e.overrode, e.override_reason, e.entered_by_name, e.entered_at
  FROM timesheet_entry e
 WHERE e.superseded_at IS NULL AND cardinality(e.overrode) > 0;


CREATE VIEW v_donated_time AS
SELECT e.period, e.employee_key, e.objective_id, o.label AS objective_label,
       o.is_federal, o.is_final,
       sum(e.hours)                                  AS hours,
       count(DISTINCT e.work_date)                   AS days,
       min(e.work_date)                              AS first_day,
       max(e.work_date)                              AS last_day,
       min(e.entry_grade)                            AS weakest_grade,
       r.hourly_rate,
       CASE WHEN r.hourly_rate IS NOT NULL
            THEN round(sum(e.hours) * r.hourly_rate, 2) END AS valued_at,
       r.basis                                       AS rate_basis,
       (r.hourly_rate IS NULL)                       AS rate_missing
  FROM v_timesheet_entry e
  JOIN cost_objective o USING (objective_id)
  LEFT JOIN donation_rate r ON r.period = e.period
                           AND r.employee_key = e.employee_key
                           AND r.superseded_at IS NULL
 WHERE e.donated
 GROUP BY e.period, e.employee_key, e.objective_id, o.label, o.is_federal,
          o.is_final, r.hourly_rate, r.basis;

COMMENT ON VIEW v_donated_time IS
  'Hours given, by objective, valued where a documented rate exists. '
  'Potential cost share under 2 CFR 200.306(e)-(h); unvalued rows are listed '
  'rather than valued at a guess.';


CREATE OR REPLACE VIEW v_timesheet_distribution AS
SELECT period, employee_key, objective_id,
       sum(hours)                                   AS hours,
       count(*)                                     AS days,
       min(work_date)                               AS first_day,
       max(work_date)                               AS last_day,
       min(entry_grade)                             AS weakest_grade,
       max(entered_at)                              AS last_entered_at,
       round(avg(lag_days))                         AS mean_lag_days
  FROM v_timesheet_entry
 WHERE is_final AND NOT donated          -- paid, chargeable hours only
 GROUP BY period, employee_key, objective_id;


-- Coverage measures whether a paid period is accounted for, so donated hours
-- do not count toward it — otherwise a volunteer weekend would help somebody
-- clear the bar on their paid year. They are carried alongside instead, since
-- they are worth seeing.
CREATE OR REPLACE VIEW v_timesheet_coverage AS
SELECT p.period, e.employee_key,
       sum(e.hours) FILTER (WHERE NOT e.donated)      AS entered_hours,
       sum(e.hours) FILTER (WHERE e.is_final AND NOT e.donated)
                                                      AS chargeable_hours,
       sum(e.hours) FILTER (WHERE NOT e.is_final AND NOT e.donated)
                                                      AS leave_hours,
       count(DISTINCT e.work_date) FILTER (WHERE NOT e.donated)
                                                      AS days_with_time,
       min(e.work_date)                               AS first_day,
       max(e.work_date)                               AS last_day,
       round((p.end_date - p.start_date + 1) / 7.0, 2) AS weeks_in_period,
       (SELECT s.coverage FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_coverage,
       (SELECT s.submitted_at FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_at,
       x.expected_hours, x.employed_days, x.weekly_hours, x.statuses,
       x.from_date AS employed_from, x.to_date AS employed_to,
       CASE WHEN x.expected_hours > 0
            THEN round(sum(e.hours) FILTER (WHERE NOT e.donated)
                       / x.expected_hours, 4) END     AS coverage,
       (x.expected_hours IS NOT NULL)                 AS terms_known,
       -- Appended: hours given rather than paid.
       COALESCE(sum(e.hours) FILTER (WHERE e.donated), 0) AS donated_hours
  FROM v_timesheet_entry e
  JOIN fiscal_period p ON p.period = e.period
  LEFT JOIN v_employment_expected x
         ON x.period = e.period AND x.employee_key = e.employee_key
 GROUP BY p.period, p.start_date, p.end_date, e.employee_key,
          x.expected_hours, x.employed_days, x.weekly_hours, x.statuses,
          x.from_date, x.to_date;


CREATE OR REPLACE VIEW v_timesheet_month AS
WITH months AS (
  SELECT p.period, m::date AS month_start,
         (m + interval '1 month - 1 day')::date AS month_end
    FROM fiscal_period p,
         generate_series(date_trunc('month', p.start_date),
                         date_trunc('month', p.end_date),
                         interval '1 month') m),
people AS (
  SELECT DISTINCT period, employee_key FROM v_timesheet_entry
  UNION
  SELECT DISTINCT period, employee_key FROM employment WHERE superseded_at IS NULL),
scheduled AS (
  SELECT mo.period, e.employee_key, mo.month_start,
         sum(GREATEST(0, LEAST(COALESCE(e.employed_to, mo.month_end), mo.month_end)
                        - GREATEST(e.employed_from, mo.month_start) + 1)::numeric
             / (p.end_date - p.start_date + 1) * e.weekly_hours * 52) AS expected_hours
    FROM months mo
    JOIN fiscal_period p ON p.period = mo.period
    JOIN employment e ON e.period = mo.period AND e.superseded_at IS NULL
                     AND e.employed_from <= mo.month_end
                     AND COALESCE(e.employed_to, mo.month_end) >= mo.month_start
   GROUP BY mo.period, e.employee_key, mo.month_start)
SELECT mo.period, pe.employee_key, mo.month_start,
       to_char(mo.month_start, 'Mon YYYY')                  AS month_label,
       COALESCE(sum(t.hours) FILTER (WHERE NOT t.donated), 0) AS entered_hours,
       COALESCE(sum(t.hours) FILTER (WHERE t.is_final AND NOT t.donated), 0)
                                                            AS chargeable_hours,
       COALESCE(sum(t.hours) FILTER (WHERE NOT t.is_final AND NOT t.donated), 0)
                                                            AS leave_hours,
       count(DISTINCT t.work_date) FILTER (WHERE NOT t.donated) AS days_with_time,
       round(sc.expected_hours, 2)                          AS expected_hours,
       CASE WHEN sc.expected_hours > 0
            THEN round(COALESCE(sum(t.hours) FILTER (WHERE NOT t.donated), 0)
                       / sc.expected_hours, 4)
       END                                                  AS coverage,
       -- Appended: hours given rather than paid.
       COALESCE(sum(t.hours) FILTER (WHERE t.donated), 0)   AS donated_hours
  FROM months mo
  CROSS JOIN people pe
  LEFT JOIN v_timesheet_entry t
         ON t.period = mo.period AND t.employee_key = pe.employee_key
        AND t.work_date BETWEEN mo.month_start AND mo.month_end
  LEFT JOIN scheduled sc
         ON sc.period = mo.period AND sc.employee_key = pe.employee_key
        AND sc.month_start = mo.month_start
 WHERE pe.period = mo.period
 GROUP BY mo.period, pe.employee_key, mo.month_start, sc.expected_hours;


-- Cost share is where donated time is worth something, so it belongs on the
-- work list: hours recorded with no rate behind them are a claim nobody can
-- support, and a rate nobody wrote down is worse than none.

CREATE OR REPLACE VIEW v_worklist AS
SELECT 'UNCLASSIFIED'                                AS kind,
       'BLOCKING'                                    AS severity,
       l.period,
       l.account || COALESCE(NULLIF(' / ' || l.payee, ' / '), '') AS label,
       'ledger_group'                                AS entity,
       l.account || chr(31) || COALESCE(l.payee, '') AS entity_id,
       sum(abs(l.amount))                            AS amount,
       count(*)::text || ' lines, no decision'       AS detail
  FROM ledger_line l
  LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
 WHERE l.period = '2025' AND l.statement = 'P&L' AND dl.line_id IS NULL
 GROUP BY l.period, l.account, l.payee

UNION ALL
SELECT 'BLOCKS_SEAL', 'BLOCKING', '2025', d.scope, 'decision',
       d.decision_id::text,
       (SELECT sum(abs(l.amount)) FROM decision_line dl
          JOIN ledger_line l USING (line_id)
         WHERE dl.decision_id = d.decision_id),
       'graded ' || d.grade::text
  FROM decision d
 WHERE d.reversed_at IS NULL
   AND d.grade IN ('UNSUPPORTED', 'TEST_ASSUMPTION')

UNION ALL
SELECT 'NEEDS_EVIDENCE', 'HIGH', '2025', d.scope, 'decision',
       d.decision_id::text,
       (SELECT sum(abs(l.amount)) FROM decision_line dl
          JOIN ledger_line l USING (line_id)
         WHERE dl.decision_id = d.decision_id),
       'no document cited on the judgment'
  FROM decision d
 WHERE d.reversed_at IS NULL
   AND d.federal IN ('ALLOWABLE', 'PENDING')
   AND NOT EXISTS (SELECT 1 FROM decision_evidence de
                    WHERE de.decision_id = d.decision_id)

UNION ALL
-- Effort not attested by the person who did the work.
SELECT 'NEEDS_CERTIFICATION', 'BLOCKING', c.period,
       COALESCE(NULLIF(c.employee_name, ''), c.employee_key),
       'employee', c.employee_key, c.payroll_wages,
       CASE WHEN c.reconstructed
            THEN 'reconstructed distribution, unsigned'
            ELSE 'distribution unsigned' END
  FROM v_certification_status c WHERE NOT c.certified

UNION ALL
-- Signed, but for numbers that have since changed.
SELECT 'STALE_CERTIFICATION', 'BLOCKING', c.period,
       COALESCE(NULLIF(c.employee_name, ''), c.employee_key),
       'employee', c.employee_key, c.payroll_wages,
       'signed ' || to_char(c.signed_at, 'DD Mon YYYY')
         || ', distribution changed since'
  FROM v_certification_status c WHERE c.certified AND c.stale

UNION ALL
SELECT 'ASSET_FUNDING_UNKNOWN', 'BLOCKING', a.period, a.description, 'asset',
       a.asset_id, a.depreciation,
       'depreciation currently treated as fully allowable'
  FROM asset a
 WHERE NOT EXISTS (SELECT 1 FROM asset_funding f WHERE f.asset_id = a.asset_id)

UNION ALL
SELECT 'FACILITY_UNPARTITIONED', 'BLOCKING', f.period, f.name, 'facility',
       f.facility_id, f.usable_sqft, 'no space partition recorded'
  FROM facility f
 WHERE NOT EXISTS (SELECT 1 FROM space_partition sp
                    WHERE sp.facility_id = f.facility_id
                      AND sp.period = f.period)

UNION ALL
SELECT 'INVOICE_NO_INDIRECT', 'HIGH', v.period,
       'Invoice ' || COALESCE(v.invoice_number, '') || ' ' ||
         COALESCE(v.objective_id, ''),
       'invoice', v.invoice_id::text, v.mtdc_as_billed,
       'no indirect billed on a base of ' || v.mtdc_as_billed::text
  FROM v_invoice_category v
 WHERE v.no_indirect_billed AND v.mtdc_as_billed > 0

UNION ALL
SELECT 'INVOICE_NO_AWARD', 'MEDIUM', i.period,
       'Invoice ' || COALESCE(i.invoice_number, i.seq::text),
       'invoice', i.invoice_id::text, i.total, 'not linked to an award'
  FROM invoice i WHERE i.award_id IS NULL

UNION ALL
SELECT 'STALE_DECISION', 'HIGH', l.period, d.scope, 'decision',
       d.decision_id::text, abs(l.amount),
       'source line ' || r.change || ' after the decision'
  FROM ledger_revision r
  JOIN ledger_line l USING (line_id)
  JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
  JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
 WHERE r.detected_at > d.decided_at

UNION ALL
-- Whose employment terms nobody has recorded. Listed rather than assumed:
-- defaulting an unknown to full-time-all-year is exactly the assumption that
-- makes a part-year employee's timesheet unsubmittable, and it would do it
-- silently.
SELECT 'EMPLOYMENT_UNKNOWN', 'HIGH', a.period,
       COALESCE(NULLIF(max(a.employee_name), ''), a.employee_key),
       'employee', a.employee_key, max(a.payroll_wages),
       'no employment terms recorded, so no timesheet of theirs can be tested'
  FROM labor_allocation a
 WHERE NOT EXISTS (SELECT 1 FROM employment e
                    WHERE e.period = a.period
                      AND e.employee_key = a.employee_key
                      AND e.superseded_at IS NULL)
 GROUP BY a.period, a.employee_key

UNION ALL
-- Donated hours with no documented rate behind them. 2 CFR 200.306(e) wants a
-- rate consistent with what the organisation pays for similar work, written
-- down; hours claimed at a rate nobody recorded are not cost share, they are
-- an assertion.
SELECT 'DONATION_RATE_MISSING', 'MEDIUM', d.period,
       d.employee_key || ' — ' || d.objective_id,
       'employee', d.employee_key, d.hours,
       d.hours::text || ' donated hours with no documented rate'
  FROM v_donated_time d WHERE d.rate_missing;
