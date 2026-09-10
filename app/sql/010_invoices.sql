-- =====================================================================
-- Invoice register
--
-- The critical path for the America Makes restatement. Nothing resolves
-- without it, because a restated invoice has to be built against what the
-- original actually said.
--
-- What the three sample invoices show, and what this schema is shaped to
-- capture:
--
--   * They are line-itemised by budget category — Labor, Travel, Materials,
--     Consultant, ODCs, Indirects — and the controller's grant tabs track
--     only Labor. Invoice 10018 bills Labor 18,448.11 AND ODCs 19,145.79;
--     tracking labour alone misses more than half the invoice.
--
--   * Every line is QTY 1 at a RATE equal to the whole amount. There are no
--     hours and no rate, so nothing on the face of the invoice shows a
--     burdened labour rate. That is the "hybrid fixed-price and T&M" shape on
--     instruments that are cost reimbursement.
--
--   * Two of the three carry no Indirects line at all, and the third carries
--     a flat 3,000.00 that is the budgeted indirect straight-lined over the
--     period of performance (81,772.76 / 27 months = 3,028.62), not a rate
--     applied to incurred cost.
-- =====================================================================

CREATE TYPE invoice_category AS ENUM (
  'LABOR', 'FRINGE', 'TRAVEL', 'MATERIALS', 'CONSULTANT',
  'SUBAWARD', 'ODC', 'EQUIPMENT', 'INDIRECT', 'FEE', 'OTHER');

-- 001_core.sql already models an invoice, but as an OUTBOUND artefact: what
-- the system claims (direct_claimed, indirect_claimed, cost_share) against a
-- rate, and what it restates. That is the right model for a restatement and
-- the wrong one for an invoice as issued, which has a number on its face, a
-- purchase order, a bill-to, and lines by budget category.
--
-- They are the same object at two moments in its life, so this extends the
-- table rather than standing up a rival. awards.py and the true-up path keep
-- working unchanged.

ALTER TABLE invoice
  ADD COLUMN invoice_number   text,                 -- the number on the face
  ADD COLUMN objective_id     text REFERENCES cost_objective,
  ADD COLUMN due_on           date,
  ADD COLUMN service_from     date,
  ADD COLUMN service_to       date,
  ADD COLUMN terms            text NOT NULL DEFAULT '',
  ADD COLUMN po_number        text NOT NULL DEFAULT '',
  ADD COLUMN bill_to_name     text NOT NULL DEFAULT '',
  ADD COLUMN bill_to_address  text NOT NULL DEFAULT '',
  ADD COLUMN total            numeric(14,2),
  ADD COLUMN paid_on          date,
  ADD COLUMN paid_amount      numeric(14,2),
  ADD COLUMN source_document  text NOT NULL DEFAULT '',
  ADD COLUMN evidence_id      text REFERENCES evidence,
  ADD COLUMN note             text NOT NULL DEFAULT '',
  ADD COLUMN loaded_at        timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN loaded_by        text NOT NULL DEFAULT '';

-- An invoice can arrive before its award is registered. Requiring the award
-- first would mean holding evidence out of the system until paperwork catches
-- up, which is the wrong way round.
ALTER TABLE invoice ALTER COLUMN award_id DROP NOT NULL;

-- A credit memo returning over-collection is a distinct outcome from a
-- restatement, and Hybrid Phase 2 needs one.
ALTER TABLE invoice DROP CONSTRAINT invoice_status_check;
ALTER TABLE invoice ADD CONSTRAINT invoice_status_check
  CHECK (status IN ('DRAFT','ISSUED','RESTATED','WITHDRAWN',
                    'DEFICIENCY_ACKNOWLEDGED','CREDIT'));

CREATE UNIQUE INDEX invoice_number_key
  ON invoice (invoice_number) WHERE invoice_number IS NOT NULL;
CREATE INDEX ON invoice (objective_id, service_to);

-- Issued invoices are what the pass-through entity holds. Correct by issuing a
-- restatement or a credit, never by editing history.
CREATE TRIGGER invoice_no_delete
  BEFORE DELETE ON invoice
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


