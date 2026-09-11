-- =====================================================================
-- The fourth source document
--
-- Ten cross-reference points prove the general ledger, the profit and loss
-- and the balance sheet are three views of the same books. The payroll
-- register is a fourth document and none of them touch it — which is how a
-- forty-five thousand dollar misposting survived a year.
--
-- It matters more than its size suggests. The register is where the fringe
-- base comes from: `_build_model` takes direct labour from the effort
-- distribution, not from the ledger's wage accounts. So a difference between
-- the two is not a presentational curiosity, it is two different denominators
-- for the same rate. On the 2025 data the two readings are 21.90% and 22.45%,
-- fifty-five basis points apart, and until this control existed there was
-- nothing in the system that could say which was right.
--
-- What it found, the first time it ran:
--
--     2025-12-01  5142 Intern Wages         Vince and Phyllis Bacon  -45,000.00
--     2025-12-01  1100 Accounts Receivable  Vince and Phyllis Bacon  +45,000.00
--
-- A donor's commitment to fund interns, booked as a credit against wage
-- expense instead of as contribution income. It understates contributions and
-- wages by the same amount on the Form 990, and it understates the fringe base
-- by 2.5%. The same donor's September gift went to 4029 Sponsorships
-- correctly, so this is a misposting rather than a policy.
--
-- ── On residuals nobody can attribute ────────────────────────────────
--
-- Every other reconciling item in this system names the ledger lines it
-- consists of, and a trigger refuses one whose lines do not add up. That rule
-- is what separates a reconciling item from a plug, and it is not negotiable
-- where attribution is possible.
--
-- Sometimes it is not. After the Bacon entry is named, $53.24 remains between
-- the register and the ledger — three thousandths of one per cent of a
-- 1.8 million dollar base, with no transaction behind it. Two bad options and
-- one good one: leave the control permanently open, which teaches everybody
-- to ignore it; invent a tolerance that quietly swallows it, which is how a
-- system starts lying; or make somebody write down, in their own name, that
-- it cannot be attributed and why.
--
-- The third. A ROUNDING item may carry no lines — but it must say in at
-- least sixty characters why attribution was not possible, and it may not
-- exceed a thousand dollars, because past that "rounding" is not a credible
-- description of anything. It appears on the face of the reconciliation as
-- what it is.
-- =====================================================================


-- ── The rule, relaxed exactly once and no further ────────────────────

CREATE OR REPLACE FUNCTION reconciling_lines_must_total() RETURNS trigger AS $$
DECLARE
  r        record;
  line_sum numeric(16,2);
  n_lines  integer;
BEGIN
  FOR r IN SELECT i.item_id, i.amount, i.from_account, i.kind, i.explanation
             FROM reconciling_item i
            WHERE i.retracted_at IS NULL
              AND i.item_id = COALESCE(NEW.item_id, OLD.item_id)
  LOOP
    SELECT COALESCE(sum(l.amount), 0), count(*) INTO line_sum, n_lines
      FROM reconciling_item_line rl
      JOIN ledger_line l ON l.line_id = rl.line_id
     WHERE rl.item_id = r.item_id;

    -- A residual with no transaction behind it, owned by a person in
    -- writing. The only case where lines may be absent.
    IF r.kind = 'ROUNDING' AND n_lines = 0 THEN
      IF abs(r.amount) > 1000 THEN
        RAISE EXCEPTION
          'a rounding item cannot be % — past a thousand dollars "rounding" '
          'is not a description of anything. Name the lines.', r.amount;
      END IF;
      IF length(btrim(r.explanation)) < 60 THEN
        RAISE EXCEPTION
          'a rounding item carries no lines, so its explanation has to do '
          'the work: say why the amount cannot be attributed.';
      END IF;
      CONTINUE;
    END IF;

    IF round(line_sum, 2) <> round(r.amount, 2) THEN
      RAISE EXCEPTION
        'reconciling item % claims % but its lines total % — a reconciling '
        'item names the lines it is made of, or it is a plug',
        r.item_id, r.amount, line_sum;
    END IF;
    IF EXISTS (SELECT 1 FROM reconciling_item_line rl
                 JOIN ledger_line l ON l.line_id = rl.line_id
                WHERE rl.item_id = r.item_id AND l.account <> r.from_account) THEN
      RAISE EXCEPTION
        'reconciling item % moves money out of % but names lines posted '
        'elsewhere', r.item_id, r.from_account;
    END IF;
  END LOOP;
  RETURN NULL;
END $$ LANGUAGE plpgsql;


-- ── The register against the ledger ──────────────────────────────────

