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
                      require_own_writes, require_reader)
from app import storage
from app.db import execute, one, query
from app.settings import settings

router = APIRouter(prefix="/documents", tags=["documents"])


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

    safe = Path(file.filename or "document").name
    # What it is, read from the bytes rather than from what the client said
    # it was. A content type on the way in is a claim the uploader makes, and
    # the library decides whether to show a document in the page from this
    # column — so a claim is exactly the wrong thing to keep.
    mime = storage.sniff_type(raw, safe)
    dest = storage.place(
        storage.evidence_path(period, kind, sha, safe), raw)
    eid = f"EV-{sha[:12]}"
    execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                     received_from, byte_size, mime_type,
                                     ingest_channel, uploaded_by, note,
                                     suggested_for, filename)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'UPLOAD',%s,%s,%s,%s)""",
            (eid, period, kind, str(dest), sha, actor.display_name, len(raw),
             mime, actor.actor_id, note, suggested_for, safe))
    record(actor, "DOCUMENT_UPLOAD", "evidence", eid,
           after={"kind": kind, "filename": safe, "bytes": len(raw),
                  "suggested_for": suggested_for},
           reason=note or "uploaded")
    return {"evidence_id": eid, "deduplicated": False,
            "filename": safe, "bytes": len(raw), "mime_type": mime}


@router.get("/mine")
def mine(actor: Actor = Depends(current_actor)) -> dict:
    """What I have sent in, and what became of it.

    The second half matters more than the first. Somebody who uploads three
    receipts and never learns whether they were used stops uploading.
    """
    # Reads the library view rather than the inbox one for the two columns
    # the inbox has no use for: what the file was called, and whether it can
    # be shown in the page. Same rows either way — this is your own corner of
    # the same shelf, not a second copy of it.
    rows = query("""SELECT evidence_id, period, kind, filename, received_at,
                           byte_size, mime_type, note, suggested_for,
                           attachments, is_attached, inline_safe, doc_date,
                           doc_amount, vendor_name
                      FROM v_document_library
                     WHERE uploaded_by = %s
                     ORDER BY received_at DESC""", (actor.actor_id,))
    return {"documents": rows,
            "uploaded": len(rows),
            "in_use": sum(1 for r in rows if r["is_attached"]),
            "waiting": sum(1 for r in rows if not r["is_attached"])}


#: The types a browser renders without running anything the uploader wrote.
#: Everybody signed in may upload, so an inline render on this origin is a
#: door held open by whoever sends a file in — `text/html` inline would be a
#: script running as the controller, on a system whose entire claim is that
#: the controller's judgments are their own. The list lives in
#: `v_document_library.inline_safe` as well; this constant is the same set,
#: kept here so the handler can decide without a second query, and
#: `tests/test_document_access.py` fails if the two ever disagree.
INLINE_SAFE = frozenset({
    "application/pdf",
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "text/plain", "text/csv",
})


@router.get("/{evidence_id}/file")
def download(evidence_id: str, inline: bool = False,
             actor: Actor = Depends(current_actor)):
    """Hand back a document, to read here or to keep.

    Your own, always. Anybody else's only if you can read the record — an
    employee's receipt is not public to the organisation just because it was
    sent to the finance system.

    `?inline=1` asks for it in the page rather than in a downloads folder,
    and is granted only for the types on `INLINE_SAFE`. Anything else comes
    back as an attachment however it is asked for, including anything
    unrecognised: an uploader who mislabels a file gets a download, not a
    decision made in their favour.
    """
    row = one("""SELECT uri, mime_type, uploaded_by,
                        coalesce(filename, '') AS filename
                   FROM evidence WHERE evidence_id = %s""", (evidence_id,))
    if not row:
        raise HTTPException(404, "No such document.")
    if str(row["uploaded_by"]) != actor.actor_id and not actor.can_read:
        raise HTTPException(403, "That is not your document.")
    path = Path(row["uri"])
    if not path.exists():
        raise HTTPException(410, "The file is no longer in storage.")

    declared = (row["mime_type"] or "application/octet-stream").split(";")[0]
    declared = declared.strip().lower()
    shown = inline and declared in INLINE_SAFE

    # Reading a document and taking a copy of it are different acts and the
    # trail should not call them the same thing. An auditor who opened nine
    # leases in a panel and downloaded one has done one thing worth asking
    # about, and the register should say which.
    record(actor, "EVIDENCE_VIEW" if shown else "EVIDENCE_DOWNLOAD",
           "evidence", evidence_id,
           reason="read in the page" if shown else "copy taken")

    name = row["filename"] or path.name
    response = FileResponse(
        path,
        media_type=declared if shown else "application/octet-stream",
        # FileResponse only sets `attachment` when a filename is given, so
        # the inline case sets the header itself rather than going without
        # a name — a panel with no title is a worse document than a file.
        filename=None if shown else name)
    if shown:
        response.headers["Content-Disposition"] = (
            f'inline; filename="{_header_safe(name)}"')
    # A content type is a claim the uploader made, not a fact about the
    # bytes. Refusing to sniff past it is what keeps the allowlist an
    # allowlist; the sandbox is the second lock, in case a type on the list
    # grows a way to execute that it does not have today.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
        "object-src 'none'; sandbox")
    return response


def _header_safe(name: str) -> str:
    """A filename fit for a header.

    The name is whatever the uploader called the file. A quote or a newline
    in it would end the header early and let the rest be read as another
    one, so both go; everything outside Latin-1 goes too, because a header
    is Latin-1 and a browser handed anything else may drop the whole field.
    """
    cleaned = "".join(c for c in name if c.isprintable() and c not in '"\\')
    cleaned = cleaned.encode("latin-1", "ignore").decode("latin-1").strip()
    return cleaned or "document"


# ── The library ──────────────────────────────────────────────────────

@router.get("/library")
def library(q: str = "", period: str = "", kind: str = "",
            attached: str = "", limit: int = 500,
            actor: Actor = Depends(require_reader)) -> dict:
    """Every document in the record, for the people entitled to read it.

    `/mine` answers "what did I send in" and the inbox answers "what has
    nobody filed yet". Neither answers the question an auditor actually
    arrives with, which is "show me the lease". This does.

    Who: `require_reader` — the controller, the people holding CONTROLLER
    rank alongside them for this engagement, the auditor, the organisation's
    administrator, and anyone carrying a recorded `record_access` grant. It
    is deliberately the same gate as the review screens rather than a new
    one: reading the cost record is one permission, and a document is part
    of the cost record.

    Every column here is descriptive. Nothing says where a file sits on
    disk — a path is derived from the row and never travels the other way,
    and it is nobody's business outside `storage.py` in any case.
    """
    where = ["1=1"]
    args: list[object] = []
    if period:
        where.append("period = %s")
        args.append(period)
    if kind:
        where.append("kind = %s")
        args.append(kind)
    if attached == "yes":
        where.append("is_attached")
    elif attached == "no":
        where.append("NOT is_attached")
    if q.strip():
        # One box over the fields somebody would actually remember: what it
        # was called, what it was said to relate to, who sent it, the vendor
        # on it, and the identifier itself — because an auditor working from
        # a workpaper has the identifier and nothing else.
        where.append("""(filename ILIKE %s OR suggested_for ILIKE %s
                         OR note ILIKE %s OR coalesce(vendor_name,'') ILIKE %s
                         OR coalesce(uploaded_by_name,'') ILIKE %s
                         OR evidence_id ILIKE %s)""")
        args.extend([f"%{q.strip()}%"] * 6)

    limit = max(1, min(limit, 2000))
    rows = query(f"""SELECT * FROM v_document_library
                      WHERE {' AND '.join(where)}
                      ORDER BY received_at DESC, evidence_id
                      LIMIT {limit}""", tuple(args))

    facets = query("""SELECT kind, count(*) AS n, sum(byte_size) AS bytes
                        FROM v_document_library
                       GROUP BY kind ORDER BY n DESC, kind""")
    periods = query("""SELECT period, count(*) AS n
                         FROM v_document_library
                        GROUP BY period ORDER BY period DESC""")
    total = one("""SELECT count(*) AS n,
                          coalesce(sum(byte_size), 0) AS bytes,
                          count(*) FILTER (WHERE is_attached) AS attached
                     FROM v_document_library""")

    record(actor, "DOCUMENT_LIBRARY_READ", "evidence", "library",
           after={"matched": len(rows), "query": q, "period": period,
                  "kind": kind},
           reason="opened the document library")

    return {"documents": rows, "matched": len(rows),
            "truncated": len(rows) >= limit,
            "kinds": facets, "periods": periods,
            "total": total["n"], "total_bytes": total["bytes"],
            "total_attached": total["attached"]}


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
