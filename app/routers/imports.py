"""QuickBooks import: upload, parse under a profile, preview, accept.

Two-phase commit. Nothing reaches ledger_line until the account subtotals QBO
printed in its own report reconcile against what we parsed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db import execute, one, query
from app.domain.qbo import (QBO_GENERAL_LEDGER, QBO_TIME_ACTIVITY,
                            parse_general_ledger, parse_time_activity)
from app.settings import settings

router = APIRouter(prefix="/imports", tags=["imports"])
STORAGE = Path(settings.storage_dir)


@router.post("/upload")
async def upload(file: UploadFile = File(...), report: str = "GENERAL_LEDGER",
                 period: str = "2025", uploaded_by: str = "unknown") -> dict:
    raw = await file.read()
    sha = hashlib.sha256(raw).hexdigest()

    dup = one("""SELECT batch_id, status FROM staging_batch
                  WHERE period=%s AND report=%s AND sha256=%s""", (period, report, sha))
    if dup:
        return {"batch_id": str(dup["batch_id"]), "status": dup["status"],
                "note": "This exact file has already been uploaded."}

    STORAGE.mkdir(parents=True, exist_ok=True)
    dest = STORAGE / f"{sha[:16]}_{file.filename}"
    dest.write_bytes(raw)

    row = one("""INSERT INTO staging_batch
                   (period, report, profile_id, original_name, storage_uri,
                    sha256, byte_size, uploaded_by)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING batch_id""",
              (period, report, "qbo-gl-v1", file.filename, str(dest),
               sha, len(raw), uploaded_by))
    return {"batch_id": str(row["batch_id"]), "status": "UPLOADED", "sha256": sha}


@router.post("/{batch_id}/parse")
def parse(batch_id: str) -> dict:
    b = one("SELECT * FROM staging_batch WHERE batch_id=%s", (batch_id,))
    if not b:
        raise HTTPException(404, "batch not found")
    path = Path(b["storage_uri"])

    if b["report"] == "TIME_ACTIVITY":
        rows = parse_time_activity(path, QBO_TIME_ACTIVITY)
        return {"batch_id": batch_id, "kind": "TIME_ACTIVITY", "rows": len(rows),
                "sample": rows[:5]}

    staged = parse_general_ledger(path, QBO_GENERAL_LEDGER, sha256=b["sha256"])
    execute("DELETE FROM staging_line WHERE batch_id=%s", (batch_id,))
    execute("DELETE FROM staging_subtotal WHERE batch_id=%s", (batch_id,))

    for l in staged.lines:
        execute("""INSERT INTO staging_line
                     (batch_id,row_number,natural_key,account,txn_date,txn_type,
                      doc_num,name,memo,split_account,amount,class_name,location,
                      customer_job,objective_hint)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (batch_id, l.row_number, l.natural_key, l.account, l.date or None,
                 l.txn_type, l.num, l.name, l.memo, l.split, l.amount,
                 l.class_, l.location, l.customer_job, l.objective_hint))

    parsed = staged.account_totals()
    for account, printed in staged.subtotals.items():
        execute("""INSERT INTO staging_subtotal (batch_id,account,printed_total,parsed_total)
                   VALUES (%s,%s,%s,%s)""",
                (batch_id, account, printed, parsed.get(account, 0)))

    execute("UPDATE staging_batch SET status='PARSED', parsed_at=now() WHERE batch_id=%s",
            (batch_id,))
    return {"batch_id": batch_id, "lines": len(staged.lines),
            "total": float(staged.total), "subtotals_checked": len(staged.subtotals),
            "warnings": staged.warnings, "skipped": staged.skipped}


@router.get("/{batch_id}/preview")
def preview(batch_id: str) -> dict:
    recon = one("SELECT * FROM v_staging_reconciliation WHERE batch_id=%s", (batch_id,))
    mismatches = query("""SELECT account, printed_total, parsed_total,
                                 parsed_total - printed_total AS variance
                            FROM staging_subtotal
                           WHERE batch_id=%s AND abs(parsed_total-printed_total) > 0.005
                           ORDER BY abs(parsed_total-printed_total) DESC LIMIT 25""",
                       (batch_id,))
    hints = query("""SELECT objective_hint, count(*) AS lines, sum(amount) AS amount
                       FROM staging_line
                      WHERE batch_id=%s AND objective_hint <> ''
                      GROUP BY objective_hint ORDER BY abs(sum(amount)) DESC""", (batch_id,))
    return {"reconciliation": recon, "mismatches": mismatches,
            "objective_hints": hints,
            "acceptable": bool(recon and recon["mismatches"] == 0)}


@router.post("/{batch_id}/accept")
def accept(batch_id: str, accepted_by: str) -> dict:
    """A trigger refuses this while any subtotal is off by more than half a
    cent, so the guarantee holds even if this handler is wrong."""
    execute("""UPDATE staging_batch
                  SET status='ACCEPTED', accepted_at=now(), accepted_by=%s
                WHERE batch_id=%s""", (accepted_by, batch_id))
    n = one("""
        WITH ins AS (
          INSERT INTO ledger_line (line_id, import_id, period, txn_date, account,
                                   payee, description, amount, statement, section,
                                   source_key, customer_job_hint)
          SELECT s.natural_key, b.batch_id, b.period, s.txn_date, s.account,
                 s.name, s.memo, s.amount, 'P&L', '', s.natural_key, s.objective_hint
            FROM staging_line s JOIN staging_batch b USING (batch_id)
           WHERE s.batch_id=%s
          ON CONFLICT (line_id) DO NOTHING
          RETURNING 1)
        SELECT count(*) AS n FROM ins""", (batch_id,))
    return {"batch_id": batch_id, "lines_promoted": n["n"] if n else 0}


@router.get("")
def list_batches(period: str = "2025") -> list[dict]:
    return query("""SELECT batch_id, report, original_name, status, byte_size,
                           uploaded_by, uploaded_at, accepted_at
                      FROM staging_batch WHERE period=%s
                     ORDER BY uploaded_at DESC""", (period,))
