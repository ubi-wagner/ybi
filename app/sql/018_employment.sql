-- =====================================================================
-- Employment terms: the denominator
--
-- A timesheet is only allowed to speak for a period once it covers that
-- period, and the first cut worked out what "covering it" meant from a
-- weekly-hours figure the employee typed in, times the whole year. That is
-- wrong for anybody who was not full-time for all of it — which, in this
-- ledger, is most of the list. The 2025 payroll runs from $192,087 down to
-- $220.59: somebody worked a day. Asking them for 90% of two thousand hours
-- makes their timesheet unsubmittable, so the person whose time is hardest to
-- reconstruct is the one the system refuses to let record it.
--
-- So the denominator comes from employment terms — status, contracted hours a
-- week, and the dates between which they applied — and not from a number the
-- person being measured supplies. It is payroll's fact, so the controller
-- records it and the employee reads it.
--
-- Terms change: someone goes from part-time to full-time in June. A change is
-- a new row for the new span, not an edit to the old one, so the year is the
-- sum of its spans and the record shows what was true when.
-- =====================================================================

CREATE TYPE employment_status AS ENUM (
  'FULL_TIME', 'PART_TIME', 'TEMPORARY', 'INTERN', 'CONTRACT');

CREATE TABLE employment (
  employment_id   bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  employee_key    text NOT NULL,
  status          employment_status NOT NULL,
  weekly_hours    numeric(5,2) NOT NULL,
  employed_from   date NOT NULL,
  employed_to     date,                       -- NULL: still there at period end
  source_document text NOT NULL DEFAULT '',
  note            text NOT NULL DEFAULT '',
  recorded_by     uuid NOT NULL REFERENCES actor,
  recorded_name   text NOT NULL DEFAULT '',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  superseded_at   timestamptz,
  superseded_reason text,

  CONSTRAINT employment_hours_sane
    CHECK (weekly_hours > 0 AND weekly_hours <= 80),
  CONSTRAINT employment_span_ordered
    CHECK (employed_to IS NULL OR employed_to >= employed_from),
  CONSTRAINT employment_supersession_pair
    CHECK ((superseded_at IS NULL) = (superseded_reason IS NULL))
);
CREATE INDEX ON employment (period, employee_key) WHERE superseded_at IS NULL;

-- Two live spans for one person must not overlap, or the year would be
-- counted twice across the join. Checked at COMMIT so a correction can close
-- the old span and open the new one in a single transaction.
CREATE OR REPLACE FUNCTION employment_spans_must_not_overlap() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE clash record;
BEGIN
  SELECT a.employment_id, a.employed_from, a.employed_to INTO clash
    FROM employment a
    JOIN employment b ON b.employee_key = a.employee_key
                     AND b.period = a.period
                     AND b.employment_id <> a.employment_id
                     AND b.superseded_at IS NULL
                     AND daterange(a.employed_from,
                                   COALESCE(a.employed_to, 'infinity'::date), '[]')
                         && daterange(b.employed_from,
                                      COALESCE(b.employed_to, 'infinity'::date), '[]')
   WHERE a.employee_key = NEW.employee_key AND a.period = NEW.period
     AND a.superseded_at IS NULL
   LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION
      'Employment spans for % overlap (% to %). Close the earlier span before opening the next.',
      NEW.employee_key, clash.employed_from, COALESCE(clash.employed_to::text, 'open');
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER employment_no_overlap
  AFTER INSERT OR UPDATE ON employment
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION employment_spans_must_not_overlap();

CREATE TRIGGER employment_immutable
  BEFORE UPDATE OF period, employee_key, status, weekly_hours, employed_from,
                   employed_to, recorded_by, recorded_at
  ON employment
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER employment_no_delete
  BEFORE DELETE ON employment
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ── What a full record would hold ────────────────────────────────────
--
-- A full-time year is 2,080 hours — fifty-two weeks at forty — and somebody
-- who started on 1 July is owed half of that, not half of the 2,086 you get
-- by dividing 365 days by seven. So the standard year is weekly_hours × 52,
-- and each employment span takes the share of it that its days are of the
-- period''s days.
--
-- Spans rather than one figure, because terms change: part-time until June
-- and full-time after it is two spans and one year, and the total is their
-- sum.

