-- Cost is not income, and the controller has been asked to judge $6.9m of it.
--
-- `039` put the definition of coverage in the schema, scoped to the P&L,
-- because the classification screen and the auditor's report answered 13.0%
-- and 2.2% at the same moment. Its comment says what the scope means:
--
--     'the P&L scope — balance sheet movements are not cost to classify'
--
-- Which is true and one level too coarse. **Income is on the P&L and income
-- is not cost.** Measured on the live record, the scope every progress
-- figure is taken against holds:
--
--     Expense                      $10,026,369.84    748 groups
--     Other Income                    $116,948.54      6 groups
--     COGS                             $37,323.72      3 groups
--     Income                        $6,876,763.86    242 groups   <- revenue
--
-- So **242 of 999 groups and 40.3% of the scope is revenue**, and all 242 are
-- open, because there is no correct answer: you do not put grant income in a
-- cost pool. Four of the six largest things in Tom's queue are `3900 Grant
-- Income` and `4015 Program Fees`. The screen this file calls *the one that
-- matters* opens on work that cannot be done.
--
-- Two consequences, and the second is worse than the first:
--
--   * **A quarter of the queue cannot be actioned.** 999 groups to look at
--     where 757 is the real number, with the unanswerable ones sorted to the
--     top because they are large.
--   * **Coverage reads 13.0% where the truth is 21.8%** — the figure on
--     every workpaper, in the NOT FILEABLE banner on the 990, in the
--     "working figure" caveat on the rate, and quoted to the board. Wrong by
--     a factor of 1.7, in the pessimistic direction, because its denominator
--     is 41% revenue.
--
-- `ledger_line.section` has carried the P&L's own section on every line
-- since the import — Income, COGS, Expense, Other Income, CHECK-constrained
-- on `pl_account` — and nothing has ever used it to decide what is cost.
-- That is the discriminator, not a regex on account numbers: *never join on
-- a name where a key exists.*
--
-- **Other Income stays in scope on purpose.** $116,948.54 across six groups,
-- and 2 CFR 200.406 makes applicable credits — refunds, rebates, adjustments
-- — a reduction of cost rather than revenue. Somebody has to look at those.
-- Only the Income section comes out.
--
-- A blank section stays in too. `section` defaults to '' and *unclassified
-- cost is never defaulted out of the queue*: not knowing what something is
-- is a reason to look at it, not a reason to hide it.

-- Defined once, because this is the shape that produced 13.0% and 2.2%.
-- Four places expressed "the P&L scope" for classification — the coverage
-- view, the worklist, the queue handler and the evidence matcher — each by
-- hand. They read this now.
CREATE VIEW v_cost_line AS
SELECT l.*
  FROM ledger_line l
 WHERE l.statement = 'P&L'
   AND l.section <> 'Income';

COMMENT ON VIEW v_cost_line IS
  'The ledger lines that are cost to classify: the P&L less its Income '
  'section. Other Income stays — 200.406 applicable credits reduce cost and '
  'somebody has to judge them — and so does a line whose section is blank, '
  'because not knowing what something is is a reason to look at it. Every '
  'definition of what the controller must judge reads this, so there cannot '
  'be a second one to disagree with it.';

-- Lifted from the live definition with the source swapped, never retyped.
CREATE OR REPLACE VIEW v_classification_coverage AS
 WITH scope AS (
         SELECT l.line_id,
            l.period,
            l.account,
            l.payee,
            l.amount,
            dl.decision_id IS NOT NULL AS decided
           FROM v_cost_line l
             LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
             LEFT JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
        )
 SELECT period,
    count(*) AS total_lines,
    count(*) FILTER (WHERE decided) AS decided_lines,
    count(DISTINCT ROW(account, payee)) AS groups_total,
    count(DISTINCT ROW(account, payee)) FILTER (WHERE decided) AS groups_decided,
    COALESCE(sum(abs(amount)), 0::numeric) AS scope_dollars,
    COALESCE(sum(abs(amount)) FILTER (WHERE decided), 0::numeric) AS classified,
    COALESCE(sum(abs(amount)) FILTER (WHERE NOT decided), 0::numeric) AS unclassified,
    round(100.0 * COALESCE(sum(abs(amount)) FILTER (WHERE decided), 0::numeric) / NULLIF(sum(abs(amount)), 0::numeric), 1) AS pct_dollars_covered
   FROM scope
  GROUP BY period;

COMMENT ON VIEW v_classification_coverage IS
  'Coverage, over cost rather than over the P&L. classified + unclassified = '
  'scope_dollars still holds, so the percentage reproduces from the row — it '
  'is the denominator that changed, from $17,057,405.96 of P&L to '
  '$10,180,642.10 of cost, and the figure from 13.0% to 21.8%.';

CREATE OR REPLACE VIEW v_worklist AS
 SELECT 'UNCLASSIFIED'::text AS kind,
    'BLOCKING'::text AS severity,
    l.period,
    l.account || COALESCE(NULLIF(' / '::text || l.payee, ' / '::text), ''::text) AS label,
    'ledger_group'::text AS entity,
    (l.account || chr(31)) || COALESCE(l.payee, ''::text) AS entity_id,
    sum(abs(l.amount)) AS amount,
    count(*)::text || ' lines, no decision'::text AS detail
   FROM v_cost_line l
     LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
  WHERE l.period = '2025'::text AND dl.line_id IS NULL
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
