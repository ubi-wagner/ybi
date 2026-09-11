"""Restating the America Makes invoices.

The point of the whole system. Everything upstream — the classification, the
seal, the rate, the allocation — exists so that a number put in front of
NCDMM can be traced back to a judgment somebody signed their name to.

Three things this handler will not do.

It will not compute from an unsealed set. The rate it uses carries a seal and
the database checks that the restatement carries the same one, so a
restatement is provably a consequence of the classifications rather than of
somebody's preferred answer.

It will not present a proposal as a position. Neither America Makes agreement
was billed under a provisional rate, so moving off the de minimis election is
a change of basis requiring a written modification under §4.4 — not a
corrected invoice in the post. Everything here is PROPOSED until a sponsor
says otherwise in writing, and accepting one without naming the modification
that authorised it is refused.

It will not net an over-collection against an under-recovery. They are two
different conversations: one is money to ask for, the other is money to give
back, and a single net figure hides both.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import one, query, transaction
from app.statelock import turn
from app.domain.invoice import Category, Invoice, InvoiceLine, assess
from app.settings import settings

router = APIRouter(prefix="/restate", tags=["restate"],
                   dependencies=[Depends(require_reader)])


class RestateIn(BaseModel):
    objective_id: str
    rate_kind: str = "INDIRECT_COMBINED"
    basis: str = Field(..., min_length=21)


class DecideIn(BaseModel):
    status: str
    modification_ref: str = ""
    note: str = ""


def _invoices(period: str, objective_id: str) -> list[tuple[dict, Invoice]]:
    """The invoices as billed, rebuilt into the domain object that knows how
    to read them."""
    headers = query("""SELECT invoice_id, invoice_number, invoice_date,
                              objective_id, award_id, po_number, bill_to_name,
                              total
                         FROM invoice
                        WHERE period = %s AND objective_id = %s
                          AND status <> 'WITHDRAWN'
                        ORDER BY invoice_date, invoice_number""",
                    (period, objective_id))
    out = []
    for h in headers:
        lines = query("""SELECT category::text AS category, amount, description,
                                personnel
                           FROM invoice_line WHERE invoice_id = %s
                          ORDER BY sequence""", (h["invoice_id"],))
        out.append((h, Invoice(
            invoice_id=h["invoice_number"] or str(h["invoice_id"]),
            objective_id=h["objective_id"] or objective_id,
            po_number=h["po_number"] or "",
            bill_to=h["bill_to_name"] or "",
            lines=tuple(InvoiceLine.of(Category(l["category"]),
                                       str(l["amount"]),
                                       l["description"] or "",
                                       l["personnel"] or "")
                        for l in lines))))
    return out


@router.get("/candidates")
def candidates(period: str = None) -> dict:
    """What could be restated, and what stands in the way.

    Deliberately answers "not yet, because" rather than an empty list. The
    reasons are the work.
    """
    period = period or settings.period
    rates = query("""SELECT rate_id, kind, rate, seal_hash, status, computed_at
                       FROM rate WHERE period = %s AND status <> 'SUPERSEDED'
                      ORDER BY computed_at DESC""", (period,))
    rows = query("""
        SELECT i.objective_id, o.label, count(*) AS invoices,
               sum(i.total) AS billed,
               sum(i.indirect_claimed) AS indirect_billed,
               max(a.award_id) AS award_id,
               max(a.ceiling_federal) AS ceiling,
               max(a.rate_method::text) AS billed_under
          FROM invoice i
          LEFT JOIN cost_objective o ON o.objective_id = i.objective_id
          LEFT JOIN award a ON a.award_id = i.award_id
         WHERE i.period = %s AND i.status <> 'WITHDRAWN'
         GROUP BY i.objective_id, o.label ORDER BY sum(i.total) DESC""",
        (period,))
    return {
        "period": period, "rates": rates, "objectives": rows,
        "blocked_because": ([] if rates else [
            "No rate has been computed for this period. Seal the "
            "classifications and compute a rate first — a restatement is a "
            "consequence of the rate, and the rate of the judgments."]),
    }


@router.post("")
def restate(body: RestateIn, period: str = None,
            actor: Actor = Depends(require_controller)) -> dict:
    """Measure every invoice on one objective against the sealed rate.

    The result is a proposal with its arithmetic attached, per invoice, in the
    direction the difference actually runs.
    """
    period = period or settings.period

    rate = one("""SELECT rate_id, kind, rate, seal_hash, base_type::text AS base_type
                    FROM rate
                   WHERE period = %s AND kind = %s AND status <> 'SUPERSEDED'
                   ORDER BY computed_at DESC LIMIT 1""",
               (period, body.rate_kind))
    if not rate:
        raise HTTPException(
            409, f"No live {body.rate_kind} rate for {period}. Seal the "
                 f"classifications and compute a rate first — a restatement "
                 f"is a consequence of the rate, and the rate of the "
                 f"judgments.")

    pairs = _invoices(period, body.objective_id)
    if not pairs:
        raise HTTPException(404, f"No invoices on file for "
                                 f"{body.objective_id} in {period}.")

    fringe = one("""SELECT rate FROM rate WHERE period = %s AND kind = 'FRINGE'
                      AND status <> 'SUPERSEDED'
                     ORDER BY computed_at DESC LIMIT 1""", (period,))
    fringe_rate = Decimal(str(fringe["rate"])) if fringe else Decimal(0)
    indirect_rate = Decimal(str(rate["rate"]))

    award = one("""SELECT award_id, ceiling_federal, cost_share_required,
                          rate_method::text AS rate_method
                     FROM award WHERE objective_id = %s LIMIT 1""",
                (body.objective_id,))

    lines, under, over = [], Decimal(0), Decimal(0)
    billed_total = base_total = indirect_billed = indirect_supported = Decimal(0)
    for header, inv in pairs:
        # The labour lines are burdened — fringe is inside them — so fringe is
        # not separately foregone and only indirect is at issue.
        rec = assess(inv, indirect_rate=indirect_rate, fringe_rate=fringe_rate,
                     labor_is_burdened=True,
                     rate_label=f"{rate['kind']} {indirect_rate:.4f}")
        variance = rec.indirect_variance
        direction = ("UNDER" if variance > 0
                     else "OVER" if variance < 0 else "EVEN")
        if variance > 0:
            under += variance
        elif variance < 0:
            over += -variance
        billed_total += inv.total
        base_total += rec.mtdc_as_billed
        indirect_billed += rec.indirect_billed
        indirect_supported += rec.indirect_supported
        lines.append({
            "invoice_id": header["invoice_id"],
            "invoice_number": header["invoice_number"],
            "invoice_date": header["invoice_date"],
            "base_as_billed": rec.mtdc_as_billed,
            "indirect_billed": rec.indirect_billed,
            "indirect_supported": rec.indirect_supported,
            "variance": variance, "direction": direction,
            "finding": " ".join(rec.findings),
        })

    # The ceiling caps what can be claimed. A restatement that would take the
    # award past its ceiling is not a bigger claim, it is a modification
    # conversation — and saying so is more useful than presenting a number
    # that cannot be paid.
    headroom = capped = None
    if award and award["ceiling_federal"] and award["ceiling_federal"] > 0:
        claimed_to_date = one("""SELECT COALESCE(sum(total), 0) AS t
                                   FROM invoice
                                  WHERE award_id = %s AND status <> 'WITHDRAWN'""",
                              (award["award_id"],))["t"]
        headroom = Decimal(str(award["ceiling_federal"])) - Decimal(str(claimed_to_date))
        capped = under > headroom

    # Held, like every other act on the cost record. A restatement is measured
    # against a rate read a few milliseconds ago; the rate can be superseded by
    # an unseal in between, so this re-reads it under the lock before writing.
    with turn(period) as cur:
        cur.execute("""SELECT status::text AS status FROM rate WHERE rate_id = %s""",
                    (rate["rate_id"],))
        still = cur.fetchone()
        if not still or still["status"] == 'SUPERSEDED':
            raise HTTPException(409, {
                "error": "RATE_SUPERSEDED",
                "message": ("The rate this restatement was measured against was "
                            "superseded while it was being computed — most "
                            "likely the classifications were reopened. Nothing "
                            "was written."),
                "rate_id": str(rate["rate_id"])})
        cur.execute("""UPDATE restatement SET status = 'SUPERSEDED'
                        WHERE period = %s AND objective_id = %s
                          AND status = 'PROPOSED'""",
                    (period, body.objective_id))
        cur.execute("""INSERT INTO restatement
                         (period, award_id, objective_id, rate_id, seal_hash,
                          invoices, billed_total, base_total, indirect_billed,
                          indirect_supported, under_recovered, over_collected,
                          ceiling_headroom, capped_by_ceiling, basis,
                          computed_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING restatement_id""",
                    (period, award["award_id"] if award else None,
                     body.objective_id, rate["rate_id"], rate["seal_hash"],
                     len(lines), billed_total, base_total, indirect_billed,
                     indirect_supported, under, over, headroom,
                     bool(capped), body.basis.strip(), actor.display_name))
        rid = cur.fetchone()["restatement_id"]
        for l in lines:
            cur.execute("""INSERT INTO restatement_line
                             (restatement_id, invoice_id, invoice_number,
                              invoice_date, base_as_billed, indirect_billed,
                              indirect_supported, variance, direction, finding)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (rid, l["invoice_id"], l["invoice_number"],
                         l["invoice_date"], l["base_as_billed"],
                         l["indirect_billed"], l["indirect_supported"],
                         l["variance"], l["direction"], l["finding"][:1000]))
        record(actor, "RESTATE", "restatement", str(rid),
               after={"objective_id": body.objective_id,
                      "rate": str(indirect_rate),
                      "seal_hash": rate["seal_hash"],
                      "under_recovered": str(under),
                      "over_collected": str(over)},
               reason=body.basis.strip()[:400], cursor=cur)

    return {
        "restatement_id": str(rid), "objective_id": body.objective_id,
        "status": "PROPOSED",
        "rate": {"kind": rate["kind"], "rate": str(indirect_rate),
                 "base_type": rate["base_type"], "seal_hash": rate["seal_hash"]},
        "invoices": len(lines),
        "billed_total": str(billed_total),
        "base_total": str(base_total),
        "indirect_billed": str(indirect_billed),
        "indirect_supported": str(indirect_supported),
        "under_recovered": str(under),
        "over_collected": str(over),
        "ceiling_headroom": str(headroom) if headroom is not None else None,
        "capped_by_ceiling": bool(capped),
        "lines": [{**l, "invoice_id": str(l["invoice_id"]),
                   "invoice_date": str(l["invoice_date"]),
                   "base_as_billed": str(l["base_as_billed"]),
                   "indirect_billed": str(l["indirect_billed"]),
                   "indirect_supported": str(l["indirect_supported"]),
                   "variance": str(l["variance"])} for l in lines],
        "standing": (
            "A proposal. Neither agreement was billed under a provisional "
            "rate, so this is a change of basis and needs a written "
            "modification under §4.4 before it becomes a claim."),
    }