CREATE VIEW v_payroll_reconciliation AS
WITH wages AS (
  SELECT l.period,
         sum(l.amount)                                            AS account_total,
         -- A reading aid, not the control. QuickBooks memos carry the shape
         -- of a payroll month — a gross run, an accrual and its reversal,
         -- the odd named correction — and seeing them separated is what
         -- turns "there is a difference" into "there is one line wrong".
         sum(l.amount) FILTER (WHERE l.description ILIKE 'GROSS%')  AS gross_runs,
         sum(l.amount) FILTER (WHERE l.description ILIKE '%accrual%')
                                                                   AS net_accruals,
         sum(l.amount) FILTER (WHERE l.description ILIKE '%- Wages%')
                                                                   AS named_corrections,
         count(*)                                                  AS lines
    FROM ledger_line l
   WHERE l.statement = 'P&L' AND l.account ILIKE '%Wages%'
   GROUP BY l.period),
register AS (
  SELECT period, sum(distributed_wages) AS distributed,
         count(DISTINCT employee_key)   AS people
    FROM v_labor_effective GROUP BY period),
named AS (
  SELECT period, COALESCE(sum(amount), 0) AS amount, count(*) AS items
    FROM reconciling_item
   WHERE control = 'PAYROLL_REGISTER' AND retracted_at IS NULL
   GROUP BY period)
SELECT p.period,
       COALESCE(r.distributed, 0)                              AS register_wages,
       COALESCE(r.people, 0)                                   AS people,
       COALESCE(w.account_total, 0)                            AS ledger_wages,
       COALESCE(w.gross_runs, 0)                               AS gross_runs,
       COALESCE(w.net_accruals, 0)                             AS net_accruals,
       COALESCE(w.named_corrections, 0)                        AS named_corrections,
       COALESCE(w.lines, 0)                                    AS ledger_lines,
       round(COALESCE(r.distributed, 0) - COALESCE(w.account_total, 0), 2)
                                                               AS gross_difference,
       COALESCE(n.amount, 0)                                   AS named,
       COALESCE(n.items, 0)                                    AS named_items,
       -- Added, not subtracted, and the sign is worth being explicit about.
       -- A reconciling item's amount is forced by the trigger to equal the
       -- ledger lines it names, signed as the ledger has them — the Bacon
       -- credit is -45,000 because that is what sits in the account. Taking
       -- a -45,000 line out of the ledger raises the ledger by 45,000, which
       -- lowers a register-minus-ledger difference by the same. So the item
       -- amount adds. Items with no lines follow the same convention: the
       -- amount by which the ledger's wage accounts are wrong, signed as the
       -- ledger has it.
       round(COALESCE(r.distributed, 0) - COALESCE(w.account_total, 0)
             + COALESCE(n.amount, 0), 2)                       AS unexplained,
       -- What the fringe rate reads on each basis. Two denominators for one
       -- rate is the whole reason this control exists, so it says so.
       (SELECT COALESCE(sum(amount), 0) FROM pl_account a
         WHERE a.period = p.period
           AND a.leaf IN ('5130 Benefits', '5133 401k Match & Profit Sharing',
                          '5145 Bureau of Worker''s Compensation',
                          '5151 Social Security & Medicare', '5185 FUTA',
                          '5195 SUI'))                          AS fringe_pool
  FROM fiscal_period p
  LEFT JOIN wages w   ON w.period = p.period
  LEFT JOIN register r ON r.period = p.period
  LEFT JOIN named n   ON n.period = p.period;

COMMENT ON VIEW v_payroll_reconciliation IS
  'The payroll register against the ledger''s wage accounts — the fourth '
  'source document, and the one the fringe base actually comes from. A '
  'difference here is two denominators for one rate, not a presentation '
  'question.';


-- ── The eleventh cross-reference point ───────────────────────────────

-- The ten stay where they are; this adds an eleventh beside them rather than
-- restating two hundred lines of union to insert one row.
ALTER VIEW v_statement_reconciliation RENAME TO v_statement_reconciliation_core;

CREATE VIEW v_statement_reconciliation AS
SELECT * FROM v_statement_reconciliation_core
UNION ALL
SELECT v.period,
       110                                                   AS seq,
       'PAYROLL_REGISTER'                                    AS control,
       'EXCEPTIONS'                                          AS basis,
       'The payroll register agrees with the ledger''s wage accounts'
                                                             AS description,
       'Register'                                            AS left_label,
       v.register_wages                                      AS left_value,
       'Ledger wage accounts'                                AS right_label,
       v.ledger_wages                                        AS right_value,
       v.unexplained                                         AS variance,
       CASE WHEN v.unexplained = 0 THEN 0 ELSE 1 END::numeric AS exceptions,
       (v.unexplained = 0)                                   AS ties,
       'The fringe base comes from the register, not from the ledger, so a '
       'difference here is two denominators for one rate. None of the other '
       'ten points touches the register — which is how a $45,000 donor '
       'credit sat in an intern wage account for a year.'    AS note
  FROM v_payroll_reconciliation v;

COMMENT ON VIEW v_statement_reconciliation IS
  'The cross-reference register: every point at which the general ledger, '
  'the profit and loss, the balance sheet and the payroll register are '
  'required to agree, and what is left over at each. Read before anything '
  'is classified, and again before any rate.';
