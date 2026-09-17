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
from app.audit import note, record
from app.auth import Actor
from app import storage
from app.db import execute, one, query, transaction
from app.domain.qbo import (QBO_GENERAL_LEDGER, QBO_TIME_ACTIVITY,
                            parse_general_ledger, parse_profit_loss,
                            parse_time_activity, parse_balance_sheet)
from app.settings import settings

router = APIRouter(prefix="/imports", tags=["imports"],
                   dependencies=[Depends(require_reader)])


def _trail(actor, by: str, action: str, entity: str, entity_id: str,
           **kw) -> None:
    """The trail, from whoever is there. A person's act names their account
    and their session; the deployment's names itself and claims neither."""
    if actor is not None:
        record(actor, action, entity, entity_id, **kw)
    else:
        note(by, action, entity, entity_id, **kw)


def stage_file(raw: bytes, filename: str, report: str, period: str,
               by: str) -> dict:
    """Put a source file on the volume and open a staging batch for it.

    The body of `POST /upload`, lifted so that **the boot can transcribe the
    books without a person and without a socket.** `app/foundation.py` files
    the eighteen foundational documents at boot and read no row out of them;
    the ledger is one of those documents, and the only thing that kept it out
    was that this work lived inside an HTTP handler with an `Actor` in its
    signature.

    `by` is a **provenance label and not a user** — `deployment bootstrap`
    when the deployment transcribes its own shipped documents, the
    controller's display name when a person uploads one. Migration `087`
    defines that shape: a mechanism that names itself and carries no
    `actor_id` had no session to record. There is no account and nothing that
    can sign in.

    One implementation, two callers. The handler below adds the audit row,
    because a person uploading a file is an act; the boot writes the
    provenance column and no audit row claiming anybody.
    """
    sha = hashlib.sha256(raw).hexdigest()

    dup = one("""SELECT batch_id, status FROM staging_batch
                  WHERE period=%s AND report=%s AND sha256=%s""", (period, report, sha))
    if dup:
        return {"batch_id": str(dup["batch_id"]), "status": dup["status"],
                "sha256": sha, "deduplicated": True,
                "note": "This exact file has already been uploaded."}

    dest = storage.place(
        storage.source_path(period, report, sha, filename), raw)

    row = one("""INSERT INTO staging_batch
                   (period, report, profile_id, original_name, storage_uri,
                    sha256, byte_size, uploaded_by)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING batch_id""",
              (period, report, "qbo-gl-v1", filename, str(dest),
               sha, len(raw), by))
    return {"batch_id": str(row["batch_id"]), "status": "UPLOADED",
            "sha256": sha, "byte_size": len(raw), "deduplicated": False}


@router.post("/upload")
async def upload(file: UploadFile = File(...), report: str = "GENERAL_LEDGER",
                 period: str = "2025", uploaded_by: str = "unknown",
                 actor: Actor = Depends(require_controller)) -> dict:
    # Identity comes from the session. uploaded_by is a label for a file
    # received on someone else's behalf, not a claim about who did this.
    uploaded_by = actor.display_name or uploaded_by
    raw = await file.read()
    out = stage_file(raw, file.filename, report, period, uploaded_by)
    record(actor, "IMPORT_UPLOAD", "staging_batch", out["batch_id"],
           after={"report": report, "sha256": out["sha256"],
                  "byte_size": out.get("byte_size"),
                  "original_name": file.filename,
                  "deduplicated": out["deduplicated"]},
           reason=(f"{file.filename} — already on file" if out["deduplicated"]
                   else f"{file.filename} received"))
    return {k: v for k, v in out.items()
            if k in ("batch_id", "status", "sha256", "note")}


