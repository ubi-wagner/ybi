-- =====================================================================
-- Cross-reference reconciliation: the general ledger against both
-- statements it produces
--
-- Every control in this system up to now proved one report against itself,
-- or one figure against the ledger it came from. None of them proved that
-- the three source documents are three views of the same books. They have
-- to be, and an auditor will check, so the system should check first.
--
-- Three ties, and one of them was not previously possible:
--
--   General ledger to profit and loss. Every dated line in P&L scope,
--   summed by account, against the account as the P&L prints it.
--
--   General ledger to balance sheet. A balance sheet states a position and
--   a ledger states a year of movement, so the two are only comparable
--   through the position carried in. The parser skipped the "Beginning
--   Balance" rows as non-transactions — correct, they are not
--   transactions — and in skipping them threw away the only thing that
--   makes the balance sheet tieable. It keeps them now, and the sheet is
--   proved account by account off the ledger rather than trusted.
--
--   Balance sheet to profit and loss. Net income, already enforced in 023.
--
-- The ties do not come out clean, and that is the point. A reconciliation
-- whose only two outcomes are "zero" and "broken" gets forced to zero. This
-- one has a third outcome: a difference that is named, quantified, and
-- carried on the face of the reconciliation with the specific ledger lines
-- behind it. That is what a reconciling item is in an audit workpaper, and
-- reconciling_item is that workpaper line.
--
-- What a reconciling item may NOT be is a plug. Each one names the lines it
-- consists of, and a deferred trigger refuses it unless those lines add to
-- the amount claimed. A difference nobody can attribute to specific lines
-- stays unexplained, and the register says so.
-- =====================================================================


-- ── Opening balances ─────────────────────────────────────────────────

CREATE TABLE staging_opening (
  batch_id  uuid    NOT NULL REFERENCES staging_batch ON DELETE CASCADE,
  account   text    NOT NULL,
  amount    numeric(16,2) NOT NULL,
  PRIMARY KEY (batch_id, account)
);

CREATE TABLE gl_opening (
  period    text    NOT NULL REFERENCES fiscal_period,
  account   text    NOT NULL,
  import_id uuid    REFERENCES ledger_import,
  amount    numeric(16,2) NOT NULL,
  PRIMARY KEY (period, account)
);

COMMENT ON TABLE gl_opening IS
  'The balance each account was carried into the period at, as the general '
  'ledger prints it. Not activity — which is why it is not a ledger_line — '
  'but without it the balance sheet cannot be tied to anything.';


-- ── Accounts the two documents call by different names ───────────────
--
-- The general ledger calls the accumulated surplus "Retained Earnings"; the
-- balance sheet prints "3000 Fund Balance". Same $13,535,775.43, same
-- account, two labels. Matching on name alone would report it as a ledger
-- account missing from the sheet and a sheet account missing from the
-- ledger, which is two false findings standing in for one naming habit.
--
-- The alias is a written judgment with a reason, not a silent mapping table.

CREATE TABLE account_alias (
  period            text NOT NULL REFERENCES fiscal_period,
  gl_account        text NOT NULL,
  statement         text NOT NULL CHECK (statement IN ('P&L', 'BALANCE_SHEET')),
  statement_account text NOT NULL,      -- the leaf as that statement prints it
  reason            text NOT NULL CHECK (length(btrim(reason)) >= 20),
  recorded_by       text NOT NULL,
  recorded_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (period, gl_account, statement)
);


-- ── Reconciling items ────────────────────────────────────────────────

CREATE TYPE reconciling_kind AS ENUM (
  'RECLASS_AFTER_EXPORT',   -- the books moved between the two exports
  'TIMING',                 -- the two reports are two moments
  'PRESENTATION',           -- same figure, different place on the page
  'ROUNDING',
  'SOURCE_DEFECT');         -- the export itself is wrong

