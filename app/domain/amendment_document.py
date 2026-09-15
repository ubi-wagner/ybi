"""The two papers a restated invoice cannot travel without.

`restate_2025_invoices.py` renders the America Makes invoices rebuilt on the
negotiated rate. A payables clerk holding one of those and nothing else has
two questions the invoice itself cannot answer:

  * **Why is this different from the one I paid?** The face shows a labour
    line taken down and an indirect line added, and nothing on it names the
    authority for the change. §4.4 of the executed agreement is that
    authority, and `acceptance_names_its_modification` in the schema already
    refuses a restatement that cannot name it — which this repository calls
    *the most likely thing in this whole exercise to become a finding.*
  * **How do I say yes?** Nothing in the record is a claim until a sponsor
    answers in writing, and there was no form for them to answer on.

So: an **amendment memo** that states the change and cites the clause from
the record, and an **acceptance form** they sign. Both render on the face
`invoice_document.py` already establishes, because a sponsor's payables
recognises that letterhead and three different faces from one organisation
read as three organisations.

Four rules, each one this system already keeps somewhere:

  * **Never net an over-collection against an under-recovery.** The form has
    two columns and no third. `v_restatement` had `net_movement`
    pre-computed, in a column named as though it were the summary, and `061`
    removed it: *$120,000 to ask for and $120,000 to give back is not a quiet
    year.* A form that printed one number would put that back on paper, in
    front of the sponsor, which is the worst place for it.
  * **A proposal is not a position.** Everything is PROPOSED until NCDMM
    answers, and the memo says so in its first line rather than in a footnote.
  * **The clause is quoted, never recalled.** Every citation on these papers
    is passed in from `award_term`, which was read out of the executed
    agreement — and `056` found three provisions on two awards cited to
    clauses those agreements do not contain. A memo that recited a clause
    from memory would be that defect on a sponsor's desk.
  * **The band prints in both directions**, as `082` requires of everything
    that leaves the building.

Pure, like the invoice renderer: no database, and deterministic so a filing
route can content-address what it produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from app.domain.core import money
from app.domain.invoice_document import (INK, MARGIN, MUTED, PAGE_H, PAGE_W,
                                         TABLE_W, Party, _fmt_date,
                                         _fmt_money, _page_number, _wrap)

BAND = colors.HexColor("#F3F1EC")
RULE = colors.HexColor("#D8D4CC")
WARN_BG = colors.HexColor("#F8E7E4")
WARN_INK = colors.HexColor("#8C2A1E")


@dataclass(frozen=True)
class Movement:
    """One invoice, and which way the money runs on it.

    Two fields and never a third. `under_recovered` is money to ask for;
    `over_collected` is money to give back. A single signed figure would be
    tidier and is exactly what `061` took out of the view.
    """

    #: What this row covers. `v_restatement` aggregates to the **objective**
    #: — its `invoices` column is a *count*, and a first draft printed that
    #: count under a heading reading INVOICE, so the form told a payables
    #: clerk to match on invoice "1". The unit is named for what it is, and
    #: the numbers it covers are listed beside it.
    covers: str
    objective: str
    award: str
    as_billed: Decimal
    invoice_count: int = 0
    invoice_numbers: str = ""
    under_recovered: Decimal = Decimal("0")
    over_collected: Decimal = Decimal("0")
    finding: str = ""

    def __post_init__(self) -> None:
        if self.under_recovered and self.over_collected:
            raise ValueError(
                f"{self.covers} carries both an "
                f"under-recovery and an over-collection. One invoice runs one "
                f"way; two directions on one line is the netting this "
                f"document exists to refuse.")


@dataclass(frozen=True)
class AmendmentPapers:
    """Everything both papers print, read from the record by the caller."""

    period: str
    issued_on: date
    remit_to: Party
    bill_to: Party
    award: str
    award_title: str
    #: The clause that authorises a change of basis, quoted from `award_term`
    #: with its own citation. Empty where the agreement carries none — which
    #: is a fact about the award and is printed as one, not papered over.
    modification_clause: str = ""
    modification_citation: str = ""
    #: What was billed, and on what basis, as the register holds it.
    as_billed_basis: str = ""
    #: What is now claimed, and on what basis.
    proposed_basis: str = ""
    rate_kind: str = ""
    rate: Decimal | None = None
    base_type: str = ""
    seal_hash: str = ""
    movements: tuple[Movement, ...] = ()
    #: **The position, passed in — never summed from the lines.**
    #:
    #: `invoice_document.py` takes its header total the same way and for the
    #: same reason: *an invoice that does not foot can print both figures and
    #: say so instead of agreeing with itself by construction.* Here the two
    #: genuinely differ and the difference is the whole finding.
    #:
    #: A `Movement` is the **as-billed reading** of one invoice — the indirect
    #: line on its face against what the rate supports on its own base. The
    #: position is `restatement.under_recovered` / `over_collected`, which the
    #: engine rebuilds for the whole objective against the cost record. On the
    #: America Makes awards the indirect was recovered *inside a loaded labour
    #: rate*, so not one invoice carries an indirect line and every line reads
    #: as under-recovery — $254,808.06 "to claim" on Drive AM, where the
    #: rebuilt position is $58,786.31 to **give back**. A form that summed the
    #: lines would put a claim in front of NCDMM that runs the opposite way
    #: from what the record supports.
    position_under: Decimal = Decimal("0")
    position_over: Decimal = Decimal("0")
    #: What is unfinished, above the figures, as everywhere else here.
    caveats: tuple[str, ...] = ()
    certified: bool = False
    certification_line: str = ""
    reference: str = ""

    #: Deliberately no check that only one of the two is set. A `Movement` is
    #: one invoice and runs one way, so two directions there is a netting
    #: error. These papers cover an **award**, which can carry more than one
    #: objective, and one objective under-recovering while another
    #: over-collects is exactly the case the two columns exist for. Refusing
    #: it here would force the caller to net them to get a document out.

    @property
    def to_claim(self) -> Decimal:
        """What NCDMM is being asked for. The recorded position, not a sum."""
        return money(self.position_under)

    @property
    def to_return(self) -> Decimal:
        """What YBI is giving back. The recorded position, not a sum."""
        return money(self.position_over)

    @property
    def line_claim(self) -> Decimal:
        """The as-billed reading added up — detail, and never the ask."""
        return money(sum((m.under_recovered for m in self.movements), Decimal("0")))

    @property
    def line_return(self) -> Decimal:
        return money(sum((m.over_collected for m in self.movements), Decimal("0")))

    @property
    def lines_foot_to_the_position(self) -> bool:
        return (self.line_claim == self.to_claim
                and self.line_return == self.to_return)


# ── the furniture both papers share ──────────────────────────────────

def _head(c, p: AmendmentPapers, title: str, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGIN, y, p.remit_to.name)
    y -= 15
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    for part in (p.remit_to.address, p.remit_to.detail):
        for row in (part.split("\n") if part else []):
            c.drawString(MARGIN, y, row)
            y -= 11

    right = PAGE_W - MARGIN
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 17)
    c.drawRightString(right, PAGE_H - MARGIN, title)
    c.setFont("Helvetica", 10)
    c.setFillColor(MUTED)
    c.drawRightString(right, PAGE_H - MARGIN - 17, _fmt_date(p.issued_on))
    if p.reference:
        c.drawRightString(right, PAGE_H - MARGIN - 30, p.reference)
    return min(y, PAGE_H - MARGIN - 44) - 14


def _proposed_band(c, y: float) -> float:
    """PROPOSED, before anything else.

    `061`'s rule on the screen, on the paper: *a proposal is not a position.*
    A sponsor who reads the total first has already formed a view about what
    is being asserted.
    """
    c.setFillColor(BAND)
    c.rect(MARGIN, y - 6, TABLE_W, 22, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN + 6, y + 4, "PROPOSED — NOT A CLAIM")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(MARGIN + 150, y + 4,
                 "Nothing here is billed until NCDMM accepts it in writing.")
    return y - 22


def _certification(c, p: AmendmentPapers, y: float) -> float:
    """The same question `082` puts on an invoice, in both directions."""
    if p.certified:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGIN, y,
                     p.certification_line or "Certified against the rate on file.")
        return y - 16
    c.setFillColor(WARN_BG)
    c.rect(MARGIN, y - 13, TABLE_W, 26, stroke=0, fill=1)
    c.setFillColor(WARN_INK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 6, y + 3, "NOT CERTIFIED")
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN + 6, y - 7,
                 p.certification_line
                 or "The rate this is built on carries no signature.")
    return y - 32


def _para(c, text: str, y: float, *, size: float = 9.5,
          lead: float = 12.5, colour=INK) -> float:
    c.setFillColor(colour)
    c.setFont("Helvetica", size)
    for row in _wrap(c, text, TABLE_W, "Helvetica", size):
        c.drawString(MARGIN, y, row)
        y -= lead
    return y - 4


def _label(c, text: str, y: float) -> float:
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN, y, text.upper())
    return y - 13


def _caveats(c, p: AmendmentPapers, y: float) -> float:
    if not p.caveats:
        return y
    y = _label(c, "What is not finished", y)
    for line in p.caveats:
        y = _para(c, f"·  {line}", y, size=8.5, lead=11, colour=MUTED)
    return y


# ── the memo ─────────────────────────────────────────────────────────

def render_memo(p: AmendmentPapers) -> bytes:
    """Why the invoices are being reissued, and under what authority."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    c.setTitle(f"Amendment memorandum — {p.award} — {p.period}")

    y = _head(c, p, "AMENDMENT", PAGE_H - MARGIN)
    y = _proposed_band(c, y) - 6
    y = _certification(c, p, y) - 4

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN, y, "TO")
    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    yy = y - 13
    for row in ([p.bill_to.name] + (p.bill_to.address or "").split("\n")):
        if row:
            c.drawString(MARGIN, yy, row)
            yy -= 12
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 3.55 * 72, y, "AWARD")
    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    c.drawRightString(PAGE_W - MARGIN, y, p.award)
    if p.award_title:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawRightString(PAGE_W - MARGIN, y - 13, p.award_title[:54])
    y = yy - 12

    y = _label(c, "What is being proposed", y)
    y = _para(c, (
        f"Youngstown Business Incubator proposes to reissue the {p.period} "
        f"invoices listed overleaf on a negotiated indirect cost rate. The "
        f"work, the period of performance and the deliverables are unchanged. "
        f"What changes is the basis on which indirect cost is claimed."), y)

    if p.as_billed_basis:
        y = _label(c, "As billed", y)
        y = _para(c, p.as_billed_basis, y)
    if p.proposed_basis:
        y = _label(c, "As proposed", y)
        y = _para(c, p.proposed_basis, y)

    if p.rate is not None:
        y = _label(c, "The rate", y)
        y = _para(c, (
            f"{p.rate_kind or 'Indirect'} at {p.rate * 100:.2f}% on "
            f"{p.base_type or 'the modified total direct cost base'}. The rate "
            f"is computed only from classifications sealed before it, and it "
            f"carries that seal: {p.seal_hash[:16] or '—'}…  The sealing is "
            f"what lets this be checked rather than taken on trust — the "
            f"judgments behind the rate were fixed and hashed before any rate "
            f"existed, so none of them was chosen to produce it."), y)

    y = _label(c, "Authority", y)
    if p.modification_clause:
        y = _para(c, f"“{p.modification_clause}”", y, size=9)
        y = _para(c, f"— {p.modification_citation or 'the executed agreement'}",
                  y, size=8.5, lead=11, colour=MUTED)
        y = _para(c, (
            "This memorandum is that request. No restated invoice is a claim "
            "against the award until NCDMM incorporates the change in a "
            "written modification, and none has been submitted for payment."), y)
    else:
        y = _para(c, (
            "The executed agreement for this award carries no clause on record "
            "governing a change of basis. That is a fact about the agreement "
            "rather than an omission here, and it is the first thing to settle: "
            "YBI is asking NCDMM to name the instrument this should be made "
            "under."), y)

    y = _para(c, (
        "Both directions are shown separately on the acceptance form. Where "
        "this award over-collected, YBI is proposing to give that money back; "
        "where it under-recovered, YBI is asking for it. These are two "
        "conversations and a single net figure would hide both."), y)

    # The direction, on the memo, so a reader knows which conversation this
    # is before they reach the form. Said plainly and in this order because
    # an organisation that raises its own over-collection first is one the
    # rest of the ask can be believed from.
    if p.to_return:
        y = _para(c, (
            f"On this award the rebuild against the cost record shows "
            f"{_fmt_money(p.to_return)} collected above what {p.period} "
            f"supports. YBI is raising that itself and proposes to return "
            f"it." + (f" A further {_fmt_money(p.to_claim)} is under-recovered "
                      f"and is asked for separately." if p.to_claim else "")), y)
    elif p.to_claim:
        y = _para(c, (
            f"On this award the rebuild against the cost record shows "
            f"{_fmt_money(p.to_claim)} of indirect cost supported by "
            f"{p.period} and not recovered. That is what is being asked "
            f"for."), y)

    y = _caveats(c, p, y)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, MARGIN - 18,
                 "Generated from the cost record. Every figure is read from "
                 "the row it was recorded in.")
    _page_number(c, 1, 1)
    c.showPage()
    c.save()
    return buf.getvalue()


