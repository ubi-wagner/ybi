-- 109 — two anchors that read green over nothing at all
--
-- Found by running the register against a database built from empty, which
-- is the only population where either could show. On a period with no ledger
-- and no payroll:
--
--   FRINGE_POOL_IS_THE_PAYROLL_FRINGE  reads **TIES**
--   Part VII names everybody the register pays  reads **OPEN**
--
-- Both wrong, in opposite directions, and both are `029` — *an empty period
-- compares zero against zero and looks green* — in the anchors written to
-- catch that.
--
-- The first is the purer instance. The P&L names no fringe, no pool holds
-- any, and `0 = 0` is a pass. `066` already reads this family against the
-- completion of the classification, and that guard does not fire when there
-- is no classification *scope* either: nought of nought is complete. Both
-- sides nought is `NO DATA`, which is what a control that cannot be
-- evaluated has always been.
--
-- The second is the other half of the same idea and reads worse: the roster
-- is seeded by `096` and the payroll register is loaded by a person, so on
-- any period nobody has loaded there are officers and no wages, and every
-- officer came out as *an officer the register does not carry*. **Nothing to
-- compare is not a failure to compare** — a control that reports a finding
-- against an empty record teaches the reader the list is wrong, and the next
-- real one they see they will dismiss.
--
-- Neither moves a figure on the live record: 2025 carries both a ledger and
-- a register, so both anchors evaluate exactly as they did.
--
-- Lifted from the definitions in force.

CREATE OR REPLACE VIEW v_rate_anchor AS
 WITH cov AS (
         SELECT v_classification_coverage.period,
            v_classification_coverage.unclassified,
            v_classification_coverage.scope_dollars,
            v_classification_coverage.pct_dollars_covered
           FROM v_classification_coverage
        ), judged AS (
         SELECT l.period,
            COALESCE(sum(l.amount), 0::numeric) AS classified_signed
           FROM decision d
             JOIN decision_line dl ON dl.decision_id = d.decision_id AND dl.live
             JOIN ledger_line l ON l.line_id = dl.line_id
          WHERE d.reversed_at IS NULL
          GROUP BY l.period
        ), pooled AS (
         SELECT v_pool_balance.period,
            COALESCE(sum(v_pool_balance.gross), 0::numeric) AS pools_total
           FROM v_pool_balance
          GROUP BY v_pool_balance.period
        ), wage AS (
         SELECT rate.period,
            max(rate.base_amount) AS wage_base
           FROM rate
          WHERE rate.status <> 'SUPERSEDED'::text AND rate.base_type = 'SALARIES_WAGES'::allocation_base
          GROUP BY rate.period
        )
 SELECT p.period,
    1 AS seq,
    'POOLS_ACCOUNT_FOR_JUDGMENTS'::text AS control,
    'Every classified dollar lands in exactly one pool'::text AS description,
    COALESCE(j.classified_signed, 0::numeric) AS expected,
    COALESCE(pl.pools_total, 0::numeric) AS actual,
    COALESCE(j.classified_signed, 0::numeric) - COALESCE(pl.pools_total, 0::numeric) AS variance,
        CASE
            WHEN j.classified_signed IS NULL THEN 'NO DATA'::text
            WHEN COALESCE(j.classified_signed, 0::numeric) = COALESCE(pl.pools_total, 0::numeric) THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
    'Signed on both sides: coverage counts absolute dollars by design, so it is not the figure to compare against a pool.'::text AS note,
    c.unclassified = 0::numeric AS classification_complete,
    c.pct_dollars_covered,
    'DOLLARS'::text AS unit
   FROM fiscal_period p
     LEFT JOIN cov c ON c.period = p.period
     LEFT JOIN judged j ON j.period = p.period
     LEFT JOIN pooled pl ON pl.period = p.period