CREATE TABLE reconciling_item (
  item_id       bigserial PRIMARY KEY,
  period        text NOT NULL REFERENCES fiscal_period,
  control       text NOT NULL,          -- which control it explains
  from_account  text NOT NULL,          -- where the ledger puts the money
  to_account    text NOT NULL,          -- where the statement puts it
  amount        numeric(16,2) NOT NULL CHECK (amount <> 0),
  kind          reconciling_kind NOT NULL,
  explanation   text NOT NULL CHECK (length(btrim(explanation)) >= 30),
  recorded_by   text NOT NULL,
  recorded_at   timestamptz NOT NULL DEFAULT now(),
  -- Append-only, like every other judgment here. A reconciling item that
  -- turns out to be wrong is superseded in writing, not edited away.
  retracted_at     timestamptz,
  retracted_by     text,
  retracted_reason text,
  CHECK ((retracted_at IS NULL) = (retracted_reason IS NULL)),
  CHECK (from_account <> to_account)
);
CREATE INDEX ON reconciling_item (period, control) WHERE retracted_at IS NULL;

COMMENT ON TABLE reconciling_item IS
  'A named, evidenced difference between two source documents. Carried on '
  'the face of the reconciliation rather than netted away, because the '
  'difference is the finding.';

CREATE TABLE reconciling_item_line (
  item_id  bigint NOT NULL REFERENCES reconciling_item ON DELETE CASCADE,
  line_id  text   NOT NULL REFERENCES ledger_line,
  PRIMARY KEY (item_id, line_id)
);

COMMENT ON TABLE reconciling_item_line IS
  'The specific ledger lines an item consists of. This is what separates a '
  'reconciling item from a plug.';

-- The lines must add to the amount claimed. Deferred, so an item and its
-- lines can be written in one transaction in either order.
CREATE FUNCTION reconciling_lines_must_total() RETURNS trigger AS $$
DECLARE
  r        record;
  line_sum numeric(16,2);
BEGIN
  FOR r IN SELECT i.item_id, i.amount, i.from_account
             FROM reconciling_item i
            WHERE i.retracted_at IS NULL
              AND i.item_id = COALESCE(NEW.item_id, OLD.item_id)
  LOOP
    SELECT COALESCE(sum(l.amount), 0) INTO line_sum
      FROM reconciling_item_line rl
      JOIN ledger_line l ON l.line_id = rl.line_id
     WHERE rl.item_id = r.item_id;
    IF round(line_sum, 2) <> round(r.amount, 2) THEN
      RAISE EXCEPTION
        'reconciling item % claims % but its lines total % — a reconciling '
        'item names the lines it is made of, or it is a plug',
        r.item_id, r.amount, line_sum;
    END IF;
    -- Every line must actually sit in the account the item moves money out
    -- of, or the item is describing something other than what it says.
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

CREATE CONSTRAINT TRIGGER reconciling_lines_total
  AFTER INSERT OR UPDATE OR DELETE ON reconciling_item_line
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION reconciling_lines_must_total();

CREATE CONSTRAINT TRIGGER reconciling_item_total
  AFTER INSERT OR UPDATE ON reconciling_item
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION reconciling_lines_must_total();


-- ── The ledger against the profit and loss, account by account ───────

CREATE VIEW v_gl_pl_account AS
WITH gl AS (
  SELECT period, account, sum(amount) AS gl_amount, count(*) AS gl_lines
    FROM ledger_line WHERE statement = 'P&L' GROUP BY period, account),
pl AS (
  SELECT period, account, section, amount AS pl_amount FROM pl_account),
moved AS (
  SELECT period,
         from_account AS account,
         -sum(amount) AS adjustment
    FROM reconciling_item
   WHERE control = 'GL_PL_ACCOUNT' AND retracted_at IS NULL
   GROUP BY period, from_account
  UNION ALL
  SELECT period, to_account, sum(amount)
    FROM reconciling_item
   WHERE control = 'GL_PL_ACCOUNT' AND retracted_at IS NULL
   GROUP BY period, to_account),
adj AS (
  SELECT period, account, sum(adjustment) AS adjustment FROM moved
   GROUP BY period, account)
SELECT COALESCE(gl.period, pl.period, adj.period)            AS period,
       COALESCE(gl.account, pl.account, adj.account)         AS account,
       pl.section,
       COALESCE(gl.gl_amount, 0)                             AS gl_amount,
       COALESCE(gl.gl_lines, 0)                              AS gl_lines,
       COALESCE(pl.pl_amount, 0)                             AS pl_amount,
       COALESCE(adj.adjustment, 0)                           AS reconciling,
       round(COALESCE(gl.gl_amount, 0) - COALESCE(pl.pl_amount, 0), 2)
                                                             AS gross_variance,
       round(COALESCE(gl.gl_amount, 0) + COALESCE(adj.adjustment, 0)
             - COALESCE(pl.pl_amount, 0), 2)                 AS unexplained
  FROM gl
  FULL OUTER JOIN pl  ON pl.period = gl.period AND pl.account = gl.account
  FULL OUTER JOIN adj ON adj.period = COALESCE(gl.period, pl.period)
                     AND adj.account = COALESCE(gl.account, pl.account);

