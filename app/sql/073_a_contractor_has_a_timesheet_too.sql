-- 073 — the person the money paid, and where their hours went
--
-- `v_labor_hours_check` reported one person as `HOURS WITHOUT WAGES`: Tom
-- Metzinger, 781 hours across all twelve months of 2025, with no row in the
-- payroll distribution and — searching his surname — no payment anywhere in
-- the general ledger.
--
-- **He is 1099, and the expense was on the record the whole time.** It is
-- `Management & Administrative Expenses:5201 Professional Services:5202
-- Accounting`, payee **`Metz Consulting, LLC.`**, $73,024.44 over 25 lines:
-- twenty-two semi-monthly payments at $3,000, two December payments at
-- $3,375 after a rate rise, and $274.44 of 1099 filing fees. The
-- controller's own workbook carries him too, in a block below the payroll
-- rows headed `5202 Accounting` — at $72,375, which is the same figure less
-- one December payment still at the old rate ($375) and the filing fees
-- ($274.44). Both differences reconcile exactly.
--
-- A surname search found nothing because a contractor is paid as a company.
-- That is the whole reason this table exists: **the link between a person in
-- the hours log and the payee that pays them is a fact somebody establishes
-- once**, and rediscovering it costs a trip through a spreadsheet. Never
-- join on a name — this is the key that was missing, written down.

CREATE TABLE IF NOT EXISTS contractor_identity (
    period          text NOT NULL REFERENCES fiscal_period(period),
    employee_key    text NOT NULL,
    payee           text NOT NULL,
    basis           text NOT NULL DEFAULT 'W9_1099',
    note            text NOT NULL DEFAULT '',
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    recorded_by     text NOT NULL DEFAULT '',
    PRIMARY KEY (period, employee_key, payee),
    CONSTRAINT contractor_basis_known
        CHECK (basis IN ('W9_1099', 'ENTITY', 'OTHER')),
    -- A link with no explanation is the next person's puzzle again.
    CONSTRAINT contractor_identity_says_why
        CHECK (length(btrim(note)) >= 20)
);

COMMENT ON TABLE contractor_identity IS
    'Who in the hours log is paid as which ledger payee. A contractor is '
    'paid as a company, so a search for their name finds nothing — this is '
    'the key that fact is held in rather than rediscovered.';


-- **What the money was classified as, against where the hours went.**
--
-- **One row per group**, because the group — an account and a payee — is the
-- unit everything else here is judged in, and Metz Consulting is paid three
-- ways that mean three different things:
--
--   `5202 Accounting`                 $73,024.44  the retainer, his time
--   `5215 Dues and Subscriptions`      $4,909.82  software he buys and rebills
--   `Program Expenses:ESP:5221`        $4,880.00  EIR work, already DIRECT
--
-- Rolling those into one figure and applying an hours percentage to it would
-- put a share of a software subscription on a cost objective. It would also
-- hide the most useful fact on the page: **YBI already direct-charges his
-- project work when it is billed as project work** — the ESP line is in a
-- programme account and the log puts it on ESP. That is evidence about how
-- the organisation treats this, and it belongs in front of whoever answers
-- the question rather than averaged away.
--
-- **What it cannot tell is time from pass-through.** `5215 Dues and
-- Subscriptions` is software he buys and rebills, and the view flags it
-- beside the retainer because nothing in the data distinguishes them. The
-- account name does, to a reader, and the rows are ordered by size so the
-- $73,024.44 question sits above the $4,909.82 one. Inventing a rule to
-- separate them would be guessing at a judgment; naming both and letting
-- somebody read two account names is cheaper and does not pretend.
--
-- The question is the retainer: his log puts 240 hours on Hybrid II and
-- Rising Tides that nothing bills separately. **This view does not decide
-- it**, because 2 CFR 200.413(c) allows an otherwise administrative function
-- to be charged direct only on four conditions, and the third — explicitly
-- in the budget, or prior written approval — is what these awards do not
-- have. It states the amount and names the objectives.
CREATE OR REPLACE VIEW v_contractor_effort_check AS
-- **Which objective is the administration is read from the schema**, not
-- named here. `cost_objective.objective_type` already carries it —
-- `ADMINISTRATION` — and writing `'YBI-GA'` as a literal would be a second
-- copy of that fact, free to be wrong the day somebody opens another
-- administrative objective. A test caught exactly that.
WITH admin_hours AS (
    SELECT m.period, m.employee_key,
           sum(m.adjusted_hours)
               FILTER (WHERE o.objective_type = 'ADMINISTRATION')  AS admin,
           sum(m.adjusted_hours)                                   AS total,
           string_agg(DISTINCT m.objective_id, ', ')
               FILTER (WHERE o.objective_type <> 'ADMINISTRATION') AS objectives
      FROM labor_month m
      JOIN cost_objective o USING (objective_id)
     GROUP BY m.period, m.employee_key
),
grouped AS (
    SELECT c.period, c.employee_key, c.payee, l.account,
           sum(l.amount)  AS expense,
           count(*)       AS lines,
           string_agg(DISTINCT d.pool::text, ', ' ORDER BY d.pool::text) AS pools
      FROM contractor_identity c
      JOIN v_cost_line l ON l.period = c.period AND l.payee = c.payee
      LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
      LEFT JOIN decision d ON d.decision_id = dl.decision_id
                          AND d.reversed_at IS NULL
     GROUP BY c.period, c.employee_key, c.payee, l.account
)
SELECT g.period, g.employee_key, g.payee, g.account,
       g.expense, g.lines, g.pools,
       h.total                                          AS hours,
       COALESCE(h.total, 0) - COALESCE(h.admin, 0)      AS project_hours,
       h.objectives,
       CASE WHEN COALESCE(h.total, 0) > 0
            THEN round(100 * (h.total - COALESCE(h.admin, 0)) / h.total, 2)
       END                                              AS project_pct,
       -- Only where the question arises. A group already on a cost
       -- objective has been answered, and a figure against it would be a
       -- number in a control that means nothing.
       CASE WHEN COALESCE(h.total, 0) > 0
             AND g.pools IN ('G&A', 'OVERHEAD')
            THEN round(g.expense * (h.total - COALESCE(h.admin, 0)) / h.total, 2)
       END                                              AS at_stake,
       CASE
           WHEN h.total IS NULL                     THEN 'NO HOURS LOG'
           WHEN g.pools IS NULL                     THEN 'NOT CLASSIFIED'
           WHEN h.total = COALESCE(h.admin, 0)      THEN 'TIES'
           WHEN g.pools NOT IN ('G&A', 'OVERHEAD')  THEN 'TIES'
           ELSE 'OPEN'
       END                                              AS state
  FROM grouped g
  LEFT JOIN admin_hours h USING (period, employee_key);

COMMENT ON VIEW v_contractor_effort_check IS
    'A contractor''s classified cost, one row per group, against where their '
    'own hours went. OPEN is a question, not a defect: 2 CFR 200.413(c) '
    'allows an otherwise administrative function to be charged direct only '
    'on four conditions, and the third — explicitly budgeted, or prior '
    'written approval — is what these awards do not have. A group already on '
    'a cost objective has been answered and carries no figure.';