UNION ALL
 SELECT p.period,
    2 AS seq,
    'WAGE_BASE_IS_THE_REGISTER'::text AS control,
    'The fringe denominator is the payroll register, not the ledger'::text AS description,
    COALESCE(pr.register_wages, 0::numeric) AS expected,
    COALESCE(w.wage_base, 0::numeric) AS actual,
    COALESCE(pr.register_wages, 0::numeric) - COALESCE(w.wage_base, 0::numeric) AS variance,
        CASE
            WHEN w.wage_base IS NULL THEN 'NO DATA'::text
            WHEN pr.register_wages IS NULL THEN 'NO DATA'::text
            WHEN pr.register_wages = w.wage_base THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
    'The eleventh statement control reconciles the register to the ledger''s wage accounts; this is the other half — that the rate actually used it.'::text AS note,
    c.unclassified = 0::numeric AS classification_complete,
    c.pct_dollars_covered,
    'DOLLARS'::text AS unit
   FROM fiscal_period p
     LEFT JOIN cov c ON c.period = p.period
     LEFT JOIN wage w ON w.period = p.period
     LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period
UNION ALL
 SELECT p.period,
    3 AS seq,
    'FRINGE_POOL_IS_THE_PAYROLL_FRINGE'::text AS control,
    'What is judged into FRINGE is the P&L''s fringe accounts'::text AS description,
    COALESCE(pr.fringe_pool, 0::numeric) AS expected,
    COALESCE(fp.gross, 0::numeric) AS actual,
    COALESCE(pr.fringe_pool, 0::numeric) - COALESCE(fp.gross, 0::numeric) AS variance,
        CASE
            WHEN pr.fringe_pool IS NULL THEN 'NO DATA'::text
            -- Both sides nought is not a tie. On a period with no ledger the
            -- P&L names no fringe and no pool holds any, and 0 = 0 read TIES
            -- inside the anchor written to catch exactly that.
            WHEN COALESCE(pr.fringe_pool, 0::numeric) = 0::numeric
                 AND COALESCE(fp.gross, 0::numeric) = 0::numeric THEN 'NO DATA'::text
            WHEN fp.gross IS NULL AND COALESCE(c.unclassified, 0::numeric) > 0::numeric THEN 'NO DATA'::text
            WHEN COALESCE(pr.fringe_pool, 0::numeric) = COALESCE(fp.gross, 0::numeric) THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
    'Six accounts named on the face of the P&L: 5130 Benefits, 5133 401k, 5145 BWC, 5151 FICA, 5185 FUTA, 5195 SUI.'::text AS note,
    c.unclassified = 0::numeric AS classification_complete,
    c.pct_dollars_covered,
    'DOLLARS'::text AS unit
   FROM fiscal_period p
     LEFT JOIN cov c ON c.period = p.period
     LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period
     LEFT JOIN ( SELECT v_pool_balance.period,
            v_pool_balance.gross
           FROM v_pool_balance
          WHERE v_pool_balance.pool::text = 'FRINGE'::text) fp ON fp.period = p.period
UNION ALL
 SELECT p.period,
    4 AS seq,
    'FRINGE_RATE_ON_THE_REGISTER'::text AS control,
    'The rate the source documents imply, against the one computed'::text AS description,
    round(pr.fringe_pool / NULLIF(pr.register_wages, 0::numeric), 4) AS expected,
    fr.rate AS actual,
    round(pr.fringe_pool / NULLIF(pr.register_wages, 0::numeric), 4) - fr.rate AS variance,
        CASE
            WHEN pr.fringe_pool IS NULL OR COALESCE(pr.register_wages, 0::numeric) = 0::numeric THEN 'NO DATA'::text
            WHEN fr.rate IS NULL THEN 'NO DATA'::text
            WHEN fr.rate = 0::numeric AND COALESCE(c.unclassified, 0::numeric) > 0::numeric THEN 'NO DATA'::text
            WHEN round(pr.fringe_pool / pr.register_wages, 4) = fr.rate THEN 'TIES'::text
            ELSE 'OPEN'::text
        END AS state,
    'Over the payroll register, not the ledger''s wage accounts: those are understated by the $45,053.23 credit and give 0.2245.'::text AS note,
    c.unclassified = 0::numeric AS classification_complete,
    c.pct_dollars_covered,
    'RATE'::text AS unit
   FROM fiscal_period p
     LEFT JOIN cov c ON c.period = p.period
     LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period
     LEFT JOIN ( SELECT rate.period,
            rate.rate
           FROM rate
          WHERE rate.kind = 'FRINGE'::text AND rate.status <> 'SUPERSEDED'::text
          ORDER BY rate.computed_at DESC
         LIMIT 1) fr ON fr.period = p.period;

