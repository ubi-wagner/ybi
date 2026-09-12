-- The hard anchors, especially for fringe.
--
-- `066` anchored the fringe *denominator* — the wage base is the payroll
-- register, $1,835,047.18 — and left the numerator and the rate itself
-- unanchored. The engagement has hard figures for both, off the source
-- documents rather than out of the model, and they reproduce on the live
-- record to the basis point:
--
--     the P&L's six fringe accounts        401,783.60
--     the payroll register's wages       1,835,047.18
--     ---------------------------------------------- = 0.2190   21.90%
--
--     the same pool over the *ledger's*
--     wage accounts, 1,789,993.94        = 0.2245   22.45%
--
-- **That difference is one number: $45,053.24.** A donor credit sat in an
-- intern wage account for a year, so the ledger's wage accounts are
-- understated by it and a rate taken over them reads high. The eleventh
-- statement control already finds it — `gross_difference` 45,053.24, `named`
-- -45,053.24, `unexplained` 0.00 — and this is the other end of the same
-- fact: **21.90% and 22.45% are not two opinions, they are one pool over two
-- denominators, and only one of the denominators is the payroll.**
--
-- **These are controls, not inputs.** Nothing here sets a rate. The rate
-- remains a consequence of the judgments — *no rate is computed or displayed
-- during classification, the decision set is sealed first, and the rate
-- carries the seal.* What the anchors add is the question a reviewer asks
-- next: does what the controller judged produce the figure the source
-- documents imply, and if not, by how much. Writing 21.90% in as an input
-- would be the reverse-engineering this whole system exists to rule out.
--
-- So the fringe rate is anchored the honest way — **by anchoring both of its
-- parts.** With the numerator tied to the P&L's fringe accounts and the
-- denominator tied to the payroll register, 21.90% falls out rather than
-- being asserted, and the fourth row below is the arithmetic saying so.
--
-- One thing to know rather than to trust: the six accounts that make up
-- `fringe_pool` are named by hand inside `v_payroll_reconciliation` — 5130
-- Benefits, 5133 401k, 5145 BWC, 5151 FICA, 5185 FUTA, 5195 SUI. That is a
-- transcription of which accounts are fringe, which is a judgment somebody
-- made once and put in the schema. It is the hand-kept-map shape and it is
-- left alone deliberately: the list is short, it is on the face of the P&L,
-- and inventing a rule to derive it would be guessing at a judgment.
--
-- Dropped and recreated rather than replaced: `unit` goes in beside the
-- figures it describes, and this register now carries dollars *and* rates in
-- one column. A reader scanning 1,835,047.18 and 0.2190 in the same place
-- needs to be told which is which.
DROP VIEW v_rate_anchor;
CREATE VIEW v_rate_anchor AS
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
-- ── 3. The fringe pool is the P&L's fringe accounts ──────────────────
--
-- The numerator. What the controller classifies into FRINGE should come to
-- what the P&L's own fringe accounts say fringe cost was; a difference is a
-- judgment they made on purpose and should be able to name.
SELECT p.period, 3 AS seq,
       'FRINGE_POOL_IS_THE_PAYROLL_FRINGE'::text AS control,
       'What is judged into FRINGE is the P&L''s fringe accounts'::text,
       COALESCE(pr.fringe_pool, 0)                          AS expected,
       COALESCE(fp.gross, 0)                                AS actual,
       COALESCE(pr.fringe_pool, 0) - COALESCE(fp.gross, 0)  AS variance,
       CASE
           WHEN pr.fringe_pool IS NULL                      THEN 'NO DATA'
           WHEN fp.gross IS NULL
            AND COALESCE(c.unclassified, 0) > 0             THEN 'NO DATA'
           WHEN COALESCE(pr.fringe_pool, 0)
                = COALESCE(fp.gross, 0)                     THEN 'TIES'
           ELSE 'OPEN'
       END                                                  AS state,
       'Six accounts named on the face of the P&L: 5130 Benefits, 5133 '
       '401k, 5145 BWC, 5151 FICA, 5185 FUTA, 5195 SUI.'::text AS note,
       (c.unclassified = 0)                                 AS classification_complete,
       c.pct_dollars_covered,
       'DOLLARS'::text                                      AS unit
  FROM fiscal_period p
  LEFT JOIN cov c ON c.period = p.period
  LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period
  LEFT JOIN (SELECT period, gross FROM v_pool_balance
              WHERE pool::text = 'FRINGE') fp ON fp.period = p.period
UNION ALL
-- ── 4. And therefore the fringe rate ─────────────────────────────────
--
-- Both parts anchored above, so this row is arithmetic rather than an
-- assertion: the pool the P&L names over the wages the register names, at
-- the four decimal places `rate.rate` stores, against what was actually
-- computed. **0.2190.** The same pool over the ledger's wage accounts is
-- 0.2245, and the $45,053.24 between them is the credit.
SELECT p.period, 4 AS seq,
       'FRINGE_RATE_ON_THE_REGISTER'::text,
       'The rate the source documents imply, against the one computed'::text,
       round(pr.fringe_pool / NULLIF(pr.register_wages, 0), 4) AS expected,
       fr.rate                                                 AS actual,
       round(pr.fringe_pool / NULLIF(pr.register_wages, 0), 4)
         - fr.rate                                             AS variance,
       CASE
           WHEN pr.fringe_pool IS NULL
             OR COALESCE(pr.register_wages, 0) = 0            THEN 'NO DATA'
           WHEN fr.rate IS NULL                               THEN 'NO DATA'
           WHEN fr.rate = 0 AND COALESCE(c.unclassified, 0) > 0 THEN 'NO DATA'
           WHEN round(pr.fringe_pool / pr.register_wages, 4) = fr.rate
                                                              THEN 'TIES'
           ELSE 'OPEN'
       END,
       'Over the payroll register, not the ledger''s wage accounts: those '
       'are understated by the $45,053.24 credit and give 0.2245.'::text,
       (c.unclassified = 0),
       c.pct_dollars_covered,
       'RATE'::text
  FROM fiscal_period p
  LEFT JOIN cov c ON c.period = p.period
  LEFT JOIN v_payroll_reconciliation pr ON pr.period = p.period
  LEFT JOIN (SELECT period, rate FROM rate
              WHERE kind = 'FRINGE' AND status <> 'SUPERSEDED'
              ORDER BY computed_at DESC LIMIT 1) fr ON fr.period = p.period;

COMMENT ON VIEW v_rate_anchor IS
  'What the rate is anchored to, beyond each pool tying to itself: the pools '
  'account for every judgment, the wage base is the payroll register, what '
  'is judged into FRINGE is the P&L''s fringe accounts, and the fringe rate '
  'the two imply — 0.2190 over the register, against 0.2245 over the '
  'ledger''s wage accounts, which are understated by the $45,053.24 credit. '
  'Controls, not inputs: nothing here sets a rate. NO DATA is not a pass, '
  'and `unit` says whether a row is dollars or a rate.';
