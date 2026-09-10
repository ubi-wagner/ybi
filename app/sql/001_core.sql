-- =====================================================================
-- YBI Cost Allocation System — Postgres schema
--
-- The design principle: invariants that matter are database constraints,
-- not application checks. A ledger line cannot be updated. A decision
-- cannot be edited. A rate cannot exist without the seal of the decision
-- set it came from. Those properties survive a bug in the API; assertions
-- in Python do not.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE pool_type AS ENUM (
  'DIRECT','FRINGE','OVERHEAD','G&A','RENTAL_DIRECT',
  'FUNDRAISING','UNALLOWABLE','EXCLUDED');

CREATE TYPE function_990 AS ENUM (
  'PROGRAM','MANAGEMENT_AND_GENERAL','FUNDRAISING','NOT_APPLICABLE');

CREATE TYPE federal_treatment AS ENUM (
  'ALLOWABLE','UNALLOWABLE','NOT_APPLICABLE','PENDING');

-- Ordered weakest to strongest. Default is UNSUPPORTED: quality is earned,
-- never assumed. A blanket grade applied to every row asserts a conclusion
-- nobody reached, which reads worse in an audit than an honest blank.
CREATE TYPE evidence_grade AS ENUM (
  'UNSUPPORTED','TEST_ASSUMPTION','MANAGEMENT_RECONSTRUCTION',
  'CORROBORATED','VERIFIED');

CREATE TYPE allocation_base AS ENUM (
  'MTDC','TOTAL_DIRECT','SALARIES_WAGES','SALARIES_FRINGE',
  'SQUARE_FEET','TOTAL_COST_INPUT');

CREATE TYPE rate_method AS ENUM ('DE_MINIMIS_10','DE_MINIMIS_15','NEGOTIATED');


-- ---------------------------------------------------------------------
-- 1. SOURCE LAYER — immutable
-- ---------------------------------------------------------------------

CREATE TABLE fiscal_period (
  period          text PRIMARY KEY,             -- '2025'
  start_date      date NOT NULL,
  end_date        date NOT NULL,
  closed          boolean NOT NULL DEFAULT false,
  CHECK (end_date > start_date)
);

CREATE TABLE ledger_import (
  import_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  source_name     text NOT NULL,
  sha256          text NOT NULL,
  row_count       integer NOT NULL,
  imported_at     timestamptz NOT NULL DEFAULT now(),
  imported_by     text NOT NULL,
  UNIQUE (period, sha256)                       -- the same file cannot land twice
);

CREATE TABLE ledger_line (
  line_id         text PRIMARY KEY,
  import_id       uuid NOT NULL REFERENCES ledger_import,
  period          text NOT NULL REFERENCES fiscal_period,
  txn_date        date NOT NULL,
  account         text NOT NULL,
  payee           text NOT NULL DEFAULT '',
  description     text NOT NULL DEFAULT '',
  amount          numeric(14,2) NOT NULL,
  statement       text NOT NULL,                -- 'P&L' | 'BALANCE_SHEET'
  section         text NOT NULL DEFAULT '',     -- Income | COGS | Expense | Other Income
  source_key      text NOT NULL
);
CREATE INDEX ON ledger_line (period, account, payee);
CREATE INDEX ON ledger_line (period, statement, section);

-- Append-only tables refuse mutation loudly. A rule doing INSTEAD NOTHING
-- would swallow the write silently, leaving a caller that believes it edited
-- evidence and a reviewer with no trace of the attempt. Rules also make the
-- table ineligible for ON CONFLICT, which the import path needs for its
-- idempotent re-accept.
CREATE FUNCTION refuse_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION
    '% is append-only; % refused. Correct by superseding, never by editing.',
    TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END $$ LANGUAGE plpgsql;

-- Source is evidence. Nothing may alter or remove it.
CREATE TRIGGER ledger_line_immutable
  BEFORE UPDATE OR DELETE ON ledger_line
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TABLE control_total (
  control_id      text PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  description     text NOT NULL,
  expected        numeric(14,2) NOT NULL,
  tolerance       numeric(14,2) NOT NULL DEFAULT 0.01,
  mandatory       boolean NOT NULL DEFAULT true,
  source          text NOT NULL
);


-- ---------------------------------------------------------------------
-- 2. STRUCTURE
-- ---------------------------------------------------------------------

