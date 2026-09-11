"""QuickBooks import: upload, parse under a profile, preview, accept.

Two-phase commit. Nothing reaches ledger_line until the account subtotals QBO
printed in its own report reconcile against what we parsed.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import psycopg

from fastapi import Depends, APIRouter, File, HTTPException, UploadFile

from app.auth import require_controller, require_reader
from app.audit import record
from app.auth import Actor
from app.db import execute, one, query, transaction
from app.domain.qbo import (QBO_GENERAL_LEDGER, QBO_TIME_ACTIVITY,
                            parse_general_ledger, parse_profit_loss,
                            parse_time_activity, parse_balance_sheet)
from app.settings import settings

router = APIRouter(prefix="/imports", tags=["imports"],
                   dependencies=[Depends(require_reader)])
STORAGE = Path(settings.storage_dir)


@router.post("/upload")
async def upload(file: UploadFile = File(...), report: str = "GENERAL_LEDGER",
                 period: str = "2025", uploaded_by: str = "unknown",
                 actor: Actor = Depends(require_controller)) -> dict:
    # Identity comes from the session. uploaded_by is a label for a file
    # received on someone else's behalf, not a claim about who did this.
    uploaded_by = actor.display_name or uploaded_by
    raw = await file.read()
    sha = hashlib.sha256(raw).hexdigest()

    dup = one("""SELECT batch_id, status FROM staging_batch
                  WHERE period=%s AND report=%s AND sha256=%s""", (period, report, sha))
    if dup:
        record(actor, "IMPORT_UPLOAD", "staging_batch", str(dup["batch_id"]),
               after={"report": report, "sha256": sha, "deduplicated": True},
               reason=f"{file.filename} — already on file")
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
    record(actor, "IMPORT_UPLOAD", "staging_batch", str(row["batch_id"]),
           after={"report": report, "sha256": sha, "byte_size": len(raw),
                  "original_name": file.filename},
           reason=f"{file.filename} received")
    return {"batch_id": str(row["batch_id"]), "status": "UPLOADED", "sha256": sha}


@router.post("/{batch_id}/parse")
def parse(batch_id: str, actor: Actor = Depends(require_controller)) -> dict:
    b = one("SELECT * FROM staging_batch WHERE batch_id=%s", (batch_id,))
    if not b:
        raise HTTPException(404, "batch not found")
    # A parse writes: it can replace every pl_account row for the period. That
    # is a change to the cost scope every classification is then measured in,
    # so it belongs on the record whatever its outcome.
    record(actor, "IMPORT_PARSE", "staging_batch", batch_id,
           after={"report": b["report"], "original_name": b["original_name"]},
           reason=f"parsing {b['original_name']}")
    path = Path(b["storage_uri"])

    if b["report"] == "PROFIT_LOSS":
        pl = parse_profit_loss(path, sha256=b["sha256"])
        variance = pl.check_net_income()
        if abs(variance) > Decimal("0.01"):
            raise HTTPException(409, {
                "error": "PL_DOES_NOT_FOOT",
                "message": f"Sections do not foot to net income; off by {variance}.",
            })
        execute("DELETE FROM pl_account WHERE period=%s", (b["period"],))
        for account, (section, amount) in pl.accounts.items():
            execute("""INSERT INTO pl_account (period, account, leaf, section, amount)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (period, account) DO UPDATE
                         SET section = EXCLUDED.section, amount = EXCLUDED.amount""",
                    (b["period"], account, account.split(":")[-1], section, amount))
        execute("UPDATE staging_batch SET status='ACCEPTED', parsed_at=now(), "
                "accepted_at=now(), accepted_by='parser' WHERE batch_id=%s", (batch_id,))
        return {"batch_id": batch_id, "kind": "PROFIT_LOSS",
                "accounts": len(pl.accounts),
                "sections": {k: str(v) for k, v in pl.section_totals.items()},
                "net_income": str(pl.net_income), "variance": str(variance)}

    if b["report"] == "BALANCE_SHEET":
        bs = parse_balance_sheet(path, sha256=b["sha256"])
        balance = bs.check_balance()
        if abs(balance) > Decimal("0.01"):
            raise HTTPException(409, {
                "error": "SHEET_DOES_NOT_BALANCE",
                "message": f"Assets less liabilities and equity is {balance}. "
                           f"A balance sheet that does not balance is not an "
                           f"import problem, it is an export taken mid-post.",
            })
        failing = bs.failing_subtotals()
        if failing:
            raise HTTPException(409, {
                "error": "BS_SUBTOTALS_DO_NOT_FOOT",
                "message": f"{len(failing)} printed subtotal(s) disagree with "
                           f"the accounts beneath them.",
                "first": [{"account": f[0], "printed": str(f[1]),
                           "derived": str(f[2]), "variance": str(f[3])}
                          for f in failing[:5]],
            })

        # The cross-statement tie. It can only run once the P&L is in, which
        # is the right order anyway — the P&L defines cost scope.
        pl_net = one("""SELECT COALESCE(sum(amount) FILTER (WHERE section='Income'), 0)
                             - COALESCE(sum(amount) FILTER (WHERE section='Expense'), 0)
                             - COALESCE(sum(amount) FILTER (WHERE section='COGS'), 0)
                             + COALESCE(sum(amount) FILTER (WHERE section='Other Income'), 0)
                               AS net
                          FROM pl_account WHERE period = %s""", (b["period"],))
        net_variance = None
        if pl_net and pl_net["net"]:
            net_variance = bs.check_net_income(Decimal(str(pl_net["net"])))
            if abs(net_variance) > Decimal("0.01"):
                raise HTTPException(409, {
                    "error": "NET_INCOME_DISAGREES",
                    "message": f"The balance sheet carries net income of "
                               f"{bs.net_income} and the profit and loss "
                               f"derives {pl_net['net']}. Two exports that "
                               f"disagree are two different moments in the "
                               f"same books; take both again from the same "
                               f"point.",
                    "variance": str(net_variance),
                })

        with transaction() as cur:
            cur.execute("DELETE FROM bs_account WHERE period=%s", (b["period"],))
            for account, (side, amount) in bs.accounts.items():
                cur.execute("""INSERT INTO bs_account
                                 (period, account, leaf, side, amount,
                                  is_rollup, depth)
                               VALUES (%s,%s,%s,%s,%s,false,%s)""",
                            (b["period"], account, account.split(":")[-1],
                             side or "ASSET", amount, account.count(":")))
            for account, (side, amount) in bs.rollups.items():
                cur.execute("""INSERT INTO bs_account
                                 (period, account, leaf, side, amount,
                                  is_rollup, depth)
                               VALUES (%s,%s,%s,%s,%s,true,%s)""",
                            (b["period"], account, account.split(":")[-1],
                             side or "ASSET", amount, account.count(":")))
            cur.execute("""UPDATE staging_batch
                              SET status='ACCEPTED', parsed_at=now(),
                                  accepted_at=now(), accepted_by=%s
                            WHERE batch_id=%s""",
                        (actor.display_name, batch_id))
            record(actor, "IMPORT_ACCEPT", "staging_batch", batch_id,
                   after={"report": "BALANCE_SHEET",
                          "accounts": len(bs.accounts),
                          "assets": str(bs.assets),
                          "net_income": str(bs.net_income)},
                   reason=f"balance sheet accepted — balances to "
                          f"{balance}, net income ties", cursor=cur)

        return {"batch_id": batch_id, "kind": "BALANCE_SHEET",
                "accounts": len(bs.accounts), "rollups": len(bs.rollups),
                "assets": str(bs.assets), "liabilities": str(bs.liabilities),
                "equity": str(bs.equity), "balance_variance": str(balance),
                "net_income": str(bs.net_income),
                "net_income_variance": (str(net_variance)
                                        if net_variance is not None else None),
                "fixed_assets": str(bs.fixed_assets),
                "warnings": bs.warnings}

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
def accept(batch_id: str, accepted_by: str = "",
           actor: Actor = Depends(require_controller)) -> dict:
    """A trigger refuses this while any subtotal is off by more than half a
    cent, so the guarantee holds even if this handler is wrong."""
    try:
        execute("""UPDATE staging_batch
                      SET status='ACCEPTED', accepted_at=now(), accepted_by=%s
                    WHERE batch_id=%s""", (accepted_by, batch_id))
    except psycopg.errors.RaiseException as exc:
        # The accept gate declining an import is an expected outcome, not a
        # server fault. Surface what failed to tie so the controller can act
        # on it instead of reading "Internal Server Error".
        mismatches = query(
            """SELECT account, printed_total, parsed_total,
                      (parsed_total - printed_total) AS variance
                 FROM staging_subtotal
                WHERE batch_id=%s AND abs(parsed_total - printed_total) > 0.005
                ORDER BY abs(parsed_total - printed_total) DESC LIMIT 25""",
            (batch_id,))
        raise HTTPException(status_code=409, detail={
            "error": "ACCEPT_GATE",
            "message": str(exc).split("\n")[0].strip(),
            "mismatches": mismatches,
        }) from exc
    # A staging batch becomes a ledger_import on acceptance. ledger_line
    # references that, not the batch: staging is scratch space, the import is
    # the permanent provenance record every ledger line points back to.
    # UNIQUE (period, sha256) makes re-accepting the same file a no-op.
    imp = one("""
        INSERT INTO ledger_import (period, source_name, sha256, row_count, imported_by)
        SELECT b.period, b.original_name, b.sha256,
               (SELECT count(*) FROM staging_line WHERE batch_id = b.batch_id),
               %s
          FROM staging_batch b
         WHERE b.batch_id = %s
        ON CONFLICT (period, sha256)
          DO UPDATE SET source_name = EXCLUDED.source_name
        RETURNING import_id""", (accepted_by, batch_id))
    if not imp:
        raise HTTPException(404, "batch not found")

    n = one("""
        WITH ins AS (
          INSERT INTO ledger_line (line_id, import_id, period, txn_date, account,
                                   payee, description, amount, statement, section,
                                   source_key, customer_job_hint)
          SELECT s.natural_key, %s, b.period, s.txn_date, s.account,
                 s.name, s.memo, s.amount,
                 CASE WHEN p.section IS NULL THEN 'BALANCE_SHEET' ELSE 'P&L' END,
                 coalesce(p.section, ''), s.natural_key, s.objective_hint
            FROM staging_line s
            JOIN staging_batch b USING (batch_id)
            LEFT JOIN pl_account p
                   ON p.period = b.period
                  AND p.leaf = split_part(s.account, ':',
                        array_length(string_to_array(s.account, ':'), 1))
           WHERE s.batch_id=%s
          ON CONFLICT (line_id) DO NOTHING
          RETURNING 1)
        SELECT count(*) AS n FROM ins""", (imp["import_id"], batch_id))
    record(actor, "IMPORT_ACCEPT", "ledger_import", str(imp["import_id"]),
           after={"batch_id": batch_id,
                  "lines_promoted": n["n"] if n else 0},
           reason="accepted after every printed subtotal tied")
    return {"batch_id": batch_id, "import_id": str(imp["import_id"]),
            "lines_promoted": n["n"] if n else 0}


@router.get("")
def list_batches(period: str = "2025") -> list[dict]:
    return query("""SELECT batch_id, report, original_name, status, byte_size,
                           uploaded_by, uploaded_at, accepted_at
                      FROM staging_batch WHERE period=%s
                     ORDER BY uploaded_at DESC""", (period,))
