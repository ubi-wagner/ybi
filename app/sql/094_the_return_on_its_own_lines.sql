-- 094 — Form 990 Part IX on the return's own lines
--
-- `092` made the compensation rows cross-foot and left the sheet organised by
-- **natural category** — the bookkeeper's own top-level account groups, ten of
-- them. That is the right shape for reading the ledger and it is **not the
-- Statement of Functional Expenses.** Part IX has twenty-five numbered lines
-- and a preparer has to put every account on one of them; a workbook that
-- prints `Management & Administrative Expenses  935,379.44` tells them
-- nothing about which line it goes on, and the 2024 return split that same
-- money across occupancy, office, insurance, dues, meals, real estate taxes
-- and four others.
--
-- So the comparison the file has never been able to make — **this year's
-- return against last year's, line for line** — could not be made at all.
-- `docs/FORM_990_2025_vs_2024.md` is that comparison and this is what it
-- reads.
--
-- **The map is a transcription of a judgment, and it is data.** Which IRS
-- line an account belongs on is what a preparer decided; `v_payroll
-- _reconciliation`'s six fringe accounts are named by hand for exactly this
-- reason and `CLAUDE.md` says why — *inventing a rule to derive that judgment
-- would be guessing at it*. So it is a table rather than a CASE, seeded here,
-- readable, and amendable by a preparer who disagrees. What is **not** a
-- judgment is completeness, and `v_form_990_line_check` holds that: an
-- account on no line is money that would fall off the return.
--
-- **Longest prefix wins**, so `5080 Fundraising:5089 Special Events` beats
-- `5080 Fundraising` and a child can be routed away from its parent without
-- restating the parent.
--
-- Three things the 2024 return does that this had no way to express:
--
--   * **Part VIII line 8b.** The direct expenses of a fundraising event are
--     netted against that event's gross receipts in Part VIII and are
--     **excluded from Part IX** — the form says so at the head of the part,
--     "do not include amounts reported on lines 6b, 7b, 8b, 9b and 10b".
--     2024 netted $139,739 that way. Line `8b` here is a real line of the
--     return and carries that cost out of the functional total, so Part IX
--     stops over-reporting expenses by the cost of the Shark Tank.
--   * **Line 5 against line 7.** The 2024 return put $167,967 of officer,
--     director, trustee and key-employee compensation on line 5. Nothing on
--     this record separates it: `5140 Employee Wages` is undifferentiated and
--     no column says who is an officer. The line exists and is **empty on
--     purpose**, and the comparison names it — an empty line that should
--     carry something is a question, and a line silently folded into another
--     is not.
--   * **Line 3, foreign.** 2024 reported $63,568 there. Nothing in the 2025
--     ledger names a foreign recipient, so the line is zero and the
--     comparison asks about it rather than assuming.

CREATE TABLE IF NOT EXISTS form_990_line (
    line_id   text PRIMARY KEY,
    seq       integer NOT NULL,
    part      text    NOT NULL DEFAULT 'IX',
    label     text    NOT NULL,
    note      text    NOT NULL DEFAULT '',

    CONSTRAINT form_990_part_is_known CHECK (part IN ('IX', 'VIII'))
);

COMMENT ON TABLE form_990_line IS
  'The numbered lines of Form 990 Part IX, in the order the form prints '
  'them, plus the one Part VIII line whose amounts are netted out of Part IX. '
  'Declared rather than derived from the rows: a line with nothing on it is a '
  'fact about the year and has to print, which a SELECT DISTINCT over the '
  'ledger cannot do — 029 in the place a tax return is read.';

