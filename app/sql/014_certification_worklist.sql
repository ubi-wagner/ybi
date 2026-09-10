-- =====================================================================
-- The certification work list
--
-- v_worklist carried a NEEDS_CERTIFICATION label with nothing behind it,
-- because effort distribution did not exist yet. It does now, so the class
-- reads real rows: whose effort is unattested, and whose signature has gone
-- stale because the distribution changed after they signed it.
--
-- A stale signature is listed as blocking, not as a warning. It attested to
-- different numbers, which makes it worse than no signature: it looks like
-- support and is not.
-- =====================================================================

CREATE OR REPLACE VIEW v_worklist AS
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
-- Effort not attested by the person who did the work.
SELECT 'NEEDS_CERTIFICATION', 'BLOCKING', c.period,
       COALESCE(NULLIF(c.employee_name, ''), c.employee_key),
       'employee', c.employee_key, c.payroll_wages,
       CASE WHEN c.reconstructed
            THEN 'reconstructed distribution, unsigned'
            ELSE 'distribution unsigned' END
  FROM v_certification_status c WHERE NOT c.certified

UNION ALL
-- Signed, but for numbers that have since changed.
SELECT 'STALE_CERTIFICATION', 'BLOCKING', c.period,
       COALESCE(NULLIF(c.employee_name, ''), c.employee_key),
       'employee', c.employee_key, c.payroll_wages,
       'signed ' || to_char(c.signed_at, 'DD Mon YYYY')
         || ', distribution changed since'
  FROM v_certification_status c WHERE c.certified AND c.stale

UNION ALL
SELECT 'ASSET_FUNDING_UNKNOWN', 'BLOCKING', a.period, a.description, 'asset',
       a.asset_id, a.depreciation,
       'depreciation currently treated as fully allowable'
  FROM asset a
 WHERE NOT EXISTS (SELECT 1 FROM asset_funding f WHERE f.asset_id = a.asset_id)

UNION ALL
SELECT 'FACILITY_UNPARTITIONED', 'BLOCKING', f.period, f.name, 'facility',
       f.facility_id, f.usable_sqft, 'no space partition recorded'
  FROM facility f
 WHERE NOT EXISTS (SELECT 1 FROM space_partition sp
                    WHERE sp.facility_id = f.facility_id
                      AND sp.period = f.period)

UNION ALL
SELECT 'INVOICE_NO_INDIRECT', 'HIGH', v.period,
       'Invoice ' || COALESCE(v.invoice_number, '') || ' ' ||
         COALESCE(v.objective_id, ''),
       'invoice', v.invoice_id::text, v.mtdc_as_billed,
       'no indirect billed on a base of ' || v.mtdc_as_billed::text
  FROM v_invoice_category v
 WHERE v.no_indirect_billed AND v.mtdc_as_billed > 0

UNION ALL
SELECT 'INVOICE_NO_AWARD', 'MEDIUM', i.period,
       'Invoice ' || COALESCE(i.invoice_number, i.seq::text),
       'invoice', i.invoice_id::text, i.total, 'not linked to an award'
  FROM invoice i WHERE i.award_id IS NULL

UNION ALL
SELECT 'STALE_DECISION', 'HIGH', l.period, d.scope, 'decision',
       d.decision_id::text, abs(l.amount),
       'source line ' || r.change || ' after the decision'
  FROM ledger_revision r
  JOIN ledger_line l USING (line_id)
  JOIN decision_line dl ON dl.line_id = l.line_id AND dl.live
  JOIN decision d ON d.decision_id = dl.decision_id AND d.reversed_at IS NULL
 WHERE r.detected_at > d.decided_at;
