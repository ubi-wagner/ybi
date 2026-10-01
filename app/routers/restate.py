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

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.audit import record
from app.auth import Actor, require_controller, require_reader
from app.db import one, query, transaction
from app.statelock import turn
from app.domain.audit_package import certification_lines
from app.domain.amendment_document import (AmendmentPapers, Movement,
                                           render_acceptance, render_memo)
from app.domain.reconciliation_document import (Contract, RateLine,
                                                Reconciliation,
                                                render_reconciliation)
from app.domain.core import money
from app.papers import as_pdf as _as_pdf
from app.domain.invoice import (Category, DirectCost, Invoice, InvoiceLine,
                                assess, rebuild)
from app.domain.invoice_document import Party
from app.routers.rates import rate_certification
from app.settings import settings

router = APIRouter(prefix="/restate", tags=["restate"],
                   dependencies=[Depends(require_reader)])


#: The de minimis an award is set to, as a rate. Both places it is written
#: down are cited because they are different kinds of evidence and an auditor
#: will want to know which is which:
#:
#:   * Last Tactical Mile — the only EXECUTED agreement that budgets it.
#:     Schedule B carries 10.0000% of total direct to four decimal places,
#:     and LTM's are the only invoices in the register with an indirect line.
#:   * Hybrid Phase 2 — a COST PROPOSAL, not an executed schedule. Its ODCs
#:     tab computes "ICR 10% maximum 45,457.00" over a $454,570 base and puts
#:     the result inside the labour line. It is the document that proves the
#:     indirect is embedded rather than absent.
#:
#: Every one of the four awards carries DE_MINIMIS_10 on the record, so the
#: election is what they are all measured against.
ELECTED = {
    "DE_MINIMIS_10": Decimal("0.10"),
    "DE_MINIMIS_15": Decimal("0.15"),
    "NEGOTIATED": Decimal(0),      # a negotiated rate is the rate itself
}


class RestateIn(BaseModel):
    objective_id: str
    rate_kind: str = "INDIRECT_COMBINED"
    basis: str = Field(..., min_length=21)


class DecideIn(BaseModel):
    status: str
    modification_ref: str = ""
    note: str = ""


