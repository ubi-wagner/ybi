-- 110 — Part X, and the balance sheet that was never mapped onto it
--
-- `094` put Part IX on the return's own numbered lines and `095` did Part
-- VIII. Part X is the third statement and had nothing: `bs_account` carries
-- all 74 closing balances and **nothing had ever said which of the return's
-- 33 lines each one belongs on**, so the return could print two of its three
-- financial statements and not the balance sheet.
--
-- The mapping is a **preparer's judgment**, so it is data rather than a
-- `CASE`, the way `form_990_account_line` is for Part IX and the way
-- `v_payroll_reconciliation` names its six fringe accounts by hand.
-- Inventing a rule to derive it would be guessing at somebody's judgment.
--
-- What is *not* a judgment is completeness, and `v_form_990_part_x_check`
-- holds it: an account on no line is money that falls off the balance sheet
-- with nothing saying so, and the sheet has to foot — line 16 equals line 33
-- — because a balance sheet that does not balance is not one.
--
-- Two of the mappings are genuinely arguable and carry their reason on the
-- row rather than in anybody's head. `1456 Accrued Receivables` is unbilled
-- grant revenue on a grant-funded incubator, so it goes to line 3 with the
-- pledges rather than to line 4 with the trade receivables; and the two
-- Carmel material inventories go to line 8, which the 2024 return left
-- blank because it had none.

CREATE TABLE form_990_bs_line (
  leaf_prefix  text PRIMARY KEY,
  line_id      text NOT NULL,
  note         text NOT NULL DEFAULT ''
);

COMMENT ON TABLE form_990_bs_line IS
  'Which line of Form 990 Part X each balance sheet account belongs on. A '
  'preparer''s judgment, transcribed — not a rule. Completeness is checked; '
  'the judgment is not, because nothing could check it.';

-- The Part X lines themselves, in the order the form prints them. `side`
-- and `contra` are what let the view add a line up without the reader
-- having to know that accumulated depreciation is negative.
CREATE TABLE form_990_bs_line_def (
  line_id  text PRIMARY KEY,
  seq      integer NOT NULL,
  side     text NOT NULL CHECK (side IN ('ASSET', 'LIABILITY', 'EQUITY')),
  label    text NOT NULL,
  note     text NOT NULL DEFAULT ''
);

INSERT INTO form_990_bs_line_def (line_id, seq, side, label, note) VALUES
  ('X1',  10, 'ASSET',     'Cash—non-interest-bearing', ''),
  ('X2',  20, 'ASSET',     'Savings and temporary cash investments', ''),
  ('X3',  30, 'ASSET',     'Pledges and grants receivable, net', ''),
  ('X4',  40, 'ASSET',     'Accounts receivable, net', ''),
  ('X7',  70, 'ASSET',     'Notes and loans receivable, net', ''),
  ('X8',  80, 'ASSET',     'Inventories for sale or use', ''),
  ('X9',  90, 'ASSET',     'Prepaid expenses and deferred charges', ''),
  ('X10a',100,'ASSET',     'Land, buildings, and equipment: cost or other basis', ''),
  ('X10b',101,'ASSET',     'Less: accumulated depreciation', 'A contra account; printed positive and subtracted.'),
  ('X15', 150,'ASSET',     'Other assets', ''),
  ('X17', 170,'LIABILITY', 'Accounts payable and accrued expenses', ''),
  ('X18', 180,'LIABILITY', 'Grants payable', ''),
  ('X19', 190,'LIABILITY', 'Deferred revenue', ''),
  ('X23', 230,'LIABILITY', 'Secured mortgages and notes payable to unrelated third parties', ''),
  ('X24', 240,'LIABILITY', 'Unsecured notes and loans payable to unrelated third parties', ''),
  ('X25', 250,'LIABILITY', 'Other liabilities', ''),
  ('X27', 270,'EQUITY',    'Net assets without donor restrictions', ''),
  ('X28', 280,'EQUITY',    'Net assets with donor restrictions', '');

