-- =====================================================================
-- YBI Cost Allocation System — schema v2
--   1. Import staging (QuickBooks and anything else)
--   2. Scenario lanes
--   3. Documents, notes and evidence binding
--
-- Depends on schema.sql.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. IMPORT STAGING
--
-- Two-phase commit. A file lands in staging, is parsed under a named
-- profile, and is previewed against control totals. Only an import that
-- ties is promoted into ledger_line. Nothing is written on the strength
-- of "the numbers looked about right".
-- ---------------------------------------------------------------------

CREATE TYPE import_status AS ENUM
  ('UPLOADED','PARSED','PREVIEWED','ACCEPTED','REJECTED','SUPERSEDED');

CREATE TYPE source_report AS ENUM
  ('GENERAL_LEDGER','PROFIT_LOSS','BALANCE_SHEET','TRIAL_BALANCE',
   'TIME_ACTIVITY','PAYROLL_REGISTER','AR_AGING','AP_AGING',
   'CHART_OF_ACCOUNTS','CUSTOMER_LIST','FIXED_ASSETS','MANUAL');

-- A profile is the recipe for reading one export shape. QBO renames columns
-- between versions and between the CSV and Excel export paths, so the
-- mapping is data. A new shape is configuration, not a deploy.
CREATE TABLE import_profile (
  profile_id      text PRIMARY KEY,             -- 'qbo-gl-v1'
  report          source_report NOT NULL,
  system_name     text NOT NULL DEFAULT 'QuickBooks Online',
  column_aliases  jsonb NOT NULL,               -- {"date":["date","txn date"], ...}
  options         jsonb NOT NULL DEFAULT '{}',  -- debit_credit_columns, date_formats, ...
  notes           text NOT NULL DEFAULT '',
  created_at      timestamptz NOT NULL DEFAULT now(),
  created_by      text NOT NULL
);

CREATE TABLE staging_batch (
  batch_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  report          source_report NOT NULL,
  profile_id      text REFERENCES import_profile,
  original_name   text NOT NULL,
  storage_uri     text NOT NULL,                -- the untouched file, kept forever
  sha256          text NOT NULL,
  byte_size       bigint NOT NULL,
  status          import_status NOT NULL DEFAULT 'UPLOADED',
  uploaded_by     text NOT NULL,
  uploaded_at     timestamptz NOT NULL DEFAULT now(),
  parsed_at       timestamptz,
  accepted_at     timestamptz,
  accepted_by     text,
  rejected_reason text,
  supersedes      uuid REFERENCES staging_batch,
  UNIQUE (period, report, sha256),              -- the same export cannot land twice
  CHECK ((status = 'REJECTED') = (rejected_reason IS NOT NULL))
);

CREATE TABLE staging_line (
  staging_id      bigserial PRIMARY KEY,
  batch_id        uuid NOT NULL REFERENCES staging_batch ON DELETE CASCADE,
  row_number      integer NOT NULL,
  natural_key     text NOT NULL,                -- composed; QBO reports carry no txn id
  account         text NOT NULL DEFAULT '',
  txn_date        date,
  txn_type        text NOT NULL DEFAULT '',
  doc_num         text NOT NULL DEFAULT '',
  name            text NOT NULL DEFAULT '',
  memo            text NOT NULL DEFAULT '',
  split_account   text NOT NULL DEFAULT '',
  amount          numeric(14,2) NOT NULL DEFAULT 0,
  class_name      text NOT NULL DEFAULT '',
  location        text NOT NULL DEFAULT '',
  customer_job    text NOT NULL DEFAULT '',     -- raw "Customer:Job"
  objective_hint  text NOT NULL DEFAULT '',     -- segment after the colon
  parse_warning   text,
  matched_line_id text REFERENCES ledger_line   -- set when re-importing a period
);
CREATE INDEX ON staging_line (batch_id, account);
CREATE INDEX ON staging_line (natural_key);
CREATE INDEX ON staging_line (batch_id) WHERE parse_warning IS NOT NULL;

-- QBO prints its own "Total for <account>" rows. Reconciling parsed lines
-- against them proves the parser dropped nothing — a free internal control
-- that catches nearly every parsing mistake before a human sees the data.
CREATE TABLE staging_subtotal (
  batch_id        uuid NOT NULL REFERENCES staging_batch ON DELETE CASCADE,
  account         text NOT NULL,
  printed_total   numeric(14,2) NOT NULL,
  parsed_total    numeric(14,2) NOT NULL,
  PRIMARY KEY (batch_id, account)
);