INSERT INTO form_990_line (line_id, seq, part, label, note) VALUES
  ('1',   10, 'IX', 'Grants and other assistance to domestic organizations and domestic governments', ''),
  ('2',   20, 'IX', 'Grants and other assistance to domestic individuals', ''),
  ('3',   30, 'IX', 'Grants and other assistance to foreign organizations, foreign governments, and foreign individuals', ''),
  ('4',   40, 'IX', 'Benefits paid to or for members', ''),
  ('5',   50, 'IX', 'Compensation of current officers, directors, trustees, and key employees',
   'Nothing on this record separates officer compensation from other wages. The 2024 return reported 167,967 here.'),
  ('6',   60, 'IX', 'Compensation not included above, to disqualified persons', ''),
  ('7',   70, 'IX', 'Other salaries and wages', ''),
  ('8',   80, 'IX', 'Pension plan accruals and contributions', ''),
  ('9',   90, 'IX', 'Other employee benefits', ''),
  ('10', 100, 'IX', 'Payroll taxes', ''),
  ('11a',110, 'IX', 'Fees for services (non-employees): Management', ''),
  ('11b',120, 'IX', 'Fees for services (non-employees): Legal', ''),
  ('11c',130, 'IX', 'Fees for services (non-employees): Accounting', ''),
  ('11d',140, 'IX', 'Fees for services (non-employees): Lobbying', ''),
  ('11e',150, 'IX', 'Fees for services (non-employees): Professional fundraising services', ''),
  ('11f',160, 'IX', 'Fees for services (non-employees): Investment management fees', ''),
  ('11g',170, 'IX', 'Fees for services (non-employees): Other', ''),
  ('12', 180, 'IX', 'Advertising and promotion', ''),
  ('13', 190, 'IX', 'Office expenses', ''),
  ('14', 200, 'IX', 'Information technology', ''),
  ('15', 210, 'IX', 'Royalties', ''),
  ('16', 220, 'IX', 'Occupancy', ''),
  ('17', 230, 'IX', 'Travel', ''),
  ('18', 240, 'IX', 'Payments of travel or entertainment expenses for any federal, state, or local public officials', ''),
  ('19', 250, 'IX', 'Conferences, conventions, and meetings', ''),
  ('20', 260, 'IX', 'Interest', ''),
  ('21', 270, 'IX', 'Payments to affiliates', ''),
  ('22', 280, 'IX', 'Depreciation, depletion, and amortization', ''),
  ('23', 290, 'IX', 'Insurance', ''),
  ('24a',300, 'IX', 'Dues and subscriptions', ''),
  ('24b',310, 'IX', 'Training and seminars', ''),
  ('24c',320, 'IX', 'Real estate taxes', ''),
  ('24d',330, 'IX', 'Meals', ''),
  ('24e',340, 'IX', 'All other expenses', ''),
  ('8b', 900, 'VIII', 'Direct expenses of fundraising events — netted in Part VIII and excluded from Part IX',
   'The form''s own instruction at the head of Part IX. The 2024 return netted 139,739 this way.')
ON CONFLICT (line_id) DO UPDATE
  SET seq = EXCLUDED.seq, part = EXCLUDED.part,
      label = EXCLUDED.label, note = EXCLUDED.note;


CREATE TABLE IF NOT EXISTS form_990_account_line (
    account_prefix text PRIMARY KEY,
    line_id        text NOT NULL REFERENCES form_990_line(line_id),
    note           text NOT NULL DEFAULT ''
);

COMMENT ON TABLE form_990_account_line IS
  'Which Part IX line each account belongs on, by longest matching prefix of '
  'the account path. A transcription of a preparer''s judgment, held as data '
  'so it can be read and amended — the same reason v_payroll_reconciliation '
  'names its six fringe accounts by hand. Completeness is not a judgment and '
  'v_form_990_line_check holds it.';

INSERT INTO form_990_account_line (account_prefix, line_id, note) VALUES
  ('Grant Expenses', '1',
   'Subawards and pass-through grants to named organisations — Lake to River Foundation, Ohio State University, Columbiana County Port Authority, NCDMM and forty others.'),

  ('5129 Payroll Expenses:5139 Wages', '7', ''),
  ('5129 Payroll Expenses:5133 401k Match & Profit Sharing', '8', ''),
  ('5129 Payroll Expenses:5130 Benefits', '9', ''),
  ('5129 Payroll Expenses:5141 Payroll Taxes', '10', ''),
  ('5129 Payroll Expenses:5137 Payroll Processing Fees', '13',
   'The cost of administering the payroll, not compensation. The classification log puts it in G&A under 200.414(a) for the same reason.'),

  ('Management & Administrative Expenses:5201 Professional Services:5202 Accounting', '11c', ''),
  ('Management & Administrative Expenses:5201 Professional Services', '11g', ''),
  ('Program Expenses:ESP:5221 ESP/EIR Consulting', '11g', ''),
  ('Program Expenses:ESP:5227 Portfolio consulting', '11g',
   'The fifty-fifty cost share with portfolio companies. 200.331 reads these as contractors, which is also what the return calls them.'),

  ('5080 Fundraising:5085 Advertising', '12', ''),
  ('Program Expenses:ESP:ESP Marketing', '12', ''),
  ('Program Expenses:5900 Additive Manufacturing:Advanced Mfg Marketing', '12', ''),
  ('Program Expenses:5014 MBAC - ODSA - YBI:MBAC/Power Marketing', '12', ''),

  ('Management & Administrative Expenses:5100 Office Expenses', '13', ''),
  ('Management & Administrative Expenses:5000 Bank Service Charges', '13', ''),
  ('Management & Administrative Expenses:5315 Finance Charge/Paypal/Eventbrit', '13', ''),
  ('Channel selling fees', '13', ''),

  ('Management & Administrative Expenses:5024 Facilities Expense', '16',
   'Maintenance, utilities, janitorial, security and waste removal across five buildings. The 200.465 carve-out is a rate adjustment and does not reach the return.'),

  ('Management & Administrative Expenses:5205 Travel', '17', ''),
  ('Management & Administrative Expenses:5205 Travel:5213 Conference/Seminar', '19', ''),
  ('5080 Fundraising:5095 Workshops/Seminars', '19', ''),

  ('5310 Interest Expense', '20', ''),
  ('5010 Depreciation Expense', '22', ''),
  ('Management & Administrative Expenses:5075 Insurance', '23', ''),
  ('Management & Administrative Expenses:5215 Dues and Subscriptions', '24a', ''),
  ('Management & Administrative Expenses:5300 Staff Training - Education', '24b', ''),
  ('Management & Administrative Expenses:5200 Real Estate Tax', '24c', ''),
  ('Management & Administrative Expenses:5250 Meals & Entertainment', '24d', ''),

  ('5001 Cost of Goods Sold', '24e', ''),
  ('5400 Bad Debt Expense', '24e', ''),
  ('Management & Administrative Expenses', '24e',
   'The residual of the administrative tree — anything not routed to a line of its own above.'),
  ('Management & Administrative Expenses:5015 Equipment Expenses', '24e', ''),
  ('Management & Administrative Expenses:5220 Contributions', '24e', ''),
  ('5080 Fundraising:5120 Government Relations', '24e', ''),
  ('Program Expenses', '24e',
   'Programme delivery cost that is not consulting or marketing — MBAC, Youth Entrepreneurship, SBA Growth Accelerator, additive manufacturing supplies, VGV.'),

  ('5080 Fundraising:5089 Special Events', '8b',
   'Shark Tank, AMUX, EmpowerUS and the mixers. Netted against those events'' gross receipts in Part VIII line 8 and excluded from Part IX by the form''s own instruction.')
