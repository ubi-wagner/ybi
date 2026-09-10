-- =====================================================================
-- Taking the record away is part of the record
--
-- A reviewer downloading the audit package, or opening the invoice PDF
-- behind a decision, is activity. It was happening and leaving no trace in
-- the feed, so the feed said the auditor had never looked at anything.
--
-- These two actions have no record of their own — nothing is written but the
-- audit log entry — so they belong in the audit-log arm of v_activity.
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
-- The employee's own signature. It is the support for a labour charge, so it
-- belongs in the feed beside the classification it supports.
SELECT c.signed_at, 'CERTIFY', c.signed_by, 'labor_certification',
       c.certification_id::text, c.employee_key,
       -- payroll_wages is total compensation carried on every objective row,
       -- so it is taken once, not summed across them.
       (SELECT max(la.payroll_wages) FROM labor_allocation la
         WHERE la.period = c.period AND la.employee_key = c.employee_key),
       c.certifier_role::text ||
       CASE WHEN c.superseded_at IS NOT NULL THEN ' · superseded' ELSE '' END
  FROM labor_certification c

UNION ALL
-- Only what has no record of its own.
SELECT al.occurred_at, al.action, al.actor, al.entity, al.entity_id,
       left(al.reason, 120), NULL, COALESCE(al.actor_role::text, '')
  FROM audit_log al
 WHERE al.action IN ('SEAL', 'UNSEAL', 'SIGN_IN', 'SIGN_OUT', 'ACTOR_CREATE',
                     'DEFER', 'LANE_CREATE', 'LANE_PROMOTE',
                     'EXPORT', 'EVIDENCE_DOWNLOAD');