CREATE VIEW v_staging_reconciliation AS
SELECT b.batch_id, b.original_name, b.status,
       count(*)                                   AS subtotal_rows,
       count(*) FILTER (WHERE abs(s.parsed_total - s.printed_total) > 0.005) AS mismatches,
       sum(s.printed_total)                       AS printed,
       sum(s.parsed_total)                        AS parsed,
       sum(s.parsed_total - s.printed_total)      AS variance
  FROM staging_batch b JOIN staging_subtotal s USING (batch_id)
 GROUP BY b.batch_id, b.original_name, b.status;

-- Acceptance gate: an import is promotable only when it ties.
CREATE OR REPLACE FUNCTION staging_accept_gate() RETURNS trigger AS $$
DECLARE bad integer;
BEGIN
  IF NEW.status <> 'ACCEPTED' THEN RETURN NEW; END IF;
  SELECT count(*) INTO bad FROM staging_subtotal
   WHERE batch_id = NEW.batch_id
     AND abs(parsed_total - printed_total) > 0.005;
  IF bad > 0 THEN
    RAISE EXCEPTION 'Import % cannot be accepted: % account subtotal(s) do not tie',
      NEW.original_name, bad;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER staging_accept_check BEFORE UPDATE ON staging_batch
  FOR EACH ROW EXECUTE FUNCTION staging_accept_gate();

