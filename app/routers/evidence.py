"""Documents and notes.

Content addressed: the same lease attached to forty lines is stored once.
Attachment is polymorphic so a document can support a line, a decision, a
carve-out, an award or an invoice without a table per relationship.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Depends, APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_office, require_reader
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
                 actor: Actor = Depends(require_office)) -> dict:
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
                                         received_from,byte_size,mime_type,
                                         ingest_channel,uploaded_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'UPLOAD',%s)""",
                (eid, period, kind, str(dest), sha, uploaded_by,
                 len(raw), file.content_type or "application/octet-stream",
                 actor.actor_id))

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


@router.get("")
def register(period: str = "2025") -> list[dict]:
    """The document register.

    Everything received for the period, what it supports and how many places
    it supports. Available to any reader: an auditor who has to ask the
    controller for a copy of a document is an auditor being managed.
    """
    return query("""
        SELECT e.evidence_id, e.kind, e.uri, e.sha256, e.byte_size, e.mime_type,
               e.received_from, e.received_at, e.ingest_channel,
               (SELECT count(*) FROM attachment a
                 WHERE a.evidence_id = e.evidence_id
                   AND a.detached_at IS NULL)                  AS attachments,
               (SELECT max(a.relevance) FROM attachment a
                 WHERE a.evidence_id = e.evidence_id
                   AND a.detached_at IS NULL)                  AS relevance,
               (SELECT count(DISTINCT l.account) FROM attachment a
                  JOIN ledger_line l ON l.line_id::text = a.target_id
                 WHERE a.evidence_id = e.evidence_id
                   AND a.target_type = 'LEDGER_LINE'
                   AND a.detached_at IS NULL)                  AS accounts,
               (SELECT COALESCE(sum(abs(l.amount)), 0) FROM attachment a
                  JOIN ledger_line l ON l.line_id::text = a.target_id
                 WHERE a.evidence_id = e.evidence_id
                   AND a.target_type = 'LEDGER_LINE'
                   AND a.detached_at IS NULL)                  AS supported_amount
          FROM evidence e WHERE e.period = %s
         ORDER BY e.received_at DESC""", (period,))


@router.get("/{evidence_id}/file")
def download(evidence_id: str, actor: Actor = Depends(require_reader)):
    """Hand back the document itself.

    A register that lists a lease but cannot produce it is a claim, not
    evidence. Reading is logged like everything else — the record shows who
    looked at what, which is the auditor's side of the same guarantee.
    """
    row = one("""SELECT uri, mime_type, kind, sha256 FROM evidence
                  WHERE evidence_id = %s""", (evidence_id,))
    if not row:
        raise HTTPException(404, "no such document")
    path = Path(row["uri"])
    if not path.exists():
        raise HTTPException(410, "the file behind this record is missing")

    record(actor, "EVIDENCE_DOWNLOAD", "evidence", evidence_id,
           after={"sha256": row["sha256"]},
           reason=f"{row['kind']} retrieved")
    return FileResponse(path, filename=path.name.split("_", 1)[-1],
                        media_type=row["mime_type"] or "application/octet-stream")


@router.get("/group")
def for_group(group_key: str, period: str = "2025") -> dict:
    """Everything hanging off one account/payee group.

    Documents attach per line — that is what the evidence gate reads — but
    the controller works in groups, so the lookup has to fan back in. Notes
    are recorded against the group itself, because a note is about the
    judgment, not about one of the eighty-five rows underneath it.
    """
    account, _, payee = group_key.partition("\x1f")
    return {
        "documents": query("""
            SELECT DISTINCT e.evidence_id, e.kind, e.byte_size, e.mime_type,
                   e.uri, a.relevance, a.attached_by, max(a.attached_at) AS attached_at,
                   count(*) AS lines
              FROM attachment a
              JOIN evidence e USING (evidence_id)
              JOIN ledger_line l ON l.line_id::text = a.target_id
             WHERE a.target_type = 'LEDGER_LINE' AND a.detached_at IS NULL
               AND l.period = %s AND l.account = %s
               AND coalesce(l.payee, '') = %s
             GROUP BY e.evidence_id, e.kind, e.byte_size, e.mime_type, e.uri,
                      a.relevance, a.attached_by
             ORDER BY max(a.attached_at) DESC""", (period, account, payee)),
        "notes": query("""SELECT note_id, body, author, created_at, is_workpaper
                            FROM note
                           WHERE target_type = 'LEDGER_GROUP' AND target_id = %s
                           ORDER BY created_at""", (group_key,)),
    }


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
             actor: Actor = Depends(require_office)) -> dict:
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
