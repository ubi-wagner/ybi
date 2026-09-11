"""My documents — the module everybody in the organisation gets.

The person holding the receipt is the person who was there. Routing every
document through the controller is how a receipt ends up in a drawer, so
anybody signed in can put one into the system: a receipt, an invoice, a
project plan, a photograph of a nameplate, a comparable lease.

What they cannot do is say what it proves. Uploading is a contribution;
attaching a document to a cost and grading the support is a judgment, and it
stays with whoever holds the portfolio that judgment belongs to. An uploaded,
unattached document is therefore a queue rather than a loose end — which is
what makes it safe to open the door this wide.

The same door serves 2025 and 2026 onward. A document is a document; which
period's record it ends up supporting is decided when somebody attaches it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import (Actor, Portfolio, current_actor, require_office,
                      require_own_writes)
from app.db import execute, one, query
from app.settings import settings

router = APIRouter(prefix="/documents", tags=["documents"])

# The same place every other uploader writes, which on Railway is a mounted
# volume. This was a hardcoded "var/evidence" — a path inside the container
# filesystem, which Railway discards on every deploy. Everyone in the
# organisation uploads through this route, so every receipt, invoice and
# project plan they sent in would have disappeared on the next push while
# v_evidence_inbox went on listing them. The loss would have been silent
# until somebody asked for a document.
STORAGE = Path(settings.storage_dir) / "evidence"

#: A cap that stops a phone photograph library from becoming the ledger's
#: storage tier, without being so tight that a scanned lease is refused.
MAX_BYTES = 40 * 1024 * 1024


@router.post("/upload")
async def upload(file: UploadFile = File(...),
                 kind: str = Form("document"),
                 period: str = Form(""),
                 note: str = Form(""),
                 suggested_for: str = Form(""),
                 actor: Actor = Depends(require_own_writes)) -> dict:
    """Put a document in. Anybody signed in.

    Nothing is attached to anything here, deliberately. The uploader says in
    their own words what it relates to; somebody with the portfolio decides
    what it supports.
    """
    period = period or settings.period
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "That file is empty.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            413, f"That file is {len(raw) / 1e6:.0f} MB; the limit is "
                 f"{MAX_BYTES // 1024 // 1024} MB. Send the pages that matter "
                 f"rather than the whole scan.")

    sha = hashlib.sha256(raw).hexdigest()
    existing = one("""SELECT e.evidence_id, e.uploaded_by, a.display_name
                        FROM evidence e LEFT JOIN actor a
                          ON a.actor_id = e.uploaded_by
                       WHERE e.sha256 = %s""", (sha,))
    if existing:
        # Content-addressed: the same document sent twice is one document.
        # Say who already sent it, so the second person knows it landed
        # rather than wondering whether it did.
        record(actor, "DOCUMENT_UPLOAD", "evidence", existing["evidence_id"],
               after={"duplicate_of": existing["evidence_id"],
                      "sha256": sha},
               reason=note or "already on file")
        return {"evidence_id": existing["evidence_id"], "deduplicated": True,
                "already_uploaded_by": existing["display_name"],
                "message": ("That document is already on file"
                            + (f", sent in by {existing['display_name']}."
                               if existing["display_name"] else "."))}

    STORAGE.mkdir(parents=True, exist_ok=True)
    safe = Path(file.filename or "document").name
    dest = STORAGE / f"{sha[:16]}_{safe}"
    dest.write_bytes(raw)
    eid = f"EV-{sha[:12]}"
    execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                     received_from, byte_size, mime_type,
                                     ingest_channel, uploaded_by, note,
                                     suggested_for)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'UPLOAD',%s,%s,%s)""",
            (eid, period, kind, str(dest), sha, actor.display_name, len(raw),
             file.content_type or "application/octet-stream",
             actor.actor_id, note, suggested_for))
    record(actor, "DOCUMENT_UPLOAD", "evidence", eid,
           after={"kind": kind, "filename": safe, "bytes": len(raw),
                  "suggested_for": suggested_for},
           reason=note or "uploaded")
    return {"evidence_id": eid, "deduplicated": False,
            "filename": safe, "bytes": len(raw)}


@router.get("/mine")
def mine(actor: Actor = Depends(current_actor)) -> dict:
    """What I have sent in, and what became of it.

    The second half matters more than the first. Somebody who uploads three
    receipts and never learns whether they were used stops uploading.
    """
    rows = query("""SELECT evidence_id, period, kind, received_at, byte_size,
                           mime_type, note, suggested_for, attachments,
                           is_attached, doc_date, doc_amount, vendor_name
                      FROM v_evidence_inbox
                     WHERE uploaded_by = %s
                     ORDER BY received_at DESC""", (actor.actor_id,))
    return {"documents": rows,
            "uploaded": len(rows),
            "in_use": sum(1 for r in rows if r["is_attached"]),
            "waiting": sum(1 for r in rows if not r["is_attached"])}


@router.get("/{evidence_id}/file")
def download(evidence_id: str, actor: Actor = Depends(current_actor)):
    """Hand back a document.

    Your own, always. Anybody else's only if you can read the record — an
    employee's receipt is not public to the organisation just because it was
    sent to the finance system.
    """
    row = one("""SELECT uri, mime_type, uploaded_by
                   FROM evidence WHERE evidence_id = %s""", (evidence_id,))
    if not row:
        raise HTTPException(404, "No such document.")
    if str(row["uploaded_by"]) != actor.actor_id and not actor.can_read:
        raise HTTPException(403, "That is not your document.")
    path = Path(row["uri"])
    if not path.exists():
        raise HTTPException(410, "The file is no longer in storage.")
    record(actor, "EVIDENCE_DOWNLOAD", "evidence", evidence_id,
           reason="document retrieved")
    return FileResponse(path, media_type=row["mime_type"] or
                        "application/octet-stream", filename=path.name)


# ── The other side of the door ───────────────────────────────────────

@router.get("/inbox")
def inbox(period: str | None = None, unattached_only: bool = True,
          actor: Actor = Depends(require_office)) -> dict:
    """What people have sent in that nobody has yet put to work."""
    period = period or settings.period
    where = "AND NOT is_attached" if unattached_only else ""
    rows = query(f"""SELECT * FROM v_evidence_inbox
                      WHERE period = %s {where}
                      ORDER BY received_at DESC""", (period,))
    return {"period": period, "documents": rows, "waiting": len(rows)}


class AttachIn(BaseModel):
    evidence_id: str
    target_type: str
    target_id: str
    relevance: str = Field(min_length=3)


@router.post("/attach", status_code=201)
def attach(body: AttachIn, actor: Actor = Depends(require_office)) -> dict:
    """Say what a document supports.

    The judgment the upload deliberately withheld. It is recorded against the
    person making it, with their words for why — an attachment with no stated
    relevance is a document filed near a number, not evidence for it.
    """
    if not one("SELECT 1 FROM evidence WHERE evidence_id = %s",
               (body.evidence_id,)):
        raise HTTPException(404, "No such document.")
    execute("""INSERT INTO attachment (evidence_id, target_type, target_id,
                                       relevance, attached_by)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (evidence_id, target_type, target_id)
                 DO UPDATE SET relevance = EXCLUDED.relevance,
                               detached_at = NULL""",
            (body.evidence_id, body.target_type, body.target_id,
             body.relevance, actor.display_name))
    record(actor, "EVIDENCE_ATTACH", body.target_type, body.target_id,
           after={"evidence_id": body.evidence_id},
           reason=body.relevance)
    return {"evidence_id": body.evidence_id, "target_id": body.target_id}
