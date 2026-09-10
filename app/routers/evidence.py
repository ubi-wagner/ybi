"""Documents and notes.

Content addressed: the same lease attached to forty lines is stored once.
Attachment is polymorphic so a document can support a line, a decision, a
carve-out, an award or an invoice without a table per relationship.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Depends, APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.auth import require_controller, require_reader
from app.audit import record
from app.auth import Actor
from app.db import execute, one, query
from app.settings import settings

router = APIRouter(prefix="/evidence", tags=["evidence"],
                   dependencies=[Depends(require_reader)])
STORAGE = Path(settings.storage_dir) / "evidence"


class NoteIn(BaseModel):
    target_type: str
    target_id: str
    body: str
    author: str
    is_workpaper: bool = False


@router.post("/upload")
async def upload(file: UploadFile = File(...), kind: str = Form("document"),
                 period: str = Form("2025"), uploaded_by: str = Form("unknown"),
                 target_type: str | None = Form(None),
                 target_id: str | None = Form(None),
                 relevance: str = Form(""),
                 actor: Actor = Depends(require_controller)) -> dict:
    # Identity comes from the session, not the form. uploaded_by is kept for
    # the case where a document is received on someone else's behalf, but it
    # is a label, not a claim about who did this.
    uploaded_by = actor.display_name or uploaded_by
    raw = await file.read()
    sha = hashlib.sha256(raw).hexdigest()

    existing = one("SELECT evidence_id FROM evidence WHERE sha256=%s", (sha,))
    if existing:
        eid = existing["evidence_id"]
    else:
        STORAGE.mkdir(parents=True, exist_ok=True)
        dest = STORAGE / f"{sha[:16]}_{file.filename}"
        dest.write_bytes(raw)
        eid = f"EV-{sha[:12]}"
        execute("""INSERT INTO evidence (evidence_id,period,kind,uri,sha256,
                                         received_from,byte_size,mime_type,ingest_channel)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'UPLOAD')""",
                (eid, period, kind, str(dest), sha, uploaded_by,
                 len(raw), file.content_type or "application/octet-stream"))

    attached = 0
    if target_type and target_id:
        if target_type == "LEDGER_GROUP":
            # The controller works in account/payee groups, but attachment is
            # per line: that is what the evidence-grade gate reads, and it is
            # what keeps a document tied to the specific dollars it supports
            # when a group is later split. One document, many attachments.
            account, _, payee = target_id.partition("\x1f")
            lines = query("""SELECT line_id FROM ledger_line
                              WHERE period=%s AND account=%s
                                AND coalesce(payee,'')=%s""",
                          (period, account, payee))
            for line in lines:
                execute("""INSERT INTO attachment (evidence_id,target_type,target_id,
                                                   relevance,attached_by)
                           VALUES (%s,'LEDGER_LINE',%s,%s,%s)
                           ON CONFLICT DO NOTHING""",
                        (eid, line["line_id"], relevance, uploaded_by))
            attached = len(lines)
        else:
            execute("""INSERT INTO attachment (evidence_id,target_type,target_id,
                                               relevance,attached_by)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (eid, target_type, target_id, relevance, uploaded_by))
            attached = 1

    record(actor, "EVIDENCE_UPLOAD", "evidence", eid,
           after={"kind": kind, "sha256": sha, "target_type": target_type,
                  "target_id": target_id, "attached_to": attached},
           reason=relevance)
    return {"evidence_id": eid, "sha256": sha, "deduplicated": bool(existing),
            "attached_to": attached}


@router.get("/for/{target_type}/{target_id}")
def for_target(target_type: str, target_id: str) -> dict:
    return {
        "documents": query("""SELECT e.evidence_id,e.kind,e.uri,e.byte_size,e.mime_type,
                                     a.relevance,a.attached_by,a.attached_at
                                FROM attachment a JOIN evidence e USING (evidence_id)
                               WHERE a.target_type=%s AND a.target_id=%s
                                 AND a.detached_at IS NULL
                               ORDER BY a.attached_at DESC""", (target_type, target_id)),
        "notes": query("""SELECT note_id,body,author,created_at,is_workpaper,resolved_at
                            FROM note WHERE target_type=%s AND target_id=%s
                           ORDER BY created_at""", (target_type, target_id)),
    }


@router.post("/note")
def add_note(body: NoteIn,
             actor: Actor = Depends(require_controller)) -> dict:
    r = one("""INSERT INTO note (target_type,target_id,body,author,is_workpaper)
               VALUES (%s,%s,%s,%s,%s) RETURNING note_id""",
            (body.target_type, body.target_id, body.body,
             actor.display_name, body.is_workpaper))
    record(actor, "NOTE", body.target_type, body.target_id,
           after={"is_workpaper": body.is_workpaper}, reason=body.body[:400])
    return {"note_id": str(r["note_id"])}


@router.get("/coverage")
def coverage(period: str = "2025") -> list[dict]:
    """Documented dollars by pool — the number an auditor asks for, and the
    one that tells Tom when he can stop."""
    return query("SELECT * FROM v_evidence_coverage WHERE period=%s ORDER BY pool", (period,))
