-- Tom holds forty-three signed certifications and nowhere to put them.
--
-- `labor_certification` has sixteen columns and **not one points at a
-- document.** The signature it records is a click: `signed_by` is the calling
-- actor's display name, beside their `actor_id`, `session_id` and user agent.
-- So a page somebody physically signed could be uploaded — everybody signed
-- in may upload — and land in the library attached to nothing, while
-- `v_certification_status` went on reading *0 of 43 certified*. Forty signed
-- pages on file and forty uncertified people, at the same moment, on two
-- screens. That is 13.0%-and-2.2% in the register 200.430(i) turns on.
--
-- The only thing the controller could do instead was sign `as_supervisor`,
-- which writes a **different assertion** — *I have firsthand knowledge of the
-- work performed* — over forty-three people including those on projects he
-- does not run. Forty-three of those from one account in one sitting is the
-- reading problem `decision.origin` exists for, and the route's own docstring
-- says the role "is not yet issued to anyone".
--
-- **What was missing is a value for the kind of act**, which is the fourth
-- time this schema has needed exactly that: `038` had no `ingest_channel`
-- meaning *this system made it*, `070` no `basis` meaning *the organisation
-- reconstructed it and the person affirmed it*, `083` no `origin` meaning
-- *the machine proposed it*. `PAPER` is the fourth: **the person signed, on
-- paper, and somebody else filed the page.**
--
-- So the two facts are kept apart on the row, which is the whole of it:
--
--     signed_by        the person on the page, read off their signature
--     actor_id         whoever filed it, with their session
--     paper_signed_on  the date the page carries
--     signed_at        when the row was written
--     evidence_id      the page
--
-- **The document is mandatory and the fence is an equivalence**, not a pair
-- of one-way checks: a PAPER row without a page is the citation-with-no-
-- document shape this repository has paid for three times, and an EMPLOYEE
-- row *with* one would claim a scan behind a click. `direct_needs_objective`
-- is the same shape for the same reason.
--
-- Nothing downstream is blocked by any of this, per `082`. A certification
-- changes whether the direct labour charge is allowable, not whether a rate
-- can be computed.
--
-- Two mechanics worth knowing, both recorded here before and both live:
--   * a new enum label **cannot be used in the transaction that adds it**,
--     which is what migrations run in — so every comparison against PAPER
--     below casts `::text`, exactly as `070` had to;
--   * `CREATE OR REPLACE VIEW` can only **append** a column, so `by_paper`
--     goes last rather than beside `by_supervisor` (`118`).

ALTER TYPE certifier_role ADD VALUE IF NOT EXISTS 'PAPER';

ALTER TABLE labor_certification
  ADD COLUMN IF NOT EXISTS evidence_id text REFERENCES evidence(evidence_id),
  ADD COLUMN IF NOT EXISTS paper_signed_on date;

COMMENT ON COLUMN labor_certification.evidence_id IS
  'The signed page, for a PAPER certification and for nothing else. '
  'Mandatory there: a PAPER row is a claim that a named person signed '
  'something, and a claim with no document behind it is worth less than no '
  'row at all.';
COMMENT ON COLUMN labor_certification.paper_signed_on IS
  'The date the page carries, which is not signed_at — that is when this row '
  'was written. The gap between them is the filing lag and a reviewer is '
  'entitled to see it.';

ALTER TABLE labor_certification
  ADD CONSTRAINT paper_names_its_page CHECK (
    (certifier_role::text = 'PAPER') = (evidence_id IS NOT NULL));

ALTER TABLE labor_certification
  ADD CONSTRAINT paper_carries_the_date_on_the_page CHECK (
    (certifier_role::text = 'PAPER') = (paper_signed_on IS NOT NULL));

-- Effort cannot be certified before the period it covers began, and a page
-- dated after it was filed is a transcription error rather than a signature.
ALTER TABLE labor_certification
  ADD CONSTRAINT paper_is_dated_within_reason CHECK (
    paper_signed_on IS NULL
    OR (paper_signed_on >= period_start AND paper_signed_on <= signed_at::date));

-- The two new columns join the ones that may never be edited. Supersession
-- writes `superseded_at` and `superseded_reason`, which are deliberately not
-- in this list — that is how the register corrects itself.
DROP TRIGGER IF EXISTS labor_certification_immutable ON labor_certification;
CREATE TRIGGER labor_certification_immutable
  BEFORE UPDATE OF statement, distribution, distribution_hash, actor_id,
                   signed_by, signed_at, evidence_id, paper_signed_on
  ON labor_certification
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

-- Lifted from `017`, which is the definition in force; `by_paper` is appended
-- because a replace cannot insert a column, and it is compared as text
-- because the label is added in this same transaction.
CREATE OR REPLACE VIEW v_certification_status AS
WITH dist AS (
  SELECT period, employee_key,
         max(employee_name)                       AS employee_name,
         max(payroll_wages)                       AS payroll_wages,
         count(*)                                 AS objectives,
         bool_or(is_reconstructed)                AS reconstructed,
         bool_or(source = 'TIMESHEET')            AS from_timesheet,
         min(evidence_quality)                    AS weakest_grade,
         md5(string_agg(objective_id || ':' || effective_units::text,
                        '|' ORDER BY objective_id)) AS current_hash
    FROM v_labor_effective GROUP BY period, employee_key),
cert AS (
  SELECT period, employee_key,
         max(signed_at)                                       AS signed_at,
         max(distribution_hash)                               AS signed_hash,
         bool_or(certifier_role = 'EMPLOYEE')                 AS by_employee,
         bool_or(certifier_role = 'SUPERVISOR')               AS by_supervisor,
         bool_or(certifier_role::text = 'PAPER')              AS by_paper,
         max(paper_signed_on)                                 AS paper_signed_on,
         string_agg(DISTINCT signed_by, ', ')                 AS signed_by
    FROM labor_certification
   WHERE superseded_at IS NULL
   GROUP BY period, employee_key)
SELECT d.period, d.employee_key, d.employee_name, d.payroll_wages,
       d.objectives, d.reconstructed,
       c.signed_at, c.signed_by,
       COALESCE(c.by_employee, false)   AS by_employee,
       COALESCE(c.by_supervisor, false) AS by_supervisor,
       (c.signed_at IS NOT NULL)        AS certified,
       (c.signed_at IS NOT NULL AND c.signed_hash IS DISTINCT FROM d.current_hash)
                                        AS stale,
       d.from_timesheet, d.weakest_grade,
       -- Appended: a replace cannot insert a column.
       COALESCE(c.by_paper, false)      AS by_paper,
       c.paper_signed_on
  FROM dist d LEFT JOIN cert c USING (period, employee_key);

COMMENT ON VIEW v_certification_status IS
  'Who has signed, who has not, and whose signature has gone stale — with '
  'which kind of signature it was. A PAPER certification is somebody else '
  'filing the page a person signed, so by_paper and signed_by together say '
  'what happened where one column could not.';