def parse_batch(batch_id: str, by: str = "deployment bootstrap",
                actor: Actor | None = None) -> dict:
    """Read a staged file and write what it says, without an actor.

    Lifted out of the handler for the same reason `stage_file` was: the boot
    transcribes the books and has nobody to be. The controls are unchanged
    and they are not in this function — the profit and loss must foot to net
    income, the balance sheet must balance and agree with the P&L's net
    income, and every printed subtotal must equal what sits under it, which a
    trigger enforces at accept.
    """
    b = one("SELECT * FROM staging_batch WHERE batch_id=%s", (batch_id,))
    if not b:
        raise HTTPException(404, "batch not found")
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
                        (by, batch_id))
            _trail(actor, by, "IMPORT_ACCEPT", "staging_batch", batch_id,
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
    execute("DELETE FROM staging_opening WHERE batch_id=%s", (batch_id,))

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
        if account in staged.unprinted_subtotals:
            # The export saved this total as a formula with no cached value.
            # Storing a zero here would let the accept gate compare against
            # nothing and pass; the warning below says so out loud instead.
            continue
        execute("""INSERT INTO staging_subtotal (batch_id,account,printed_total,parsed_total)
                   VALUES (%s,%s,%s,%s)""",
                (batch_id, account, printed, parsed.get(account, 0)))

    # Opening balances. Not transactions, and so not lines — but the only
    # thing that makes the balance sheet tieable to the ledger at all.
    for account, amount in staged.openings.items():
        execute("""INSERT INTO staging_opening (batch_id,account,amount)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (batch_id,account) DO UPDATE SET amount=EXCLUDED.amount""",
                (batch_id, account, amount))

    warnings = list(staged.warnings)
    if staged.unprinted_subtotals:
        warnings.append(
            f"{len(staged.unprinted_subtotals)} printed account total(s) carry "
            f"no figure in this export — the subtotal control cannot be "
            f"evaluated for them: "
            + ", ".join(sorted(staged.unprinted_subtotals)[:8]))

    execute("UPDATE staging_batch SET status='PARSED', parsed_at=now() WHERE batch_id=%s",
            (batch_id,))
    return {"batch_id": batch_id, "lines": len(staged.lines),
            "total": float(staged.total),
            "subtotals_checked": len(staged.subtotals) - len(staged.unprinted_subtotals),
            "subtotals_unprinted": len(staged.unprinted_subtotals),
            "openings": len(staged.openings),
            "warnings": warnings, "skipped": staged.skipped}


@router.post("/{batch_id}/parse")
def parse(batch_id: str, actor: Actor = Depends(require_controller)) -> dict:
    # A parse writes: it can replace every pl_account row for the period. That
    # is a change to the cost scope every classification is then measured in,
    # so it belongs on the record whatever its outcome — recorded before the
    # work, so a parse that raises is still on the trail.
    b = one("SELECT report, original_name FROM staging_batch WHERE batch_id=%s",
            (batch_id,))
    if not b:
        raise HTTPException(404, "batch not found")
    record(actor, "IMPORT_PARSE", "staging_batch", batch_id,
           after={"report": b["report"], "original_name": b["original_name"]},
           reason=f"parsing {b['original_name']}")
    return parse_batch(batch_id, actor.display_name, actor)


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


def promote_batch(batch_id: str, by: str,
                  actor: Actor | None = None) -> dict:
    """Promote a staged batch into the ledger.

    A trigger refuses this while any subtotal is off by more than half a
    cent, so the guarantee holds even if this function is wrong — and it is
    why the boot can call it. The control is in the schema, not in the
    handler, so a transcription done without a person is held to exactly the
    same standard as one a controller presses Accept on.

    `by` lands in `staging_batch.accepted_by` and `ledger_import.imported_by`,
    which is the permanent provenance record every ledger line points back
    to. It is a label and never an identity: `deployment bootstrap` when the
    deployment transcribes the export it ships, the controller's display name
    when a person promotes one.
    """
    accepted_by = by
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
            -- Match the qualified path first, and fall back to the leaf
            -- only where that leaf is unambiguous.
            --
            -- Matching on the leaf alone was wrong in a way that did not
            -- show: four leaves exist under both an income and an expense
            -- parent — Drive AM, Digital Engineering, DLA Grant, Youth
            -- Entrepreneurship — so 138 lines worth $1,570,174.17 took
            -- whichever section the join happened to reach first, and
            -- "Grant Expenses:Drive AM" was being read as revenue. The
            -- LEFT JOIN also matched twice per line; only ON CONFLICT kept
            -- the row count right.
            LEFT JOIN LATERAL (
              SELECT p2.section
                FROM pl_account p2
               WHERE p2.period = b.period
                 AND (p2.account = s.account
                      OR (p2.leaf = split_part(s.account, ':',
                            array_length(string_to_array(s.account, ':'), 1))
                          AND NOT EXISTS (
                            SELECT 1 FROM pl_account p3
                             WHERE p3.period = p2.period AND p3.leaf = p2.leaf
                               AND p3.account <> p2.account)))
               -- An exact path beats a leaf, always.
               ORDER BY (p2.account = s.account) DESC
               LIMIT 1) p ON true
           WHERE s.batch_id=%s
          ON CONFLICT (line_id) DO NOTHING
          RETURNING 1)
        SELECT count(*) AS n FROM ins""", (imp["import_id"], batch_id))

    # ON CONFLICT DO NOTHING makes re-accepting the same file harmless. It
    # also makes losing a line harmless-looking, which is worse: two staged
    # lines that hash alike promote as one and the count simply comes back
    # smaller. Count what actually landed and say so.
    landed = one("""SELECT count(*) AS n
                     FROM staging_line s
                     JOIN ledger_line l ON l.line_id = s.natural_key
                    WHERE s.batch_id = %s AND s.txn_date IS NOT NULL""", (batch_id,))
    staged_rows = one("""SELECT count(*) AS n FROM staging_line
                          WHERE batch_id = %s AND txn_date IS NOT NULL""", (batch_id,))
    if landed["n"] != staged_rows["n"]:
        lost = staged_rows["n"] - landed["n"]
        raise HTTPException(status_code=409, detail={
            "error": "PROMOTE_INCOMPLETE",
            "message": (f"{lost} staged line(s) did not reach the ledger. Two "
                        f"different lines are hashing to the same natural key; "
                        f"accepting would lose them silently."),
            "staged": staged_rows["n"], "promoted": landed["n"]})

    # Opening balances travel with the import they came from, so the balance
    # sheet tie can name its source.
    execute("""INSERT INTO gl_opening (period, account, import_id, amount)
               SELECT b.period, o.account, %s, o.amount
                 FROM staging_opening o JOIN staging_batch b USING (batch_id)
                WHERE o.batch_id = %s
               ON CONFLICT (period, account)
                 DO UPDATE SET amount = EXCLUDED.amount,
                               import_id = EXCLUDED.import_id""",
            (imp["import_id"], batch_id))

    # Only when nobody above will. A person promoting a file is an act and
    # the handler records it from the session; the boot has no session, so
    # the trail is written here and names the mechanism. Writing it in both
    # places would put two rows on one promote.
    if actor is None:
        note(by, "IMPORT_ACCEPT", "ledger_import", str(imp["import_id"]),
             after={"batch_id": batch_id,
                    "lines_promoted": n["n"] if n else 0,
                    "lines_in_ledger": landed["n"]},
             reason="accepted after every printed subtotal tied")
    return {"batch_id": batch_id, "import_id": str(imp["import_id"]),
            "lines_promoted": n["n"] if n else 0,
            "lines_in_ledger": landed["n"]}


@router.post("/{batch_id}/accept")
def accept(batch_id: str, accepted_by: str = "",
           actor: Actor = Depends(require_controller)) -> dict:
    """Identity comes from the session. ``accepted_by`` is a label, the way
    it is on ``upload`` — and this was the one route of nine that did not say
    so, while the screen sent the literal string ``tom`` in the query string.
    It reached the permanent provenance record every ledger line points back
    to: who promoted the general ledger was whatever the URL said.
    """
    accepted_by = actor.display_name or accepted_by
    out = promote_batch(batch_id, accepted_by)
    record(actor, "IMPORT_ACCEPT", "ledger_import", out["import_id"],
           after={"batch_id": batch_id,
                  "lines_promoted": out.get("lines_promoted", 0)},
           reason="accepted after every printed subtotal tied")
    return out


@router.get("")
def list_batches(period: str = "2025") -> list[dict]:
    return query("""SELECT batch_id, report, original_name, status, byte_size,
                           uploaded_by, uploaded_at, accepted_at
                      FROM staging_batch WHERE period=%s
                     ORDER BY uploaded_at DESC""", (period,))