COMMENT ON VIEW v_gl_pl_account IS
  'Each P&L account as the ledger sums it, as the P&L prints it, and what '
  'is left once the named reconciling items are applied.';


-- ── The ledger against the balance sheet, account by account ─────────

CREATE VIEW v_gl_bs_account AS
WITH activity AS (
  SELECT period, account, sum(amount) AS amount, count(*) AS lines
    FROM ledger_line WHERE statement = 'BALANCE_SHEET' GROUP BY period, account),
gl AS (
  SELECT COALESCE(a.period, o.period)                  AS period,
         COALESCE(a.account, o.account)                AS account,
         COALESCE(o.amount, 0)                         AS opening,
         COALESCE(a.amount, 0)                         AS activity,
         COALESCE(a.lines, 0)                          AS lines,
         round(COALESCE(o.amount, 0) + COALESCE(a.amount, 0), 2) AS closing
    FROM activity a
    FULL OUTER JOIN gl_opening o ON o.period = a.period AND o.account = a.account),
named AS (
  SELECT gl.*,
         -- The sheet prints leaves, the ledger prints qualified paths.
         COALESCE(al.statement_account,
                  split_part(gl.account, ':',
                             array_length(string_to_array(gl.account, ':'), 1)))
                                                       AS bs_leaf,
         (al.gl_account IS NOT NULL)                   AS matched_by_alias
    FROM gl
    LEFT JOIN account_alias al ON al.period = gl.period
                              AND al.gl_account = gl.account
                              AND al.statement = 'BALANCE_SHEET')
SELECT n.period, n.account, n.bs_leaf, n.matched_by_alias,
       n.opening, n.activity, n.lines, n.closing,
       b.amount                                        AS bs_amount,
       b.side,
       (b.leaf IS NOT NULL)                            AS on_balance_sheet,
       round(n.closing - COALESCE(b.amount, 0), 2)     AS variance,
       -- QuickBooks omits an account whose ending balance is zero. That is
       -- a complete explanation, and a checkable one: the ledger has to
       -- agree that it closed at zero.
       (b.leaf IS NULL AND n.closing = 0)              AS absent_because_zero
  FROM named n
  LEFT JOIN bs_account b ON b.period = n.period AND b.leaf = n.bs_leaf
                        AND NOT b.is_rollup;

COMMENT ON VIEW v_gl_bs_account IS
  'Opening balance plus the year''s movement against the balance sheet as '
  'printed. An account the sheet omits has to close at zero in the ledger, '
  'which is checked rather than assumed.';


-- ── The control register ─────────────────────────────────────────────
--
-- One row per cross-reference point, in the order a reviewer would work
-- them: each report internally, then each report against the ledger, then
-- the two reports against each other, then what the ledger carries into
-- classification. A control that cannot be evaluated reports that, and does
-- not report "passed".

--
-- Each row carries a basis, because the controls are not all the same shape.
-- Some are a difference between two figures; some are a count of accounts
-- that disagree, where the two figures alongside are context. Saying which
-- one decides the row keeps a count of zero exceptions from being read as a
-- variance of zero, and the other way round.

