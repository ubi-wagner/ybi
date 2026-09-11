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
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import (Actor, Portfolio, current_actor, require_office,
                      require_own_writes, require_reader)
from app import storage
from app.db import execute, one, query
from app.domain.evidence_match import Document as MatchDocument
from app.domain.evidence_match import Target as MatchTarget
from app.domain.evidence_match import propose as match_propose
from app.settings import settings

router = APIRouter(prefix="/documents", tags=["documents"])


#: A cap that stops a phone photograph library from becoming the ledger's
#: storage tier, without being so tight that a scanned lease is refused.
MAX_BYTES = 40 * 1024 * 1024


def _facts(doc_amount: str, doc_date: str, vendor_name: str) -> tuple:
    """What is on the face of the document, or nothing.

    A blank stays NULL. "There is no amount on this document" and "nobody
    has read it off yet" are not the same fact, and the second must never be
    written as 0.00 — the intake rule, and the same reason unclassified cost
    is never defaulted into a pool.

    A cell that will not read costs that one field and no more: the document
    still lands. A receipt held back because somebody typed "March" in the
    date box is a receipt in a drawer, which is what the wide upload door
    exists to prevent.
    """
    amount = None
    if doc_amount.strip():
        try:
            amount = Decimal(doc_amount.strip().replace(",", "").lstrip("$"))
        except (InvalidOperation, ValueError):
            amount = None
    when = None
    if doc_date.strip():
        try:
            when = date.fromisoformat(doc_date.strip())
        except ValueError:
            when = None
    return amount, when, vendor_name.strip()


@router.post("/upload")
async def upload(file: UploadFile = File(...),
                 kind: str = Form("document"),
                 period: str = Form(""),
                 note: str = Form(""),
                 suggested_for: str = Form(""),
                 doc_amount: str = Form(""),
                 doc_date: str = Form(""),
                 vendor_name: str = Form(""),
                 actor: Actor = Depends(require_own_writes)) -> dict:
    """Put a document in. Anybody signed in.

    Nothing is attached to anything here, deliberately. The uploader says in
    their own words what it relates to; somebody with the portfolio decides
    what it supports.

    What they may say is what is **on the face of it** — the amount, the
    date, the vendor. That is not a judgment, it is transcription, and it is
    the person holding the paper who can do it. Those three columns were
    read by four views and written by nothing at all, so every one of the
    forty-three documents on file carried NULL in each, and nothing could be
    matched to any cost.
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
    amount, when, vendor = _facts(doc_amount, doc_date, vendor_name)
    execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                     received_from, byte_size, mime_type,
                                     ingest_channel, uploaded_by, note,
                                     suggested_for, filename,
                                     doc_amount, doc_date, vendor_name)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'UPLOAD',%s,%s,%s,%s,%s,%s,%s)""",
            (eid, period, kind, str(dest), sha, actor.display_name, len(raw),
             mime, actor.actor_id, note, suggested_for, safe,
             amount, when, vendor))
    record(actor, "DOCUMENT_UPLOAD", "evidence", eid,
           after={"kind": kind, "filename": safe, "bytes": len(raw),
                  "suggested_for": suggested_for,
                  "doc_amount": str(amount) if amount is not None else None,
                  "doc_date": when.isoformat() if when else None,
                  "vendor_name": vendor or None},
           reason=note or "uploaded")
    unread = [n for n, given, got in
              (("amount", doc_amount, amount), ("date", doc_date, when))
              if given.strip() and got is None]
    return {"evidence_id": eid, "deduplicated": False,
            "filename": safe, "bytes": len(raw), "mime_type": mime,
            "doc_amount": str(amount) if amount is not None else None,
            "doc_date": when.isoformat() if when else None,
            "vendor_name": vendor or None,
            # A field that would not read is named rather than dropped. The
            # document still landed, which is the point of saying so.
            "could_not_read": unread}


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


# ── What a document is of, after the fact ─────────────────────────────

class FactsIn(BaseModel):
    """A blank field is left alone; an explicit null clears it.

    Those are different acts. "I do not know the vendor" must not wipe one
    somebody else read off the paper, and "there is no amount on this
    document" has to be recordable — otherwise the only way to say it is to
    leave the field looking unread for ever.
    """
    doc_amount: Decimal | None = None
    doc_date: date | None = None
    vendor_name: str | None = None
    clear: list[str] = Field(default_factory=list)