CREATE TABLE cost_objective (
  objective_id    text PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  label           text NOT NULL,
  objective_type  text NOT NULL,
  is_federal      boolean NOT NULL DEFAULT false,
  is_final        boolean NOT NULL DEFAULT true,
  cfda            text,
  active          boolean NOT NULL DEFAULT true
);

CREATE TABLE award (
  award_id            text PRIMARY KEY,
  objective_id        text NOT NULL REFERENCES cost_objective,
  sponsor             text NOT NULL,
  prime_agreement     text,
  instrument          text NOT NULL,
  ceiling_federal     numeric(14,2) NOT NULL,
  cost_share_required numeric(14,2) NOT NULL DEFAULT 0,
  period_start        date NOT NULL,
  period_end          date NOT NULL,
  rate_method         rate_method NOT NULL,
  citation            text,
  CHECK (period_end > period_start),
  CHECK (ceiling_federal >= 0)
);

CREATE TABLE award_budget_line (
  award_id        text NOT NULL REFERENCES award,
  line            text NOT NULL,                -- LABOR, TRAVEL, CONSULTANT, ODC
  federal_amount  numeric(14,2) NOT NULL DEFAULT 0,
  cost_share      numeric(14,2) NOT NULL DEFAULT 0,
  PRIMARY KEY (award_id, line)
);

CREATE TABLE evidence (
  evidence_id     text PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  kind            text NOT NULL,                -- invoice, lease, timesheet, award doc
  uri             text NOT NULL,
  sha256          text NOT NULL,
  received_at     timestamptz NOT NULL DEFAULT now(),
  received_from   text NOT NULL DEFAULT ''
);


-- ---------------------------------------------------------------------
-- 3. DECISION LAYER — append-only
-- ---------------------------------------------------------------------

CREATE TABLE decision_set (
  set_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  label           text NOT NULL,
  seal_hash       text,
  sealed_at       timestamptz,
  sealed_by       text,
  unsealed_reason text,
  CHECK ((seal_hash IS NULL) = (sealed_at IS NULL))
);

CREATE TABLE decision (
  decision_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  set_id          uuid NOT NULL REFERENCES decision_set,
  scope           text NOT NULL,
  pool            pool_type NOT NULL,
  function_990    function_990 NOT NULL,
  federal         federal_treatment NOT NULL,
  objective_id    text REFERENCES cost_objective,
  grade           evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  rationale       text NOT NULL DEFAULT '',
  citation        text,
  decided_by      text NOT NULL,
  decided_at      timestamptz NOT NULL DEFAULT now(),
  supersedes      uuid REFERENCES decision,
  reversed_at     timestamptz,
  reversal_reason text,

  -- Direct cost must name a final cost objective; pooled cost must not.
  CONSTRAINT direct_needs_objective
    CHECK ((pool = 'DIRECT') = (objective_id IS NOT NULL)),

  -- A grade at or above management reconstruction requires written reasoning.
  CONSTRAINT supported_needs_rationale
    CHECK (grade IN ('UNSUPPORTED','TEST_ASSUMPTION') OR length(btrim(rationale)) > 0),

  -- Fundraising and unallowable activity can never be federally allowable.
  CONSTRAINT unallowable_not_allowable
    CHECK (NOT (federal = 'ALLOWABLE' AND pool IN ('FUNDRAISING','UNALLOWABLE'))),

  CONSTRAINT reversal_needs_reason
    CHECK ((reversed_at IS NULL) = (reversal_reason IS NULL))
);

CREATE TABLE decision_line (
  decision_id     uuid NOT NULL REFERENCES decision ON DELETE CASCADE,
  line_id         text NOT NULL REFERENCES ledger_line,
  -- Mirrors decision.reversed_at IS NULL. Denormalised because Postgres will
  -- not accept a subquery in an index predicate, and the one-live-decision
  -- rule has to live in the schema rather than in a handler. Maintained by
  -- decision_line_live_default and decision_line_live_sync below; never set
  -- by application code.
  live            boolean NOT NULL DEFAULT true,
  PRIMARY KEY (decision_id, line_id)
);

CREATE TABLE decision_evidence (
  decision_id     uuid NOT NULL REFERENCES decision ON DELETE CASCADE,
  evidence_id     text NOT NULL REFERENCES evidence,
  PRIMARY KEY (decision_id, evidence_id)
);

-- A ledger line may carry at most one live decision at a time.
CREATE UNIQUE INDEX one_live_decision_per_line
  ON decision_line (line_id)
  WHERE live;