CREATE VIEW v_statement_reconciliation AS
WITH p AS (SELECT period FROM fiscal_period),
reg AS (

-- 1. Net income, computed one way and carried the other.
SELECT p.period, 10 AS seq, 'PL_FOOTING' AS control, 'VARIANCE' AS basis,
       'Profit and loss foots to the net income the sheet carries' AS description,
       'P&L sections' AS left_label,
       COALESCE((SELECT sum(amount) FILTER (WHERE section = 'Income')
                      - sum(amount) FILTER (WHERE section = 'Expense')
                      - sum(amount) FILTER (WHERE section = 'COGS')
                      + sum(amount) FILTER (WHERE section = 'Other Income')
                   FROM pl_account a WHERE a.period = p.period), 0) AS left_value,
       'Balance sheet net income' AS right_label,
       COALESCE((SELECT b.amount FROM bs_account b
                  WHERE b.period = p.period AND b.leaf ILIKE 'net income%'
                    AND NOT b.is_rollup LIMIT 1), 0) AS right_value,
       0::numeric AS exceptions,
       'Net income as the P&L computes it must equal what the sheet carries '
       'in equity. Two exports that disagree are two different moments in '
       'the same books, and everything built on either is suspect.' AS note
  FROM p

UNION ALL
-- 2. The oldest control there is.
SELECT p.period, 20, 'BS_FOOTING', 'VARIANCE',
       'Balance sheet balances',
       'Assets',
       COALESCE((SELECT sum(amount) FROM bs_account b
                  WHERE b.period = p.period AND b.side = 'ASSET'
                    AND NOT b.is_rollup), 0),
       'Liabilities and equity',
       COALESCE((SELECT sum(amount) FROM bs_account b
                  WHERE b.period = p.period AND b.side IN ('LIABILITY', 'EQUITY')
                    AND NOT b.is_rollup), 0),
       0,
       'Assets less liabilities and equity.'
  FROM p

UNION ALL
-- 3. Nothing lost between the file and the ledger.
SELECT p.period, 30, 'GL_PROMOTE_COMPLETE', 'VARIANCE',
       'Every staged line reached the ledger',
       'Dated lines staged',
       COALESCE((SELECT count(*) FROM staging_line s
                   JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'
                    AND b.status = 'ACCEPTED' AND s.txn_date IS NOT NULL), 0),
       'Lines in the ledger',
       COALESCE((SELECT count(*) FROM ledger_line l WHERE l.period = p.period), 0),
       0,
       'The promote path dedupes on each line''s natural key. When two '
       'genuinely different lines hash alike one is dropped and nothing '
       'raises: 71 lines carrying $24,082.67 went that way before the key '
       'learned to number repeats. This counts them.'
  FROM p

UNION ALL
-- 4. The report reconciles to itself.
SELECT p.period, 40, 'GL_SUBTOTALS', 'VARIANCE',
       'Printed account totals agree with the parsed lines',
       'Printed',
       COALESCE((SELECT sum(printed_total) FROM staging_subtotal s
                   JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'
                    AND b.status = 'ACCEPTED'), 0),
       'Parsed',
       COALESCE((SELECT sum(parsed_total) FROM staging_subtotal s
                   JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'
                    AND b.status = 'ACCEPTED'), 0),
       COALESCE((SELECT count(*) FROM staging_subtotal s
                   JOIN staging_batch b USING (batch_id)
                  WHERE b.period = p.period AND b.report = 'GENERAL_LEDGER'
                    AND b.status = 'ACCEPTED'
                    AND abs(s.parsed_total - s.printed_total) > 0.005), 0),
       'QuickBooks prints its own account totals. Reconciling against them '
       'catches almost every parsing mistake and costs nothing.'
  FROM p

UNION ALL
-- 5. The ledger against the P&L, by section.
SELECT p.period, 50, 'GL_PL_SECTION', 'VARIANCE',
       'Ledger P&L-scope activity agrees with the P&L by section',
       'Ledger',
       COALESCE((SELECT sum(amount) FROM ledger_line l
                  WHERE l.period = p.period AND l.statement = 'P&L'), 0),
       'P&L',
       COALESCE((SELECT sum(amount) FROM pl_account a WHERE a.period = p.period), 0),
       COALESCE((SELECT count(*) FROM (
            SELECT COALESCE(g.section, a.section) AS section
              FROM (SELECT section, sum(amount) amt FROM ledger_line
                     WHERE period = p.period AND statement = 'P&L'
                     GROUP BY section) g
              FULL OUTER JOIN (SELECT section, sum(amount) amt FROM pl_account
                                WHERE period = p.period GROUP BY section) a
                ON a.section = g.section
             WHERE round(COALESCE(g.amt, 0) - COALESCE(a.amt, 0), 2) <> 0) x), 0),
       'Section totals are where a mis-sectioned account shows: four leaves '
       'in this chart sit under both an income and an expense parent, and '
       'reading an expense as revenue moves the section without moving the '
       'grand total.'
  FROM p

UNION ALL
-- 6. The ledger against the P&L, account by account.
SELECT p.period, 60, 'GL_PL_ACCOUNT', 'EXCEPTIONS',
       'Ledger agrees with the P&L account by account',
       'Gross difference',
       COALESCE((SELECT sum(abs(gross_variance)) FROM v_gl_pl_account v
                  WHERE v.period = p.period), 0),
       'Left unexplained',
       COALESCE((SELECT sum(abs(unexplained)) FROM v_gl_pl_account v
                  WHERE v.period = p.period), 0),
       COALESCE((SELECT count(*) FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.unexplained <> 0), 0),
       'Sections can tie while accounts do not: money moved between two '
       'expense accounts nets to nothing at the section line. Each account '
       'that differs is either a named reconciling item with the ledger '
       'lines behind it, or it is unexplained.'
  FROM p

UNION ALL
-- 7. No account on one side the other has never heard of.
SELECT p.period, 70, 'GL_PL_COVERAGE', 'EXCEPTIONS',
       'Every P&L account exists on both sides',
       'Ledger accounts absent from the P&L',
       COALESCE((SELECT count(*) FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.gl_lines > 0
                    AND v.pl_amount = 0 AND v.section IS NULL), 0),
       'P&L accounts with no ledger lines',
       COALESCE((SELECT count(*) FROM v_gl_pl_account v
                  WHERE v.period = p.period AND v.gl_lines = 0
                    AND v.pl_amount <> 0), 0),
       COALESCE((SELECT count(*) FROM v_gl_pl_account v
                  WHERE v.period = p.period
                    AND ((v.gl_lines > 0 AND v.pl_amount = 0 AND v.section IS NULL)
                      OR (v.gl_lines = 0 AND v.pl_amount <> 0))), 0),
       'A P&L account with no ledger behind it cannot be classified, and a '
       'ledger account off the P&L is cost with nowhere to land.'
  FROM p

UNION ALL
-- 8. The ledger against the balance sheet, account by account.
SELECT p.period, 80, 'GL_BS_ACCOUNT', 'EXCEPTIONS',
       'Opening balance plus the year''s movement equals the sheet',
       'Accounts tied',
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet
                    AND v.variance = 0), 0),
       'Accounts off',
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet
                    AND v.variance <> 0), 0),
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND v.on_balance_sheet
                    AND v.variance <> 0), 0),
       'The tie the system could not make until the ledger''s opening '
       'balances were kept. It proves the sheet off the ledger rather than '
       'trusting two exports to agree.'
  FROM p