CREATE TABLE invoice_line (
  invoice_id        uuid NOT NULL REFERENCES invoice ON DELETE CASCADE,
  sequence          integer NOT NULL,
  activity          text NOT NULL DEFAULT '',     -- the ACTIVITY column
  description       text NOT NULL DEFAULT '',
  category          invoice_category NOT NULL,
  quantity          numeric(12,4) NOT NULL DEFAULT 1,
  rate              numeric(14,4) NOT NULL DEFAULT 0,
  amount            numeric(14,2) NOT NULL,
  -- Named individuals appear in the labour descriptions. Captured so a line
  -- can be tested against the labour distribution rather than taken on trust.
  personnel         text NOT NULL DEFAULT '',
  PRIMARY KEY (invoice_id, sequence)
);


-- The face of the invoice must foot. Deferred so the header and its lines
-- land together.
CREATE FUNCTION invoice_lines_must_foot() RETURNS trigger AS $$
DECLARE
  target uuid := COALESCE(NEW.invoice_id, OLD.invoice_id);
  lines  numeric(14,2);
  header numeric(14,2);
  n      integer;
BEGIN
  SELECT count(*), COALESCE(sum(amount), 0) INTO n, lines
    FROM invoice_line WHERE invoice_id = target;
  IF n = 0 THEN RETURN NULL; END IF;

  SELECT total INTO header FROM invoice WHERE invoice_id = target;
  IF header IS NULL THEN RETURN NULL; END IF;

  IF abs(lines - header) > 0.01 THEN
    RAISE EXCEPTION
      'Invoice % lines total % against a header total of %. An invoice that '
      'does not foot cannot be reconciled to cost.', target, lines, header
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER invoice_lines_foot
  AFTER INSERT OR UPDATE OR DELETE ON invoice_line
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION invoice_lines_must_foot();

CREATE CONSTRAINT TRIGGER invoice_header_foots
  AFTER INSERT OR UPDATE ON invoice
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION invoice_lines_must_foot();


-- ── What was billed, by category ─────────────────────────────────────

CREATE VIEW v_invoice_category AS
SELECT i.invoice_id, i.invoice_number, i.period, i.award_id,
       i.objective_id, i.status, i.invoice_date, i.service_to,
       i.po_number, i.total,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'LABOR'), 0)      AS labor,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'FRINGE'), 0)     AS fringe,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'TRAVEL'), 0)     AS travel,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'MATERIALS'), 0)  AS materials,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'CONSULTANT'), 0) AS consultant,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'SUBAWARD'), 0)   AS subaward,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'ODC'), 0)        AS odc,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'EQUIPMENT'), 0)  AS equipment,
       COALESCE(sum(l.amount) FILTER (WHERE l.category = 'INDIRECT'), 0)   AS indirect,
       -- Modified total direct cost as invoiced: everything direct except
       -- equipment, which 2 CFR 200.1 excludes from the base.
       COALESCE(sum(l.amount) FILTER (
         WHERE l.category IN ('LABOR','FRINGE','TRAVEL','MATERIALS',
                              'CONSULTANT','SUBAWARD','ODC')), 0)          AS mtdc_as_billed,
       (COALESCE(sum(l.amount) FILTER (WHERE l.category = 'INDIRECT'), 0) = 0)
                                                                           AS no_indirect_billed
  FROM invoice i
  LEFT JOIN invoice_line l USING (invoice_id)
 GROUP BY i.invoice_id, i.invoice_number, i.period, i.award_id,
          i.objective_id, i.status, i.invoice_date, i.service_to,
          i.po_number, i.total;

COMMENT ON VIEW v_invoice_category IS
  'Billed amounts by budget category. no_indirect_billed is the flag that '
  'matters most on a cost-reimbursement instrument: an invoice carrying no '
  'indirect line has foregone recovery outright, not merely under-recovered.';


-- The effective indirect rate each invoice actually carried, which is the
-- fastest way to see an instrument being billed as though it were fixed price.
CREATE VIEW v_invoice_effective_rate AS
SELECT invoice_id, invoice_number, period, award_id, objective_id,
       invoice_date, service_to,
       mtdc_as_billed, indirect,
       CASE WHEN mtdc_as_billed > 0
            THEN round(indirect / mtdc_as_billed, 6) ELSE NULL END AS effective_rate,
       no_indirect_billed
  FROM v_invoice_category;