# ── the acceptance form ──────────────────────────────────────────────

#: One row is one invoice — `restatement_line`, which is the unit the engine
#: measured in. The count column a first draft carried printed "1" on every
#: row, which is a column that says nothing; and before that it printed
#: `v_restatement.invoices`, a *count*, under a heading reading INVOICE.
_COLS = (("Invoice", "l", 74.0), ("Project", "l", 106.0),
         ("As billed", "r", 76.0), ("To claim", "r", 76.0),
         ("To return", "r", 76.0))


def _form_heads(c, y: float) -> float:
    c.setFillColor(BAND)
    c.rect(MARGIN, y - 17, TABLE_W, 17, stroke=0, fill=1)
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    x = MARGIN + 5
    for label, align, w in _COLS:
        if align == "l":
            c.drawString(x, y - 12, label.upper())
        else:
            c.drawRightString(x + w - 10, y - 12, label.upper())
        x += w
    return y - 17


def _form_row(c, m: Movement, y: float, shade: bool) -> float:
    h = 19.0
    extra = 0.0
    detail = " ".join(x for x in (m.invoice_numbers, m.finding) if x)
    note = _wrap(c, detail, TABLE_W - 20, "Helvetica", 7.5) if detail else []
    extra = 10.0 * len(note)
    if shade:
        c.setFillColor(colors.HexColor("#FAFAF8"))
        c.rect(MARGIN, y - h - extra, TABLE_W, h + extra, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    x = MARGIN + 5
    values = [m.covers, m.objective,
              _fmt_money(m.as_billed),
              _fmt_money(m.under_recovered) if m.under_recovered else "—",
              _fmt_money(m.over_collected) if m.over_collected else "—"]
    for (label, align, w), value in zip(_COLS, values):
        if align == "l":
            c.drawString(x, y - 13, str(value))
        else:
            c.drawRightString(x + w - 10, y - 13, str(value))
        x += w
    yy = y - h
    if note:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        for row in note:
            c.drawString(MARGIN + 5, yy - 7, row)
            yy -= 10
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(MARGIN, yy, MARGIN + TABLE_W, yy)
    return yy


def _signature_block(c, p: AmendmentPapers, y: float) -> float:
    y = _label(c, "Accepted for NCDMM", y)
    c.setStrokeColor(INK)
    c.setLineWidth(0.7)
    half = TABLE_W / 2 - 14
    for i, label in enumerate(("Signature", "Printed name")):
        x = MARGIN + i * (half + 28)
        c.line(x, y - 22, x + half, y - 22)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(x, y - 32, label)
    y -= 52
    for i, label in enumerate(("Title", "Date")):
        x = MARGIN + i * (half + 28)
        c.line(x, y - 22, x + half, y - 22)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(x, y - 32, label)
    y -= 50
    y = _label(c, "Modification this is made under", y)
    c.setStrokeColor(INK)
    c.line(MARGIN, y - 20, MARGIN + TABLE_W, y - 20)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, y - 30,
                 "Number and date of the written modification incorporating "
                 "this change of basis. YBI records no acceptance without it.")
    return y - 46


