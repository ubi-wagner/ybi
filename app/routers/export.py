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


@router.get("/reconciliation")
def reconciliation(period: str = None, actor: Actor = Depends(require_reader)) -> dict:
    """Schedule A-1: the three source documents against each other.

    Ahead of classification, not after it. The question a reviewer asks first
    is not whether the rate is right, it is whether the numbers under it are
    the numbers in the books — and the answer has to be available before
    anyone has an interest in what it says.
    """
    period = period or settings.period
    controls = query("""SELECT control, basis, description, left_label, left_value,
                               right_label, right_value, variance, exceptions,
                               ties, state, note
                          FROM v_statement_reconciliation
                         WHERE period = %s ORDER BY seq""", (period,))
    pl = query("""SELECT account, section, gl_amount, gl_lines, pl_amount,
                         reconciling, gross_variance, unexplained
                    FROM v_gl_pl_account
                   WHERE period = %s AND gross_variance <> 0
                   ORDER BY abs(gross_variance) DESC""", (period,))
    bs = query("""SELECT account, bs_leaf, matched_by_alias, opening, activity,
                         closing, bs_amount, on_balance_sheet, variance,
                         absent_because_zero
                    FROM v_gl_bs_account
                   WHERE period = %s
                     AND (variance <> 0 OR NOT on_balance_sheet)
                   ORDER BY abs(variance) DESC, account""", (period,))
    items = query("""SELECT i.item_id, i.control, i.from_account, i.to_account,
                            i.amount, i.kind, i.explanation, i.recorded_by,
                            i.recorded_at,
                            (SELECT count(*) FROM reconciling_item_line rl
                              WHERE rl.item_id = i.item_id) AS lines
                       FROM reconciling_item i
                      WHERE i.period = %s AND i.retracted_at IS NULL
                      ORDER BY abs(i.amount) DESC""", (period,))
    failing = [c["control"] for c in controls if not c["ties"]]
    record(actor, "EXPORT", "reconciliation", period,
           after={"controls": len(controls), "failing": failing},
           reason="cross-reference reconciliation read")
    return {"period": period, "controls": controls,
            "gl_pl_differences": pl, "gl_bs_differences": bs,
            "reconciling_items": items,
            "failing": failing,
            "ties": not failing}


@router.get("/audit-package")
def audit_package(period: str = None, actor: Actor = Depends(require_reader)):
    """The whole record as one workbook.

    Available to the auditor as well as the controller. A read-only reviewer
    who cannot export is a reviewer who has to ask someone else for a copy,
    which puts the person being reviewed between the reviewer and the evidence.
    """
    period = period or settings.period

    rollup = one("SELECT * FROM v_dashboard WHERE period = %s", (period,)) or {}

    # Schedule A-1 is the cross-reference register, and the Controls sheet is
    # its short form. They come from the same view so the package cannot show
    # a control tying on one sheet and open on another.
    controls = (query("""
        SELECT control, description,
               left_label, left_value, right_label, right_value,
               CASE WHEN basis = 'VARIANCE' THEN variance ELSE exceptions END
                   AS variance,
               ties, state, note
          FROM v_statement_reconciliation
         WHERE period = %s ORDER BY seq""", (period,)) or [])
    # `ties` reads `evaluable` as well as the variance, for the same reason
    # migration 029 gave the other eleven a state: with no register loaded the
    # variance is the whole of the ledger's depreciation, which reads as a
    # disagreement rather than as a missing document.
    controls += query("""SELECT 'ASSET_REGISTER' AS control,
                                'Asset register agrees with the ledger' AS description,
                                'Register' AS left_label,
                                register_depreciation AS left_value,
                                'Ledger' AS right_label,
                                ledger_depreciation AS right_value,
                                variance, (variance = 0 AND evaluable) AS ties,
                                state,
                                CASE WHEN evaluable THEN
                                  'The register is the basis for depreciation, so it '
                                  'has to be the same assets the ledger carries.'
                                ELSE 'Not evaluated: this needs ' || needs || '.'
                                END AS note
                           FROM v_asset_control WHERE period = %s""", (period,))

    gl_pl = query("""SELECT account, section, gl_amount, gl_lines, pl_amount,
                            reconciling, gross_variance, unexplained
                       FROM v_gl_pl_account
                      WHERE period = %s AND gross_variance <> 0
                      ORDER BY abs(gross_variance) DESC""", (period,))
    gl_bs = query("""SELECT account, bs_leaf, opening, activity, closing,
                            bs_amount, on_balance_sheet, variance,
                            absent_because_zero, matched_by_alias
                       FROM v_gl_bs_account
                      WHERE period = %s AND (variance <> 0 OR NOT on_balance_sheet)
                      ORDER BY abs(variance) DESC, account""", (period,))
    reconciling_items = query("""
        SELECT from_account, to_account, amount, kind::text AS kind,
               explanation, recorded_by, recorded_at,
               (SELECT count(*) FROM reconciling_item_line rl
                 WHERE rl.item_id = i.item_id) AS lines
          FROM reconciling_item i
         WHERE i.period = %s AND i.retracted_at IS NULL
         ORDER BY abs(i.amount) DESC""", (period,))

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
        allocations=allocations, gl_pl=gl_pl, gl_bs=gl_bs,
        reconciling_items=reconciling_items,
        generated_by=f"{actor.display_name} ({actor.role.value})")

    record(actor, "EXPORT", "audit_package", name,
           after={"period": period, "decisions": len(decisions),
                  "evidence": len(evidence), "activity": len(activity)},
           reason="audit package downloaded")

    return FileResponse(
        out, filename=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