CREATE VIEW v_employment_expected AS
SELECT e.period, e.employee_key,
       min(GREATEST(e.employed_from, p.start_date))              AS from_date,
       max(LEAST(COALESCE(e.employed_to, p.end_date), p.end_date)) AS to_date,
       sum(LEAST(COALESCE(e.employed_to, p.end_date), p.end_date)
           - GREATEST(e.employed_from, p.start_date) + 1)        AS employed_days,
       round(sum((LEAST(COALESCE(e.employed_to, p.end_date), p.end_date)
                  - GREATEST(e.employed_from, p.start_date) + 1)::numeric
                 / (p.end_date - p.start_date + 1)
                 * e.weekly_hours * 52), 2)                      AS expected_hours,
       max(e.weekly_hours)                                       AS weekly_hours,
       string_agg(DISTINCT e.status::text, ', ')                 AS statuses,
       count(*)                                                  AS spans
  FROM employment e
  JOIN fiscal_period p ON p.period = e.period
 WHERE e.superseded_at IS NULL
   AND e.employed_from <= p.end_date
   AND COALESCE(e.employed_to, p.end_date) >= p.start_date
 GROUP BY e.period, e.employee_key;

COMMENT ON VIEW v_employment_expected IS
  'Hours a person was employed to work in the period, from their terms and '
  'the dates those terms ran — the denominator a timesheet is measured '
  'against. Never supplied by the person being measured.';


-- ── Month by month ───────────────────────────────────────────────────
--
-- A year is rebuilt a week at a time and checked a month at a time. This is
-- what tells someone which month they still have to go back to, rather than
-- leaving them with one number for the whole year and no idea where the gap
-- is.

CREATE VIEW v_timesheet_month AS
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
  -- The hours each employment span implies inside each month, on the same
  -- 2,080 basis: the span's days in the month, as a share of the year, times
  -- the standard year.
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
       COALESCE(sum(t.hours), 0)                            AS entered_hours,
       COALESCE(sum(t.hours) FILTER (WHERE t.is_final), 0)  AS chargeable_hours,
       COALESCE(sum(t.hours) FILTER (WHERE NOT t.is_final), 0) AS leave_hours,
       count(DISTINCT t.work_date)                          AS days_with_time,
       round(sc.expected_hours, 2)                          AS expected_hours,
       CASE WHEN sc.expected_hours > 0
            THEN round(COALESCE(sum(t.hours), 0) / sc.expected_hours, 4)
       END                                                  AS coverage
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

COMMENT ON VIEW v_timesheet_month IS
  'Entered against expected, month by month, so the gap in a rebuilt year is '
  'a month somebody can go back to rather than a number at the bottom.';


-- ── Coverage, now against the right denominator ──────────────────────

CREATE OR REPLACE VIEW v_timesheet_coverage AS
SELECT p.period, e.employee_key,
       sum(e.hours)                                   AS entered_hours,
       sum(e.hours) FILTER (WHERE e.is_final)         AS chargeable_hours,
       sum(e.hours) FILTER (WHERE NOT e.is_final)     AS leave_hours,
       count(DISTINCT e.work_date)                    AS days_with_time,
       min(e.work_date)                               AS first_day,
       max(e.work_date)                               AS last_day,
       round((p.end_date - p.start_date + 1) / 7.0, 2) AS weeks_in_period,
       (SELECT s.coverage FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_coverage,
       (SELECT s.submitted_at FROM timesheet_submission s
         WHERE s.period = p.period AND s.employee_key = e.employee_key
           AND s.withdrawn_at IS NULL)                AS submitted_at,
       -- Appended: the terms, and the coverage they imply.
       x.expected_hours, x.employed_days, x.weekly_hours, x.statuses,
       x.from_date AS employed_from, x.to_date AS employed_to,
       CASE WHEN x.expected_hours > 0
            THEN round(sum(e.hours) / x.expected_hours, 4) END AS coverage,
       (x.expected_hours IS NOT NULL)                 AS terms_known
  FROM v_timesheet_entry e
  JOIN fiscal_period p ON p.period = e.period
  LEFT JOIN v_employment_expected x
         ON x.period = e.period AND x.employee_key = e.employee_key
 GROUP BY p.period, p.start_date, p.end_date, e.employee_key,
          x.expected_hours, x.employed_days, x.weekly_hours, x.statuses,
          x.from_date, x.to_date;


-- ── Whose terms nobody has recorded ──────────────────────────────────

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
 GROUP BY a.period, a.employee_key;
