-- =====================================================================
-- Segmentation
--
-- A booked entry is often not one thing. `5250 Meals & Entertainment` mixes
-- allowable business meals with unallowable entertainment; `5227 Portfolio
-- consulting` is $588,539 across 442 lines with no objective signal and is
-- almost certainly part direct and part G&A; a single vendor invoice can
-- carry travel, materials and labour on one line.
--
-- Forcing such a line into one pool because the bookkeeping entry was
-- aggregated is the mistake this table exists to prevent. From the Foundation
-- spec: "A mixed GL or revenue source must never be forced into one
-- analytical classification simply because the original bookkeeping entry was
-- aggregated. Segmentation is the canonical mechanism."
--
-- Three properties make it safe to rely on:
--
--   1. The source is untouched. ledger_line stays append-only and immutable;
--      a segment is an analytical layer above it, never an edit to it.
--   2. Segments reconcile. The live segments of a line sum to the line's
--      booked amount within a cent, enforced at COMMIT. A segmentation that
--      loses or invents money is refused.
--   3. Segments are reversible under audit, never deleted. Reversing restores
--      the parent line as the analytical unit.
-- =====================================================================

CREATE TABLE ledger_segment (
  segment_id      text PRIMARY KEY,
  line_id         text NOT NULL REFERENCES ledger_line,
  period          text NOT NULL REFERENCES fiscal_period,
  amount          numeric(14,2) NOT NULL,
  label           text NOT NULL,               -- what this part of the line is
  rationale       text NOT NULL,
  citation        text,
  created_by      text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  batch_key       text NOT NULL,               -- one segmentation of one group
  reversed_at     timestamptz,
  reversed_by     text,
  reversal_reason text,

  CONSTRAINT segment_needs_rationale
    CHECK (length(btrim(rationale)) > 0),
  CONSTRAINT segment_reversal_needs_reason
    CHECK ((reversed_at IS NULL) = (reversal_reason IS NULL)),
  CONSTRAINT segment_reversal_needs_actor
    CHECK ((reversed_at IS NULL) = (reversed_by IS NULL))
);
CREATE INDEX ON ledger_segment (line_id) WHERE reversed_at IS NULL;
CREATE INDEX ON ledger_segment (period, batch_key);

-- Segments are analysis, and analysis is evidence. Reverse, never remove.
CREATE TRIGGER ledger_segment_no_delete
  BEFORE DELETE ON ledger_segment
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();


-- ── The reconciliation gate ──────────────────────────────────────────
--
-- Deferred so a whole segmentation lands in one transaction and is judged as
-- a set. Checked per line touched, on both insert and reversal, because a
-- reversal that leaves a partial set behind is as wrong as a bad split.

CREATE FUNCTION segments_must_reconcile() RETURNS trigger AS $$
DECLARE
  target      text;
  booked      numeric(14,2);
  segmented   numeric(14,2);
  n           integer;
BEGIN
  target := COALESCE(NEW.line_id, OLD.line_id);

  SELECT count(*), COALESCE(sum(amount), 0)
    INTO n, segmented
    FROM ledger_segment
   WHERE line_id = target AND reversed_at IS NULL;

  -- No live segments is a valid state: the line is classified whole.
  IF n = 0 THEN
    RETURN NULL;
  END IF;

  IF n = 1 THEN
    RAISE EXCEPTION
      'Line % has a single segment. Splitting a line into one part changes '
      'nothing and hides the fact that no judgment was made.', target
      USING ERRCODE = 'check_violation';
  END IF;

  SELECT amount INTO booked FROM ledger_line WHERE line_id = target;

  IF abs(segmented - booked) > 0.01 THEN
    RAISE EXCEPTION
      'Segments of line % total %, but the line is booked at %. A '
      'segmentation must reconcile to its source within a cent.',
      target, segmented, booked
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ledger_segment_reconciles
  AFTER INSERT OR UPDATE ON ledger_segment
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION segments_must_reconcile();


-- ── Decisions attach to the analytical unit, not always the line ─────

ALTER TABLE decision_line
  ADD COLUMN segment_id text REFERENCES ledger_segment;

-- A segment belongs to the line it is recorded against.
CREATE FUNCTION decision_segment_belongs() RETURNS trigger AS $$
BEGIN
  IF NEW.segment_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM ledger_segment
                      WHERE segment_id = NEW.segment_id
                        AND line_id = NEW.line_id) THEN
    RAISE EXCEPTION 'Segment % does not belong to line %.',
      NEW.segment_id, NEW.line_id USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER decision_segment_belongs
  BEFORE INSERT OR UPDATE ON decision_line
  FOR EACH ROW EXECUTE FUNCTION decision_segment_belongs();

-- One live decision per analytical unit. An unsegmented line is one unit; a
-- segmented line is one unit per segment.
DROP INDEX one_live_decision_per_line;
CREATE UNIQUE INDEX one_live_decision_per_unit
  ON decision_line (line_id, COALESCE(segment_id, ''))
  WHERE live;


-- ── The effective analytical representation ──────────────────────────
--
-- Segments where live ones exist, otherwise the parent line. Everything
-- downstream of classification reads this rather than ledger_line, so a
-- segmented line is never double counted and never lost.

CREATE VIEW v_analytical_line AS
SELECT l.line_id,
       s.segment_id,
       COALESCE(s.segment_id, l.line_id)      AS unit_id,
       l.period,
       l.txn_date,
       l.account,
       l.payee,
       COALESCE(s.label, l.description)       AS description,
       COALESCE(s.amount, l.amount)           AS amount,
       l.statement,
       l.section,
       l.customer_job_hint,
       (s.segment_id IS NOT NULL)             AS is_segment
  FROM ledger_line l
  LEFT JOIN ledger_segment s
         ON s.line_id = l.line_id
        AND s.reversed_at IS NULL;

COMMENT ON VIEW v_analytical_line IS
  'The effective analytical representation of the ledger: live segments where '
  'a line has been split, otherwise the line itself. Reads that drive '
  'classification, coverage and the economic ledger use this; the source '
  'ledger_line is never altered.';

-- Proof, for the control register: the analytical layer must carry exactly the
-- dollars the source carries. Any drift here is a segmentation bug.
CREATE VIEW v_segmentation_control AS
SELECT p.period,
       (SELECT count(*) FROM ledger_line
         WHERE period = p.period)                       AS source_lines,
       (SELECT count(DISTINCT line_id) FROM ledger_segment
         WHERE period = p.period AND reversed_at IS NULL) AS segmented_lines,
       (SELECT count(*) FROM ledger_segment
         WHERE period = p.period AND reversed_at IS NULL) AS live_segments,
       (SELECT COALESCE(sum(amount), 0) FROM ledger_line
         WHERE period = p.period)                       AS source_total,
       (SELECT COALESCE(sum(amount), 0) FROM v_analytical_line
         WHERE period = p.period)                       AS analytical_total,
       (SELECT COALESCE(sum(amount), 0) FROM ledger_line
         WHERE period = p.period)
       - (SELECT COALESCE(sum(amount), 0) FROM v_analytical_line
           WHERE period = p.period)                     AS variance
  FROM fiscal_period p;

COMMENT ON VIEW v_segmentation_control IS
  'Proof that the analytical layer carries exactly the dollars the source '
  'carries. Every total is an independent scalar subquery: joining '
  'ledger_line to ledger_segment and summing would count a segmented line '
  'once per segment and report a variance equal to the amount segmented.';