@router.patch("/{evidence_id}/facts")
def facts(evidence_id: str, body: FactsIn,
          actor: Actor = Depends(require_office)) -> dict:
    """Read the amount, date and vendor off a document already on file.

    Transcription rather than judgment — but it decides what the matcher may
    propose, and a wrong amount typed here produces a confident proposal for
    the wrong cost. So it takes the portfolio that says what a document
    supports, and it is on the record like everything else.

    Forty-three documents were filed before the upload could carry these,
    including every one of the eighteen foundational ones. This is how they
    are brought up without re-uploading them.
    """
    before = one("""SELECT doc_amount, doc_date, vendor_name
                      FROM evidence WHERE evidence_id = %s""", (evidence_id,))
    if not before:
        raise HTTPException(404, "No such document.")

    sets, args = [], []
    for column, given in (("doc_amount", body.doc_amount),
                          ("doc_date", body.doc_date),
                          ("vendor_name", body.vendor_name)):
        if column in body.clear:
            sets.append(f"{column} = %s")
            args.append("" if column == "vendor_name" else None)
        elif given is not None:
            sets.append(f"{column} = %s")
            args.append(given)
    if not sets:
        raise HTTPException(422, "Nothing to record. Give an amount, a date "
                                 "or a vendor, or name a field to clear.")
    execute(f"UPDATE evidence SET {', '.join(sets)} WHERE evidence_id = %s",
            (*args, evidence_id))
    after = one("""SELECT doc_amount, doc_date, vendor_name
                     FROM evidence WHERE evidence_id = %s""", (evidence_id,))
    record(actor, "EVIDENCE_FACTS", "evidence", evidence_id,
           before=_readable(before), after=_readable(after),
           reason="read off the face of the document")
    return {"evidence_id": evidence_id, **_readable(after)}


def _readable(row: dict) -> dict:
    return {"doc_amount": str(row["doc_amount"]) if row["doc_amount"] is not None else None,
            "doc_date": row["doc_date"].isoformat() if row["doc_date"] else None,
            "vendor_name": row["vendor_name"] or None}


# ── Proposing what a document supports ────────────────────────────────

def _targets(period: str) -> list[MatchTarget]:
    """Every cost a document could be about, as a group and as a line.

    Both, because a document supports whichever the person says it does: an
    invoice for one transaction belongs on the line, and a statement
    covering a month of them belongs on the group. Offering only groups
    would make the second impossible and the first imprecise.
    """
    rows = query("""
        SELECT l.account || %s || l.payee              AS target_id,
               l.account || ' · ' || l.payee           AS label,
               sum(l.amount)                           AS amount,
               max(l.payee)                            AS payee,
               min(l.txn_date)                         AS first_day,
               max(l.txn_date)                         AS last_day,
               count(*)                                AS lines
          FROM ledger_line l
         WHERE l.period = %s AND l.statement = 'P&L'
         GROUP BY l.account, l.payee
        HAVING sum(l.amount) <> 0""", ("\x1f", period))
    out = [MatchTarget(target_type="LEDGER_GROUP", target_id=r["target_id"],
                       label=r["label"], amount=r["amount"],
                       payee=r["payee"] or "", first_day=r["first_day"],
                       last_day=r["last_day"], lines=r["lines"])
           for r in rows]
    lines = query("""
        SELECT l.line_id::text                         AS target_id,
               l.account || ' · ' || coalesce(l.description, '') AS label,
               l.amount, l.payee, l.txn_date
          FROM ledger_line l
         WHERE l.period = %s AND l.statement = 'P&L' AND l.amount <> 0""",
        (period,))
    out.extend(MatchTarget(target_type="LEDGER_LINE", target_id=r["target_id"],
                           label=r["label"], amount=r["amount"],
                           payee=r["payee"] or "", first_day=r["txn_date"],
                           last_day=r["txn_date"], lines=1)
               for r in lines)
    return out


