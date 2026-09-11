"""Taking the record away.

A system that only answers questions on screen makes the reviewer work at your
desk, on your schedule. The auditor gets a file.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.audit import record
from app.auth import Actor, require_reader
from app.db import one, query
from app.domain.audit_package import build_audit_package
from app.settings import settings

router = APIRouter(prefix="/export", tags=["export"],
                   dependencies=[Depends(require_reader)])


@router.get("/exceptions")
def exceptions(period: str = None, actor: Actor = Depends(require_reader)) -> dict:
    """Every place the standard was bent, who bent it and why.

    The first schedule a reviewer asks for. Making them reconstruct it from a
    five-thousand-row activity feed is how a candid file reads as managed.
    """
    period = period or settings.period
    rows = query("""SELECT period, kind, occurred_at, actor, subject, detail,
                           reason, amount
                      FROM v_exceptions
                     WHERE period = %s
                     ORDER BY occurred_at DESC NULLS LAST""", (period,))
    by_kind: dict[str, int] = {}
    unexplained = 0
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
        if not (r["reason"] or "").strip():
            unexplained += 1
    return {"period": period, "exceptions": rows, "by_kind": by_kind,
            "total": len(rows), "unexplained": unexplained}


@router.get("/audit-package")
def audit_package(period: str = None, actor: Actor = Depends(require_reader)):
    """The whole record as one workbook.

    Available to the auditor as well as the controller. A read-only reviewer
    who cannot export is a reviewer who has to ask someone else for a copy,
    which puts the person being reviewed between the reviewer and the evidence.
    """
    period = period or settings.period

    rollup = one("SELECT * FROM v_dashboard WHERE period = %s", (period,)) or {}

    controls = (query("""SELECT 'GL subtotals' AS control, variance,
                                (variance = 0) AS ties
                           FROM v_staging_reconciliation LIMIT 1""") or [])
    controls += query("""SELECT 'Segmentation' AS control, variance,
                                (variance = 0) AS ties
                           FROM v_segmentation_control WHERE period = %s""",
                      (period,))
    controls += query("""SELECT 'Asset register' AS control, variance,
                                (variance = 0) AS ties
                           FROM v_asset_control WHERE period = %s""", (period,))

    decisions = query("""
        SELECT d.scope, d.pool::text AS pool, d.function_990::text AS function_990,
               d.federal::text AS federal, d.grade::text AS grade,
               d.rationale, d.citation, d.decided_by, d.decided_at, d.reversed_at,
               (SELECT sum(abs(l.amount)) FROM decision_line dl
                  JOIN ledger_line l USING (line_id)
                 WHERE dl.decision_id = d.decision_id) AS amount
          FROM decision d ORDER BY d.decided_at""")

    segments = query("""
        SELECT batch_key, label, count(*) AS segments, sum(amount) AS amount,
               max(rationale) AS rationale, max(citation) AS citation,
               max(created_by) AS created_by, min(created_at) AS created_at,
               max(reversed_at) AS reversed_at
          FROM ledger_segment WHERE period = %s
         GROUP BY batch_key, label ORDER BY min(created_at)""", (period,))

    evidence = query("""
        SELECT e.evidence_id, e.kind, e.sha256, e.byte_size, e.received_from,
               e.received_at,
               (SELECT count(*) FROM attachment a
                 WHERE a.evidence_id = e.evidence_id
                   AND a.detached_at IS NULL) AS attachments,
               (SELECT max(a.relevance) FROM attachment a
                 WHERE a.evidence_id = e.evidence_id) AS relevance
          FROM evidence e WHERE e.period = %s ORDER BY e.received_at""",
        (period,))

    certifications = query("""
        SELECT employee_key, certifier_role::text AS certifier_role, signed_by,
               signed_at, statement, distribution::text AS distribution,
               superseded_at,
               jsonb_array_length(distribution) AS objectives
          FROM labor_certification WHERE period = %s ORDER BY signed_at""",
        (period,))

    activity = query("""
        SELECT occurred_at, kind, actor, entity, label, detail, amount
          FROM v_activity WHERE occurred_at IS NOT NULL
         ORDER BY occurred_at DESC LIMIT 5000""")

    worklist = query("""
        SELECT kind, severity, label, detail, amount FROM v_worklist
         WHERE period = %s
         ORDER BY CASE severity WHEN 'BLOCKING' THEN 0 WHEN 'HIGH' THEN 1
                                ELSE 2 END,
                  COALESCE(abs(amount), 0) DESC
         LIMIT 5000""", (period,))

    exceptions = query("""
        SELECT kind, occurred_at, actor, subject, detail, reason, amount
          FROM v_exceptions WHERE period = %s
         ORDER BY occurred_at DESC NULLS LAST LIMIT 5000""", (period,))

    materiality = query("""
        SELECT scope, pool, amount, grade::text AS grade,
               required_grade::text AS required_grade, meets_standard,
               federal::text AS federal, decided_by
          FROM v_materiality_compliance WHERE period = %s
         ORDER BY meets_standard, amount DESC LIMIT 5000""", (period,))

    rates = query("""
        SELECT kind, pool_amount, base_type::text AS base_type, base_amount,
               rate, status, seal_hash, computed_by, computed_at
          FROM rate WHERE period = %s ORDER BY computed_at DESC, kind""",
        (period,))

    allocations = query("""
        SELECT r.kind, a.objective_id, a.base_amount, a.allocated
          FROM allocation a JOIN rate r USING (rate_id)
         WHERE r.period = %s AND r.status <> 'SUPERSEDED'
         ORDER BY a.allocated DESC""", (period,))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    name = f"YBI-{period}-cost-record-{stamp}.xlsx"
    out = Path(tempfile.gettempdir()) / name
    build_audit_package(
        period=period, out_path=out, controls=controls, decisions=decisions,
        segments=segments, evidence=evidence, certifications=certifications,
        activity=activity, worklist=worklist, rollup=rollup,
        exceptions=exceptions, materiality=materiality, rates=rates,
        allocations=allocations,
        generated_by=f"{actor.display_name} ({actor.role.value})")

    record(actor, "EXPORT", "audit_package", name,
           after={"period": period, "decisions": len(decisions),
                  "evidence": len(evidence), "activity": len(activity)},
           reason="audit package downloaded")

    return FileResponse(
        out, filename=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
