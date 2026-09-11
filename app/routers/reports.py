"""Two documents the reconciliation needs on paper.

The timesheet report is the labour evidence behind the fringe base: coverage,
the distribution, who has certified, and every entry with what it was
reconstructed from. It exists because `v_statement_reconciliation`'s eleventh
point compares the payroll register to the ledger's wage accounts and a
reviewer who sees a difference then has to ask *which people*.

The regenerated invoice is the same three America Makes invoices rendered off
the register rather than off a PDF somebody has to find. The point is not
tidiness — it is that a restatement has to be issued on a face NCDMM's
payables recognises, and that face is the one the originals already use.

Both are reads, and both take `require_reader`. Filing a regenerated invoice
into the evidence volume is not a read; it puts an artefact into the record,
so it takes `CONTROLLER` and records who did it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app import storage
from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import execute, one, query
from app.domain.invoice_document import (DocumentLine, InvoiceDocument, Party,
                                         render)
from app.domain.timesheet_report import build_timesheet_report
from app.settings import settings

router = APIRouter(prefix="/reports", tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Who is billing, and where the money goes back to. Read off the executed
#: sub-recipient agreements, which name the entity, the address, the UEI and
#: the CAGE code — the four things a federal payables clerk matches on. It is
#: a constant rather than a settings key because getting it from an
#: environment variable would mean an invoice could go out under a name
#: nobody checked.
REMIT_TO = Party(
    name="Youngstown Business Incubator",
    address="241 West Federal Street\nYoungstown, OH 44503",
    detail="UEI E38PN6F4AVU3 · CAGE 5EAR9")


# ── The timesheet report ─────────────────────────────────────────────

@router.get("/timesheet")
def timesheet_report(period: str | None = None,
                     employee_key: str | None = None,
                     actor: Actor = Depends(require_reader)):
    """Schedule G, as a workbook.

    `employee_key` narrows it to one person — which is what a supervisor
    chasing a certification wants, and what somebody checking their own year
    before signing it wants. Without it, everybody.
    """
    period = period or settings.period

    where, args = "period = %s", [period]
    if employee_key:
        where += " AND employee_key = %s"
        args.append(employee_key)

    coverage = query(f"SELECT * FROM v_timesheet_coverage WHERE {where} "
                     f"ORDER BY employee_key", tuple(args))
    distribution = query(f"SELECT * FROM v_labor_effective WHERE {where} "
                         f"ORDER BY employee_key, objective_id", tuple(args))
    certification = query(f"SELECT * FROM v_certification_status WHERE {where} "
                          f"ORDER BY employee_key", tuple(args))
    entries = query(
        f"SELECT * FROM v_timesheet_entry WHERE {where} AND is_final "
        f"ORDER BY employee_key, work_date, objective_id", tuple(args))
    reconciliation = one("SELECT * FROM v_payroll_reconciliation "
                         "WHERE period = %s", (period,)) or {}

    caveats = _timesheet_caveats(period, coverage, certification,
                                 distribution, reconciliation, employee_key)

    who = f"-{storage.slug(employee_key)}" if employee_key else ""
    name = (f"YBI-{period}-timesheet-report{who}-"
            f"{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M}.xlsx")
    out = Path(tempfile.gettempdir()) / name
    build_timesheet_report(
        period=period, coverage=coverage, distribution=distribution,
        entries=entries, certification=certification,
        reconciliation=reconciliation, caveats=caveats, out_path=out)

    record(actor, "EXPORT", "timesheet_report", name,
           after={"period": period, "employee_key": employee_key,
                  "entries": len(entries), "people": len(coverage)},
           reason="timesheet report downloaded")
    return FileResponse(out, filename=name, media_type=XLSX)


def _timesheet_caveats(period, coverage, certification, distribution,
                       reconciliation, employee_key) -> list[str]:
    """What a reviewer has to know before they read the figures.

    Stated rather than implied, and above the numbers rather than under
    them — a reviewer handed a distribution has formed a view long before
    they reach a footnote.
    """
    notes: list[str] = []

    uncertified = [r for r in certification if not r.get("certified")]
    if uncertified:
        notes.append(
            f"{len(uncertified)} of {len(certification)} people have not "
            f"certified their {period} effort under 2 CFR 200.430(i). The "
            f"distribution below is not yet supported by their signature.")

    reconstructed = sum(1 for r in distribution if r.get("is_reconstructed"))
    if reconstructed:
        notes.append(
            f"{reconstructed} of {len(distribution)} distribution rows are "
            f"reconstructed after the fact from calendars, project logs and "
            f"email rather than kept contemporaneously. Each entry names what "
            f"it rests on; a reconstruction that names its source is evidence "
            f"and one that does not is a guess.")

    unexplained = reconciliation.get("unexplained")
    if unexplained is not None and Decimal(str(unexplained)) != 0:
        notes.append(
            f"The payroll register and the ledger's wage accounts differ by "
            f"{Decimal(str(unexplained)):,.2f} that no reconciling item names. "
            f"The fringe base comes from the distribution and not from the "
            f"ledger, so this is two denominators for one rate.")

    thin = [r for r in coverage
            if r.get("coverage") is not None and float(r["coverage"]) < 50]
    if thin:
        notes.append(
            f"{len(thin)} people have entered under half the hours their "
            f"employment dates imply. Their share of effort is carried by "
            f"whatever they did enter.")

    if employee_key:
        notes.append(f"This report covers {employee_key} only. It is not the "
                     f"organisation's distribution and does not foot to the "
                     f"payroll register.")
    if not notes:
        notes.append(f"Every person on the {period} register has certified, "
                     f"and the register agrees with the ledger.")
    return notes


# ── Invoice regeneration ─────────────────────────────────────────────

def _load(invoice_id: str) -> tuple[dict, list[dict]]:
    head = one("""SELECT i.*, o.label AS objective_label, a.sponsor
                    FROM invoice i
                    LEFT JOIN cost_objective o ON o.objective_id = i.objective_id
                    LEFT JOIN award a ON a.award_id = i.award_id
                   WHERE i.invoice_id::text = %s OR i.invoice_number = %s""",
              (invoice_id, invoice_id))
    if not head:
        raise HTTPException(404, "No such invoice.")
    lines = query("""SELECT * FROM invoice_line WHERE invoice_id = %s
                      ORDER BY sequence""", (head["invoice_id"],))
    return head, lines


#: A status this organisation is *issuing* under, rather than one it is
#: reproducing. Only these render without the "not the document of record"
#: band, because only these are documents YBI is putting its name to now.
ISSUING = frozenset({"DRAFT", "RESTATED", "CREDIT"})


def _document(head: dict, lines: list[dict]) -> InvoiceDocument:
    """The register as a document. Nothing is computed on the way through.

    Every figure comes off the row it was recorded in, including the header
    total — which is *not* re-derived from the lines, so that if the two ever
    disagree the invoice can print both and say so rather than quietly
    printing whichever the code happened to prefer.
    """
    status = (head.get("status") or "").upper()
    bill_to = Party(name=head.get("bill_to_name") or head.get("sponsor") or "",
                    address=head.get("bill_to_address") or "")
    return InvoiceDocument(
        number=head.get("invoice_number") or str(head["invoice_id"])[:8],
        invoice_date=head.get("invoice_date"),
        remit_to=REMIT_TO,
        bill_to=bill_to,
        lines=tuple(
            DocumentLine(
                category=str(l["category"]),
                amount=Decimal(str(l["amount"])),
                description=l.get("description") or "",
                activity=l.get("activity") or "",
                quantity=Decimal(str(l.get("quantity") or 1)),
                rate=(Decimal(str(l["rate"])) if l.get("rate") is not None
                      else None),
                personnel=l.get("personnel") or "")
            for l in lines),
        total=(Decimal(str(head["total"])) if head.get("total") is not None
               else None),
        terms=head.get("terms") or "",
        po_number=head.get("po_number") or "",
        due_on=head.get("due_on"),
        service_from=head.get("service_from"),
        service_to=head.get("service_to"),
        objective=head.get("objective_id") or "",
        award=head.get("award_id") or "",
        is_original=status in ISSUING,
        status=status,
        source_document=head.get("source_document") or "",
        caveats=tuple(_invoice_caveats(head, lines)))


def _invoice_caveats(head: dict, lines: list[dict]) -> list[str]:
    """What this invoice does not say on its face.

    The whole America Makes finding is a thing the invoices do not say: two
    of three carry no indirect line at all, and the third carries a flat
    amount that is a budget draw rather than a rate on a base. An invoice
    reproduced without that noted is the same invoice that caused the
    problem.
    """
    notes: list[str] = []
    indirect = sum(Decimal(str(l["amount"])) for l in lines
                   if str(l["category"]) == "INDIRECT")
    direct = sum(Decimal(str(l["amount"])) for l in lines
                 if str(l["category"]) in
                 ("LABOR", "FRINGE", "TRAVEL", "MATERIALS", "CONSULTANT",
                  "SUBAWARD", "ODC"))
    if indirect == 0 and direct > 0:
        notes.append(
            "This invoice bills no indirect cost against "
            f"{direct:,.2f} of direct cost. Indirect recovery on this award "
            "is unbilled, not waived.")
    if all(Decimal(str(l.get("quantity") or 1)) == 1 for l in lines) and lines:
        notes.append(
            "Every line is quantity one at a rate equal to the whole amount, "
            "as the original was issued. No hours and no burdened labour rate "
            "appear on the face of this invoice.")
    return notes


@router.get("/invoice/{invoice_id}")
def invoice_pdf(invoice_id: str, actor: Actor = Depends(require_reader)):
    """The invoice, rendered off the register.

    Takes the invoice number or the identifier, because somebody working
    from a workpaper has the number and somebody working from a screen has
    the identifier.
    """
    head, lines = _load(invoice_id)
    doc = _document(head, lines)
    body = render(doc)

    record(actor, "EXPORT", "invoice", str(head["invoice_id"]),
           after={"invoice_number": doc.number, "lines": len(lines),
                  "total": str(doc.total), "original": doc.is_original},
           reason="invoice regenerated")

    name = f"YBI-invoice-{doc.number}.pdf"
    return Response(
        body, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"',
                 "X-Content-Type-Options": "nosniff"})


@router.post("/invoice/{invoice_id}/file", status_code=201)
def file_invoice(invoice_id: str, actor: Actor = Depends(require_controller)):
    """Put the regenerated invoice into the record.

    A read hands somebody a file; this puts an artefact in the evidence
    volume with a hash, where it can be attached to the cost it supports and
    where an auditor will find it without asking anybody.

    Content-addressed like every other upload, and the render is
    deterministic — so filing the same invoice twice files one document, and
    a *changed* invoice files a second one alongside the first rather than
    overwriting it. Two versions of an invoice is a fact about the
    engagement; one that quietly changed underneath is not.
    """
    head, lines = _load(invoice_id)
    doc = _document(head, lines)
    raw = render(doc)
    sha = hashlib.sha256(raw).hexdigest()

    existing = one("SELECT evidence_id FROM evidence WHERE sha256 = %s", (sha,))
    if existing:
        record(actor, "EXPORT", "invoice", str(head["invoice_id"]),
               after={"evidence_id": existing["evidence_id"],
                      "deduplicated": True},
               reason="regenerated invoice was already on file")
        return {"evidence_id": existing["evidence_id"], "deduplicated": True,
                "invoice_number": doc.number,
                "message": "That rendering is already on file."}

    filename = f"YBI-invoice-{doc.number}.pdf"
    period = head.get("period") or settings.period
    dest = storage.place(
        storage.evidence_path(period, "invoice", sha, filename), raw)
    eid = f"EV-{sha[:12]}"
    execute("""INSERT INTO evidence (evidence_id, period, kind, uri, sha256,
                                     received_from, byte_size, mime_type,
                                     ingest_channel, uploaded_by, note,
                                     suggested_for, filename)
               VALUES (%s,%s,'invoice',%s,%s,%s,%s,'application/pdf',
                       'GENERATED',%s,%s,%s,%s)""",
            (eid, period, str(dest), sha, actor.display_name, len(raw),
             actor.actor_id,
             "Rendered from the invoice register, not the document as issued."
             if not doc.is_original else
             "Issued from the invoice register.",
             f"Invoice {doc.number}", filename))
    execute("UPDATE invoice SET evidence_id = COALESCE(evidence_id, %s) "
            "WHERE invoice_id = %s", (eid, head["invoice_id"]))

    record(actor, "EVIDENCE_GENERATED", "invoice", str(head["invoice_id"]),
           after={"evidence_id": eid, "invoice_number": doc.number,
                  "bytes": len(raw), "sha256": sha,
                  "original": doc.is_original},
           reason=f"invoice {doc.number} rendered and filed")
    return {"evidence_id": eid, "deduplicated": False,
            "invoice_number": doc.number, "bytes": len(raw),
            "filename": filename}


@router.get("/invoices")
def invoices(period: str | None = None,
             actor: Actor = Depends(require_reader)) -> dict:
    """What there is to render, with enough on each row to choose."""
    period = period or settings.period
    rows = query("""SELECT c.*, i.bill_to_name, i.evidence_id,
                           i.source_document
                      FROM v_invoice_category c
                      JOIN invoice i USING (invoice_id)
                     WHERE c.period = %s
                     ORDER BY c.invoice_number""", (period,))
    return {"period": period, "invoices": rows, "count": len(rows)}