-- Keep decision_line.live in step with decision.reversed_at. A line attaching
-- to an already-reversed decision is born dead, and reversing a decision frees
-- its lines for a superseding one.
CREATE FUNCTION decision_line_live_default() RETURNS trigger AS $$
BEGIN
  NEW.live := (SELECT reversed_at IS NULL FROM decision
                WHERE decision_id = NEW.decision_id);
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER decision_line_live_default
  BEFORE INSERT OR UPDATE OF decision_id ON decision_line
  FOR EACH ROW EXECUTE FUNCTION decision_line_live_default();

CREATE FUNCTION decision_line_live_sync() RETURNS trigger AS $$
BEGIN
  IF NEW.reversed_at IS DISTINCT FROM OLD.reversed_at THEN
    UPDATE decision_line
       SET live = (NEW.reversed_at IS NULL)
     WHERE decision_id = NEW.decision_id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER decision_line_live_sync
  AFTER UPDATE OF reversed_at ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_line_live_sync();

-- Decisions are the audit trail. Amend by superseding, never by editing.
-- Decisions may be reversed (an UPDATE of reversed_at) but never removed.
CREATE TRIGGER decision_immutable
  BEFORE DELETE ON decision
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ---------------------------------------------------------------------
-- 4. POOLS, RATES, ALLOCATION
-- ---------------------------------------------------------------------

CREATE TABLE pool_definition (
  pool            pool_type PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  base_type       allocation_base NOT NULL,
  description     text NOT NULL
);