#: A restatement that stands as a claim, for the two papers that describe it.
#:
#: `PROPOSED` is a position YBI has taken, `SUBMITTED` is one in the post and
#: `ACCEPTED` is one the sponsor has agreed to — which is the *strongest* form
#: of standing and was the one both papers refused. The memorandum and the
#: acceptance form filtered on `PROPOSED` alone, so the moment NCDMM accepted,
#: the paper explaining the change and the paper they had just signed both
#: answered 404. That is backwards in the place it costs most: after
#: acceptance is exactly when a payables clerk holding a reissued invoice goes
#: looking for the two documents that explain it.
#:
#: `SUPERSEDED` and `REJECTED` are history and stay out. A superseded
#: restatement is *supposed* to disagree with the register.
STANDING = ("PROPOSED", "SUBMITTED", "ACCEPTED")


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

    # ── The cost record for this objective, which is what a rebuild is ──
    #
    # Before migration 076 the position was the rate applied to the invoice's
    # own base. That base carries labour which already contains embedded
    # indirect — YBI's Hybrid cost proposal computes $45,457 of 10% ICR into a
    # $449,043.40 labour line — so the rate went on top of a figure that
    # already held it. Across the four America Makes awards the two readings
    # differ by $722,095.49, in the direction that would have YBI ask a
    # federal pass-through for money it cannot support.
    #
    # Annual rather than per-invoice because the cost record is annual, and
    # splitting a year of classified cost across twelve invoices needs a
    # driver nobody has recorded.
    wages = one("""SELECT COALESCE(round(sum(distributed_wages), 2), 0) AS w
                     FROM v_labor_effective
                    WHERE period = %s AND objective_id = %s""",
                (period, body.objective_id))["w"]
    nonlabour = one("""SELECT COALESCE(sum(l.amount), 0) AS a
                         FROM decision d
                         JOIN decision_line dl
                           ON dl.decision_id = d.decision_id AND dl.live
                         JOIN ledger_line l ON l.line_id = dl.line_id
                        WHERE d.reversed_at IS NULL AND d.pool = 'DIRECT'
                          AND d.objective_id = %s""",
                    (body.objective_id,))["a"]
    mtdc_row = one("""SELECT a.base_amount AS b FROM allocation a
                       WHERE a.rate_id = %s AND a.objective_id = %s""",
                   (rate["rate_id"], body.objective_id))
    if not mtdc_row:
        raise HTTPException(409, {
            "error": "NO_BASE_FOR_OBJECTIVE",
            "message": (f"The sealed rate carries no allocation for "
                        f"{body.objective_id}, so there is no MTDC base to "
                        f"rebuild against. A restatement is measured against "
                        f"the cost record, and this objective has none under "
                        f"this rate."),
            "objective_id": body.objective_id})
    cost = DirectCost(wages=Decimal(str(wages)),
                      fringe=money(Decimal(str(wages)) * fringe_rate),
                      nonlabour=Decimal(str(nonlabour)),
                      mtdc=Decimal(str(mtdc_row["b"])))
    elected_rate = ELECTED.get(
        (award or {}).get("rate_method") or "", Decimal(0))

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

    # ── The position, rebuilt ───────────────────────────────────────────
    #
    # `under` and `over` above were accumulated from the per-invoice as-billed
    # reading, which is kept as detail. The POSITION is the rebuild, and the
    # two are deliberately both on the row: an auditor comparing this to
    # anything written before migration 076 has to be able to see why they
    # differ, and removing the old figure would make the difference invisible
    # rather than resolved.
    rb = rebuild(body.objective_id, invoices=len(lines), billed=billed_total,
                 cost=cost, indirect_rate=indirect_rate,
                 elected_rate=elected_rate, indirect_billed=indirect_billed,
                 as_billed_base=base_total)
    as_billed_under, as_billed_over = under, over
    under = rb.position if rb.position > 0 else Decimal(0)
    over = -rb.position if rb.position < 0 else Decimal(0)

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
        # One objective carries one claim YBI would bill on, and the index
        # `one_standing_restatement_per_objective` holds it. This is the
        # same rule in the handler, where it can say what happened.
        #
        # Recomputing supersedes a PROPOSED position — YBI's own, unsent, and
        # the recompute *is* the correction. It must not silently replace one
        # the sponsor has SUBMITTED to or ACCEPTED: that is a position
        # somebody agreed to, and `drive_recertify` settled the principle —
        # *the one act that takes something away from the person who made it
        # is never automatic.*
        #
        # The first draft declined to supersede those and **wrote the new row
        # anyway**, so the guard produced the state it existed to prevent:
        # two standing claims on one objective, added together by every
        # reader, putting $265,008.84 on the acceptance form for an award
        # that owes $136,534.61.
        cur.execute("""SELECT restatement_id, status::text AS status,
                              over_collected, under_recovered, modification_ref
                         FROM restatement
                        WHERE period = %s AND objective_id = %s
                          AND status IN ('SUBMITTED', 'ACCEPTED')""",
                    (period, body.objective_id))
        held = cur.fetchone()
        if held:
            stands = (f"{held['over_collected']:,.2f} to return"
                      if held["over_collected"] else
                      f"{held['under_recovered']:,.2f} to claim")
            raise HTTPException(409, {
                "error": "A_POSITION_IS_STANDING",
                "message": (
                    f"{body.objective_id} already carries a position that has "
                    f"been put to the sponsor — {held['status'].lower()}, at "
                    f"{stands}"
                    + (f", under {held['modification_ref']}"
                       if (held.get("modification_ref") or "").strip() else "")
                    + ". Measuring again would replace it, and taking back "
                    "something a sponsor has seen is not something this does "
                    "on your behalf. Withdraw that position first, with the "
                    "reason, and then measure."),
                "restatement_id": str(held["restatement_id"]),
                "status": held["status"]})

        cur.execute("""UPDATE restatement SET status = 'SUPERSEDED'
                        WHERE period = %s AND objective_id = %s
                          AND status = 'PROPOSED'""",
                    (period, body.objective_id))
        cur.execute("""INSERT INTO restatement
                         (period, award_id, objective_id, rate_id, seal_hash,
                          invoices, billed_total, base_total, indirect_billed,
                          indirect_supported, under_recovered, over_collected,
                          ceiling_headroom, capped_by_ceiling, basis,
                          computed_by, direct_supported, indirect_rebuilt,
                          supported_total, as_billed_base, as_billed_indirect,
                          elected_rate, elected_indirect, implied_rate, method)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s,%s,%s,'REBUILD')
                       RETURNING restatement_id""",
                    (period, award["award_id"] if award else None,
                     body.objective_id, rate["rate_id"], rate["seal_hash"],
                     len(lines), billed_total, base_total, indirect_billed,
                     rb.indirect_supported, under, over, headroom,
                     bool(capped), body.basis.strip(), actor.display_name,
                     rb.direct_supported, rb.indirect_supported, rb.supported,
                     rb.as_billed_base, rb.as_billed_indirect,
                     rb.elected_rate, rb.elected_indirect, rb.implied_rate))
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
        "indirect_supported": str(rb.indirect_supported),
        "under_recovered": str(under),
        "over_collected": str(over),
        # The position, and the reading it replaced, side by side and named.
        "method": "REBUILD",
        "rebuild": {
            "direct_supported": str(rb.direct_supported),
            "indirect_supported": str(rb.indirect_supported),
            "supported_total": str(rb.supported),
            "position": str(rb.position),
            "wages": str(cost.wages), "fringe": str(cost.fringe),
            "nonlabour": str(cost.nonlabour), "mtdc": str(cost.mtdc),
        },
        "as_billed": {
            "base": str(rb.as_billed_base),
            "indirect_supported": str(rb.as_billed_indirect),
            "position": str(rb.as_billed_position),
            "under_recovered": str(as_billed_under),
            "over_collected": str(as_billed_over),
            "note": ("The invoice-only reading, kept for comparison and never "
                     "the position. It applies the rate to a base that "
                     "already carries embedded indirect."),
        },
        "elected": {
            "rate": str(rb.elected_rate),
            "indirect": str(rb.elected_indirect),
            "position": str(rb.elected_indirect - indirect_billed),
            "cited": ("Both places the 10% is written down: Last Tactical "
                      "Mile's executed Schedule B budgets 10.0000% of total "
                      "direct, and Hybrid Phase 2's cost proposal computes "
                      "'ICR 10% maximum 45,457.00' into its labour line."),
        },
        "implied_rate": (str(rb.implied_rate) if rb.implied_rate is not None
                         else None),
        "findings": rb.findings,
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
                           modification_ref, computed_by, computed_at,
                           -- Both readings reach the screen, or the screen
                           -- shows a position with no way to see why it is
                           -- not the figure anybody wrote down before today.
                           method, direct_supported, indirect_rebuilt,
                           supported_total, as_billed_base, as_billed_indirect,
                           as_billed_position, elected_rate, elected_indirect,
                           elected_position, implied_rate,
                           -- What the register holds now, beside what this
                           -- measured. `088`: three claims stood for a week
                           -- over three invoices that had been moved to
                           -- another period, and nothing anywhere said so.
                           register_invoices, register_billed, still_agrees,
                           -- And what it was measured *on*. `132`: the same
                           -- question one column along, and the worse half —
                           -- a changed population moves which invoices a
                           -- claim covers, a changed rate moves every figure.
                           rate_status, rate_is_live
                      FROM v_restatement WHERE period = %s
                     ORDER BY computed_at DESC""", (period,))


# Declared **before** `/{restatement_id}`, and that is load-bearing rather
# than tidy. Starlette matches routes in declaration order, so a literal path
# registered after a parameterised sibling never runs: `/restate/reconciliation`
# reached `detail(restatement_id="reconciliation")` and answered 500 on
# `invalid input syntax for type uuid`. The route existed, the sweep that asks
# whether every capability has a door saw it, and the tests called the
# assembly function directly — so nothing anywhere could see that the door was
# walled up. `test_no_route_is_shadowed_by_a_parameterised_sibling` is the
# property; it found exactly this one across 200 routes.
@router.get("/reconciliation")
def contract_reconciliation(period: str = "2025", inline: bool = False,
                            actor: Actor = Depends(require_reader)) -> Response:
    """The three America Makes contracts on one page, for one signature.

    A read, like the other two papers: rendering asserts nothing that was
    not already recorded when the restatements were computed, and the band
    says where each stands.
    """
    r = _reconciliation(period)
    body = render_reconciliation(r)
    record(actor, "EXPORT", "period", period,
           after={"paper": "reconciliation",
                  "awards": [c.award_id for c in r.contracts],
                  "to_return": str(r.total_return),
                  "to_claim": str(r.total_claim),
                  "certified": r.certified},
           reason="contract reconciliation rendered")
    return _as_pdf(body, f"YBI-contract-reconciliation-{period}.pdf", inline)


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
    if body.status not in ("SUBMITTED", "ACCEPTED", "REJECTED", "SUPERSEDED"):
        raise HTTPException(422, f"Unknown status {body.status!r}.")
    # Withdrawing a position YBI has put to a sponsor is the second of the
    # two conscious acts `POST /api/restate` refuses to collapse into one,
    # and it is the only one that takes something back. So it carries a
    # reason, the way unsealing does — and the reason is the whole of what
    # the record will have to say about it later.
    if body.status == "SUPERSEDED" and len(body.note.strip()) < 20:
        raise HTTPException(
            422, "Withdrawing a position the sponsor has seen needs a reason "
                 "on the record — what changed, and why the figure no longer "
                 "stands. Twenty characters or more.")
    head = one("""SELECT status::text AS status, modification_ref, objective_id
                    FROM restatement WHERE restatement_id = %s""",
               (restatement_id,))
    if not head:
        raise HTTPException(404, "No such restatement.")
    if head["status"] == "SUPERSEDED":
        raise HTTPException(409, "That restatement has been superseded by a "
                                 "later computation.")
    # `acceptance_names_its_modification` holds this in the schema, which is
    # where it belongs — it has to hold when a handler is wrong. But the
    # schema's refusal reaches the person as the constraint's name, and this
    # is the one place in the whole exercise where that is least affordable:
    # the docstring above calls the omission the most likely thing here to
    # become a finding, and what it answered was
    # "The database refused this write: acceptance_names_its_modification."
    if (body.status == "ACCEPTED"
            and not (body.modification_ref.strip()
                     or (head["modification_ref"] or "").strip())):
        raise HTTPException(
            422, f"Accepting this needs the modification that authorised the "
                 f"change of basis — neither America Makes agreement was "
                 f"billed under a provisional rate, so moving off the de "
                 f"minimis election is a §4.4 change of basis rather than a "
                 f"corrected invoice. Name the modification (its number and "
                 f"the date it was signed) and try again. Until then "
                 f"{head['objective_id']} stays a proposal, which is what it "
                 f"is.")

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


# ── the two papers a restated invoice cannot travel without ──────────
#
# The memorandum and the acceptance form, assembled **here** rather than in
# the publication script, because `scripts/publish.py` opens on the rule that
# every document is fetched from the route the screen calls: a second
# assembly would be a second implementation of the same paper, free to drift
# from this one. The screen and the script now render the same bytes.

#: Where the papers are issued from and to. Both are on the face of the
#: three invoices already in the register, which is why they are not
#: configuration: a letterhead somebody can change from a settings screen is
#: one that can differ from the document the sponsor already holds.
_YBI = Party("Youngstown Business Incubator",
             "241 W Federal St\nYoungstown, OH 44503", "ybi.org")
_SPONSOR_ADDRESS = "6800 Innovation Blvd\nJohnstown, PA 15904"


def _papers(award_id: str, period: str) -> AmendmentPapers:
    """Everything both papers print, read from the rows that hold it.

    Per award rather than per invoice: the change of basis is one
    conversation with one sponsor about one agreement, and a clerk holding
    twelve memos for twelve invoices on one award has to work out that they
    are the same ask.
    """
    rows = query("""SELECT r.award_id, r.objective_id, r.invoices,
                           r.billed_total, r.under_recovered, r.over_collected,
                           r.rate_kind, r.rate_applied, r.rate_base,
                           r.seal_hash, r.sponsor, r.billed_under,
                           r.register_invoices, r.register_billed,
                           r.still_agrees, r.rate_is_live, r.rate_status,
                           r.status, r.modification_ref
                      FROM v_restatement r
                     WHERE r.period = %s AND r.status = ANY(%s)
                       AND r.award_id = %s
                     ORDER BY r.objective_id""",
                 (period, list(STANDING), award_id))
    if not rows:
        raise HTTPException(404, (
            f"No restatement is standing as a claim on {award_id} for "
            f"{period}, so there is nothing to put an amendment memorandum "
            f"against. POST /api/restate is what makes one, and it is a "
            f"judgment."))

    # `agreement_name`, not `title` — the schema's own word for what the
    # executed instrument is called.
    award = one("""SELECT award_id, agreement_name, sponsor, instrument
                     FROM award WHERE award_id = %s""", (award_id,)) or {}
    # Quoted from the record, never recalled: `056` found three provisions on
    # two awards cited to clauses those agreements do not contain, so the
    # citation travels with the words rather than being written here.
    clause = one("""SELECT term_value, citation FROM award_term
                     WHERE award_id = %s AND term_key = 'Change of basis'""",
                 (award_id,)) or {}
    billed = one("""SELECT term_value FROM award_term
                     WHERE award_id = %s
                       AND term_key IN ('Indirect basis as billed',
                                        'Indirect provision',
                                        'Indirect recovery')
                     ORDER BY term_key LIMIT 1""", (award_id,)) or {}

    # One row per **invoice**, from `restatement_line`. `v_restatement`
    # aggregates to the objective and its `invoices` column is a *count*: a
    # first draft printed that count under a heading reading INVOICE, so the
    # form told a payables clerk to match on invoice "1".
    lines = query("""SELECT rl.invoice_number, rl.invoice_date,
                            rl.base_as_billed, rl.variance, rl.direction,
                            rl.finding, r.objective_id
                       FROM restatement_line rl
                       JOIN restatement r USING (restatement_id)
                      WHERE r.period = %s AND r.status = ANY(%s)
                        AND r.award_id = %s
                      ORDER BY rl.invoice_number""",
                 (period, list(STANDING), award_id))
    movements = tuple(
        Movement(covers=l["invoice_number"], objective=l["objective_id"],
                 award=award_id, invoice_count=1,
                 invoice_numbers=(l["invoice_date"].strftime("%d %b %Y")
                                  if l["invoice_date"] else ""),
                 as_billed=money(l["base_as_billed"] or 0),
                 under_recovered=(money(l["variance"] or 0)
                                  if l["direction"] == "UNDER" else Decimal(0)),
                 over_collected=(money(l["variance"] or 0)
                                 if l["direction"] == "OVER" else Decimal(0)),
                 finding=l["finding"] or "")
        for l in lines)
    if not movements:
        raise HTTPException(409, (
            f"The standing restatement on {award_id} records no invoice "
            f"lines, so the acceptance form would have nothing to accept."))

    cert = rate_certification(period) or {}
    first = rows[0]
    return AmendmentPapers(
        period=period, issued_on=date.today(), remit_to=_YBI,
        bill_to=Party(award.get("sponsor") or first.get("sponsor") or "NCDMM",
                      _SPONSOR_ADDRESS),
        award=award_id,
        award_title=(award.get("agreement_name")
                     or award.get("instrument") or ""),
        modification_clause=clause.get("term_value") or "",
        modification_citation=clause.get("citation") or "",
        as_billed_basis=billed.get("term_value") or "",
        proposed_basis=(f"{first.get('rate_kind') or 'Indirect'} at the "
                        f"negotiated rate on "
                        f"{first.get('rate_base') or 'modified total direct cost'}."),
        rate_kind=first.get("rate_kind") or "",
        rate=(Decimal(str(first["rate_applied"]))
              if first.get("rate_applied") is not None else None),
        base_type=first.get("rate_base") or "",
        seal_hash=first.get("seal_hash") or "",
        # Where this stands with the sponsor, and the instrument it is
        # recorded against. The *least* advanced of the award's objectives,
        # because an award whose objectives stand differently has not been
        # accepted as a whole and a band claiming otherwise would overstate
        # it — the same direction of error the certification band refuses.
        status=min((r["status"] for r in rows),
                   key=lambda st: STANDING.index(st)
                   if st in STANDING else -1),
        modification_ref=next((r["modification_ref"] for r in rows
                               if (r.get("modification_ref") or "").strip()),
                              ""),
        movements=movements,
        # The position, from the restatement row — **never** the sum of the
        # lines. A `restatement_line` is the as-billed reading of one
        # invoice; the position is the objective rebuilt against the cost
        # record, and on these awards they run opposite ways: Drive AM's
        # lines add to 254,808.06 of forgone recovery while the rebuild shows
        # 58,786.31 over-collected, because the indirect was recovered inside
        # a loaded labour rate and no invoice carries an indirect line at
        # all. Summing the lines would put a claim in front of NCDMM running
        # the opposite way from what the record supports.
        #
        # Summed across the award's objectives, with the two directions in
        # their own columns: that is not netting, it is the refusal to net.
        position_under=money(sum((r["under_recovered"] or 0) for r in rows)),
        position_over=money(sum((r["over_collected"] or 0) for r in rows)),
        # The walk's unfinished steps, and — first — anything on this
        # award's own position that the register has since overtaken. It is
        # not blocked, per `082`: the paper says so. But it says so **above**
        # the general caveats, because a reader who has to reach the fourth
        # bullet to learn the figures measure a population that has moved has
        # already formed a view.
        caveats=(
            # A rate that has since been superseded comes first, because it
            # moves *every figure* on the paper where a changed invoice
            # population only moves which invoices are covered. `132`.
            tuple(
                f"Measured on a rate that no longer stands — "
                f"{r['objective_id']} was computed against "
                f"{(r['rate_applied'] or 0) * 100:.2f}% "
                f"{r['rate_kind']}, which is now {r['rate_status']}. Every "
                f"figure here is against arithmetic the record has moved "
                f"past. Recompute before this goes to a sponsor."
                for r in rows if r.get("rate_is_live") is False)
            + tuple(
                f"Overtaken — {r['objective_id']} measured "
                f"{r['invoices']} invoice(s) totalling {r['billed_total']:,.2f}, "
                f"and the register now holds {r['register_invoices']} "
                f"totalling {r['register_billed']:,.2f}. Recompute before "
                f"this goes to a sponsor."
                for r in rows if r.get("still_agrees") is False)
            + tuple(f"{r['step']} — {r['detail']}" for r in query(
                """SELECT step, detail FROM v_audit_walk
                    WHERE period = %s AND state <> 'DONE' ORDER BY seq""",
                (period,)))),
        # The one sentence-maker, not a second spelling of it. This composed
        # its own line from `certified_by`, so when `drive_the_close.py` typed
        # a controller's name into the certify route the memorandum addressed
        # to NCDMM printed *"Certified by Tom Metzinger."* over a rate nobody
        # had signed — and `122`'s rehearsal state could not reach the paper
        # at all, because the paper was not asking the question through the
        # thing that knows the answer. It is `money()`'s eight spellings in
        # the place it costs most.
        certified=bool(cert.get("certified")) and not cert.get("rehearsal"),
        certification_line=" ".join(certification_lines(cert)),
        reference=f"{award_id} · {period}")


def _paper(award_id: str, period: str, actor: Actor, which: str,
           inline: bool = False) -> Response:
    p = _papers(award_id, period)
    body = (render_memo(p) if which == "memo" else render_acceptance(p))
    record(actor, "EXPORT", "award", award_id,
           after={"paper": which, "period": period,
                  "to_claim": str(p.to_claim), "to_return": str(p.to_return),
                  "certified": p.certified},
           reason=f"amendment {which} rendered")
    name = (f"YBI-amendment-memo-{award_id}.pdf" if which == "memo"
            else f"YBI-acceptance-{award_id}.pdf")
    return _as_pdf(body, name, inline)


@router.get("/award/{award_id}/memo")
def amendment_memo(award_id: str, period: str = "2025", inline: bool = False,
                   actor: Actor = Depends(require_reader)) -> Response:
    """Why this award's invoices are being reissued, and under what clause.

    A read, like every other document route here — `require_reader`, not
    `require_controller`. Rendering the memorandum asserts nothing: the
    position it describes was taken when the restatement was recorded, and
    the paper says PROPOSED on its first line. Refusing it to the auditor,
    who may read everything and holds no portfolio, would be the library
    defect in a new place.
    """
    return _paper(award_id, period, actor, "memo", inline)


@router.get("/award/{award_id}/acceptance")
def acceptance_form(award_id: str, period: str = "2025", inline: bool = False,
                    actor: Actor = Depends(require_reader)) -> Response:
    """What NCDMM signs. Both directions, and never their difference."""
    return _paper(award_id, period, actor, "acceptance", inline)


# ── One page, three contracts, one signature ─────────────────────────
#
# The memorandum and the acceptance form are per award, which is the right
# unit for a change of basis and the wrong one for the conversation. YBI is
# asking NCDMM one question — *was the rate acceptable, and will you settle
# 2025 on it* — and a sponsor handed three of each has to work out that they
# are one ask. Assembled here for the reason `_papers` is: `publish.py` opens
# on the rule that every document is fetched from the route the screen calls,
# and a second assembly in a script is a second implementation of one paper.

#: Which awards belong on an America Makes page, and which do not.
#:
#: Read from the record rather than listed here: an award is on the page
#: when its prime flows from the America Makes cooperative agreement. Digital
#: Engineering is administered by NCDMM and its prime is N00174-20-1-0031
#: through Energetics Technology Center and NSWC Indian Head, so it is a
#: different programme's money — and federal award funds are not fungible
#: between programmes. It is named on the page as excluded rather than
#: silently dropped, because a page three-quarters complete with no note is
#: worse than one that says which quarter is missing.
_AM_PRIME = "FA8650-20-2-5700"


def _rate_lines(period: str, rate_id: str | None) -> tuple[RateLine, ...]:
    """The build-up, off the rate the restatements were actually measured on.

    Read by `rate_id` and not by "the live rate": a restatement carries the
    rate it used, and a page that printed today's rate over yesterday's
    settlement would be the overtaken-claim shape with the two halves
    swapped. Where the restatements name no rate — which cannot happen,
    `restatement_requires_sealed_rate` sees to it — nothing is printed rather
    than a plausible substitute.
    """
    if not rate_id:
        return ()
    rows = query("""SELECT r.kind, r.rate, r.pool_amount, r.base_amount,
                           r.base_type
                      FROM rate r
                     WHERE r.period = %s
                       AND r.computed_at = (SELECT computed_at FROM rate
                                             WHERE rate_id = %s)
                     ORDER BY CASE r.kind WHEN 'FRINGE' THEN 1
                                          WHEN 'OVERHEAD' THEN 2
                                          WHEN 'G&A' THEN 3 ELSE 4 END""",
                 (period, rate_id))
    says = {"SALARIES_WAGES": "the payroll register's wages",
            "SALARIES_FRINGE": "wages and fringe",
            "MTDC": "modified total direct cost"}
    return tuple(RateLine(kind=r["kind"], rate=Decimal(str(r["rate"])),
                          pool=money(r["pool_amount"] or 0),
                          base=money(r["base_amount"] or 0),
                          base_says=says.get(r["base_type"] or "", ""))
                 for r in rows)


def _reconciliation(period: str) -> Reconciliation:
    rows = query("""SELECT r.award_id, r.objective_id, r.invoices,
                           r.billed_total, r.direct_supported,
                           r.indirect_rebuilt, r.supported_total,
                           r.indirect_billed, r.under_recovered,
                           r.over_collected, r.status, r.modification_ref,
                           r.decided_at, r.rate_id, r.seal_hash, r.sponsor,
                           r.still_agrees, r.rate_is_live, r.rate_status,
                           r.rate_kind, r.rate_applied,
                           r.register_invoices, r.register_billed,
                           a.agreement_name, a.prime_agreement, a.instrument
                      FROM v_restatement r
                      LEFT JOIN award a USING (award_id)
                     WHERE r.period = %s AND r.status = ANY(%s)
                     ORDER BY r.over_collected DESC NULLS LAST,
                              r.award_id""",
                 (period, list(STANDING)))
    if not rows:
        raise HTTPException(404, (
            f"No restatement is standing as a claim for {period}, so there "
            f"is nothing to reconcile. POST /api/restate is what makes one, "
            f"and it is a judgment."))

    ours = [r for r in rows if _AM_PRIME in (r.get("prime_agreement") or "")]
    others = [r for r in rows if r not in ours]
    if not ours:
        raise HTTPException(409, (
            f"No standing restatement for {period} is on an award whose "
            f"prime is {_AM_PRIME}, so there is no America Makes "
            f"reconciliation to draw. {len(rows)} restatement(s) stand on "
            f"other programmes and each is its own conversation."))

    # Two of these three run against YBI, and the page raises the give-back
    # first — `AMERICA_MAKES_RESTATEMENT.md` records why: a page that led
    # with the claim and mentioned the credits underneath is read once. The
    # ORDER BY does it, so the order is a property of the figures rather
    # than of a list written here.
    contracts = tuple(
        Contract(award_id=r["award_id"], objective_id=r["objective_id"],
                 title=(r.get("agreement_name") or r.get("instrument") or ""),
                 invoices=r["invoices"] or 0,
                 billed=money(r["billed_total"] or 0),
                 direct_supported=money(r["direct_supported"] or 0),
                 indirect_supported=money(r["indirect_rebuilt"] or 0),
                 supported=money(r["supported_total"] or 0),
                 indirect_billed=money(r["indirect_billed"] or 0),
                 to_return=money(r["over_collected"] or 0),
                 to_claim=money(r["under_recovered"] or 0),
                 status=r["status"],
                 accepted_on=(r["decided_at"].date()
                              if r.get("decided_at") and r["status"] == "ACCEPTED"
                              else None),
                 modification_ref=r.get("modification_ref") or "")
        for r in ours)

    first = ours[0]
    clauses = []
    for r in ours:
        # Quoted from `award_term`, never recalled — `056` found three
        # provisions on two awards cited to clauses those agreements do not
        # contain, and this page puts the citation in front of the person
        # signing it.
        cl = one("""SELECT term_value, citation FROM award_term
                     WHERE award_id = %s AND term_key = 'Change of basis'""",
                 (r["award_id"],)) or {}
        clauses.append((r["objective_id"], cl.get("term_value") or "",
                        cl.get("citation") or ""))

    seal = one("""SELECT sealed_at, seal_hash,
                         (SELECT count(*) FROM decision d
                           WHERE d.set_id = ds.set_id AND d.reversed_at IS NULL)
                         AS judgments
                    FROM decision_set ds
                   WHERE ds.period = %s AND ds.sealed_at IS NOT NULL
                   ORDER BY ds.sealed_at DESC LIMIT 1""", (period,)) or {}

    anchors = query("""SELECT control, state FROM v_rate_anchor
                        WHERE period = %s""", (period,))
    pools = one("""SELECT count(*) FILTER (WHERE ties) AS tie,
                          count(*) AS n FROM v_rate_buildup
                    WHERE period = %s""", (period,)) or {}

    # Each ground is a statement the record can be asked to prove. "The rate
    # is reasonable" is an adjective and belongs on nobody's letterhead.
    grounds = [
        "The classifications were sealed before any rate was computed and "
        "the rate carries the seal, enforced by the database rather than by "
        "assertion: a rate whose seal does not match a sealed set is "
        "refused, and changing a classification afterwards requires an "
        "unsealing with a written reason, which supersedes the rate.",
        "The fringe rate is anchored at both ends to source documents — the "
        "profit and loss's six fringe accounts over the payroll register's "
        "wages — so it falls out of the judgments rather than being asserted.",
    ]
    # One ground, not two. The build-up rows and the rate anchors are both
    # "the arithmetic reconciles", and a page that spent two numbered points
    # on one claim reads as padding — which is the opposite of what a
    # numbered list of reasons is for.
    tied = sum(1 for a in anchors if a["state"] == "TIES")
    if pools.get("n") or anchors:
        grounds.append(
            f"Every pool reconciles to the general ledger — {pools.get('tie', 0)} "
            f"of {pools.get('n', 0)} build-up rows and {tied} of "
            f"{len(anchors)} independent rate anchors tie — and the eleven "
            f"cross-reference controls between the ledger, the profit and "
            f"loss, the balance sheet and the payroll register must all tie "
            f"before a rate can be computed at all.")
    grounds.append(
        "The 200.465 carve-out removes the occupancy cost of let and vacant "
        "space from the pool before any federal rate is taken, and 200.436(b) "
        "removes depreciation on federally funded assets — recorded "
        "adjustments with their citations, not estimates.")

    cert = rate_certification(period) or {}
    return Reconciliation(
        period=period, issued_on=date.today(), remit_to=_YBI,
        bill_to=Party(first.get("sponsor") or "NCDMM", _SPONSOR_ADDRESS),
        programme=f"America Makes · prime {_AM_PRIME}",
        contracts=contracts,
        rates=_rate_lines(period, first.get("rate_id")),
        basis=("Indirect is applied to modified total direct cost, as "
               "2 CFR 200.1 defines it."),
        admin_labour_basis=(one("""SELECT admin_labour_basis FROM rate
                                    WHERE rate_id = %s""",
                                (first.get("rate_id"),)) or {}
                            ).get("admin_labour_basis") or "",
        seal_hash=first.get("seal_hash") or seal.get("seal_hash") or "",
        judgments=seal.get("judgments") or 0,
        clauses=tuple(clauses),
        grounds=tuple(grounds),
        # Anything the register has since overtaken comes first, for the
        # reason it does on the amendment papers: a reader who reaches the
        # fourth bullet before learning the figures measure a population
        # that has moved has already formed a view.
        # Above the figures, because these are the ones that make the table
        # itself untrustworthy rather than merely incomplete.
        #
        # One sentence for all of them, not one per award. Every standing
        # restatement is measured on the same rate, so three copies of one
        # fact at the top of the page is the defect the evidence screen
        # already learned — *thirty-two unread workbooks buried three real
        # proposals* — and the awards are named rather than counted.
        warnings=_stale_rate_warning(ours),
        caveats=tuple(
            f"Overtaken — {r['objective_id']} measured {r['invoices']} "
            f"invoice(s) totalling {r['billed_total']:,.2f}, and the "
            f"register now holds {r['register_invoices']} totalling "
            f"{r['register_billed']:,.2f}. Recompute before this is sent."
            for r in ours if r.get("still_agrees") is False),
        excluded=tuple(
            (r["objective_id"],
             "administered by NCDMM and primed elsewhere"
             + (f" ({r['prime_agreement']})" if r.get("prime_agreement") else "")
             + f". {_fmt(r['over_collected'], r['under_recovered'])} stands "
             f"on it and is settled against that programme, not this one.")
            for r in others),
        certified=bool(cert.get("certified")) and not cert.get("rehearsal"),
        certification_line=" ".join(certification_lines(cert)),
        reference=f"America Makes · {period}")


def _stale_rate_warning(rows: list[dict]) -> tuple[str, ...]:
    """One line per rate that has been superseded, naming the awards on it."""
    by_rate: dict[tuple, list[str]] = {}
    for r in rows:
        if r.get("rate_is_live") is False:
            key = (r["rate_kind"], r["rate_applied"], r["rate_status"])
            by_rate.setdefault(key, []).append(r["objective_id"])
    return tuple(
        f"Measured on a rate that no longer stands — "
        f"{', '.join(sorted(names))} "
        f"{'was' if len(names) == 1 else 'were'} computed against "
        f"{(kind_rate or 0) * 100:.2f}% {kind}, which is now {status}. Every "
        f"figure below is against arithmetic the record has moved past. "
        f"Recompute before this is sent."
        for (kind, kind_rate, status), names in by_rate.items())


def _fmt(over, under) -> str:
    over, under = money(over or 0), money(under or 0)
    if over:
        return f"{over:,.2f} to return"
    if under:
        return f"{under:,.2f} to claim"
    return "Nothing"


