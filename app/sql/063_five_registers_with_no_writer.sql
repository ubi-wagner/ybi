-- Five registers with no writer, found by sweeping rather than by reading.
--
-- This shape has now appeared twelve times: `space_partition`,
-- `rate.superseded_by`, the three `evidence` fact columns, `award_budget_line`,
-- `donation_rate`, the three `lane_*` override tables — and now these. Every
-- one was found by somebody reading one area closely, and `CLAUDE.md` has
-- said "assume there is a fifth" for months, which is a note to self rather
-- than a check. A note to self is the hand-kept map applied to defects.
--
-- `tests/test_no_register_is_dead.py` is the check. It derives every table
-- and column from the database, asks what could write each, and fails on one
-- that something reads and nothing writes. Anything deliberately empty has
-- to be named in it **with a reason**, and an entry that is no longer needed
-- fails too — so the allowlist cannot quietly become the thing it replaced.
--
-- The sweep found five tables. They split three ways, and the split is the
-- interesting part: two get a writer, one gets dropped because the shape it
-- records cannot occur, and two get dropped because nothing reads them.

-- ── Kept, and given the writer it always needed ──────────────────────
--
-- `carve_out` is the worst instance of the shape in the system, because of
-- where the wrong answer lands. `POST /api/rates/compute` builds the 200.465
-- facilities carve-out from `v_facility_occupancy` and applies it to the
-- overhead pool **in memory** — correctly, and the rate it persists is right.
-- It just never wrote the carve-out down. Three things read this table:
-- `v_pool_balance`, `v_rate_buildup` and the `/review/rate` screen.
--
-- Measured against the live record at the moment this was written: the
-- computation carved **$932,254.78** out of a $1,678,057.27 overhead pool —
-- 3,000 of 5,400 usable square feet at Tech Block 5, tenant and vacant — and
-- `v_pool_balance` reported `carved = 0, allocable = 1,678,057.27` while
-- `/review/rate` showed no carve-out at all. The single largest adjustment in
-- the rate model, 55.6% of the pool it applies to, absent from the workpaper
-- an auditor reads, with a control-shaped view asserting the opposite.
--
-- That also breaks the rule the review screens are built on: *nothing on a
-- review screen is computed, every figure is read from the row it was
-- recorded in.* The row was never written, so the screen read zero.
--
-- The handler writes it now, inside the same turn that writes the rate and
-- against the same seal, so the disclosure cannot drift from the figure.
COMMENT ON TABLE carve_out IS
  'What was excluded from a pool and under which authority. Written by '
  'POST /api/rates/compute inside the turn that writes the rate, carrying '
  'the same seal, because a carve-out that is applied to a rate and not '
  'recorded beside it is an adjustment an auditor cannot see. It went '
  'unwritten for the life of the system while v_pool_balance and '
  '/review/rate read it and reported zero.';

-- `constraint_result` is the same shape with a different landing.
-- `GET /api/awards/{id}/trueup` counts blocking failures in this table and
-- answers `issuable: true, disposition: INVOICE_ISSUABLE` when it finds
-- none. It found none on all four awards because **nothing had ever written
-- a row** — `app/domain/awards.py::test_constraints()` is a complete engine
-- with no callers. So the system said an invoice was safe to issue *because
-- nobody had checked*: an empty set matching an empty set perfectly, which
-- `v_invoice_budget_check` already reports as `evaluable = false` rather
-- than as a pass, and which migration `029` fixed for the eleven controls.
-- The three-state, in the register as well as in the engine. A constraint
-- whose input is absent — an award with no cost classified to its objective
-- has no evidence grade to test — is recorded as unevaluable rather than as
-- failed or passed, the way v_award_budget_check and v_award_citation_check
-- already do it. `passed` stays false on those, so `blocked` still stops the
-- claim: a control that cannot be evaluated has not passed.
ALTER TABLE constraint_result
  ADD COLUMN IF NOT EXISTS evaluable boolean NOT NULL DEFAULT true;

ALTER TABLE constraint_result
  ADD CONSTRAINT unevaluable_never_passes
  CHECK (evaluable OR NOT passed);

COMMENT ON TABLE constraint_result IS
  'The contract constraint tests, evaluated. Written by the awards router '
  'through domain/awards.py::test_constraints. An award with no rows has '
  'not been tested, which is not the same as passing — /trueup reports '
  'evaluable = false for it rather than INVOICE_ISSUABLE.';

-- ── Dropped, because the shape it records cannot occur ───────────────
--
-- `ledger_revision` records a source line that changed after somebody judged
-- it, and `v_worklist` raised STALE_DECISION off it. The importer inserts
-- ledger lines `ON CONFLICT (line_id) DO NOTHING` and no code path updates
-- one, so a ledger line cannot change after it is written and a revision
-- cannot occur. This system models change by supersession — a new line, a
-- new judgment, the old one kept — and not by revision.
--
-- So STALE_DECISION is a worklist item that **doing the work cannot clear**,
-- which is the FACILITY_UNPARTITIONED defect: it teaches the reader the list
-- is wrong, and the next item they dismiss will be real. It is also
-- `invoice.milestone_id`'s case — a register for a contract shape this
-- system does not have — except that one is documented and this one was not.
--
-- Replaced rather than dropped and recreated: removing one arm of a UNION
-- changes no column, so the dependent views are untouched. The body is
-- lifted from the live definition with that arm cut out, never retyped.
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
  WHERE d.rate_missing;

-- ── Dropped, because nothing reads them either ───────────────────────
--
-- No writer, no reader, no view. `control_total` predates
-- `v_statement_reconciliation`, which is where control totals actually live
-- and which is computed rather than stored. `evidence_match_proposal`
-- predates `app/domain/evidence_match.py`, which proposes in the answer to
-- `/api/documents/propose` and deliberately persists nothing — *proposals
-- are never decisions*, so a proposal register would be a second place for
-- a judgment to appear to have been made.
--
-- Both are dropped rather than left. A table that looks usable and is filled
-- by nothing is an invitation to fill it again, and the next person to find
-- either would have had to work out for themselves which of the two live
-- mechanisms had replaced it.
DROP TABLE IF EXISTS control_total;
DROP TABLE IF EXISTS evidence_match_proposal;

-- Last, so the view above no longer depends on it.
DROP TABLE IF EXISTS ledger_revision;