UNION ALL
-- 9. Accounts the sheet omits.
SELECT p.period, 90, 'GL_BS_COVERAGE', 'EXCEPTIONS',
       'Accounts absent from the sheet closed at zero',
       'Absent, closing at zero',
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet
                    AND v.absent_because_zero), 0),
       'Absent, carrying a balance',
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet
                    AND NOT v.absent_because_zero), 0),
       COALESCE((SELECT count(*) FROM v_gl_bs_account v
                  WHERE v.period = p.period AND NOT v.on_balance_sheet
                    AND NOT v.absent_because_zero), 0),
       'QuickBooks omits an account that ends at zero, which is a complete '
       'explanation and a checkable one. An absent account still carrying a '
       'balance is a hole in the sheet.'
  FROM p

UNION ALL
-- 10. Splitting a line is analytical, and must not move the total.
SELECT p.period, 100, 'SEGMENTATION', 'VARIANCE',
       'Split lines still sum to the lines they came from',
       'Ledger',
       COALESCE((SELECT source_total FROM v_segmentation_control s
                  WHERE s.period = p.period), 0),
       'Analytical',
       COALESCE((SELECT analytical_total FROM v_segmentation_control s
                  WHERE s.period = p.period), 0),
       0,
       'Splitting a line for classification is an analytical act on the same '
       'money. It must not change what there is.'
  FROM p
)
SELECT period, seq, control, basis, description,
       left_label, left_value, right_label, right_value,
       round(left_value - right_value, 2)                 AS variance,
       exceptions,
       CASE basis
         WHEN 'VARIANCE'   THEN round(left_value - right_value, 2) = 0
                                AND exceptions = 0
         WHEN 'EXCEPTIONS' THEN exceptions = 0
       END                                                AS ties,
       note
  FROM reg;

COMMENT ON VIEW v_statement_reconciliation IS
  'The cross-reference register: every point at which the general ledger, '
  'the profit and loss and the balance sheet are required to agree, and '
  'what is left over at each. Read before anything is classified, and '
  'again before any rate.';