CREATE OR REPLACE VIEW v_form_990_officer_check AS
 WITH roster AS (
         SELECT v_form_990_officer.period,
            count(*) AS people,
            count(*) FILTER (WHERE v_form_990_officer.on_line_5) AS officers,
            count(*) FILTER (WHERE v_form_990_officer.on_line_5 AND v_form_990_officer.employee_key IS NOT NULL AND v_form_990_officer.reportable IS NULL) AS missing_pay,
            count(*) FILTER (WHERE v_form_990_officer.employee_key IS NULL AND COALESCE(v_form_990_officer.reportable, 0::numeric) > 0::numeric) AS paid_unkeyed
           FROM v_form_990_officer
          GROUP BY v_form_990_officer.period
        ), unrostered AS (
         SELECT r.period,
            count(*) AS n
           FROM ( SELECT labor_allocation.period,
                    labor_allocation.employee_key,
                    max(labor_allocation.payroll_wages) AS wages
                   FROM labor_allocation
                  GROUP BY labor_allocation.period, labor_allocation.employee_key) r
          WHERE NOT (EXISTS ( SELECT 1
                   FROM form_990_officer f
                  WHERE f.period = r.period AND f.employee_key = r.employee_key)) AND r.wages >= 100000::numeric
          GROUP BY r.period
        )
 SELECT p.period,
    COALESCE(ro.people, 0::bigint) AS people_on_the_roster,
    COALESCE(ro.officers, 0::bigint) AS reach_line_5,
    COALESCE(ro.missing_pay, 0::bigint) AS on_the_roster_not_on_the_payroll,
    COALESCE(ro.paid_unkeyed, 0::bigint) AS paid_with_no_payroll_key,
    COALESCE(un.n, 0::bigint) AS paid_over_100k_and_not_on_the_roster,
        CASE
            WHEN COALESCE(ro.people, 0::bigint) = 0 THEN 'NO DATA'::text
            -- The roster is seeded by a migration and the register is loaded
            -- by a person, so on a period nobody has loaded there are
            -- officers and no payroll — and every one of them read as an
            -- officer the register does not carry. Nothing to compare is not
            -- a failure to compare.
            WHEN NOT (EXISTS ( SELECT 1 FROM labor_allocation la
                                WHERE la.period = p.period)) THEN 'NO DATA'::text
            WHEN COALESCE(ro.missing_pay, 0::bigint) > 0 OR COALESCE(ro.paid_unkeyed, 0::bigint) > 0 THEN 'OPEN'::text
            ELSE 'TIES'::text
        END AS state,
        CASE
            WHEN COALESCE(ro.people, 0::bigint) = 0 THEN 'Part VII of a filed return, or the board''s own roster'::text
            WHEN NOT (EXISTS ( SELECT 1 FROM labor_allocation la
                                WHERE la.period = p.period))
              THEN 'the payroll register, so the roster can be compared to it'::text
            WHEN COALESCE(ro.missing_pay, 0::bigint) > 0 THEN format('%s officer(s) name a payroll key the register does not carry, so line 5 is short by whatever they were paid.'::text, ro.missing_pay)
            WHEN COALESCE(ro.paid_unkeyed, 0::bigint) > 0 THEN format('%s compensated person(s) on the roster have no payroll key, so their pay cannot be read from the register.'::text, ro.paid_unkeyed)
            ELSE ''::text
        END AS needs
   FROM fiscal_period p
     LEFT JOIN roster ro ON ro.period = p.period
     LEFT JOIN unrostered un ON un.period = p.period;
