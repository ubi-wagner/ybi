-- The income side: charge codes, who may charge them, and what a contract
-- earns against what it costs.
--
-- Everything so far reads the cost record backwards — the ledger arrives, the
-- controller judges it, a rate falls out. That works for a year already spent
-- and not at all for a year being worked. A charge code has to exist before
-- somebody books an hour to it, the person booking has to be allowed to, and
-- the money coming in has to be traceable to the deliverable that earned it.
--
-- The cost objective is the charge code. There is deliberately no second
-- table of codes sitting beside it: an hour and a dollar spent on the same
-- work have to land in the same place, and two registers of "the thing you
-- charge to" is how they stop doing that.

-- ── Who may charge what ───────────────────────────────────────────────
--
-- Until now anybody with a timesheet could book time to any active
-- objective. That is fine for reconstructing 2025, where the question is
-- what happened, and wrong for 2026, where the question is what is
-- authorised. Charging a federal award you were never assigned to is not a
-- typo, it is an unallowable cost with somebody's name on it.
--
-- Granted by the project manager or the controller. Not self-granted: the
-- same rule the portfolios follow, and for the same reason.
CREATE TABLE charge_authority (
  authority_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period          text NOT NULL REFERENCES fiscal_period,
  objective_id    text NOT NULL REFERENCES cost_objective,
  employee_key    text NOT NULL,
  role_on_project text NOT NULL DEFAULT '',
  granted_by      text NOT NULL,
  granted_at      timestamptz NOT NULL DEFAULT now(),
  reason          text NOT NULL,
  -- A window, because an assignment ends. Null start means "from the
  -- objective's own start"; null end means "until revoked".
  opens_on        date,
  closes_on       date,
  revoked_at      timestamptz,
  revoked_reason  text,
  CHECK (reason <> ''),
  CHECK (closes_on IS NULL OR opens_on IS NULL OR closes_on >= opens_on),
  CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))
);

-- One live grant per person per code. A second is an amendment, and it
-- supersedes rather than sitting beside the first.
CREATE UNIQUE INDEX one_live_authority
  ON charge_authority (period, objective_id, employee_key)
  WHERE revoked_at IS NULL;

CREATE INDEX charge_authority_by_employee
  ON charge_authority (period, employee_key) WHERE revoked_at IS NULL;

COMMENT ON TABLE charge_authority IS
  'Who may book time to which charge code, in what window, and who said so. '
  'Absence of a row is not permission — see v_charge_authorised.';


-- ── The contract's own terms ──────────────────────────────────────────
--
-- A contract is not its ceiling. The provisions that decide what may be
-- charged, how it is invoiced and when it is paid live in clauses, and a
-- reviewer asks for the clause rather than the summary. So each term carries
-- the reference it came from and, where somebody read it off a document,
-- the document.
CREATE TABLE award_term (
  term_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id    text NOT NULL REFERENCES award ON DELETE CASCADE,
  term_key    text NOT NULL,
  term_value  text NOT NULL,
  citation    text NOT NULL DEFAULT '',
  note        text NOT NULL DEFAULT '',
  evidence_id text REFERENCES evidence,
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (award_id, term_key)
);

COMMENT ON TABLE award_term IS
  'The provisions of a contract, each with the clause it came from. The '
  'summary on a screen is worth what the citation behind it is worth.';


-- ── Milestones ────────────────────────────────────────────────────────
--
-- The unit a contract is actually managed in: a deliverable, what it is
-- worth, when it is due, and what state it is in. An invoice is raised
-- against one; money arrives against the invoice; cost is incurred against
-- the objective. That chain is the whole point — it is what lets somebody
-- ask "what did we earn on this, and what did it cost us" and get an answer
-- rather than an estimate.
CREATE TYPE milestone_state AS ENUM (
  'PLANNED', 'IN_PROGRESS', 'DELIVERED', 'ACCEPTED', 'INVOICED', 'PAID',
  'CANCELLED');

CREATE TABLE milestone (
  milestone_id  text PRIMARY KEY,
  award_id      text NOT NULL REFERENCES award,
  name          text NOT NULL,
  description   text NOT NULL DEFAULT '',
  clin          text NOT NULL DEFAULT '',
  value         numeric(14,2) NOT NULL DEFAULT 0 CHECK (value >= 0),
  due_on        date,
  delivered_on  date,
  accepted_on   date,
  state         milestone_state NOT NULL DEFAULT 'PLANNED',
  created_by    text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (name <> ''),
  -- A state that claims a date must have it. "Delivered" with no delivery
  -- date is a status somebody set, not a fact.
  CHECK (state <> 'DELIVERED' OR delivered_on IS NOT NULL),
  CHECK (state <> 'ACCEPTED'  OR accepted_on IS NOT NULL)
);