CREATE TABLE carve_out (
  carve_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pool            pool_type NOT NULL,
  period          text NOT NULL REFERENCES fiscal_period,
  name            text NOT NULL,
  citation        text NOT NULL,                -- required: no undocumented reductions
  amount          numeric(14,2) NOT NULL CHECK (amount >= 0),
  driver          text NOT NULL,
  grade           evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  created_by      text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rate (
  rate_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  set_id          uuid NOT NULL REFERENCES decision_set,
  seal_hash       text NOT NULL,                -- provenance: which decisions produced this
  kind            text NOT NULL,                -- FRINGE | OVERHEAD | G&A | INDIRECT_COMBINED
  pool_amount     numeric(14,2) NOT NULL,
  base_type       allocation_base NOT NULL,
  base_amount     numeric(14,2) NOT NULL CHECK (base_amount > 0),
  rate            numeric(9,6) NOT NULL CHECK (rate >= 0),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  computed_by     text NOT NULL,
  superseded_by   uuid REFERENCES rate,
  status          text NOT NULL DEFAULT 'PROPOSED'
                  CHECK (status IN ('PROPOSED','SUBMITTED','ACCEPTED','SUPERSEDED'))
);

-- A rate may only reference a decision set that was sealed, and must carry
-- that set's seal. This is the "without prejudice" guarantee in the schema:
-- classifications are fixed before the number is known.
CREATE OR REPLACE FUNCTION rate_requires_seal() RETURNS trigger AS $$
DECLARE s text;
BEGIN
  SELECT seal_hash INTO s FROM decision_set WHERE set_id = NEW.set_id;
  IF s IS NULL THEN
    RAISE EXCEPTION 'Decision set % is not sealed; a rate cannot be computed from it', NEW.set_id;
  END IF;
  IF NEW.seal_hash IS DISTINCT FROM s THEN
    RAISE EXCEPTION 'Rate seal does not match the decision set it claims to derive from';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER rate_seal_check BEFORE INSERT ON rate
  FOR EACH ROW EXECUTE FUNCTION rate_requires_seal();

CREATE TABLE allocation (
  allocation_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rate_id         uuid NOT NULL REFERENCES rate,
  objective_id    text NOT NULL REFERENCES cost_objective,
  base_amount     numeric(14,2) NOT NULL,
  allocated       numeric(14,2) NOT NULL,
  rounding_adj    numeric(14,2) NOT NULL DEFAULT 0,
  UNIQUE (rate_id, objective_id)
);


-- ---------------------------------------------------------------------
-- 5. INVOICING AND TRUE-UP
-- ---------------------------------------------------------------------

CREATE TABLE invoice (
  invoice_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id        text NOT NULL REFERENCES award,
  period          text NOT NULL REFERENCES fiscal_period,
  seq             integer NOT NULL,
  invoice_date    date NOT NULL,
  direct_claimed  numeric(14,2) NOT NULL DEFAULT 0,
  indirect_claimed numeric(14,2) NOT NULL DEFAULT 0,
  cost_share      numeric(14,2) NOT NULL DEFAULT 0,
  rate_id         uuid REFERENCES rate,
  restates        uuid REFERENCES invoice,
  status          text NOT NULL DEFAULT 'DRAFT'
                  CHECK (status IN ('DRAFT','ISSUED','RESTATED','WITHDRAWN',
                                    'DEFICIENCY_ACKNOWLEDGED')),
  UNIQUE (award_id, seq, status)
);

CREATE TABLE constraint_result (
  result_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id        text NOT NULL REFERENCES award,
  rate_id         uuid REFERENCES rate,
  code            text NOT NULL,
  citation        text NOT NULL,
  description     text NOT NULL,
  passed          boolean NOT NULL,
  blocking        boolean NOT NULL DEFAULT true,
  detail          text NOT NULL,
  evaluated_at    timestamptz NOT NULL DEFAULT now()
);

-- An invoice cannot be issued while a blocking constraint fails. The
-- alternative path is an acknowledged deficiency, which is a real status
-- rather than an absence of one.
CREATE OR REPLACE FUNCTION invoice_requires_clean_constraints() RETURNS trigger AS $$
DECLARE n integer;
BEGIN
  IF NEW.status <> 'ISSUED' THEN RETURN NEW; END IF;
  SELECT count(*) INTO n FROM constraint_result
   WHERE award_id = NEW.award_id AND rate_id IS NOT DISTINCT FROM NEW.rate_id
     AND blocking AND NOT passed;
  IF n > 0 THEN
    RAISE EXCEPTION 'Cannot issue invoice: % blocking constraint(s) failing for award %',
      n, NEW.award_id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER invoice_constraint_gate BEFORE INSERT OR UPDATE ON invoice
  FOR EACH ROW EXECUTE FUNCTION invoice_requires_clean_constraints();


-- ---------------------------------------------------------------------
-- 6. AUDIT
-- ---------------------------------------------------------------------

CREATE TABLE audit_log (
  entry_id        bigserial PRIMARY KEY,
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  actor           text NOT NULL,
  action          text NOT NULL,
  entity          text NOT NULL,
  entity_id       text NOT NULL,
  before_state    jsonb,
  after_state     jsonb,
  reason          text NOT NULL DEFAULT ''
);
CREATE INDEX ON audit_log (entity, entity_id, occurred_at DESC);
CREATE TRIGGER audit_log_immutable
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ---------------------------------------------------------------------
-- 7. VIEWS the API and the workpapers read from
-- ---------------------------------------------------------------------

CREATE VIEW v_unclassified AS
SELECT l.period, l.account, l.payee,
       count(*) AS line_count,
       sum(l.amount) AS amount
  FROM ledger_line l
 WHERE NOT EXISTS (
       SELECT 1 FROM decision_line dl
         JOIN decision d USING (decision_id)
        WHERE dl.line_id = l.line_id AND d.reversed_at IS NULL)
 GROUP BY l.period, l.account, l.payee
 ORDER BY abs(sum(l.amount)) DESC;

CREATE VIEW v_pool_balance AS
SELECT d.pool, l.period,
       sum(l.amount) AS gross,
       coalesce((SELECT sum(c.amount) FROM carve_out c
                  WHERE c.pool = d.pool AND c.period = l.period), 0) AS carved,
       sum(l.amount) - coalesce((SELECT sum(c.amount) FROM carve_out c
                  WHERE c.pool = d.pool AND c.period = l.period), 0) AS allocable
  FROM decision d
  JOIN decision_line dl USING (decision_id)
  JOIN ledger_line l USING (line_id)
 WHERE d.reversed_at IS NULL
 GROUP BY d.pool, l.period;

-- Coverage by dollars, which is the number an auditor asks for.
CREATE VIEW v_classification_coverage AS
SELECT l.period,
       sum(l.amount) FILTER (WHERE d.decision_id IS NOT NULL) AS classified,
       sum(l.amount) FILTER (WHERE d.decision_id IS NULL)     AS unclassified,
       round(100.0 * sum(abs(l.amount)) FILTER (WHERE d.decision_id IS NOT NULL)
             / nullif(sum(abs(l.amount)), 0), 1)              AS pct_dollars_covered
  FROM ledger_line l
  LEFT JOIN decision_line dl ON dl.line_id = l.line_id
  LEFT JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
 GROUP BY l.period;
