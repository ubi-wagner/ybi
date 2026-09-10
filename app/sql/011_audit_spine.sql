-- =====================================================================
-- Audit spine and work lists
--
-- Two defects this closes.
--
-- FIRST: audit_log.actor is a text field the caller supplies. Before there
-- were accounts that was the only option; now that a request carries an
-- authenticated session it is a hole. An audit trail whose actor is asserted
-- by the person being audited records a claim, not a fact. actor_id and
-- session_id are resolved from the session and cannot be set by the caller.
--
-- SECOND: four of sixteen mutating endpoints wrote to audit_log. Evidence
-- uploads, imports, notes, lane promotion and sign-in were invisible. A trail
-- with holes is worse than none, because its silence reads as "nothing
-- happened" rather than "nothing was recorded".
--
-- The spine itself is a union rather than a single table. Several of these
-- objects are already append-only and already carry who and when — decisions,
-- segments, imports, attachments. Copying them into a log would create a
-- second version of the truth that can disagree with the first. The view
-- reads the records themselves.
-- =====================================================================

ALTER TABLE audit_log
  ADD COLUMN actor_id   uuid REFERENCES actor,
  ADD COLUMN session_id uuid REFERENCES actor_session,
  ADD COLUMN actor_role actor_role;

CREATE INDEX ON audit_log (occurred_at DESC);
CREATE INDEX ON audit_log (actor_id, occurred_at DESC);
CREATE INDEX ON audit_log (entity, entity_id);


-- ── The spine ────────────────────────────────────────────────────────
--
-- Everything that happened, from the records that happened rather than from a
-- log written alongside them.

CREATE VIEW v_activity AS
-- Imports
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
-- Classifications
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
-- Reversals of classifications
SELECT d.reversed_at, 'CLASSIFY_REVERSE', d.decided_by, 'decision',
       d.decision_id::text, d.scope, NULL, COALESCE(d.reversal_reason, '')
  FROM decision d WHERE d.reversed_at IS NOT NULL

UNION ALL
-- Segmentation
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
-- Evidence
SELECT a.attached_at, 'EVIDENCE', a.attached_by, 'evidence', a.evidence_id,
       COALESCE(e.kind, ''), NULL, a.relevance
  FROM attachment a LEFT JOIN evidence e USING (evidence_id)
 WHERE a.detached_at IS NULL

UNION ALL
-- Notes
SELECT n.created_at, 'NOTE', n.author, 'note', n.note_id::text,
       left(n.body, 120), NULL,
       CASE WHEN n.is_workpaper THEN 'workpaper' ELSE 'comment' END
  FROM note n

UNION ALL
-- Invoices
SELECT i.loaded_at, 'INVOICE', i.loaded_by, 'invoice', i.invoice_id::text,
       COALESCE(i.invoice_number, i.seq::text), i.total,
       COALESCE(i.objective_id, '') || ' ' || i.status
  FROM invoice i

UNION ALL
-- Everything the log records that has no record of its own: seals, unseals,
-- lane promotion, actor provisioning, sign-in.
SELECT al.occurred_at, al.action, al.actor, al.entity, al.entity_id,
       left(al.reason, 120), NULL, COALESCE(al.actor_role::text, '')
  FROM audit_log al;

COMMENT ON VIEW v_activity IS
  'Everything that happened, read from the append-only records themselves '
  'rather than from a log written alongside them, so the trail cannot '
  'disagree with the thing it describes.';


-- ── Work lists ───────────────────────────────────────────────────────
--
-- One feed with a kind, so the dashboard groups rather than joins. Ordered by
-- money, because that is the order the work is worth doing in.

CREATE VIEW v_worklist AS
-- Cost in scope with no live decision. The queue itself.
SELECT 'UNCLASSIFIED'                                AS kind,
       'BLOCKING'                                    AS severity,
       l.period,
       l.account || COALESCE(NULLIF(' / ' || l.payee, ' / '), '') AS label,
       'ledger_group'                                AS entity,
       l.account || chr(31) || COALESCE(l.payee, '') AS entity_id,
       sum(abs(l.amount))                            AS amount,
       count(*)::text || ' lines, no decision'       AS detail
  FROM ledger_line l
  LEFT JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
 WHERE l.period = '2025' AND l.statement = 'P&L' AND dl.line_id IS NULL
 GROUP BY l.period, l.account, l.payee

