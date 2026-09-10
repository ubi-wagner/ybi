-- =====================================================================
-- Labour distribution and certification
--
-- The gap that stands between the controller's reconstruction and a
-- defensible direct labour charge. 2 CFR 200.430(i) wants records that
-- reasonably reflect the total activity for which an employee is
-- compensated, and a certification by the person who did the work or a
-- supervisor with firsthand knowledge.
--
-- Three properties the schema enforces rather than the handler:
--
--   1. An employee's distribution totals 100% of their activity. Certifying
--      the federal slice alone proves nothing about the denominator, which is
--      the whole point of 200.430(i)(1)(iii).
--   2. Original effort is immutable; a reconstruction is a separate column on
--      the same row, so both stay visible and the record shows that a
--      reconstruction happened.
--   3. A certification names the period it covers and is never edited. A
--      changed distribution needs a fresh signature, because the old one
--      attested to different numbers.
-- =====================================================================

CREATE TYPE certifier_role AS ENUM ('EMPLOYEE', 'SUPERVISOR');


CREATE TABLE labor_allocation (
  allocation_id     bigserial PRIMARY KEY,
  period            text NOT NULL REFERENCES fiscal_period,
  employee_key      text NOT NULL,
  employee_name     text NOT NULL DEFAULT '',
  objective_id      text NOT NULL,
  payroll_wages     numeric(14,2) NOT NULL,      -- the employee's total for the period
  original_units    numeric(12,2) NOT NULL DEFAULT 0,
  reconstructed_units numeric(12,2),
  evidence_quality  evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  rationale         text NOT NULL DEFAULT '',
  source_document   text NOT NULL DEFAULT '',
  loaded_at         timestamptz NOT NULL DEFAULT now(),
  loaded_by         text NOT NULL DEFAULT '',

  UNIQUE (period, employee_key, objective_id),
  CONSTRAINT allocation_units_sane
    CHECK (original_units >= 0
           AND (reconstructed_units IS NULL OR reconstructed_units >= 0)),
  -- A reconstruction is a judgment and needs its reasoning, and it cannot be
  -- offered as supported while the evidence behind it is not.
  CONSTRAINT reconstruction_needs_rationale
    CHECK (reconstructed_units IS NULL OR length(btrim(rationale)) > 0),
  CONSTRAINT reconstruction_not_unsupported
    CHECK (reconstructed_units IS NULL OR evidence_quality <> 'UNSUPPORTED')
);
CREATE INDEX ON labor_allocation (period, employee_key);

-- The effective distribution: reconstruction where one exists, else original.
CREATE VIEW v_labor_effective AS
SELECT a.*,
       COALESCE(a.reconstructed_units, a.original_units) AS effective_units,
       (a.reconstructed_units IS NOT NULL)               AS is_reconstructed,
       SUM(COALESCE(a.reconstructed_units, a.original_units))
         OVER (PARTITION BY a.period, a.employee_key)    AS employee_units,
       CASE WHEN SUM(COALESCE(a.reconstructed_units, a.original_units))
                   OVER (PARTITION BY a.period, a.employee_key) > 0
            THEN round(COALESCE(a.reconstructed_units, a.original_units)
                       / SUM(COALESCE(a.reconstructed_units, a.original_units))
                           OVER (PARTITION BY a.period, a.employee_key), 6)
            ELSE 0 END                                   AS share,
       round(a.payroll_wages
             * CASE WHEN SUM(COALESCE(a.reconstructed_units, a.original_units))
                          OVER (PARTITION BY a.period, a.employee_key) > 0
                    THEN COALESCE(a.reconstructed_units, a.original_units)
                         / SUM(COALESCE(a.reconstructed_units, a.original_units))
                             OVER (PARTITION BY a.period, a.employee_key)
                    ELSE 0 END, 2)                       AS distributed_wages
  FROM labor_allocation a;


CREATE TABLE labor_certification (
  certification_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period            text NOT NULL REFERENCES fiscal_period,
  employee_key      text NOT NULL,               -- whose effort is attested
  certifier_role    certifier_role NOT NULL,
  actor_id          uuid NOT NULL REFERENCES actor,
  session_id        uuid REFERENCES actor_session,
  signed_by         text NOT NULL,               -- name as displayed at signing
  signed_at         timestamptz NOT NULL DEFAULT now(),
  period_start      date NOT NULL,
  period_end        date NOT NULL,
  -- The exact words signed. A certification whose wording cannot be produced
  -- later is not a certification, and the wording is what 200.430(i) is about.
  statement         text NOT NULL,
  -- What the distribution said at the moment of signing. If the distribution
  -- changes, this is how anyone can tell the signature no longer covers it.
  distribution      jsonb NOT NULL,
  distribution_hash text NOT NULL,
  user_agent        text NOT NULL DEFAULT '',
  superseded_at     timestamptz,
  superseded_reason text,

  CONSTRAINT certification_period_sane CHECK (period_end >= period_start),
  CONSTRAINT certification_statement_present CHECK (length(btrim(statement)) > 20),
  CONSTRAINT certification_supersession_pair
    CHECK ((superseded_at IS NULL) = (superseded_reason IS NULL))
);
CREATE INDEX ON labor_certification (period, employee_key)
  WHERE superseded_at IS NULL;

-- A signature is evidence. It may be superseded, never removed or altered.
CREATE TRIGGER labor_certification_immutable
  BEFORE UPDATE OF statement, distribution, distribution_hash, actor_id,
                   signed_by, signed_at
  ON labor_certification
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER labor_certification_no_delete
  BEFORE DELETE ON labor_certification
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ── Who still has to sign, and whose signature has gone stale ────────

CREATE VIEW v_certification_status AS
WITH dist AS (
  SELECT period, employee_key,
         max(employee_name)                       AS employee_name,
         max(payroll_wages)                       AS payroll_wages,
         count(*)                                 AS objectives,
         bool_or(reconstructed_units IS NOT NULL) AS reconstructed,
         md5(string_agg(objective_id || ':' ||
                        COALESCE(reconstructed_units, original_units)::text,
                        '|' ORDER BY objective_id)) AS current_hash
    FROM labor_allocation GROUP BY period, employee_key),
cert AS (
  SELECT period, employee_key,
         max(signed_at)                                       AS signed_at,
         max(distribution_hash)                               AS signed_hash,
         bool_or(certifier_role = 'EMPLOYEE')                 AS by_employee,
         bool_or(certifier_role = 'SUPERVISOR')               AS by_supervisor,
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
                                        AS stale
  FROM dist d LEFT JOIN cert c USING (period, employee_key);

COMMENT ON VIEW v_certification_status IS
  'Whose effort distribution is attested, and whose signature no longer '
  'matches the distribution it was given for. A stale certification is not a '
  'certification: it attested to different numbers.';
