-- The audit, as the one journey it is.
--
-- The 2025 door opened on the generic dashboard — a worklist, a document
-- count, a manual panel — which answers *what is outstanding* and never
-- *where am I in this*. Those are different questions and the second is the
-- one a controller closing a year actually holds: the file is closed in an
-- order, each step depends on the one before it, and the order is the whole
-- guarantee. Classification is sealed before any rate is computed, and a
-- landing page that listed the two as peers said nothing about that.
--
-- Ten steps, each reading the view that already owns its figure. **Nothing
-- here computes anything**: the reconciliation is `v_statement_reconciliation`,
-- the coverage is `v_classification_coverage`, the partitions are
-- `v_partition_coverage`. A step that derived its own number would be a second
-- definition of it, which is the defect this schema has recorded a dozen
-- times.
--
-- Four states, and the fourth is the one a list of tasks usually gets wrong:
--
--   DONE      finished
--   OPEN      work outstanding that somebody here can do
--   NO DATA   cannot be evaluated — it needs something from outside, and an
--             empty set matching an empty set perfectly is not a pass
--   WAITING   a step earlier in the order is not done, so this one cannot
--             honestly be called open. Printing it as OPEN would put work in
--             front of somebody that the system would refuse.

CREATE VIEW v_audit_walk AS
WITH
period AS (SELECT period FROM fiscal_period),
ledger AS (
    SELECT p.period,
           (SELECT count(*) FROM ledger_line l WHERE l.period = p.period) AS lines
      FROM period p
),
recon AS (
    SELECT p.period,
           count(r.*)                             AS points,
           count(r.*) FILTER (WHERE r.ties)       AS tying,
           count(r.*) FILTER (WHERE r.state = 'NO DATA') AS blind
      FROM period p
      LEFT JOIN v_statement_reconciliation r ON r.period = p.period
     GROUP BY p.period
),
cover AS (
    SELECT p.period, c.groups_total, c.groups_decided,
           c.scope_dollars, c.classified, c.unclassified, c.pct_dollars_covered
      FROM period p
      LEFT JOIN v_classification_coverage c ON c.period = p.period
),
part AS (
    SELECT p.period,
           max(pc.state) FILTER (WHERE pc.partition = 'SPACE')  AS space_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'SPACE')  AS space_needs,
           max(pc.state) FILTER (WHERE pc.partition = 'ASSETS') AS asset_state,
           max(pc.needs) FILTER (WHERE pc.partition = 'ASSETS') AS asset_needs
      FROM period p
      LEFT JOIN v_partition_coverage pc ON pc.period = p.period
     GROUP BY p.period
),
cited AS (
    -- A judgment that names the paper it rests on. Attaching is not citing:
    -- `decision_verified_check` counts `decision_evidence`, and that is the
    -- difference between *this paper is about that money* and *this paper is
    -- why I judged it the way I did*.
    -- The period comes through `decision_set`, not off the decision.
    -- `decision.scope` is the **group key** — `account=…|payee=…` — and a
    -- first draft grouped by it, which produced one row per group and made
    -- this step report "nothing has been judged yet" over 757 judgments.
    -- That is the name-written-from-memory defect this file lists by name,
    -- committed by somebody who had just read the list.
    -- Scoped to the judgments the worklist's NEEDS_EVIDENCE scopes to —
    -- federally chargeable, ALLOWABLE or PENDING — because both appear on
    -- this one page and a first draft counted all 757 live judgments beside
    -- a worklist row saying 363. Two true figures about "judgments with no
    -- document", at the same moment, which a reader has to reconcile in
    -- their head. That is 13.0% and 2.2% in its presentation form.
    SELECT ds.period,
           count(DISTINCT d.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS live,
           count(DISTINCT de.decision_id)
             FILTER (WHERE d.federal IN ('ALLOWABLE', 'PENDING'))  AS with_citation,
           count(DISTINCT d.decision_id)                           AS all_live
      FROM decision d
      JOIN decision_set ds ON ds.set_id = d.set_id
      LEFT JOIN decision_evidence de ON de.decision_id = d.decision_id
     WHERE d.reversed_at IS NULL
     GROUP BY ds.period
),
sealed AS (
    SELECT p.period,
           bool_or(ds.sealed_at IS NOT NULL)      AS is_sealed,
           max(ds.sealed_at)                      AS at,
           max(left(ds.seal_hash, 12))            AS hash
      FROM period p
      LEFT JOIN decision_set ds ON ds.period = p.period
     GROUP BY p.period
),
rated AS (
    SELECT p.period,
           count(r.*) FILTER (WHERE r.status <> 'SUPERSEDED')  AS live,
           max(r.rate) FILTER (WHERE r.kind = 'INDIRECT_COMBINED'
                                 AND r.status <> 'SUPERSEDED') AS combined,
           max(r.admin_labour_basis) FILTER (WHERE r.status <> 'SUPERSEDED')
                                                               AS basis
      FROM period p
      LEFT JOIN rate r ON r.period = p.period
     GROUP BY p.period
),
restated AS (
    SELECT p.period,
           count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED') AS standing
      FROM period p
      LEFT JOIN restatement rs ON rs.period = p.period
     GROUP BY p.period
)
SELECT * FROM (
    SELECT l.period, 1 AS seq, 'The books are in' AS step,
           'The QuickBooks exports, as received' AS what,
           CASE WHEN l.lines = 0 THEN 'NO DATA' ELSE 'DONE' END AS state,
           CASE WHEN l.lines = 0
                THEN 'No ledger has been loaded for this period.'
                -- Grouped in the database because this sentence is built
                -- here: `api.js::money()` and `count()` are the one formatter
                -- for a figure the screen renders, and they cannot reach
                -- inside a string the view composed. 15500 read as a part
                -- number rather than a count.
                ELSE to_char(l.lines, 'FM999,999,999')
                     || ' general-ledger lines on file.' END AS detail,
           '/books/import' AS goes_to
      FROM ledger l

    UNION ALL
    SELECT r.period, 2, 'The books agree with themselves',
           'Ledger, profit and loss, balance sheet, payroll register',
           CASE WHEN r.points = 0 THEN 'NO DATA'
                WHEN r.blind > 0 THEN 'NO DATA'
                WHEN r.tying = r.points THEN 'DONE'
                ELSE 'OPEN' END,
           CASE WHEN r.points = 0
                THEN 'No control has been evaluated.'
                WHEN r.blind > 0
                THEN r.blind || ' of ' || r.points || ' points cannot be '
                     || 'evaluated, which is not the same as tying.'
                ELSE r.tying || ' of ' || r.points || ' cross-reference '
                     || 'points tie. A rate is refused while any is open.'
           END,
           '/books'
      FROM recon r

    UNION ALL
    SELECT c.period, 3, 'Every cost judged',
           'The profit and loss, less income, into 2 CFR 200 pools',
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'NO DATA'
                WHEN c.unclassified = 0 THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN c.groups_total IS NULL OR c.groups_total = 0
                THEN 'There is no cost to classify yet.'
                ELSE to_char(c.groups_decided, 'FM999,999') || ' of '
                     || to_char(c.groups_total, 'FM999,999')
                     || ' groups, ' || c.pct_dollars_covered || '% of dollars.'
           END,
           '/classify'
      FROM cover c

    UNION ALL
    SELECT pt.period, 4, 'Every square foot accounted for',
           'Each building, into tenant, programme and vacant space',
           COALESCE(pt.space_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.space_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.space_needs, 'the square footage')
                     || '. Until it lands the 200.465 carve-out cannot be '
                     || 'computed at all, and every dollar of tenant and '
                     || 'vacant occupancy cost sits in the federal pool.'
                ELSE 'The space accounts for itself.' END,
           '/classify/space'
      FROM part pt

    UNION ALL
    SELECT pt.period, 5, 'Every asset''s funding source',
           'The fixed-asset register, into funding sources',
           COALESCE(pt.asset_state, 'NO DATA'),
           CASE WHEN COALESCE(pt.asset_state, 'NO DATA') = 'NO DATA'
                THEN 'Needs ' || COALESCE(pt.asset_needs, 'the asset register')
                     || '. 200.436(b) makes depreciation on a federally '
                     || 'funded asset unallowable and the schedule has no '
                     || 'such column, which 200.313(d)(1) requires.'
                ELSE 'Every asset names where its money came from.' END,
           '/classify/assets'
      FROM part pt

    UNION ALL
    SELECT c.period, 6, 'The paper behind the judgments',
           'A judgment that cites the document it rests on',
           CASE WHEN COALESCE(ct.all_live, 0) = 0 THEN 'WAITING'
                WHEN COALESCE(ct.live, 0) = 0 THEN 'DONE'
                WHEN ct.with_citation = ct.live THEN 'DONE' ELSE 'OPEN' END,
           CASE WHEN COALESCE(ct.all_live, 0) = 0
                THEN 'Nothing has been judged yet, so there is nothing to cite.'
                WHEN COALESCE(ct.live, 0) = 0
                THEN 'No judgment is federally chargeable, so none needs a '
                     || 'citation for 2 CFR 200.'
                ELSE to_char(COALESCE(ct.with_citation, 0), 'FM999,999')
                     || ' of ' || to_char(ct.live, 'FM999,999')
                     || ' federally chargeable judgments cite a document, of '
                     || to_char(ct.all_live, 'FM999,999') || ' live. '
                     || 'Attaching is not citing: a citation is why the '
                     || 'judgment was made, and it is what VERIFIED requires.'
           END,
           '/evidence'
      FROM cover c LEFT JOIN cited ct ON ct.period = c.period

    UNION ALL
    SELECT s.period, 7, 'The classifications sealed',
           'Hashed across every judgment, before any rate exists',
           CASE WHEN s.is_sealed THEN 'DONE'
                WHEN COALESCE(c.unclassified, 1) <> 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN s.is_sealed
                THEN 'Sealed ' || to_char(s.at, 'DD Mon YYYY') || ' · '
                     || s.hash || '…'
                WHEN COALESCE(c.unclassified, 1) <> 0
                THEN 'Cost is still outstanding. Sealing an incomplete set '
                     || 'is allowed and makes the rate read high, which is '
                     || 'the honest direction to err.'
                ELSE 'Every group is judged. Sealing is the assertion that '
                     || 'the rate was not reverse-engineered, and it is '
                     || 'yours to make.'
           END,
           '/review/rate'
      FROM sealed s LEFT JOIN cover c ON c.period = s.period

    UNION ALL
    SELECT rt.period, 8, 'The rate computed',
           'A pool over a base, carrying the seal',
           CASE WHEN COALESCE(rt.live, 0) > 0 THEN 'DONE'
                WHEN NOT COALESCE(s.is_sealed, false) THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rt.live, 0) > 0
                THEN 'Indirect, combined: '
                     || round(rt.combined * 100, 2) || '% on the '
                     || rt.basis || ' basis.'
                WHEN NOT COALESCE(s.is_sealed, false)
                THEN 'No rate can exist until the set is sealed — the '
                     || 'database refuses one whose seal does not match.'
                ELSE 'The set is sealed. Computing is arithmetic from here.'
           END,
           '/review/rate'
      FROM rated rt LEFT JOIN sealed s ON s.period = rt.period

    UNION ALL
    SELECT rs.period, 9, 'The position on each invoice',
           'What was billed, against what the rate supports',
           CASE WHEN COALESCE(rs.standing, 0) > 0 THEN 'DONE'
                WHEN COALESCE(rt.live, 0) = 0 THEN 'WAITING'
                ELSE 'OPEN' END,
           CASE WHEN COALESCE(rs.standing, 0) > 0
                THEN rs.standing || ' restatement(s) standing as a claim. '
                     || 'Everything is PROPOSED until a sponsor says '
                     || 'otherwise in writing.'
                WHEN COALESCE(rt.live, 0) = 0
                THEN 'Needs a rate to measure against.'
                ELSE 'Nothing has been put to a sponsor yet.'
           END,
           '/restate'
      FROM restated rs LEFT JOIN rated rt ON rt.period = rs.period

    UNION ALL
    SELECT p.period, 10, 'The papers that leave the building',
           'The auditor''s report, Form 990, the workbooks',
           'DONE',
           'Read from the rows they were recorded in. Each states what is '
           || 'unfinished above its figures, and the workbooks repeat it on '
           || 'the first sheet because a workbook travels.',
           '/reports'
      FROM period p
) w
ORDER BY period, seq;

COMMENT ON VIEW v_audit_walk IS
'The 2025 audit as the one ordered journey it is, ten steps, each reading the '
'view that already owns its figure. WAITING is a step whose predecessor is not '
'done — printing it as OPEN would offer work the system would refuse.';