ON CONFLICT (account_prefix) DO UPDATE
  SET line_id = EXCLUDED.line_id, note = EXCLUDED.note;


-- ── The return, by line ───────────────────────────────────────────────

CREATE OR REPLACE VIEW v_form_990_part_ix AS
WITH cost AS (
  SELECT l.period, l.line_id AS ledger_line, l.account, l.amount
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Expense', 'COGS'))),
-- Longest matching prefix, so a child routed away from its parent wins.
routed AS (
  SELECT DISTINCT ON (c.period, c.ledger_line)
         c.period, c.ledger_line, c.account, c.amount, m.line_id
    FROM cost c
    JOIN form_990_account_line m
      ON c.account = m.account_prefix
      OR c.account LIKE m.account_prefix || ':%'
   ORDER BY c.period, c.ledger_line, length(m.account_prefix) DESC),
judged AS (
  SELECT r.period, r.line_id, r.amount, r.ledger_line,
         COALESCE(d.function_990::text, 'NOT_YET_CLASSIFIED') AS function_990
    FROM routed r
    LEFT JOIN decision_line dl ON dl.line_id = r.ledger_line AND dl.live
    LEFT JOIN decision d ON d.decision_id = dl.decision_id
                        AND d.reversed_at IS NULL),
-- The compensation block carries no 990 function of its own: the pool
-- judgment on a wage account is EXCLUDED, which is right about the rate and
-- says nothing about the column. `092`'s driver, on the return's own lines.
compensation AS (
  SELECT period, line_id, sum(amount) AS amount, count(*) AS lines
    FROM judged
   WHERE function_990 = 'NOT_APPLICABLE' AND line_id IN ('7', '8', '9', '10')
   GROUP BY period, line_id),
split AS (
  SELECT c.period, c.line_id, f.function_990,
         CASE f.function_990
           WHEN 'PROGRAM' THEN c.amount
             - round(c.amount * COALESCE((SELECT share
                  FROM v_labour_function_share x
                 WHERE x.period = c.period
                   AND x.function_990 = 'MANAGEMENT_AND_GENERAL'), 0), 2)
             - round(c.amount * COALESCE((SELECT share
                  FROM v_labour_function_share x
                 WHERE x.period = c.period
                   AND x.function_990 = 'FUNDRAISING'), 0), 2)
           ELSE round(c.amount * f.share, 2)
         END                                                     AS amount,
         CASE WHEN f.function_990 = 'PROGRAM' THEN c.lines ELSE 0 END AS lines
    FROM compensation c
    JOIN v_labour_function_share f ON f.period = c.period),
allocated AS (
  SELECT period, line_id, function_990, amount, 1 AS lines
    FROM judged
   WHERE NOT (function_990 = 'NOT_APPLICABLE' AND line_id IN ('7','8','9','10'))
  UNION ALL
  SELECT period, line_id, function_990, amount, lines FROM split),
by_line AS (
  SELECT period, line_id,
         sum(amount)                                                    AS total,
         sum(amount) FILTER (WHERE function_990 = 'PROGRAM')            AS program,
         sum(amount) FILTER (WHERE function_990 = 'MANAGEMENT_AND_GENERAL') AS management,
         sum(amount) FILTER (WHERE function_990 = 'FUNDRAISING')        AS fundraising,
         sum(amount) FILTER (WHERE function_990 = 'NOT_YET_CLASSIFIED') AS unjudged,
         sum(amount) FILTER (WHERE function_990 = 'NOT_APPLICABLE')     AS not_applicable,
         sum(lines)::bigint                                             AS lines
    FROM allocated GROUP BY period, line_id)
SELECT p.period,
       fl.line_id,
       fl.seq,
       fl.part,
       fl.label,
       fl.note,
       COALESCE(b.total, 0)          AS total,
       COALESCE(b.program, 0)        AS program,
       COALESCE(b.management, 0)     AS management,
       COALESCE(b.fundraising, 0)    AS fundraising,
       COALESCE(b.unjudged, 0)       AS unjudged,
       COALESCE(b.not_applicable, 0) AS not_applicable,
       COALESCE(b.lines, 0)          AS lines
  FROM fiscal_period p
 CROSS JOIN form_990_line fl
  LEFT JOIN by_line b ON b.period = p.period AND b.line_id = fl.line_id;

COMMENT ON VIEW v_form_990_part_ix IS
  'Form 990 Part IX on the return''s own numbered lines, with the one Part '
  'VIII line whose amounts the form excludes from Part IX. Every line prints '
  'whether or not it carries anything, because an empty line is a fact about '
  'the year. Compensation is split by the effort distribution, per 092.';


-- ── The control ───────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_form_990_line_check AS
WITH cost AS (
  SELECT l.period, l.account, l.amount
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Expense', 'COGS'))),
unmapped AS (
  SELECT period, count(DISTINCT account) AS accounts, sum(amount) AS amount
    FROM cost c
   WHERE NOT EXISTS (SELECT 1 FROM form_990_account_line m
                      WHERE c.account = m.account_prefix
                         OR c.account LIKE m.account_prefix || ':%')
   GROUP BY period),
ledger AS (SELECT period, sum(amount) AS amount FROM cost GROUP BY period),
onform AS (
  SELECT period,
         sum(total) FILTER (WHERE part = 'IX')   AS part_ix,
         sum(total) FILTER (WHERE part = 'VIII') AS netted
    FROM v_form_990_part_ix GROUP BY period)
SELECT p.period,
       COALESCE(l.amount, 0)            AS ledger_expense,
       COALESCE(o.part_ix, 0)           AS part_ix_total,
       COALESCE(o.netted, 0)            AS netted_in_part_viii,
       COALESCE(u.accounts, 0)          AS unmapped_accounts,
       COALESCE(u.amount, 0)            AS unmapped_amount,
       COALESCE(l.amount, 0) - COALESCE(o.part_ix, 0)
         - COALESCE(o.netted, 0)        AS variance,
       CASE WHEN COALESCE(l.amount, 0) = 0             THEN 'NO DATA'
            WHEN COALESCE(u.accounts, 0) > 0           THEN 'OPEN'
            WHEN COALESCE(l.amount, 0) - COALESCE(o.part_ix, 0)
                 - COALESCE(o.netted, 0) <> 0          THEN 'OPEN'
            ELSE 'TIES' END             AS state,
       CASE WHEN COALESCE(l.amount, 0) = 0
              THEN 'the profit and loss, imported'
            WHEN COALESCE(u.accounts, 0) > 0
              THEN format('%s account(s) carrying %s are on no line of the '
                          'return. Money on no line is money that falls off '
                          'it.', u.accounts,
                          to_char(u.amount, 'FM999,999,999.00'))
            WHEN COALESCE(l.amount, 0) - COALESCE(o.part_ix, 0)
                 - COALESCE(o.netted, 0) <> 0
              THEN 'the return and the ledger disagree'
            ELSE '' END                 AS needs
  FROM fiscal_period p
  LEFT JOIN ledger l ON l.period = p.period
  LEFT JOIN onform o ON o.period = p.period
  LEFT JOIN unmapped u ON u.period = p.period;

COMMENT ON VIEW v_form_990_line_check IS
  'Every expense account is on exactly one line of the return, and the lines '
  'add back to the ledger. An account on no line is money that would fall off '
  'the return without anything saying so — which is the only half of this '
  'mapping that is not a judgment.';
