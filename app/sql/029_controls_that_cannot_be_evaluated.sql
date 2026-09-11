-- =====================================================================
-- A control that cannot be evaluated has not passed
--
-- Ask the register about a period with nothing in it and, until now, it
-- answered that all eleven cross-reference points tie. Every figure on both
-- sides was COALESCEd to zero, zero equals zero, and the screen went green
-- over no books at all.
--
-- That is the most misleading thing this system could say. A brand-new
-- deployment on its first morning — before a single report has been
-- imported — would have shown a controller a fully reconciled file. So would
-- a period somebody opened and never loaded. The failure mode is not "wrong
-- answer"; it is "confident answer to a question nobody could have answered",
-- which is worse, because nothing about it looks wrong.
--
-- It is the same defect the general ledger's printed subtotals had: an
-- export that saved formulas without their cached values left the totals
-- empty, they read as zero, and the subtotal control reconciled zero against
-- zero and passed. That one was caught because a number looked odd. This one
-- would not have been.
--
-- So each control now says whether it could be evaluated at all, and a
-- control that could not is not a control that passed. `state` is the column
-- to read: TIES, OPEN, or NO DATA. `ties` stays boolean and stays false for
-- NO DATA, so the rate gate — which refuses to compute while any point is
-- open — also refuses over an empty period rather than waving it through.
--
-- The evaluability test differs per control, because they rest on different
-- documents. Sealing a period with no profit and loss in it is not the same
-- gap as sealing one with no payroll register, and telling somebody which
-- document is missing is most of the help they need.
-- =====================================================================

-- Dropped rather than replaced: the new columns sit before `note`,
-- and CREATE OR REPLACE cannot insert a column into a view.
DROP VIEW v_statement_reconciliation;

CREATE VIEW v_statement_reconciliation AS
WITH present AS (
  SELECT p.period,
         EXISTS (SELECT 1 FROM pl_account a  WHERE a.period = p.period) AS has_pl,
         EXISTS (SELECT 1 FROM bs_account b  WHERE b.period = p.period) AS has_bs,
         EXISTS (SELECT 1 FROM ledger_line l WHERE l.period = p.period) AS has_ledger,
         EXISTS (SELECT 1 FROM gl_opening o  WHERE o.period = p.period) AS has_openings,
         EXISTS (SELECT 1 FROM staging_batch b
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'
                    AND b.status = 'ACCEPTED')                          AS has_gl_import,
         EXISTS (SELECT 1 FROM labor_allocation la
                  WHERE la.period = p.period)                           AS has_payroll
    FROM fiscal_period p),
core AS (
  SELECT c.*,
         CASE c.control
           WHEN 'PL_FOOTING'          THEN pr.has_pl AND pr.has_bs
           WHEN 'BS_FOOTING'          THEN pr.has_bs
           WHEN 'GL_PROMOTE_COMPLETE' THEN pr.has_gl_import
           WHEN 'GL_SUBTOTALS'        THEN pr.has_gl_import
           WHEN 'GL_PL_SECTION'       THEN pr.has_ledger AND pr.has_pl
           WHEN 'GL_PL_ACCOUNT'       THEN pr.has_ledger AND pr.has_pl
           WHEN 'GL_PL_COVERAGE'      THEN pr.has_ledger AND pr.has_pl
           WHEN 'GL_BS_ACCOUNT'       THEN pr.has_openings AND pr.has_bs
           WHEN 'GL_BS_COVERAGE'      THEN pr.has_openings AND pr.has_bs
           WHEN 'SEGMENTATION'        THEN pr.has_ledger
           WHEN 'PAYROLL_REGISTER'    THEN pr.has_payroll AND pr.has_ledger
           ELSE true
         END                                               AS evaluable,
         -- What is missing, in the words of somebody who has to go and get
         -- it. "No data" on its own sends a person looking through eleven
         -- rows for which document they forgot.
         CASE c.control
           WHEN 'PL_FOOTING'          THEN 'the profit and loss and the balance sheet'
           WHEN 'BS_FOOTING'          THEN 'the balance sheet'
           WHEN 'GL_PROMOTE_COMPLETE' THEN 'an accepted general ledger import'
           WHEN 'GL_SUBTOTALS'        THEN 'an accepted general ledger import'
           WHEN 'GL_BS_ACCOUNT'       THEN 'the balance sheet, and the ledger''s opening balances'
           WHEN 'GL_BS_COVERAGE'      THEN 'the balance sheet, and the ledger''s opening balances'
           WHEN 'PAYROLL_REGISTER'    THEN 'the payroll register'
           ELSE 'the general ledger and the profit and loss'
         END                                               AS needs
    FROM (SELECT * FROM v_statement_reconciliation_core
          UNION ALL
          SELECT v.period, 110, 'PAYROLL_REGISTER', 'EXCEPTIONS',
                 'The payroll register agrees with the ledger''s wage accounts',
                 'Register', v.register_wages,
                 'Ledger wage accounts', v.ledger_wages,
                 v.unexplained,
                 CASE WHEN v.unexplained = 0 THEN 0 ELSE 1 END::numeric,
                 (v.unexplained = 0),
                 'The fringe base comes from the register, not from the '
                 'ledger, so a difference here is two denominators for one '
                 'rate. None of the other ten points touches the register — '
                 'which is how a $45,000 donor credit sat in an intern wage '
                 'account for a year.'
            FROM v_payroll_reconciliation v) c
    JOIN present pr ON pr.period = c.period)
SELECT period, seq, control, basis, description,
       left_label, left_value, right_label, right_value,
       variance, exceptions,
       -- A control that could not be evaluated has not passed.
       (ties AND evaluable)                                AS ties,
       evaluable,
       CASE WHEN NOT evaluable THEN 'NO DATA'
            WHEN ties          THEN 'TIES'
            ELSE                    'OPEN' END             AS state,
       CASE WHEN NOT evaluable
            THEN 'Nothing to compare yet — this needs ' || needs || '.'
            ELSE note END                                  AS note
  FROM core;

COMMENT ON VIEW v_statement_reconciliation IS
  'The cross-reference register. Read `state`: TIES, OPEN, or NO DATA. A '
  'control that cannot be evaluated is not a control that passed — an empty '
  'period used to report all eleven points green, which is the most '
  'misleading thing this system could have said.';