def render_acceptance(p: AmendmentPapers) -> bytes:
    """What NCDMM signs, with both directions kept apart."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    c.setTitle(f"Acceptance — {p.award} — {p.period}")

    y = _head(c, p, "ACCEPTANCE", PAGE_H - MARGIN)
    y = _proposed_band(c, y) - 6
    y = _certification(c, p, y) - 4

    y = _para(c, (
        f"{p.award}{(' — ' + p.award_title) if p.award_title else ''}. The "
        f"{p.period} invoices below, reissued on the negotiated indirect rate "
        f"described in the accompanying amendment memorandum."), y)

    y = _form_heads(c, y)
    for i, m in enumerate(p.movements):
        y = _form_row(c, m, y, shade=bool(i % 2))

    # Two rows, and the second is the ask. The first adds up the as-billed
    # reading of each invoice; the second is the position the restatement
    # recorded against the cost record. Printing only the sum would be the
    # form agreeing with itself by construction, which is what
    # `invoice_document.py` refuses on the invoice face for the same reason.
    x = MARGIN + 5 + _COLS[0][2] + _COLS[1][2]
    c1 = x + _COLS[2][2] + _COLS[3][2] - 10
    c2 = x + _COLS[2][2] + _COLS[3][2] + _COLS[4][2] - 10

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(x + _COLS[2][2] - 10, y - 15, "As billed, line by line")
    c.drawRightString(c1, y - 15, _fmt_money(p.line_claim))
    c.drawRightString(c2, y - 15, _fmt_money(p.line_return))

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(x + _COLS[2][2] - 10, y - 31, "THE POSITION")
    c.drawRightString(c1, y - 31, _fmt_money(p.to_claim))
    c.drawRightString(c2, y - 31, _fmt_money(p.to_return))
    c.setStrokeColor(RULE)
    c.line(x, y - 36, MARGIN + TABLE_W, y - 36)
    y -= 46

    y = _para(c, (
        "The two money columns are deliberately not added together. One is "
        "money YBI is asking for and the other is money YBI is giving back; a "
        "net figure would settle both in one line and say nothing about "
        "either."), y, size=8, lead=10, colour=MUTED)

    if not p.lines_foot_to_the_position:
        y = _para(c, (
            "The two rows are different readings and are not meant to add to "
            "each other. Line by line compares the indirect line on the face "
            "of each invoice against what the rate supports on that invoice's "
            "own base. THE POSITION is the whole objective rebuilt against "
            "the cost record — what the year supports against what was "
            "actually billed — and it is the only figure this form asks "
            "NCDMM to accept. Where indirect was recovered inside a loaded "
            "labour rate no invoice carries an indirect line at all, so the "
            "line-by-line reading shows recovery forgone that the rebuild "
            "then finds was collected."),
            y, size=8, lead=10, colour=MUTED)

    y = _caveats(c, p, y)
    y -= 6
    y = _signature_block(c, p, y)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, MARGIN - 18,
                 "Return one signed copy to the address above. YBI records "
                 "the acceptance against the modification named.")
    _page_number(c, 1, 1)
    c.showPage()
    c.save()
    return buf.getvalue()
