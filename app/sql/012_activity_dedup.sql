-- =====================================================================
-- Activity spine: stop double counting
--
-- v_activity reads the append-only records themselves AND the audit log.
-- Several actions write both — a note creates a note row and an audit entry,
-- a classification creates a decision and an audit entry — so those appeared
-- twice in the feed. A reviewer counting activity would have counted each of
-- them once too often.
--
-- The rule: the audit log contributes only the actions that have no record of
-- their own. Sealing, unsealing, sign-in, provisioning and deferral live
-- nowhere else; everything else is read from the thing itself.
-- =====================================================================

CREATE OR REPLACE VIEW v_activity AS
SELECT b.parsed_at                                   AS occurred_at,
       'IMPORT'                                      AS kind,
       COALESCE(b.accepted_by, b.uploaded_by)        AS actor,
       'staging_batch'                               AS entity,
       b.batch_id::text                              AS entity_id,
       b.original_name                               AS label,
       NULL::numeric                                 AS amount,
       'status ' || b.status                         AS detail
  FROM staging_batch b WHERE b.parsed_at IS NOT NULL

UNION ALL
SELECT d.decided_at, 'CLASSIFY', d.decided_by, 'decision', d.decision_id::text,
       d.scope,
       (SELECT sum(COALESCE(s.amount, l.amount))
          FROM decision_line dl
          JOIN ledger_line l ON l.line_id = dl.line_id
          LEFT JOIN ledger_segment s ON s.segment_id = dl.segment_id
         WHERE dl.decision_id = d.decision_id),
       d.pool::text || ' / ' || d.grade::text
  FROM decision d

UNION ALL
SELECT d.reversed_at, 'CLASSIFY_REVERSE', d.decided_by, 'decision',
       d.decision_id::text, d.scope, NULL, COALESCE(d.reversal_reason, '')
  FROM decision d WHERE d.reversed_at IS NOT NULL

UNION ALL
SELECT min(s.created_at), 'SEGMENT', s.created_by, 'ledger_segment', s.batch_key,
       s.label, sum(s.amount), count(*)::text || ' segments'
  FROM ledger_segment s WHERE s.reversed_at IS NULL
 GROUP BY s.batch_key, s.label, s.created_by

UNION ALL
SELECT min(s.reversed_at), 'SEGMENT_REVERSE', s.reversed_by, 'ledger_segment',
       s.batch_key, s.label, sum(s.amount), max(s.reversal_reason)
  FROM ledger_segment s WHERE s.reversed_at IS NOT NULL
 GROUP BY s.batch_key, s.label, s.reversed_by

UNION ALL
-- One document attached to a group fans out to every line in it — 85 rows for
-- one upload — and eighty-five identical entries bury everything else in the
-- feed. Grouped to the act, with the fan-out as its detail.
SELECT min(a.attached_at), 'EVIDENCE', a.attached_by, 'evidence', a.evidence_id,
       COALESCE(max(e.kind), ''), NULL,
       CASE WHEN count(*) > 1
            THEN count(*)::text || ' items · ' || COALESCE(max(a.relevance), '')
            ELSE COALESCE(max(a.relevance), '') END
  FROM attachment a LEFT JOIN evidence e USING (evidence_id)
 WHERE a.detached_at IS NULL
 GROUP BY a.evidence_id, a.attached_by

UNION ALL
SELECT n.created_at, 'NOTE', n.author, 'note', n.note_id::text,
       left(n.body, 120), NULL,
       CASE WHEN n.is_workpaper THEN 'workpaper' ELSE 'comment' END
  FROM note n

UNION ALL
SELECT i.loaded_at, 'INVOICE', i.loaded_by, 'invoice', i.invoice_id::text,
       COALESCE(i.invoice_number, i.seq::text), i.total,
       COALESCE(i.objective_id, '') || ' ' || i.status
  FROM invoice i

UNION ALL
-- Only what has no record of its own.
SELECT al.occurred_at, al.action, al.actor, al.entity, al.entity_id,
       left(al.reason, 120), NULL, COALESCE(al.actor_role::text, '')
  FROM audit_log al
 WHERE al.action IN ('SEAL', 'UNSEAL', 'SIGN_IN', 'SIGN_OUT', 'ACTOR_CREATE',
                     'DEFER', 'LANE_CREATE', 'LANE_PROMOTE');


-- The dashboard showed net operating income and called it "Net", which is a
-- different number from the one on the bottom of the P&L: other income of
-- 116,948.46 turns a 112,619.18 operating loss into net income of 4,329.28.
-- A rollup that disagrees with the statement it summarises is worse than no
-- rollup.
-- Dropped rather than replaced: CREATE OR REPLACE cannot insert a column
-- into the middle of a view's column list.
DROP VIEW IF EXISTS v_dashboard;
CREATE VIEW v_dashboard AS
SELECT p.period,
       (SELECT count(*) FROM ledger_line WHERE period = p.period)          AS ledger_lines,
       (SELECT count(*) FROM ledger_line
         WHERE period = p.period AND statement = 'P&L')                    AS scope_lines,
       (SELECT COALESCE(sum(amount), 0) FROM pl_account
         WHERE period = p.period AND section = 'Income')                   AS income,
       (SELECT COALESCE(sum(amount), 0) FROM pl_account
         WHERE period = p.period AND section = 'Expense')                  AS expense,
       (SELECT COALESCE(sum(amount), 0) FROM pl_account
         WHERE period = p.period AND section = 'COGS')                     AS cogs,
       (SELECT COALESCE(sum(amount), 0) FROM pl_account
         WHERE period = p.period AND section = 'Other Income')             AS other_income,
       (SELECT COALESCE(sum(amount), 0) FROM pl_account
         WHERE period = p.period AND section = 'Income')
       - (SELECT COALESCE(sum(amount), 0) FROM pl_account
           WHERE period = p.period AND section = 'Expense')
       - (SELECT COALESCE(sum(amount), 0) FROM pl_account
           WHERE period = p.period AND section = 'COGS')
       + (SELECT COALESCE(sum(amount), 0) FROM pl_account
           WHERE period = p.period AND section = 'Other Income')           AS net_income,
       (SELECT count(*) FROM decision d WHERE d.reversed_at IS NULL)       AS decisions,
       (SELECT count(*) FROM ledger_segment
         WHERE period = p.period AND reversed_at IS NULL)                  AS segments,
       (SELECT count(*) FROM evidence WHERE period = p.period)             AS documents,
       (SELECT count(*) FROM invoice WHERE period = p.period)              AS invoices,
       (SELECT count(*) FROM asset WHERE period = p.period)                AS assets,
       (SELECT count(*) FROM facility WHERE period = p.period)             AS facilities,
       (SELECT count(*) FROM v_worklist
         WHERE severity = 'BLOCKING' AND period = p.period)                AS blocking_items,
       (SELECT COALESCE(sum(amount), 0) FROM v_worklist
         WHERE severity = 'BLOCKING' AND period = p.period)                AS blocking_amount,
       (SELECT sealed_at FROM decision_set
         WHERE period = p.period AND seal_hash IS NOT NULL
         ORDER BY sealed_at DESC LIMIT 1)                                  AS sealed_at
  FROM fiscal_period p;