@router.get("")
def list_restatements(period: str = None) -> list[dict]:
    period = period or settings.period
    return query("""SELECT restatement_id, objective_id, award_id, status::text AS status,
                           invoices, billed_total, base_total, indirect_billed,
                           indirect_supported, under_recovered, over_collected,
                           ceiling_headroom, capped_by_ceiling, rate_applied,
                           rate_kind, billed_under, sponsor, basis,
                           modification_ref, computed_by, computed_at
                      FROM v_restatement WHERE period = %s
                     ORDER BY computed_at DESC""", (period,))


@router.get("/{restatement_id}")
def detail(restatement_id: str) -> dict:
    head = one("SELECT * FROM v_restatement WHERE restatement_id = %s",
               (restatement_id,))
    if not head:
        raise HTTPException(404, "No such restatement.")
    return {"restatement": head,
            "lines": query("""SELECT * FROM restatement_line
                               WHERE restatement_id = %s
                               ORDER BY invoice_date, invoice_number""",
                           (restatement_id,))}


@router.post("/{restatement_id}/status")
def decide(restatement_id: str, body: DecideIn,
           actor: Actor = Depends(require_controller)) -> dict:
    """Move a proposal along: submitted to the sponsor, accepted, rejected.

    Accepting without naming the modification that authorised the change of
    basis is refused by the schema. That single omission is the most likely
    thing in this whole exercise to become a finding.
    """
    if body.status not in ("SUBMITTED", "ACCEPTED", "REJECTED"):
        raise HTTPException(422, f"Unknown status {body.status!r}.")
    head = one("SELECT status::text AS status FROM restatement "
               "WHERE restatement_id = %s", (restatement_id,))
    if not head:
        raise HTTPException(404, "No such restatement.")
    if head["status"] == "SUPERSEDED":
        raise HTTPException(409, "That restatement has been superseded by a "
                                 "later computation.")

    with transaction() as cur:
        cur.execute("""UPDATE restatement
                          SET status = %s::restatement_status,
                              modification_ref = COALESCE(NULLIF(%s, ''),
                                                          modification_ref),
                              submitted_at = CASE WHEN %s = 'SUBMITTED'
                                                  THEN now() ELSE submitted_at END,
                              decided_at = CASE WHEN %s IN ('ACCEPTED','REJECTED')
                                                THEN now() ELSE decided_at END,
                              decided_note = %s
                        WHERE restatement_id = %s""",
                    (body.status, body.modification_ref.strip(), body.status,
                     body.status, body.note.strip(), restatement_id))
        record(actor, "RESTATE_STATUS", "restatement", restatement_id,
               before={"status": head["status"]},
               after={"status": body.status,
                      "modification_ref": body.modification_ref.strip()},
               reason=body.note.strip()[:400] or f"moved to {body.status}",
               cursor=cur)
    return {"restatement_id": restatement_id, "status": body.status}