INSERT INTO form_990_bs_line (leaf_prefix, line_id, note) VALUES
  -- Cash. Every bank account and the two clearing accounts that hold cash
  -- in transit; undeposited funds is cash the organisation holds.
  ('1000', 'X1', ''), ('1002', 'X1', ''), ('1003', 'X1', ''),
  ('1005', 'X1', ''), ('1010', 'X1', ''), ('1011', 'X1', ''),
  ('1012', 'X1', ''), ('1020', 'X1', ''), ('1030', 'X1', ''),
  ('1072', 'X1', ''),

  -- Trade receivables and their allowances. 1111/1112 net to nothing and
  -- are kept on the same line as each other so that they do.
  ('1100', 'X4', ''), ('1101', 'X4', 'Allowance against 1100.'),
  ('1111', 'X4', ''), ('1112', 'X4', 'Allowance against 1111.'),

  -- Grants and pledges. 1456 is unbilled grant revenue rather than a trade
  -- debt, which is the judgment on this sheet most worth a second reading.
  ('1120', 'X3', 'A federal grant receivable.'),
  ('1150', 'X3', ''),
  ('1151', 'X3', 'Discount against 1150.'),
  ('1456', 'X3', 'Unbilled grant revenue, not a trade receivable.'),

  ('HT Carmel',  'X8', 'Materials held for a programme build.'),
  ('YBI Carmel', 'X8', 'Materials held for a programme build.'),

  ('1441', 'X9', ''), ('1450', 'X9', ''), ('1451', 'X9', ''),
  ('1455', 'X9', 'A deposit held by a utility.'),

  -- Fixed assets at cost, and the contra accounts beneath them. The pairing
  -- is the fixed-asset schedule's own — 1501/1502, 1511/1512, 1521/1522,
  -- 1525/1526, 1527/1528 — which `v_asset_register_tie` also reads.
  ('1500', 'X10a', 'Land. Not depreciated.'),
  ('1505', 'X10a', 'Construction in progress. Not depreciated.'),
  ('1511', 'X10a', ''), ('1521', 'X10a', ''), ('1520', 'X10a', ''),
  ('1529', 'X10a', ''), ('1525', 'X10a', ''), ('1527', 'X10a', ''),
  ('1501', 'X10a', ''),
  ('1512', 'X10b', ''), ('1522', 'X10b', ''), ('1523', 'X10b', ''),
  ('1526', 'X10b', ''), ('1528', 'X10b', ''), ('1502', 'X10b', ''),

  ('1115', 'X15', 'An investment in a portfolio company.'),

  -- Payables, accruals and the payroll liabilities. Every card is a payable.
  ('2000', 'X17', ''), ('2003', 'X17', ''), ('2040', 'X17', ''),
  ('2041', 'X17', ''), ('2100', 'X17', ''), ('2106', 'X17', ''),
  ('2109', 'X17', ''), ('2110', 'X17', ''), ('2111', 'X17', ''),
  ('2120', 'X17', ''), ('2150', 'X17', ''), ('2151', 'X17', ''),
  ('2160', 'X17', ''), ('CC-', 'X17', 'A company card balance.'),

  ('2210', 'X19', ''),
  ('IH Advance',    'X19', 'An advance received and not yet earned.'),
  ('IH Cost Share', 'X19', 'A cost share received and not yet earned.'),

  ('2004', 'X23', ''), ('2005', 'X23', ''), ('2046', 'X23', ''),
  ('2049', 'X23', ''),

  -- The year's result rolls into unrestricted unless a donor restricted it,
  -- which nothing on this record says. Named on the return rather than
  -- assumed silently.
  ('3000', 'X27', ''),
  ('Net Income', 'X27', 'The year''s result, rolled into unrestricted.'),
  ('3010', 'X28', '');