-- Re-importing a period: what changed since last time. Amended QBO
-- transactions are the normal case, and they must be visible rather than
-- silently overwriting a line someone has already classified.
CREATE TABLE ledger_revision (
  revision_id     bigserial PRIMARY KEY,
  line_id         text NOT NULL REFERENCES ledger_line,
  batch_id        uuid NOT NULL REFERENCES staging_batch,
  change          text NOT NULL CHECK (change IN ('ADDED','AMOUNT_CHANGED','REMOVED','FIELD_CHANGED')),
  before_state    jsonb,
  after_state     jsonb,
  affects_decision uuid REFERENCES decision,     -- classification invalidated by the change
  detected_at     timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- 2. SCENARIO LANES
--
-- Two different activities look alike and must not be treated alike:
--
--   Assumption sensitivity  — "what if tenant share is 40% vs 55%"
--       Legitimate, expected, and evidence-neutral. Cheap and unrestricted.
--
--   Classification override — "reclassify these lines and see what happens"
--       Also legitimate as analysis, but it is exactly the behaviour that
--       would hollow out the sealed-decision guarantee if it were invisible.
--
-- So both are supported, and they are recorded differently. Assumption
-- variants are free. Classification overrides are counted, reasoned, and
-- disclosed in the audit package alongside which lane was submitted and why.
-- Exploration stays possible; quiet shopping does not.
-- ---------------------------------------------------------------------

CREATE TYPE lane_kind AS ENUM ('BASELINE','CANDIDATE','SANDBOX');

CREATE TABLE lane (
  lane_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  name            text NOT NULL,
  kind            lane_kind NOT NULL DEFAULT 'SANDBOX',
  parent_lane     uuid REFERENCES lane,
  set_id          uuid NOT NULL REFERENCES decision_set,
  purpose         text NOT NULL,                -- required: why does this lane exist
  created_by      text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  archived_at     timestamptz,
  UNIQUE (period, name)
);

-- Exactly one baseline per period: the lane that will actually be submitted.
CREATE UNIQUE INDEX one_baseline_per_period
  ON lane (period) WHERE kind = 'BASELINE' AND archived_at IS NULL;

-- Assumptions: free to vary, no disclosure burden.
CREATE TABLE lane_assumption (
  lane_id         uuid NOT NULL REFERENCES lane ON DELETE CASCADE,
  key             text NOT NULL,                -- 'facilities_allocable_pct'
  value           numeric(12,6) NOT NULL,
  basis           text NOT NULL DEFAULT '',     -- 'square-footage schedule rev 2'
  grade           evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  PRIMARY KEY (lane_id, key)
);

-- Classification overrides: copy-on-write against the parent lane, and each
-- one carries a reason. This is the table an auditor is entitled to read.
CREATE TABLE lane_decision_override (
  override_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lane_id         uuid NOT NULL REFERENCES lane ON DELETE CASCADE,
  base_decision   uuid REFERENCES decision,     -- null when the lane adds a new decision
  pool            pool_type NOT NULL,
  function_990    function_990 NOT NULL,
  federal         federal_treatment NOT NULL,
  objective_id    text REFERENCES cost_objective,
  grade           evidence_grade NOT NULL DEFAULT 'UNSUPPORTED',
  reason          text NOT NULL,
  created_by      text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT override_needs_reason CHECK (length(btrim(reason)) > 0),
  CONSTRAINT direct_needs_objective_ovr
    CHECK ((pool = 'DIRECT') = (objective_id IS NOT NULL))
);

CREATE TABLE lane_override_line (
  override_id     uuid NOT NULL REFERENCES lane_decision_override ON DELETE CASCADE,
  line_id         text NOT NULL REFERENCES ledger_line,
  PRIMARY KEY (override_id, line_id)
);

-- A sandbox lane can never produce a submittable rate. Promotion to
-- CANDIDATE or BASELINE is a deliberate, logged act.
CREATE TABLE lane_promotion (
  promotion_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lane_id         uuid NOT NULL REFERENCES lane,
  from_kind       lane_kind NOT NULL,
  to_kind         lane_kind NOT NULL,
  rationale       text NOT NULL,
  approved_by     text NOT NULL,
  approved_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT promotion_needs_rationale CHECK (length(btrim(rationale)) > 0)
);

ALTER TABLE rate ADD COLUMN lane_id uuid REFERENCES lane;

CREATE OR REPLACE FUNCTION rate_lane_gate() RETURNS trigger AS $$
DECLARE k lane_kind;
BEGIN
  IF NEW.lane_id IS NULL THEN RETURN NEW; END IF;
  SELECT kind INTO k FROM lane WHERE lane_id = NEW.lane_id;
  IF k = 'SANDBOX' AND NEW.status <> 'PROPOSED' THEN
    RAISE EXCEPTION 'A sandbox lane cannot produce a submitted rate. Promote it first.';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER rate_lane_check BEFORE INSERT OR UPDATE ON rate
  FOR EACH ROW EXECUTE FUNCTION rate_lane_gate();

-- Build-up view: the effect of classifications on the pools, per lane,
-- without touching anything. This is the read-only "what does this do" screen.
CREATE VIEW v_lane_buildup AS
SELECT l.lane_id, l.name, l.kind,
       coalesce(o.pool, d.pool)                       AS pool,
       sum(ll.amount)                                 AS amount,
       count(DISTINCT ll.line_id)                     AS lines,
       count(DISTINCT o.override_id)                  AS overridden_decisions
  FROM lane l
  JOIN decision d           ON d.set_id = l.set_id AND d.reversed_at IS NULL
  JOIN decision_line dl     ON dl.decision_id = d.decision_id
  JOIN ledger_line ll       ON ll.line_id = dl.line_id
  LEFT JOIN lane_override_line ol ON ol.line_id = ll.line_id
  LEFT JOIN lane_decision_override o
         ON o.override_id = ol.override_id AND o.lane_id = l.lane_id
 GROUP BY l.lane_id, l.name, l.kind, coalesce(o.pool, d.pool);

-- Disclosure: what the audit package prints about lane activity.
CREATE VIEW v_lane_disclosure AS
SELECT l.period, l.lane_id, l.name, l.kind, l.purpose, l.created_by, l.created_at,
       count(DISTINCT o.override_id) AS classification_overrides,
       count(DISTINCT a.key)         AS assumption_variants,
       (SELECT rationale FROM lane_promotion p
         WHERE p.lane_id = l.lane_id ORDER BY approved_at DESC LIMIT 1) AS promotion_rationale
  FROM lane l
  LEFT JOIN lane_decision_override o ON o.lane_id = l.lane_id
  LEFT JOIN lane_assumption a        ON a.lane_id = l.lane_id
 GROUP BY l.period, l.lane_id, l.name, l.kind, l.purpose, l.created_by, l.created_at;


-- ---------------------------------------------------------------------
-- 3. DOCUMENTS, NOTES, EVIDENCE BINDING
--
-- Content-addressed storage. The same invoice attached to six ledger lines
-- is stored once. Attachment is polymorphic so a document can hang off a
-- ledger line, a decision, a carve-out, an award, an objective or an invoice
-- without a table per relationship.
-- ---------------------------------------------------------------------

ALTER TABLE evidence
  ADD COLUMN byte_size    bigint,
  ADD COLUMN mime_type    text,
  ADD COLUMN page_count   integer,
  ADD COLUMN extracted_text text,               -- OCR / text layer, for search
  ADD COLUMN doc_date     date,                 -- date on the document itself
  ADD COLUMN doc_amount   numeric(14,2),        -- amount parsed from the document
  ADD COLUMN vendor_name  text,
  ADD COLUMN ingest_channel text NOT NULL DEFAULT 'UPLOAD'
      CHECK (ingest_channel IN ('UPLOAD','EMAIL','DRIVE_SYNC','SCAN','API'));

CREATE UNIQUE INDEX evidence_content_address ON evidence (sha256);
CREATE INDEX evidence_fts ON evidence
  USING gin (to_tsvector('english', coalesce(extracted_text,'') || ' ' || coalesce(vendor_name,'')));

CREATE TYPE attach_target AS ENUM
  ('LEDGER_LINE','DECISION','CARVE_OUT','OBJECTIVE','AWARD','INVOICE','LANE','RATE');

CREATE TABLE attachment (
  attachment_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id     text NOT NULL REFERENCES evidence,
  target_type     attach_target NOT NULL,
  target_id       text NOT NULL,
  relevance       text NOT NULL DEFAULT '',     -- "invoice supporting the charge"
  attached_by     text NOT NULL,
  attached_at     timestamptz NOT NULL DEFAULT now(),
  detached_at     timestamptz,
  UNIQUE (evidence_id, target_type, target_id)
);
CREATE INDEX ON attachment (target_type, target_id) WHERE detached_at IS NULL;

CREATE TABLE note (
  note_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target_type     attach_target NOT NULL,
  target_id       text NOT NULL,
  body            text NOT NULL,
  author          text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  in_reply_to     uuid REFERENCES note,
  resolved_at     timestamptz,
  resolved_by     text,
  is_workpaper    boolean NOT NULL DEFAULT false,  -- prints in the audit package
  CONSTRAINT note_not_empty CHECK (length(btrim(body)) > 0)
);
CREATE INDEX ON note (target_type, target_id, created_at DESC);

-- Bulk evidence: drop a folder of invoices and let the system propose which
-- ledger lines each supports, on amount, date proximity and vendor. Proposals
-- only — a human confirms, exactly as with classification.
CREATE TABLE evidence_match_proposal (
  proposal_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id     text NOT NULL REFERENCES evidence,
  line_id         text NOT NULL REFERENCES ledger_line,
  score           numeric(5,4) NOT NULL CHECK (score BETWEEN 0 AND 1),
  basis           jsonb NOT NULL,               -- {"amount":"exact","date_days":3,...}
  status          text NOT NULL DEFAULT 'PROPOSED'
                  CHECK (status IN ('PROPOSED','CONFIRMED','REJECTED')),
  decided_by      text,
  decided_at      timestamptz,
  UNIQUE (evidence_id, line_id)
);

-- Evidence coverage by dollars — the number an auditor asks for, and the one
-- that tells Tom when he can stop.
CREATE VIEW v_evidence_coverage AS
SELECT l.period,
       d.pool,
       sum(abs(l.amount))                                        AS dollars,
       sum(abs(l.amount)) FILTER (WHERE a.attachment_id IS NOT NULL) AS documented,
       round(100.0 * sum(abs(l.amount)) FILTER (WHERE a.attachment_id IS NOT NULL)
             / nullif(sum(abs(l.amount)), 0), 1)                 AS pct_documented
  FROM ledger_line l
  JOIN decision_line dl ON dl.line_id = l.line_id
  JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
  LEFT JOIN attachment a
         ON a.target_type = 'LEDGER_LINE' AND a.target_id = l.line_id
        AND a.detached_at IS NULL
 GROUP BY l.period, d.pool;

-- A VERIFIED grade requires an attachment. The schema.sql CHECK could not
-- express this because it spans tables; the trigger can.
CREATE OR REPLACE FUNCTION verified_requires_evidence() RETURNS trigger AS $$
DECLARE n integer;
BEGIN
  IF NEW.grade <> 'VERIFIED' THEN RETURN NEW; END IF;
  SELECT count(*) INTO n FROM decision_evidence WHERE decision_id = NEW.decision_id;
  IF n = 0 THEN
    RAISE EXCEPTION 'A VERIFIED classification requires at least one attached document.';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER decision_verified_check
  AFTER INSERT OR UPDATE ON decision
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION verified_requires_evidence();
