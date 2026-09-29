-- 130: steps 7, 8 and 9 happen on one screen, and the walk has to say which
--
-- Tom cleared the classification queue, opened **Rate** to seal, and found no
-- way to do it. He was in the right place by every map this system gives him,
-- and every one of those maps was wrong: the nav's Rate tab was marked `7–9`
-- and went to `/review/rate`; this view sent SEAL, RATE and CERTIFY to the
-- same address; and that screen is the **read-only workpaper**. Sealing,
-- unsealing and computing live on `/rates`, which the eight-tab fold tagged
-- as belonging to the other door.
--
-- `080`'s own rule is that a fold removes nav and never capability. It removed
-- *reach*, which is the same thing wearing a different word — the route
-- answers perfectly and the product never mentions it.
--
-- So the three acts are one screen now and it is `/rates`: the certification
-- door moved off `/review/rate`, the build-up is rendered there from the same
-- component the workpaper uses, and the review screens go back to being
-- purely read-only, which is what `CLAUDE.md` has always said they are.
-- `test_the_nav_marks_are_the_walk_s_step_numbers` derives the nav from
-- `ALL_TABS` and the steps from this view, so the tab had to move with it and
-- could not be left behind by hand.
--
-- **The body is lifted from `088`, which is the definition in force**, and the
-- only change is three string literals. `070` records what retyping a view
-- costs: a draft that lifted from `017` instead of `019` was refused by
-- Postgres for renaming a column, and a draft that rewrote a scope from memory
-- silently changed how every line was categorised.
--
-- Nothing else moves. The states, the sentences and the arithmetic are
-- `088`'s, including CERTIFY's *"Nothing is blocked by this — an invoice or a
-- workbook produced now simply carries NOT CERTIFIED"*, which is the whole
-- reason a controller may seal, compute, unseal and recompute as often as the
-- evaluation needs without anything downstream refusing him.

