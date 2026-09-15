-- 095 — Form 990 Part VIII, so the whole return is accounted for
--
-- `094` put the expenses on the return's own lines. **Nothing in this system
-- has ever touched the revenue side at all** — `064` took the Income section
-- out of the classification scope, correctly, because grant income does not
-- go in a cost pool, and this file already records what that cost once:
-- *taking it out of scope became taking it out of mind*, and thirty-six
-- months of America Makes billing sat one join away from every figure
-- computed without them.
--
-- A return is revenue and expenses. Comparing 2025 with 2024 line for line
-- over Part IX alone accounts for $6.6m of a $13.4m document.
--
-- Same two tables as `094`, same longest-prefix rule, same reason the map is
-- data rather than a CASE. What differs is the scope: the Income and Other
-- Income sections of the profit and loss, which are the sections `v_cost_line`
-- deliberately excludes.
--
-- Three things the 2024 return did that the map has to be read against, and
-- each is a question for the preparer rather than something to settle here:
--
--   * **Line 2 was zero.** YBI books $119,912 of manufacturing services,
--     service fees, X-Jet income and youth programme fees, which read as
--     programme service revenue. The 2024 preparer reported none, so those
--     receipts went somewhere else on that return.
--   * **Line 8a was $367,629.** The 2025 ledger's event ticket sales are
--     $23,162.02 and its event sponsorships $254,709.00. Whether a sponsorship
--     is a contribution on line 1c or event income on line 8a is the choice
--     the form's own parenthesis is about, and the two years plainly answer
--     it differently.
--   * **Line 6b was zero.** YBI does not net rental expenses against rents,
--     so occupancy stays in Part IX line 16. The map keeps that, because
--     changing it would move half a million dollars between two parts of the
--     return on nobody's instruction.

INSERT INTO form_990_line (line_id, seq, part, label, note) VALUES
  ('V1',  1010, 'VIII', 'Contributions, gifts, grants and other similar amounts (line 1h)', ''),
  ('V2',  1020, 'VIII', 'Program service revenue (line 2g)',
   'The 2024 return reported none. YBI books manufacturing services, service fees and programme fees, which read as this line.'),
  ('V3',  1030, 'VIII', 'Investment income (line 3)', ''),
  ('V5',  1050, 'VIII', 'Royalties (line 5)', ''),
  ('V6',  1060, 'VIII', 'Gross rents — real property (line 6a)',
   'Rental expenses are not netted here: 2024 reported line 6b as zero and occupancy stays in Part IX line 16.'),
  ('V8',  1080, 'VIII', 'Gross income from fundraising events (line 8a)',
   'Contributions reported on line 1c are excluded from this line, which is where the 2024 and 2025 treatments of event sponsorship diverge.'),
  ('V10', 1100, 'VIII', 'Gross sales of inventory (line 10a)', ''),
  ('V11', 1110, 'VIII', 'Miscellaneous revenue (line 11a)', '')
ON CONFLICT (line_id) DO UPDATE
  SET seq = EXCLUDED.seq, part = EXCLUDED.part,
      label = EXCLUDED.label, note = EXCLUDED.note;

INSERT INTO form_990_account_line (account_prefix, line_id, note) VALUES
  ('3900 Grant Income', 'V1', ''),
  ('4000 Contributions Income', 'V1',
   'Including the Shark Tank, AMUX and EmpowerUS sponsorships, read as contributions rather than as event income.'),
  ('4800 Innovation Hub', 'V1', ''),
  ('4015 Program Fees:4010 State Funding-ODSA-ESP', 'V1',
   'State of Ohio programme funding — a grant, not a fee for service.'),

  ('4015 Program Fees:4242 Manufacturing Services', 'V2', ''),
  ('4015 Program Fees:4241 Service/Fee Income', 'V2', ''),
  ('4015 Program Fees:4039 X-JET Income', 'V2', ''),
  ('4015 Program Fees:Youth Entrepreneurship', 'V2', ''),

  ('5107 Interest Income', 'V3', ''),

  ('4015 Program Fees:4015.1 Rent/Utilities', 'V6',
   'Rent and the utilities recharged with it, across the five buildings, tying to the 2025 lease schedule.'),

  ('4015 Program Fees:4035 Events/Seminars', 'V8',
   'Ticket sales only. The sponsorships of the same events are on line 1.'),

  ('4040 Reimbursements', 'V11', ''),
  ('5108 Other Income', 'V11',
   'Carrying the $105,865.41 Q1 2020 Employee Retention Tax Credit received from Staffmark in May 2025, which 200.406(b) makes due back to the awards that bore the wage cost.')
