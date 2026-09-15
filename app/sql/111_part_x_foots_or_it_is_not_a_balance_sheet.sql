-- 111 — Part X, and the control that it foots
--
-- `110` recorded which line each balance sheet account belongs on. This is
-- the line itself, and the two questions that are *not* judgments:
--
--   * **is every account on a line** — an account on none is money that
--     falls off the balance sheet with nothing saying so, which is what
--     `v_form_990_line_check` holds for Part IX and `v_form_990_revenue_
--     check` for Part VIII; and
--   * **does the sheet balance** — line 16 against line 33. A balance sheet
--     that does not balance is not one, and the return prints it either way,
--     so the control has to be beside it rather than in somebody's head.
--
-- Longest prefix wins, so `1150` and `1151` do not collide and `CC-` can
-- catch eleven company cards in one row. A leaf matching no prefix is
-- reported rather than dropped — `029`'s rule pointed at a mapping: an
-- unmapped account and an account at zero must not read the same.

CREATE OR REPLACE VIEW v_form_990_part_x AS
WITH mapped AS (
  SELECT b.period, b.leaf, b.side, b.amount,
         (SELECT m.line_id FROM form_990_bs_line m
           WHERE b.leaf LIKE m.leaf_prefix || '%'
           ORDER BY length(m.leaf_prefix) DESC LIMIT 1) AS line_id
    FROM bs_account b
   WHERE NOT b.is_rollup)
SELECT p.period, d.line_id, d.seq, d.side, d.label,
       -- Accumulated depreciation is held negative and the form prints it
       -- as a positive figure to subtract, so line 10b turns its sign. The
       -- view says so rather than the reader having to notice.
       CASE WHEN d.line_id = 'X10b' THEN -COALESCE(sum(m.amount), 0)
            ELSE COALESCE(sum(m.amount), 0) END AS amount,
       count(m.leaf)                            AS accounts
  FROM fiscal_period p
 CROSS JOIN form_990_bs_line_def d
  LEFT JOIN mapped m ON m.period = p.period AND m.line_id = d.line_id
 GROUP BY p.period, d.line_id, d.seq, d.side, d.label;

COMMENT ON VIEW v_form_990_part_x IS
  'Form 990 Part X on the return''s own numbered lines, read from the '
  'balance sheet as imported. Every line prints whether or not it carries '
  'anything, because an empty line is a fact about the year.';


CREATE OR REPLACE VIEW v_form_990_part_x_check AS
WITH sheet AS (
  SELECT period,
         sum(amount) FILTER (WHERE side = 'ASSET')     AS assets,
         sum(amount) FILTER (WHERE side = 'LIABILITY') AS liabilities,
         sum(amount) FILTER (WHERE side = 'EQUITY')    AS equity,
         count(*)                                      AS accounts
    FROM bs_account WHERE NOT is_rollup GROUP BY period),
unmapped AS (
  SELECT b.period, count(*) AS n,
         string_agg(b.leaf, ', ' ORDER BY b.leaf) AS which
    FROM bs_account b
   WHERE NOT b.is_rollup
     AND NOT EXISTS (SELECT 1 FROM form_990_bs_line m
                      WHERE b.leaf LIKE m.leaf_prefix || '%')
   GROUP BY b.period),
onform AS (
  SELECT period,
         -- Line 16 is the assets less the accumulated depreciation the form
         -- prints on its own line, which is why 10b is added back here.
         sum(amount) FILTER (WHERE side = 'ASSET' AND line_id <> 'X10b')
           - COALESCE(sum(amount) FILTER (WHERE line_id = 'X10b'), 0) AS line_16,
         sum(amount) FILTER (WHERE side = 'LIABILITY')                AS line_26,
         sum(amount) FILTER (WHERE side = 'EQUITY')                   AS line_32
    FROM v_form_990_part_x GROUP BY period)
SELECT p.period,
       COALESCE(s.accounts, 0)          AS accounts,
       COALESCE(u.n, 0)                 AS unmapped,
       COALESCE(o.line_16, 0)           AS line_16,
       COALESCE(o.line_26, 0)           AS line_26,
       COALESCE(o.line_32, 0)           AS line_32,
       COALESCE(o.line_16, 0) - COALESCE(o.line_26, 0)
                                - COALESCE(o.line_32, 0) AS variance,
       CASE WHEN COALESCE(s.accounts, 0) = 0 THEN 'NO DATA'
            WHEN COALESCE(u.n, 0) > 0        THEN 'OPEN'
            WHEN COALESCE(o.line_16, 0) - COALESCE(o.line_26, 0)
                 - COALESCE(o.line_32, 0) = 0 THEN 'TIES'
            ELSE 'OPEN' END             AS state,
       CASE WHEN COALESCE(s.accounts, 0) = 0
              THEN 'the balance sheet, imported'
            WHEN COALESCE(u.n, 0) > 0
              THEN format('%s account(s) are on no line of Part X: %s',
                          u.n, u.which)
            WHEN COALESCE(o.line_16, 0) - COALESCE(o.line_26, 0)
                 - COALESCE(o.line_32, 0) <> 0
              THEN format('Total assets %s against liabilities and net '
                          'assets of %s. A balance sheet that does not '
                          'balance is not one.',
                          to_char(o.line_16, 'FM999,999,999.00'),
                          to_char(o.line_26 + o.line_32,
                                  'FM999,999,999.00'))
            ELSE '' END                 AS needs
  FROM fiscal_period p
  LEFT JOIN sheet s   ON s.period = p.period
  LEFT JOIN unmapped u ON u.period = p.period
  LEFT JOIN onform o   ON o.period = p.period;

COMMENT ON VIEW v_form_990_part_x_check IS
  'Whether every balance sheet account reaches a line of Part X and whether '
  'the sheet foots. Neither is the preparer''s judgment about which line an '
  'account belongs on — that cannot be checked — and both are things a '
  'return printing a balance sheet has to be able to answer.';
