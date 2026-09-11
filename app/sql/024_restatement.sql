-- =====================================================================
-- Restating an invoice, and the driver behind a 2026 split
--
-- The restatement is what this whole system was built to produce. Everything
-- upstream — the classification, the seal, the rate, the allocation — exists
-- so that a number put in front of NCDMM can be traced back to a judgment
-- somebody signed.
--
-- Three properties the schema holds rather than the handler.
--
--   A restatement carries the seal of the rate it used. The same guarantee as
--   the rate itself: change a classification and the restatement built on it
--   is superseded, not quietly stale.
--
--   A restatement is a PROPOSAL until a sponsor accepts it. Neither America
--   Makes agreement was billed under a provisional rate, so moving off the de
--   minimis election is a change of basis that needs a written modification
--   under §4.4 — not a corrected invoice sent in the post. The status column
--   is what stops a proposal being mistaken for a position.
--
--   Over-collection is not a negotiating position. Where the supported amount
--   is below what was billed, the difference is returnable, and the schema
--   records it as such rather than letting it net silently against an
--   under-recovery somewhere else.
-- =====================================================================

CREATE TYPE restatement_status AS ENUM (
  'PROPOSED',      -- computed, nobody has seen it
  'SUBMITTED',     -- put to the sponsor
  'ACCEPTED',      -- sponsor agreed, in writing
  'REJECTED',
  'SUPERSEDED');   -- the rate or the classifications moved underneath it

CREATE TABLE restatement (
  restatement_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period           text NOT NULL REFERENCES fiscal_period,
  award_id         text REFERENCES award,
  objective_id     text NOT NULL REFERENCES cost_objective,
  rate_id          uuid NOT NULL REFERENCES rate,
  seal_hash        text NOT NULL,
  status           restatement_status NOT NULL DEFAULT 'PROPOSED',

  invoices         integer NOT NULL DEFAULT 0,
  billed_total     numeric(14,2) NOT NULL DEFAULT 0,
  base_total       numeric(14,2) NOT NULL DEFAULT 0,
  indirect_billed  numeric(14,2) NOT NULL DEFAULT 0,
  indirect_supported numeric(14,2) NOT NULL DEFAULT 0,
  -- Split deliberately: an under-recovery on one invoice and an
  -- over-collection on another are two different conversations, and a net
  -- figure hides both.
  under_recovered  numeric(14,2) NOT NULL DEFAULT 0,
  over_collected   numeric(14,2) NOT NULL DEFAULT 0,
  ceiling_headroom numeric(14,2),
  capped_by_ceiling boolean NOT NULL DEFAULT false,

  basis            text NOT NULL,
  modification_ref text NOT NULL DEFAULT '',
  computed_by      text NOT NULL DEFAULT '',
  computed_at      timestamptz NOT NULL DEFAULT now(),
  submitted_at     timestamptz,
  decided_at       timestamptz,
  decided_note     text NOT NULL DEFAULT '',

  CONSTRAINT restatement_basis_present CHECK (length(btrim(basis)) > 20),
  CONSTRAINT restatement_variances_are_positive
    CHECK (under_recovered >= 0 AND over_collected >= 0),
  -- Accepting a change of basis without naming the modification that
  -- authorised it is the single thing most likely to become a finding.
  CONSTRAINT acceptance_names_its_modification
    CHECK (status <> 'ACCEPTED' OR length(btrim(modification_ref)) > 0)
);
CREATE INDEX ON restatement (period, objective_id)
  WHERE status <> 'SUPERSEDED';

CREATE TRIGGER restatement_immutable
  BEFORE UPDATE OF period, award_id, objective_id, rate_id, seal_hash,
                   billed_total, base_total, indirect_supported, computed_at
  ON restatement FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TRIGGER restatement_no_delete
  BEFORE DELETE ON restatement FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- A restatement may only use a rate that came from a sealed set, and must
-- carry that rate's seal. The same gate the rate itself passes, one step
-- further down — so a number in front of a sponsor is traceable to the
-- judgments that produced it without anybody being asked to promise it.
CREATE OR REPLACE FUNCTION restatement_requires_sealed_rate() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  SELECT rate.seal_hash, rate.status INTO r FROM rate
   WHERE rate.rate_id = NEW.rate_id;
  IF r IS NULL THEN
    RAISE EXCEPTION 'No such rate.' USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF r.seal_hash IS DISTINCT FROM NEW.seal_hash THEN
    RAISE EXCEPTION
      'A restatement must carry the seal of the rate it used. The rate carries '
      '%, the restatement claims %.', r.seal_hash, NEW.seal_hash;
  END IF;
  IF r.status = 'SUPERSEDED' THEN
    RAISE EXCEPTION
      'That rate has been superseded. Recompute the rate before restating '
      'anything on it.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER restatement_seal_gate
  BEFORE INSERT ON restatement
  FOR EACH ROW EXECUTE FUNCTION restatement_requires_sealed_rate();