@router.get("/propose")
def propose_attachments(period: str | None = None, limit: int = 50,
                        actor: Actor = Depends(require_office)) -> dict:
    """What each unattached document looks like it supports.

    **Nothing here is applied.** A proposal is never a decision — the rule
    the classification queue's `propose()` already follows — and the reasons
    are written out so the person confirming is confirming something rather
    than trusting a score.

    Where two costs fit a document equally well, nothing is proposed for it
    and the answer says how many tied. Matching on amount alone will pair a
    $1,200 invoice with the wrong $1,200 line, and the honest answer to that
    is to say so.
    """
    period = period or settings.period
    docs = query("""SELECT e.evidence_id, e.filename, e.doc_amount, e.doc_date,
                           coalesce(e.vendor_name, '') AS vendor_name
                      FROM evidence e
                     WHERE e.period = %s
                       AND NOT EXISTS (SELECT 1 FROM attachment a
                                        WHERE a.evidence_id = e.evidence_id
                                          AND a.detached_at IS NULL)
                     ORDER BY e.received_at DESC
                     LIMIT %s""", (period, limit))
    targets = _targets(period)
    out = []
    for d in docs:
        p = match_propose(
            MatchDocument(evidence_id=d["evidence_id"], filename=d["filename"] or "",
                          doc_amount=d["doc_amount"], doc_date=d["doc_date"],
                          vendor_name=d["vendor_name"]),
            targets)
        out.append({
            "evidence_id": d["evidence_id"],
            "filename": d["filename"],
            "doc_amount": str(d["doc_amount"]) if d["doc_amount"] is not None else None,
            "doc_date": d["doc_date"].isoformat() if d["doc_date"] else None,
            "vendor_name": d["vendor_name"] or None,
            "proposes": p.proposes,
            "why_not": p.why_not,
            "target": ({"target_type": p.match.target.target_type,
                        "target_id": p.match.target.target_id,
                        "label": p.match.target.label,
                        "amount": str(p.match.target.amount),
                        "because": p.match.because,
                        "signals": [s.name for s in p.match.signals]}
                       if p.proposes else None),
            "also_fits": [{"label": m.target.label,
                           "target_id": m.target.target_id,
                           "target_type": m.target.target_type}
                          for m in p.runners_up],
        })
    return {"period": period, "considered": len(targets),
            "documents": out,
            "proposed": sum(1 for d in out if d["proposes"]),
            "unmatched": sum(1 for d in out if not d["proposes"])}


class BulkAttachIn(BaseModel):
    attachments: list[AttachIn] = Field(min_length=1, max_length=200)


@router.post("/attach/bulk", status_code=201)
def attach_bulk(body: BulkAttachIn,
                actor: Actor = Depends(require_office)) -> dict:
    """Confirm a screenful of proposals at once.

    Each one is still its own attachment, recorded under the person's name
    with its own stated relevance — accepting in bulk is a way of pressing
    the key faster, not a different kind of act with a weaker record.

    One transaction: a batch that refused halfway through and left the first
    nine attached while reporting nothing was is exactly the defect
    `decide()` had, where a refusal partway through a batch left the groups
    before it recorded.
    """
    from app.db import transaction
    missing = [a.evidence_id for a in body.attachments
               if not one("SELECT 1 FROM evidence WHERE evidence_id = %s",
                          (a.evidence_id,))]
    if missing:
        raise HTTPException(404, f"No such document: {', '.join(sorted(set(missing)))}")

    with transaction() as cur:
        for a in body.attachments:
            cur.execute("""INSERT INTO attachment (evidence_id, target_type,
                                                   target_id, relevance,
                                                   attached_by)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (evidence_id, target_type, target_id)
                             DO UPDATE SET relevance = EXCLUDED.relevance,
                                           detached_at = NULL""",
                        (a.evidence_id, a.target_type, a.target_id,
                         a.relevance, actor.display_name))
    for a in body.attachments:
        record(actor, "EVIDENCE_ATTACH", a.target_type, a.target_id,
               after={"evidence_id": a.evidence_id, "in_bulk": True},
               reason=a.relevance)
    return {"attached": len(body.attachments),
            "documents": sorted({a.evidence_id for a in body.attachments})}
