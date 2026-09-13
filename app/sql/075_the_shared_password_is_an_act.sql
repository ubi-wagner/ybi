-- 075  A sign-in on the organisation's password is its own act
--
-- `v_activity` selects from `audit_log` through a **hand-kept list of
-- actions**, so an action the list does not name is written to the record and
-- shown on no screen. That is the shape this repository keeps finding — a map
-- of what the code does, maintained by remembering to.
--
-- It was found before it cost anything, by checking where a new action would
-- surface rather than assuming it would. `SIGN_IN_SHARED` is the signal that
-- says a session was opened on a password the whole organisation holds, which
-- is precisely the thing an auditor asks about and precisely the thing that
-- would have gone missing.
--
-- `PASSWORD_CHANGE` goes on with it, because it is the other half of the same
-- question. "Who is still on the shared credential" and "who has claimed
-- their account" are one enquiry, and a screen that could answer only the
-- first would be read as though everybody else had claimed theirs.
--
-- The body below is **lifted from the definition in force**, not retyped: 011
-- created this view, 012 and 015 replaced it, and a body written from the
-- first one would silently revert two migrations of changes. Only the array
-- differs.

CREATE OR REPLACE VIEW v_activity AS
SELECT b.parsed_at AS occurred_at,
    'IMPORT'::text AS kind,
    COALESCE(b.accepted_by, b.uploaded_by) AS actor,
    'staging_batch'::text AS entity,
    b.batch_id::text AS entity_id,
    b.original_name AS label,
    NULL::numeric AS amount,
    'status '::text || b.status AS detail
   FROM staging_batch b
  WHERE b.parsed_at IS NOT NULL
UNION ALL
 SELECT d.decided_at AS occurred_at,
    'CLASSIFY'::text AS kind,
    d.decided_by AS actor,
    'decision'::text AS entity,
    d.decision_id::text AS entity_id,
    d.scope AS label,
    ( SELECT sum(COALESCE(s.amount, l.amount)) AS sum
           FROM decision_line dl
             JOIN ledger_line l ON l.line_id = dl.line_id
             LEFT JOIN ledger_segment s ON s.segment_id = dl.segment_id
          WHERE dl.decision_id = d.decision_id) AS amount,
    (d.pool::text || ' / '::text) || d.grade::text AS detail
   FROM decision d
UNION ALL
 SELECT d.reversed_at AS occurred_at,
    'CLASSIFY_REVERSE'::text AS kind,
    d.decided_by AS actor,
    'decision'::text AS entity,
    d.decision_id::text AS entity_id,
    d.scope AS label,
    NULL::numeric AS amount,
    COALESCE(d.reversal_reason, ''::text) AS detail
   FROM decision d
  WHERE d.reversed_at IS NOT NULL
UNION ALL
 SELECT min(s.created_at) AS occurred_at,
    'SEGMENT'::text AS kind,
    s.created_by AS actor,
    'ledger_segment'::text AS entity,
    s.batch_key AS entity_id,
    s.label,
    sum(s.amount) AS amount,
    count(*)::text || ' segments'::text AS detail
   FROM ledger_segment s
  WHERE s.reversed_at IS NULL
  GROUP BY s.batch_key, s.label, s.created_by
UNION ALL
 SELECT min(s.reversed_at) AS occurred_at,
    'SEGMENT_REVERSE'::text AS kind,
    s.reversed_by AS actor,
    'ledger_segment'::text AS entity,
    s.batch_key AS entity_id,
    s.label,
    sum(s.amount) AS amount,
    max(s.reversal_reason) AS detail
   FROM ledger_segment s
  WHERE s.reversed_at IS NOT NULL
  GROUP BY s.batch_key, s.label, s.reversed_by
UNION ALL
 SELECT min(a.attached_at) AS occurred_at,
    'EVIDENCE'::text AS kind,
    a.attached_by AS actor,
    'evidence'::text AS entity,
    a.evidence_id AS entity_id,
    COALESCE(max(e.kind), ''::text) AS label,
    NULL::numeric AS amount,
        CASE
            WHEN count(*) > 1 THEN (count(*)::text || ' items · '::text) || COALESCE(max(a.relevance), ''::text)
            ELSE COALESCE(max(a.relevance), ''::text)
        END AS detail
   FROM attachment a
     LEFT JOIN evidence e USING (evidence_id)
  WHERE a.detached_at IS NULL
  GROUP BY a.evidence_id, a.attached_by
UNION ALL
 SELECT n.created_at AS occurred_at,
    'NOTE'::text AS kind,
    n.author AS actor,
    'note'::text AS entity,
    n.note_id::text AS entity_id,
    "left"(n.body, 120) AS label,
    NULL::numeric AS amount,
        CASE
            WHEN n.is_workpaper THEN 'workpaper'::text
            ELSE 'comment'::text
        END AS detail
   FROM note n
UNION ALL
 SELECT i.loaded_at AS occurred_at,
    'INVOICE'::text AS kind,
    i.loaded_by AS actor,
    'invoice'::text AS entity,
    i.invoice_id::text AS entity_id,
    COALESCE(i.invoice_number, i.seq::text) AS label,
    i.total AS amount,
    (COALESCE(i.objective_id, ''::text) || ' '::text) || i.status AS detail
   FROM invoice i
UNION ALL
 SELECT c.signed_at AS occurred_at,
    'CERTIFY'::text AS kind,
    c.signed_by AS actor,
    'labor_certification'::text AS entity,
    c.certification_id::text AS entity_id,
    c.employee_key AS label,
    ( SELECT max(la.payroll_wages) AS max
           FROM labor_allocation la
          WHERE la.period = c.period AND la.employee_key = c.employee_key) AS amount,
    c.certifier_role::text ||
        CASE
            WHEN c.superseded_at IS NOT NULL THEN ' · superseded'::text
            ELSE ''::text
        END AS detail
   FROM labor_certification c
UNION ALL
 SELECT al.occurred_at,
    al.action AS kind,
    al.actor,
    al.entity,
    al.entity_id,
    "left"(al.reason, 120) AS label,
    NULL::numeric AS amount,
    COALESCE(al.actor_role::text, ''::text) AS detail
   FROM audit_log al
  WHERE al.action = ANY (ARRAY['SEAL'::text, 'UNSEAL'::text, 'SIGN_IN'::text, 'SIGN_OUT'::text, 'ACTOR_CREATE'::text, 'DEFER'::text, 'LANE_CREATE'::text, 'LANE_PROMOTE'::text, 'EXPORT'::text, 'EVIDENCE_DOWNLOAD'::text, 'SIGN_IN_SHARED'::text, 'PASSWORD_CHANGE'::text]);