CREATE INDEX milestone_by_award ON milestone (award_id, due_on);

ALTER TABLE invoice ADD COLUMN milestone_id text REFERENCES milestone;
CREATE INDEX invoice_by_milestone ON invoice (milestone_id)
  WHERE milestone_id IS NOT NULL;


-- ── Money in ──────────────────────────────────────────────────────────
--
-- The half the system has never had. An invoice issued is a claim; a receipt
-- is the money. Keeping them apart is what makes "billed but not collected"
-- a number somebody can act on instead of a feeling.
CREATE TABLE receipt (
  receipt_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id  uuid NOT NULL REFERENCES invoice ON DELETE CASCADE,
  received_on date NOT NULL,
  amount      numeric(14,2) NOT NULL CHECK (amount <> 0),
  method      text NOT NULL DEFAULT '',
  reference   text NOT NULL DEFAULT '',
  note        text NOT NULL DEFAULT '',
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX receipt_by_invoice ON receipt (invoice_id);

COMMENT ON TABLE receipt IS
  'Money actually received against an invoice. A negative amount is a '
  'refund or a clawback, which is why the check is <> 0 rather than > 0.';


-- ── Is this person allowed to charge this code, on this day? ──────────
--
-- One view, so the answer is the same everywhere it is asked. The handler
-- asks it before accepting a timesheet entry and the screen asks it before
-- offering the code, and neither gets to have its own opinion.
CREATE VIEW v_charge_authorised AS
SELECT ca.period, ca.objective_id, ca.employee_key, ca.role_on_project,
       ca.opens_on, ca.closes_on, ca.granted_by, ca.granted_at, ca.reason,
       o.label       AS objective_label,
       o.is_federal,
       o.active      AS objective_active,
       a.award_id,
       a.sponsor
  FROM charge_authority ca
  JOIN cost_objective o ON o.objective_id = ca.objective_id
  LEFT JOIN award a     ON a.objective_id = ca.objective_id
 WHERE ca.revoked_at IS NULL;


-- ── A charge code, with everything hanging off it ─────────────────────
CREATE VIEW v_charge_code AS
SELECT o.period, o.objective_id, o.label, o.objective_type, o.is_federal,
       o.is_final, o.active, o.cfda,
       a.award_id, a.sponsor, a.instrument, a.ceiling_federal,
       a.period_start, a.period_end,
       (SELECT count(*) FROM charge_authority ca
         WHERE ca.objective_id = o.objective_id AND ca.period = o.period
           AND ca.revoked_at IS NULL)                        AS people_authorised,
       (SELECT COALESCE(sum(t.hours), 0) FROM timesheet_entry t
         WHERE t.objective_id = o.objective_id AND t.period = o.period
           AND t.superseded_at IS NULL)                      AS hours_charged,
       (SELECT count(DISTINCT t.employee_key) FROM timesheet_entry t
         WHERE t.objective_id = o.objective_id AND t.period = o.period
           AND t.superseded_at IS NULL)                      AS people_charging,
       (SELECT COALESCE(sum(la.reconstructed_units), 0)
          FROM labor_allocation la
         WHERE la.objective_id = o.objective_id AND la.period = o.period) AS wages_distributed,
       (SELECT COALESCE(sum(l.amount), 0) FROM ledger_line l
          JOIN decision_line dl ON dl.line_id = l.line_id
          JOIN decision d ON d.decision_id = dl.decision_id
                         AND d.reversed_at IS NULL
         WHERE d.objective_id = o.objective_id AND l.period = o.period) AS cost_classified
  FROM cost_objective o
  LEFT JOIN award a ON a.objective_id = o.objective_id;


-- ── Somebody charged time to these. Did anybody say they could? ───────
--
-- The auditor's first question about an employee, and the one the system
-- could not answer until now. `authorised` is false where an hour was
-- booked with no live grant behind it — which for 2025 is every hour, and
-- says so rather than implying the question was asked and passed.
CREATE VIEW v_employee_charging AS
SELECT t.period, t.employee_key, t.objective_id,
       o.label                                        AS objective_label,
       o.is_federal,
       a.award_id, a.sponsor,
       sum(t.hours)                                   AS hours,
       count(*)                                       AS entries,
       min(t.work_date)                               AS first_charged,
       max(t.work_date)                               AS last_charged,
       EXISTS (SELECT 1 FROM charge_authority ca
                WHERE ca.period = t.period
                  AND ca.objective_id = t.objective_id
                  AND ca.employee_key = t.employee_key
                  AND ca.revoked_at IS NULL)          AS authorised
  FROM timesheet_entry t
  JOIN cost_objective o ON o.objective_id = t.objective_id
  LEFT JOIN award a     ON a.objective_id = t.objective_id
 WHERE t.superseded_at IS NULL
 GROUP BY t.period, t.employee_key, t.objective_id, o.label, o.is_federal,
          a.award_id, a.sponsor;


-- ── A milestone, the invoice against it, and the money that arrived ───
CREATE VIEW v_milestone_status AS
SELECT m.milestone_id, m.award_id, m.name, m.clin, m.description,
       m.value, m.due_on, m.delivered_on, m.accepted_on, m.state,
       a.objective_id, a.sponsor,
       (SELECT count(*) FROM invoice i
         WHERE i.milestone_id = m.milestone_id)                AS invoices,
       COALESCE((SELECT sum(i.direct_claimed + i.indirect_claimed + i.cost_share)
                   FROM invoice i WHERE i.milestone_id = m.milestone_id), 0)
                                                               AS invoiced,
       COALESCE((SELECT sum(r.amount) FROM receipt r
                   JOIN invoice i ON i.invoice_id = r.invoice_id
                  WHERE i.milestone_id = m.milestone_id), 0)   AS received,
       -- Earned and not yet collected. The number a controller chases.
       COALESCE((SELECT sum(i.direct_claimed + i.indirect_claimed + i.cost_share)
                   FROM invoice i WHERE i.milestone_id = m.milestone_id), 0)
     - COALESCE((SELECT sum(r.amount) FROM receipt r
                   JOIN invoice i ON i.invoice_id = r.invoice_id
                  WHERE i.milestone_id = m.milestone_id), 0)   AS outstanding
  FROM milestone m
  JOIN award a ON a.award_id = m.award_id;


-- ── The contract, earned against spent ────────────────────────────────
--
-- Deliberately not a margin. Cost here is what has been classified to the
-- objective, and classification is unfinished for 2025 — so a figure
-- presented as profit would be wrong in a direction that flatters. The view
-- reports both sides and the coverage behind the cost side, and lets the
-- screen say what that means.
CREATE VIEW v_award_performance AS
SELECT a.award_id, a.objective_id, a.sponsor, a.instrument,
       a.ceiling_federal, a.cost_share_required,
       a.period_start, a.period_end,
       o.period, o.label AS objective_label, o.is_federal, o.cfda,
       (SELECT count(*) FROM milestone m WHERE m.award_id = a.award_id) AS milestones,
       (SELECT count(*) FROM milestone m WHERE m.award_id = a.award_id
          AND m.state IN ('DELIVERED','ACCEPTED','INVOICED','PAID'))    AS milestones_done,
       (SELECT count(*) FROM award_term t WHERE t.award_id = a.award_id) AS terms,
       COALESCE((SELECT sum(i.direct_claimed + i.indirect_claimed)
                   FROM invoice i WHERE i.award_id = a.award_id), 0)    AS invoiced,
       COALESCE((SELECT sum(r.amount) FROM receipt r
                   JOIN invoice i ON i.invoice_id = r.invoice_id
                  WHERE i.award_id = a.award_id), 0)                    AS received,
       COALESCE((SELECT sum(l.amount) FROM ledger_line l
                   JOIN decision_line dl ON dl.line_id = l.line_id
                   JOIN decision d ON d.decision_id = dl.decision_id
                                  AND d.reversed_at IS NULL
                  WHERE d.objective_id = a.objective_id
                    AND l.period = o.period), 0)                        AS cost_classified,
       COALESCE((SELECT sum(la.reconstructed_units) FROM labor_allocation la
                  WHERE la.objective_id = a.objective_id
                    AND la.period = o.period), 0)                       AS labor_distributed
  FROM award a
  JOIN cost_objective o ON o.objective_id = a.objective_id;