ON CONFLICT (account_prefix) DO UPDATE
  SET line_id = EXCLUDED.line_id, note = EXCLUDED.note;


CREATE OR REPLACE VIEW v_form_990_part_viii AS
WITH revenue AS (
  SELECT l.period, l.line_id AS ledger_line, l.account, l.amount
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Income', 'Other Income'))),
routed AS (
  SELECT DISTINCT ON (r.period, r.ledger_line)
         r.period, r.ledger_line, r.amount, m.line_id
    FROM revenue r
    JOIN form_990_account_line m
      ON r.account = m.account_prefix
      OR r.account LIKE m.account_prefix || ':%'
   ORDER BY r.period, r.ledger_line, length(m.account_prefix) DESC),
by_line AS (
  SELECT period, line_id, sum(amount) AS amount, count(*)::bigint AS lines
    FROM routed GROUP BY period, line_id)
SELECT p.period, fl.line_id, fl.seq, fl.label, fl.note,
       COALESCE(b.amount, 0) AS amount,
       COALESCE(b.lines, 0)  AS lines
  FROM fiscal_period p
 CROSS JOIN form_990_line fl
  LEFT JOIN by_line b ON b.period = p.period AND b.line_id = fl.line_id
 WHERE fl.part = 'VIII' AND fl.line_id <> '8b';

COMMENT ON VIEW v_form_990_part_viii IS
  'Form 990 Part VIII on the return''s own lines. The revenue side had no '
  'reader at all before 095: 064 took the Income section out of the '
  'classification scope, which was right, and left it out of every document '
  'the system produces.';


CREATE OR REPLACE VIEW v_form_990_revenue_check AS
WITH revenue AS (
  SELECT l.period, l.account, l.amount
    FROM ledger_line l
   WHERE EXISTS (SELECT 1 FROM pl_account p
                  WHERE p.period = l.period AND p.account = l.account
                    AND p.section IN ('Income', 'Other Income'))),
unmapped AS (
  SELECT period, count(DISTINCT account) AS accounts, sum(amount) AS amount
    FROM revenue r
   WHERE NOT EXISTS (SELECT 1 FROM form_990_account_line m
                      WHERE r.account = m.account_prefix
                         OR r.account LIKE m.account_prefix || ':%')
   GROUP BY period),
ledger AS (SELECT period, sum(amount) AS amount FROM revenue GROUP BY period),
onform AS (SELECT period, sum(amount) AS amount
             FROM v_form_990_part_viii GROUP BY period)
SELECT p.period,
       COALESCE(l.amount, 0)   AS ledger_revenue,
       COALESCE(o.amount, 0)   AS part_viii_total,
       COALESCE(u.accounts, 0) AS unmapped_accounts,
       COALESCE(u.amount, 0)   AS unmapped_amount,
       COALESCE(l.amount, 0) - COALESCE(o.amount, 0) AS variance,
       CASE WHEN COALESCE(l.amount, 0) = 0        THEN 'NO DATA'
            WHEN COALESCE(u.accounts, 0) > 0      THEN 'OPEN'
            WHEN COALESCE(l.amount, 0) <> COALESCE(o.amount, 0) THEN 'OPEN'
            ELSE 'TIES' END    AS state,
       CASE WHEN COALESCE(l.amount, 0) = 0
              THEN 'the profit and loss, imported'
            WHEN COALESCE(u.accounts, 0) > 0
              THEN format('%s revenue account(s) carrying %s are on no line '
                          'of the return.', u.accounts,
                          to_char(u.amount, 'FM999,999,999.00'))
            WHEN COALESCE(l.amount, 0) <> COALESCE(o.amount, 0)
              THEN 'the return and the ledger disagree'
            ELSE '' END        AS needs
  FROM fiscal_period p
  LEFT JOIN ledger l ON l.period = p.period
  LEFT JOIN onform o ON o.period = p.period
  LEFT JOIN unmapped u ON u.period = p.period;

COMMENT ON VIEW v_form_990_revenue_check IS
  'Every income account is on exactly one line of Part VIII, and the lines '
  'add back to the profit and loss. The expense half of the same question is '
  'v_form_990_line_check.';