CREATE OR REPLACE VIEW v_audit_walk AS
 WITH period AS (
         SELECT fiscal_period.period
           FROM fiscal_period
        ), ledger AS (
         SELECT p.period,
            ( SELECT count(*) AS count
                   FROM ledger_line l
                  WHERE l.period = p.period) AS lines
           FROM period p
        ), recon AS (
         SELECT p.period,
            count(r.*) AS points,
            count(r.*) FILTER (WHERE r.ties) AS tying,
            count(r.*) FILTER (WHERE r.state = 'NO DATA'::text) AS blind
           FROM period p
             LEFT JOIN v_statement_reconciliation r ON r.period = p.period
          GROUP BY p.period
        ), cover AS (
         SELECT p.period,
            c.groups_total,
            c.groups_decided,
            c.scope_dollars,
            c.classified,
            c.unclassified,
            c.pct_dollars_covered
           FROM period p
             LEFT JOIN v_classification_coverage c ON c.period = p.period
        ), part AS (
         SELECT p.period,
            max(pc.state) FILTER (WHERE pc.partition = 'SPACE'::text) AS space_state,
            max(pc.needs) FILTER (WHERE pc.partition = 'SPACE'::text) AS space_needs,
            max(pc.state) FILTER (WHERE pc.partition = 'ASSETS'::text) AS asset_state,
            max(pc.needs) FILTER (WHERE pc.partition = 'ASSETS'::text) AS asset_needs,
            max(pc.pct) FILTER (WHERE pc.partition = 'SPACE'::text) AS space_pct,
            max(pc.pct) FILTER (WHERE pc.partition = 'ASSETS'::text) AS asset_pct
           FROM period p
             LEFT JOIN v_partition_coverage pc ON pc.period = p.period
          GROUP BY p.period
        ), adopt AS (
         SELECT p.period,
            count(*) FILTER (WHERE st.is_working_position AND NOT st.adopted) AS unadopted
           FROM period p
             LEFT JOIN v_classification_standing st ON st.period = p.period
          GROUP BY p.period
        ), cited AS (
         SELECT ds.period,
            count(DISTINCT d.decision_id) FILTER (WHERE d.federal = ANY (ARRAY['ALLOWABLE'::federal_treatment, 'PENDING'::federal_treatment])) AS live,
            count(DISTINCT de.decision_id) FILTER (WHERE d.federal = ANY (ARRAY['ALLOWABLE'::federal_treatment, 'PENDING'::federal_treatment])) AS with_citation,
            count(DISTINCT d.decision_id) AS all_live
           FROM decision d
             JOIN decision_set ds ON ds.set_id = d.set_id
             LEFT JOIN decision_evidence de ON de.decision_id = d.decision_id
          WHERE d.reversed_at IS NULL
          GROUP BY ds.period
        ), sealed AS (
         SELECT p.period,
            bool_or(ds.sealed_at IS NOT NULL) AS is_sealed,
            max(ds.sealed_at) AS at,
            max("left"(ds.seal_hash, 12)) AS hash
           FROM period p
             LEFT JOIN decision_set ds ON ds.period = p.period
          GROUP BY p.period
        ), rated AS (
         SELECT p.period,
            count(r.*) FILTER (WHERE r.status <> 'SUPERSEDED'::text) AS live,
            max(r.rate) FILTER (WHERE r.kind = 'INDIRECT_COMBINED'::text AND r.status <> 'SUPERSEDED'::text) AS combined,
            max(r.admin_labour_basis) FILTER (WHERE r.status <> 'SUPERSEDED'::text) AS basis
           FROM period p
             LEFT JOIN rate r ON r.period = p.period
          GROUP BY p.period
        ), restated AS (
         SELECT p.period,
            count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED'::text) AS standing,
            count(rs.*) FILTER (WHERE rs.status <> 'SUPERSEDED'::text
                                  AND NOT rs.still_agrees) AS overtaken
           FROM period p
             LEFT JOIN v_restatement rs ON rs.period = p.period
          GROUP BY p.period
        )
 SELECT period,
    seq,
    step,
    key,
    what,
    state,
    detail,
    goes_to
   FROM ( SELECT l.period,
            1 AS seq,
            'The books are in'::text AS step,
            'LEDGER'::text AS key,
            'The QuickBooks exports, as received'::text AS what,
                CASE
                    WHEN l.lines = 0 THEN 'NO DATA'::text
                    ELSE 'DONE'::text
                END AS state,
                CASE
                    WHEN l.lines = 0 THEN 'No ledger has been loaded for this period.'::text
                    ELSE to_char(l.lines, 'FM999,999,999'::text) || ' general-ledger lines on file.'::text
                END AS detail,
            '/books/import'::text AS goes_to
           FROM ledger l
        UNION ALL
         SELECT r.period,
            2,
            'The books agree with themselves'::text AS text,
            'RECONCILE'::text AS text,
            'Ledger, profit and loss, balance sheet, payroll register'::text AS text,
                CASE
                    WHEN r.points = 0 THEN 'NO DATA'::text
                    WHEN r.blind > 0 THEN 'NO DATA'::text
                    WHEN r.tying = r.points THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN r.points = 0 THEN 'No control has been evaluated.'::text
                    WHEN r.blind > 0 THEN (((r.blind || ' of '::text) || r.points) || ' points cannot be '::text) || 'evaluated, which is not the same as tying.'::text
                    ELSE (((r.tying || ' of '::text) || r.points) || ' cross-reference '::text) || 'points tie. A rate is refused while any is open.'::text
                END AS "case",
            '/books'::text AS text
           FROM recon r
        UNION ALL
         SELECT c.period,
            3,
            'Every cost judged'::text AS text,
            'CLASSIFY'::text AS text,
            'The profit and loss, less income, into 2 CFR 200 pools'::text AS text,
                CASE
                    WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'NO DATA'::text
                    WHEN c.unclassified = 0::numeric AND COALESCE(ad.unadopted, 0::bigint) = 0 THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN c.groups_total IS NULL OR c.groups_total = 0 THEN 'There is no cost to classify yet.'::text
                    WHEN c.unclassified > 0::numeric THEN ((((to_char(c.groups_decided, 'FM999,999'::text) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' groups, '::text) || c.pct_dollars_covered) || '% of dollars.'::text
                    WHEN COALESCE(ad.unadopted, 0::bigint) > 0 THEN (((('Every group carries a position. '::text || to_char(ad.unadopted, 'FM999,999'::text)) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' are working positions a script proposed and nobody '::text) || 'has adopted — classified, and not yet a judgment.'::text
                    ELSE ((((to_char(c.groups_decided, 'FM999,999'::text) || ' of '::text) || to_char(c.groups_total, 'FM999,999'::text)) || ' groups, '::text) || c.pct_dollars_covered) || '% of dollars.'::text
                END AS "case",
            '/classify'::text AS text
           FROM cover c
             LEFT JOIN adopt ad ON ad.period = c.period
        UNION ALL
         SELECT pt.period,
            4,
            'Every square foot accounted for'::text AS text,
            'SPACE'::text AS text,
            'Each building, into tenant, programme and vacant space'::text AS text,
                CASE COALESCE(pt.space_state, 'NO DATA'::text)
                    WHEN 'TIES'::text THEN 'DONE'::text
                    ELSE COALESCE(pt.space_state, 'NO DATA'::text)
                END AS "coalesce",
                CASE
                    WHEN
                    CASE COALESCE(pt.space_state, 'NO DATA'::text)
                        WHEN 'TIES'::text THEN 'DONE'::text
                        ELSE COALESCE(pt.space_state, 'NO DATA'::text)
                    END = 'NO DATA'::text THEN ((('Needs '::text || COALESCE(pt.space_needs, 'the square footage'::text)) || '. Until it lands the 200.465 carve-out cannot be '::text) || 'computed at all, and every dollar of tenant and '::text) || 'vacant occupancy cost sits in the federal pool.'::text
                    WHEN
                    CASE COALESCE(pt.space_state, 'NO DATA'::text)
                        WHEN 'TIES'::text THEN 'DONE'::text
                        ELSE COALESCE(pt.space_state, 'NO DATA'::text)
                    END = 'DONE'::text THEN 'The space accounts for itself.'::text
                    ELSE (((to_char(COALESCE(pt.space_pct, 0::numeric), 'FM990.0'::text) || '% of the square footage is accounted for. A '::text) || 'building that does not add up drops out of the '::text) || 'carve-out entirely, so its occupancy cost reaches '::text) || 'the federal pool unchallenged.'::text
                END AS "case",
            '/classify/space'::text AS text
           FROM part pt
        UNION ALL
         SELECT pt.period,
            5,
            'Every asset''s funding source'::text AS text,
            'ASSETS'::text AS text,
            'The fixed-asset register, into funding sources'::text AS text,
                CASE COALESCE(pt.asset_state, 'NO DATA'::text)
                    WHEN 'TIES'::text THEN 'DONE'::text
                    ELSE COALESCE(pt.asset_state, 'NO DATA'::text)
                END AS "coalesce",
                CASE
                    WHEN
                    CASE COALESCE(pt.asset_state, 'NO DATA'::text)
                        WHEN 'TIES'::text THEN 'DONE'::text
                        ELSE COALESCE(pt.asset_state, 'NO DATA'::text)
                    END = 'NO DATA'::text THEN ((('Needs '::text || COALESCE(pt.asset_needs, 'the asset register'::text)) || '. 200.436(b) makes depreciation on a federally '::text) || 'funded asset unallowable and the schedule has no '::text) || 'such column, which 200.313(d)(1) requires.'::text
                    WHEN
                    CASE COALESCE(pt.asset_state, 'NO DATA'::text)
                        WHEN 'TIES'::text THEN 'DONE'::text
                        ELSE COALESCE(pt.asset_state, 'NO DATA'::text)
                    END = 'DONE'::text THEN 'Every asset names where its money came from.'::text
                    ELSE ((((to_char(COALESCE(pt.asset_pct, 0::numeric), 'FM990.0'::text) || '% of the asset cost carries a funding source, so '::text) || '200.436(b) cannot be answered on the depreciation '::text) || 'the rest of it holds. It is the one column the '::text) || 'schedule does not carry and 200.313(d)(1) '::text) || 'requires.'::text
                END AS "case",
            '/classify/assets'::text AS text
           FROM part pt
        UNION ALL
         SELECT c.period,
            6,
            'The paper behind the judgments'::text AS text,
            'EVIDENCE'::text AS text,
            'A judgment that cites the document it rests on'::text AS text,
                CASE
                    WHEN COALESCE(ct.all_live, 0::bigint) = 0 THEN 'WAITING'::text
                    WHEN COALESCE(ct.live, 0::bigint) = 0 THEN 'DONE'::text
                    WHEN ct.with_citation = ct.live THEN 'DONE'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(ct.all_live, 0::bigint) = 0 THEN 'Nothing has been judged yet, so there is nothing to cite.'::text
                    WHEN COALESCE(ct.live, 0::bigint) = 0 THEN 'No judgment is federally chargeable, so none needs a '::text || 'citation for 2 CFR 200.'::text
                    ELSE ((((((to_char(COALESCE(ct.with_citation, 0::bigint), 'FM999,999'::text) || ' of '::text) || to_char(ct.live, 'FM999,999'::text)) || ' federally chargeable judgments cite a document, of '::text) || to_char(ct.all_live, 'FM999,999'::text)) || ' live. '::text) || 'Attaching is not citing: a citation is why the '::text) || 'judgment was made, and it is what VERIFIED requires.'::text
                END AS "case",
            '/evidence'::text AS text
           FROM cover c
             LEFT JOIN cited ct ON ct.period = c.period
        UNION ALL
         SELECT s.period,
            7,
            'The classifications sealed'::text AS text,
            'SEAL'::text AS text,
            'Hashed across every judgment, before any rate exists'::text AS text,
                CASE
                    WHEN s.is_sealed THEN 'DONE'::text
                    WHEN COALESCE(c.unclassified, 1::numeric) <> 0::numeric THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN s.is_sealed THEN ((('Sealed '::text || to_char(s.at, 'DD Mon YYYY'::text)) || ' · '::text) || s.hash) || '…'::text
                    WHEN COALESCE(c.unclassified, 1::numeric) <> 0::numeric THEN ('Cost is still outstanding. Sealing an incomplete set '::text || 'is allowed and makes the rate read high, which is '::text) || 'the honest direction to err.'::text
                    ELSE ('Every group is judged. Sealing is the assertion that '::text || 'the rate was not reverse-engineered, and it is '::text) || 'yours to make.'::text
                END AS "case",
            '/rates'::text AS text
           FROM sealed s
             LEFT JOIN cover c ON c.period = s.period
        UNION ALL
         SELECT rt.period,
            8,
            'The rate computed'::text AS text,
            'RATE'::text AS text,
            'A pool over a base, carrying the seal'::text AS text,
                CASE
                    WHEN COALESCE(rt.live, 0::bigint) > 0 THEN 'DONE'::text
                    WHEN NOT COALESCE(s.is_sealed, false) THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(rt.live, 0::bigint) > 0 THEN ((('Indirect, combined: '::text || round(rt.combined * 100::numeric, 2)) || '% on the '::text) || rt.basis) || ' basis.'::text
                    WHEN NOT COALESCE(s.is_sealed, false) THEN 'No rate can exist until the set is sealed — the '::text || 'database refuses one whose seal does not match.'::text
                    ELSE 'The set is sealed. Computing is arithmetic from here.'::text
                END AS "case",
            '/rates'::text AS text
           FROM rated rt
             LEFT JOIN sealed s ON s.period = rt.period
        UNION ALL
         SELECT rt.period,
            9,
            'The rate certified'::text AS text,
            'CERTIFY'::text AS text,
            'The controller''s signature on the build-up'::text AS text,
                CASE
                    WHEN cert.certified THEN 'DONE'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN cert.certified THEN (((('Signed by '::text || cert.certified_by) || ' on '::text) || to_char(cert.certified_at, 'DD Mon YYYY'::text)) || '. '::text) || 'Anything issued from here says so.'::text
                    ELSE (COALESCE(cert.why_not, 'Nobody has signed the rate.'::text) || ' Nothing is blocked by this — an invoice or a '::text) || 'workbook produced now simply carries NOT CERTIFIED.'::text
                END AS "case",
            '/rates'::text AS text
           FROM rated rt
             LEFT JOIN v_rate_certified cert ON cert.period = rt.period
        UNION ALL
         SELECT rs.period,
            10,
            'The position on each invoice'::text AS text,
            'RESTATE'::text AS text,
            'What was billed, against what the rate supports'::text AS text,
                CASE
                    WHEN COALESCE(rs.overtaken, 0::bigint) > 0 THEN 'OPEN'::text
                    WHEN COALESCE(rs.standing, 0::bigint) > 0 THEN 'DONE'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'WAITING'::text
                    ELSE 'OPEN'::text
                END AS "case",
                CASE
                    WHEN COALESCE(rs.overtaken, 0::bigint) > 0 THEN ((((rs.overtaken || ' of '::text) || rs.standing) || ' standing restatement(s) measured invoices the register no longer holds, so they are not a position to send. Recompute them.'::text))
                    WHEN COALESCE(rs.standing, 0::bigint) > 0 THEN ((rs.standing || ' restatement(s) standing as a claim. '::text) || 'Everything is PROPOSED until a sponsor says '::text) || 'otherwise in writing.'::text
                    WHEN COALESCE(rt.live, 0::bigint) = 0 THEN 'Needs a rate to measure against.'::text
                    ELSE 'Nothing has been put to a sponsor yet.'::text
                END AS "case",
            '/restate'::text AS text
           FROM restated rs
             LEFT JOIN rated rt ON rt.period = rs.period
        UNION ALL
         SELECT p.period,
            11,
            'The papers that leave the building'::text AS text,
            'REPORT'::text AS text,
            'The auditor''s report, Form 990, the workbooks'::text AS text,
            'DONE'::text AS text,
            ('Read from the rows they were recorded in. Each states what is '::text || 'unfinished above its figures, and the workbooks repeat it on '::text) || 'the first sheet because a workbook travels.'::text,
            '/reports'::text AS text
           FROM period p) w
  ORDER BY period, seq;