-- One row per invoice: what it billed, what the rate supports, and the
-- difference in the direction it actually runs.
CREATE TABLE restatement_line (
  line_id          bigserial PRIMARY KEY,
  restatement_id   uuid NOT NULL REFERENCES restatement ON DELETE CASCADE,
  invoice_id       uuid NOT NULL REFERENCES invoice,
  invoice_number   text NOT NULL DEFAULT '',
  invoice_date     date,
  base_as_billed   numeric(14,2) NOT NULL,
  indirect_billed  numeric(14,2) NOT NULL,
  indirect_supported numeric(14,2) NOT NULL,
  variance         numeric(14,2) NOT NULL,
  direction        text NOT NULL
                   CHECK (direction IN ('UNDER', 'OVER', 'EVEN')),
  finding          text NOT NULL DEFAULT '',
  UNIQUE (restatement_id, invoice_id)
);


CREATE VIEW v_restatement AS
SELECT r.*, a.sponsor, a.ceiling_federal, a.cost_share_required,
       a.rate_method::text                              AS billed_under,
       rt.kind                                          AS rate_kind,
       rt.rate                                          AS rate_applied,
       rt.base_type::text                               AS rate_base,
       (r.under_recovered - r.over_collected)           AS net_movement,
       (SELECT count(*) FROM restatement_line l
         WHERE l.restatement_id = r.restatement_id)     AS lines
  FROM restatement r
  LEFT JOIN award a ON a.award_id = r.award_id
  JOIN rate rt ON rt.rate_id = r.rate_id;

COMMENT ON VIEW v_restatement IS
  'A restatement proposal against the award it belongs to. net_movement is '
  'shown for convenience and is never the answer on its own: an '
  'under-recovery to claim and an over-collection to return are two separate '
  'conversations with a sponsor.';


-- ── The 2026 chart: a split is a judgment ────────────────────────────
--
-- crosswalk.py maps all 85 of the 2025 accounts into the 2026 chart and
-- flags 24 of them as splits — one old account whose balance has to be
-- divided across several new ones. Each of those is a real judgment about
-- what drives the division, and until the driver is written down the
-- crosswalk cannot be said to carry every dollar deliberately rather than
-- arithmetically.

CREATE TABLE chart_split_driver (
  driver_id       bigserial PRIMARY KEY,
  period          text NOT NULL REFERENCES fiscal_period,
  source_account  text NOT NULL,
  target_account  text NOT NULL,
  share           numeric(8,6) NOT NULL,
  driver          text NOT NULL,
  citation        text NOT NULL DEFAULT '',
  evidence_id     text REFERENCES evidence,
  recorded_by     uuid REFERENCES actor,
  recorded_name   text NOT NULL DEFAULT '',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  superseded_at   timestamptz,

  CONSTRAINT split_share_sane CHECK (share > 0 AND share <= 1),
  CONSTRAINT split_driver_present CHECK (length(btrim(driver)) > 20)
);
CREATE UNIQUE INDEX one_live_split_driver
  ON chart_split_driver (period, source_account, target_account)
  WHERE superseded_at IS NULL;

CREATE TRIGGER chart_split_driver_immutable
  BEFORE UPDATE OF period, source_account, target_account, share, driver,
                   recorded_by, recorded_at
  ON chart_split_driver FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- A split's shares must come to one, or the account does not survive the
-- crosswalk whole. Deferred, so a split can be entered a row at a time.
CREATE OR REPLACE FUNCTION split_shares_must_total_one() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE total numeric(10,6);
BEGIN
  SELECT COALESCE(sum(share), 0) INTO total FROM chart_split_driver
   WHERE period = NEW.period AND source_account = NEW.source_account
     AND superseded_at IS NULL;
  IF total = 0 THEN RETURN NULL; END IF;
  IF abs(total - 1) > 0.0001 THEN
    RAISE EXCEPTION
      'The split of % comes to %, not 1. An account that does not divide '
      'whole loses or invents money in the crosswalk.',
      NEW.source_account, total;
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER split_shares_total_one
  AFTER INSERT OR UPDATE ON chart_split_driver
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION split_shares_must_total_one();


CREATE VIEW v_chart_split_status AS
SELECT d.period, d.source_account,
       count(*)                                      AS targets,
       sum(d.share)                                  AS total_share,
       (abs(sum(d.share) - 1) <= 0.0001)             AS divides_whole,
       bool_and(length(btrim(d.driver)) > 20)        AS every_target_has_a_driver,
       count(*) FILTER (WHERE d.evidence_id IS NOT NULL) AS with_evidence,
       max(d.recorded_name)                          AS recorded_by,
       max(d.recorded_at)                            AS recorded_at,
       (SELECT COALESCE(sum(abs(l.amount)), 0) FROM ledger_line l
         WHERE l.period = d.period
           AND l.account LIKE '%' || d.source_account || '%')  AS amount_2025
  FROM chart_split_driver d
 WHERE d.superseded_at IS NULL
 GROUP BY d.period, d.source_account;

COMMENT ON VIEW v_chart_split_status IS
  'Each 2025 account that divides across several 2026 accounts: whether it '
  'divides whole, and whether every part names the driver that divides it. '
  'A split without a driver is arithmetic wearing the clothes of a judgment.';