UNION ALL
-- Decided, but on evidence that cannot survive a seal.
SELECT 'BLOCKS_SEAL', 'BLOCKING', '2025', d.scope, 'decision',
       d.decision_id::text,
       (SELECT sum(abs(l.amount)) FROM decision_line dl
          JOIN ledger_line l USING (line_id)
         WHERE dl.decision_id = d.decision_id),
       'graded ' || d.grade::text
  FROM decision d
 WHERE d.reversed_at IS NULL
   AND d.grade IN ('UNSUPPORTED', 'TEST_ASSUMPTION')

UNION ALL
-- Decided and federally chargeable, with nothing attached.
SELECT 'NEEDS_EVIDENCE', 'HIGH', '2025', d.scope, 'decision',
       d.decision_id::text,
       (SELECT sum(abs(l.amount)) FROM decision_line dl
          JOIN ledger_line l USING (line_id)
         WHERE dl.decision_id = d.decision_id),
       'no document cited on the judgment'
  FROM decision d
 WHERE d.reversed_at IS NULL
   AND d.federal IN ('ALLOWABLE', 'PENDING')
   AND NOT EXISTS (SELECT 1 FROM decision_evidence de
                    WHERE de.decision_id = d.decision_id)

UNION ALL
-- An asset whose funding source is unknown depreciates as if wholly YBI's,
-- which is the optimistic reading (2 CFR 200.436).
SELECT 'ASSET_FUNDING_UNKNOWN', 'BLOCKING', a.period, a.description, 'asset',
       a.asset_id, a.depreciation,
       'depreciation currently treated as fully allowable'
  FROM asset a
 WHERE NOT EXISTS (SELECT 1 FROM asset_funding f WHERE f.asset_id = a.asset_id)

UNION ALL
-- A facility with no space schedule cannot carve occupancy (200.465).
SELECT 'FACILITY_UNPARTITIONED', 'BLOCKING', f.period, f.name, 'facility',
       f.facility_id, f.usable_sqft, 'no space partition recorded'
  FROM facility f
 WHERE NOT EXISTS (SELECT 1 FROM space_partition sp
                    WHERE sp.facility_id = f.facility_id
                      AND sp.period = f.period)

UNION ALL
-- An invoice on a cost-reimbursement award carrying no indirect line.
SELECT 'INVOICE_NO_INDIRECT', 'HIGH', v.period,
       'Invoice ' || COALESCE(v.invoice_number, '') || ' ' ||
         COALESCE(v.objective_id, ''),
       'invoice', v.invoice_id::text, v.mtdc_as_billed,
       'no indirect billed on a base of ' || v.mtdc_as_billed::text
  FROM v_invoice_category v
 WHERE v.no_indirect_billed AND v.mtdc_as_billed > 0

UNION ALL
-- An invoice not tied to an award has no ceiling to test against.
SELECT 'INVOICE_NO_AWARD', 'MEDIUM', i.period,
       'Invoice ' || COALESCE(i.invoice_number, i.seq::text),
       'invoice', i.invoice_id::text, i.total, 'not linked to an award'
  FROM invoice i WHERE i.award_id IS NULL

UNION ALL
-- A classification standing on a ledger line that changed under it.
SELECT 'STALE_DECISION', 'HIGH', l.period, d.scope, 'decision',
       d.decision_id::text, abs(l.amount),
       'source line ' || r.change || ' after the decision'
  FROM ledger_revision r
  JOIN ledger_line l USING (line_id)
  JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
  JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
 WHERE r.detected_at > d.decided_at;

COMMENT ON VIEW v_worklist IS
  'What is left to do, by kind and by money. BLOCKING items prevent a seal; '
  'HIGH and MEDIUM are quality of the record rather than gates.';


-- ── The rollup ───────────────────────────────────────────────────────

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
