"""Rendering an invoice onto the face it was issued on.

The three America Makes invoices are the template, because they are what
NCDMM's accounts payable already recognises. Their shape:

    a masthead with who is billing and where to remit
    INVOICE, its number, and the date
    a BILL TO block, the purchase order, terms, and the service period
    a table — ACTIVITY, DESCRIPTION, QTY, RATE, AMOUNT
    a total

Everything above and below the table is fixed. **The table is the part that
expands**, because an invoice has as many lines as it has, and the originals
run from four to six. It paginates when it has to, repeating the column
headers and saying that it is continued, so a reader never meets an orphaned
row and never has to guess whether a total covers the page or the invoice.

Two things this module will not do.

It does not compute anything. Every figure is passed in, read from the row it
was recorded in — the same rule the review screens follow, for the same
reason: a figure derived twice is one that can disagree with itself.

And it does not pretend. An invoice already issued has a document of record,
which is the PDF the sponsor holds; what this renders is a *reproduction from
the register*, and it says so on its face. Only an invoice this organisation
is actually issuing — a draft, or a restatement — is rendered as an original.
A reproduction that could be mistaken for the issued document is a forgery
with good intentions, and the distinction is one line of code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas

from .core import money

__all__ = ["Party", "DocumentLine", "InvoiceDocument", "render"]

#: The register records categories; the invoice face prints the words the
#: sponsor's accounts payable reads. Anything unmapped prints as itself
#: rather than as a blank, because a category nobody thought about should be
#: visible on the invoice, not silently unlabelled.
CATEGORY_LABEL = {
    "LABOR": "Labor",
    "FRINGE": "Fringe",
    "TRAVEL": "Travel",
    "MATERIALS": "Materials",
    "CONSULTANT": "Consultant",
    "SUBAWARD": "Subcontract",
    "ODC": "ODC's",
    "EQUIPMENT": "Equipment",
    "INDIRECT": "Indirects",
    "FEE": "Fee",
    "OTHER": "Other",
}

PAGE_W, PAGE_H = LETTER
MARGIN = 0.75 * inch
INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#6B6B6B")
RULE = colors.HexColor("#BFBFBF")
BAND = colors.HexColor("#1F3B4D")

#: Column geometry, left edge and width, in points from the left margin.
#: ACTIVITY is narrow because the originals leave it empty; DESCRIPTION takes
#: the slack, because that is where a line says what it is for.
COLUMNS = [
    ("ACTIVITY",    0.00 * inch, 1.05 * inch, "left"),
    ("DESCRIPTION", 1.05 * inch, 3.00 * inch, "left"),
    ("QTY",         4.05 * inch, 0.55 * inch, "right"),
    ("RATE",        4.60 * inch, 1.15 * inch, "right"),
    ("AMOUNT",      5.75 * inch, 1.25 * inch, "right"),
]
TABLE_W = sum(w for _, _, w, _ in COLUMNS)


@dataclass(frozen=True)
class Party:
    name: str
    address: str = ""
    detail: str = ""


@dataclass(frozen=True)
class DocumentLine:
    """One row of the expanding middle.

    `amount` is what prints. `quantity` and `rate` print as recorded — on the
    originals every line is quantity one at a rate equal to the whole amount,
    which is the shape that hides a burdened labour rate, and reproducing it
    faithfully is the point rather than an oversight to correct here.
    """
    category: str
    amount: Decimal
    description: str = ""
    activity: str = ""
    quantity: Decimal = Decimal("1")
    rate: Decimal | None = None
    personnel: str = ""

    @property
    def label(self) -> str:
        return CATEGORY_LABEL.get(self.category, self.category)

    @property
    def unit_rate(self) -> Decimal:
        return self.amount if self.rate is None else self.rate


@dataclass(frozen=True)
class InvoiceDocument:
    number: str
    invoice_date: date
    remit_to: Party
    bill_to: Party
    lines: tuple[DocumentLine, ...] = ()
    total: Decimal | None = None
    terms: str = ""
    po_number: str = ""
    due_on: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    objective: str = ""
    award: str = ""
    #: False for anything already issued: the sponsor holds the document of
    #: record and this is a reproduction from the register.
    is_original: bool = False
    status: str = ""
    source_document: str = ""
    #: Printed under the total, above the fold. Anything the reader has to
    #: know before they act on the figure — that classification is open,
    #: that an indirect line was never billed.
    caveats: tuple[str, ...] = ()

    @property
    def footing(self) -> Decimal:
        """What the lines come to.

        Kept separate from `total`, which is what the register recorded. They
        should agree — a deferred trigger refuses an invoice where they do
        not — and `render` prints both if they ever disagree rather than
        picking one and looking tidy.
        """
        return money(sum((l.amount for l in self.lines), Decimal("0")))


def _fmt_money(value: Decimal) -> str:
    v = money(value)
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def _fmt_qty(value: Decimal) -> str:
    q = Decimal(value).normalize()
    return f"{q:f}" if q == q.to_integral() else f"{Decimal(value):.2f}"


def _fmt_date(value: date | None) -> str:
    return value.strftime("%m/%d/%Y") if value else ""


def _wrap(c, text: str, width: float, font: str, size: float) -> list[str]:
    """Break `text` to `width`, breaking inside a long word if it will not fit.

    A description is free text somebody typed; a personnel list can run to
    five surnames. Overflowing the column silently would put it under the QTY
    figures, which is how an invoice starts reading as two invoices.
    """
    if not text:
        return []
    out: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            trial = f"{line} {word}".strip()
            if c.stringWidth(trial, font, size) <= width:
                line = trial
                continue
            if line:
                out.append(line)
            while c.stringWidth(word, font, size) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and c.stringWidth(word[:cut], font, size) > width:
                    cut -= 1
                out.append(word[:cut])
                word = word[cut:]
            line = word
        out.append(line)
    return out


def _masthead(c, doc: InvoiceDocument, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGIN, y, doc.remit_to.name)
    y -= 15
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    for part in (doc.remit_to.address, doc.remit_to.detail):
        for row in part.split("\n") if part else []:
            c.drawString(MARGIN, y, row)
            y -= 11

    # INVOICE, its number and date, set against the right margin so the eye
    # lands on the number it will be quoted by.
    right = PAGE_W - MARGIN
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(right, PAGE_H - MARGIN, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(right, PAGE_H - MARGIN - 18, f"#{doc.number}")
    c.setFillColor(MUTED)
    c.drawRightString(right, PAGE_H - MARGIN - 32, _fmt_date(doc.invoice_date))
    return min(y, PAGE_H - MARGIN - 46) - 12


def _parties(c, doc: InvoiceDocument, y: float) -> float:
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN, y, "BILL TO")
    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    yy = y - 13
    for row in ([doc.bill_to.name] + doc.bill_to.address.split("\n")):
        if row:
            c.drawString(MARGIN, yy, row)
            yy -= 12

    # The facts a payables clerk matches on, each one labelled, in a block
    # that starts at the same height as BILL TO.
    facts = [("P.O. NUMBER", doc.po_number), ("TERMS", doc.terms),
             ("DUE DATE", _fmt_date(doc.due_on))]
    if doc.service_from or doc.service_to:
        facts.append(("SERVICE PERIOD",
                      f"{_fmt_date(doc.service_from)} – {_fmt_date(doc.service_to)}"))
    if doc.objective:
        facts.append(("PROJECT", doc.objective))

    fy = y
    label_x = MARGIN + 3.55 * inch
    for label, value in facts:
        if not value:
            continue
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(label_x, fy, label)
        c.setFillColor(INK)
        c.setFont("Helvetica", 10)
        c.drawRightString(PAGE_W - MARGIN, fy, str(value))
        fy -= 15
    return min(yy, fy) - 14


ROW_PAD = 5.0          # above and below the content of a row
TEXT_LEAD = 11.0       # baseline to baseline within a row
NOTE_LEAD = 10.0       # the same, for the smaller personnel line


def _column_heads(c, top: float) -> float:
    """Draw the header band with its top edge at `top`; return the next top.

    Every function in this table works in row *tops* rather than baselines.
    Mixing the two is what put the striping 3pt out of step with the rules
    and made each shaded band bleed into the row beneath it.
    """
    height = 17.0
    c.setFillColor(BAND)
    c.rect(MARGIN, top - height, TABLE_W, height, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    base = top - height + 6
    for label, x, w, align in COLUMNS:
        if align == "right":
            c.drawRightString(MARGIN + x + w - 5, base, label)
        else:
            c.drawString(MARGIN + x + 5, base, label)
    return top - height


def _rows_of(c, line: DocumentLine) -> tuple[list[str], list[str]]:
    desc_w = COLUMNS[1][2] - 10
    body = _wrap(c, line.description, desc_w, "Helvetica", 9) or [""]
    note = _wrap(c, line.personnel, desc_w, "Helvetica-Oblique", 8)
    return body, note


def _line_height(c, line: DocumentLine) -> float:
    """How tall the row will be once its description has wrapped.

    Measured before anything is drawn, so a row is never begun near the foot
    of a page and finished on the next one.
    """
    body, note = _rows_of(c, line)
    return (2 * ROW_PAD + TEXT_LEAD * len(body) + NOTE_LEAD * len(note))


def _draw_line(c, line: DocumentLine, top: float, shade: bool) -> float:
    height = _line_height(c, line)
    bottom = top - height

    if shade:
        c.setFillColor(colors.HexColor("#F4F6F7"))
        c.rect(MARGIN, bottom, TABLE_W, height, stroke=0, fill=1)

    body, note = _rows_of(c, line)
    first = top - ROW_PAD - 8          # baseline of the first line of text

    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN + COLUMNS[0][1] + 5, first, line.activity or "")

    y = first
    for row in body:
        c.setFont("Helvetica", 9)
        c.setFillColor(INK)
        c.drawString(MARGIN + COLUMNS[1][1] + 5, y, row)
        y -= TEXT_LEAD
    # Who the labour was. On the originals this is the only thing tying a
    # flat monthly amount to people, so it prints rather than being kept for
    # the register's own use.
    for row in note:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(MUTED)
        c.drawString(MARGIN + COLUMNS[1][1] + 5, y, row)
        y -= NOTE_LEAD

    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    c.drawRightString(MARGIN + COLUMNS[2][1] + COLUMNS[2][2] - 5, first,
                      _fmt_qty(line.quantity))
    c.drawRightString(MARGIN + COLUMNS[3][1] + COLUMNS[3][2] - 5, first,
                      _fmt_money(line.unit_rate))
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(MARGIN + COLUMNS[4][1] + COLUMNS[4][2] - 5, first,
                      _fmt_money(line.amount))

    c.setStrokeColor(RULE)
    c.setLineWidth(0.4)
    c.line(MARGIN, bottom, MARGIN + TABLE_W, bottom)
    return bottom


def _label_the_category(lines: tuple[DocumentLine, ...]) -> tuple[DocumentLine, ...]:
    """Put the category in ACTIVITY where the invoice left it blank.

    The originals carry an empty ACTIVITY column and say what a line is only
    in the description, which is how invoice 10018 reads as two numbers with
    no names on them. The category is already recorded; printing it costs
    nothing and is the difference between a reader seeing "19,145.79" and
    seeing that it is ODCs. An activity the invoice actually carried is left
    exactly as it was.
    """
    return tuple(
        l if l.activity else DocumentLine(
            category=l.category, amount=l.amount, description=l.description,
            activity=l.label, quantity=l.quantity, rate=l.rate,
            personnel=l.personnel)
        for l in lines)


#: How much room the total block and the caveats need. A page break is taken
#: rather than crowding them against the footer.
FOOT_RESERVE = 120.0


def _foot(c, doc: InvoiceDocument, y: float) -> None:
    right = PAGE_W - MARGIN
    c.setStrokeColor(BAND)
    c.setLineWidth(1.1)
    c.line(MARGIN + COLUMNS[3][1], y + 14, right, y + 14)

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN + COLUMNS[3][1], y, "TOTAL DUE")
    c.setFont("Helvetica-Bold", 14)
    total = doc.total if doc.total is not None else doc.footing
    c.drawRightString(right, y - 1, f"${_fmt_money(total)}")
    y -= 22

    # If the header total and the lines disagree, both print. The schema has
    # a deferred trigger that should make this unreachable; if it is ever
    # reached, the invoice says so rather than choosing the tidier number.
    if doc.total is not None and money(doc.total) != doc.footing:
        c.setFillColor(colors.HexColor("#B03030"))
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(right, y,
                          f"Lines total {_fmt_money(doc.footing)} — this "
                          f"invoice does not foot.")
        y -= 16

    for caveat in doc.caveats:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 8.5)
        for row in _wrap(c, caveat, TABLE_W, "Helvetica-Oblique", 8.5):
            c.drawString(MARGIN, y, row)
            y -= 10
        y -= 3


def _provenance(c, doc: InvoiceDocument) -> None:
    """The band that keeps a reproduction from passing as the original.

    An invoice already issued has a document of record and it is not this
    one. Printing the same face without saying so would put a second
    artefact into circulation that a reader could not tell from the first,
    which is the one thing a system built to be audited must not do.
    """
    if doc.is_original:
        return
    y = MARGIN - 18
    c.setFillColor(colors.HexColor("#FFF2CC"))
    c.rect(MARGIN, y - 6, TABLE_W, 26, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#7A5B00"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 6, y + 11,
                 "REPRODUCED FROM THE REGISTER — NOT THE DOCUMENT OF RECORD")
    c.setFont("Helvetica", 7.5)
    where = (f"The invoice as issued is {doc.source_document}."
             if doc.source_document else
             "The invoice as issued is held by the sponsor.")
    c.drawString(MARGIN + 6, y + 1,
                 f"{where} This is invoice {doc.number} as recorded"
                 + (f", status {doc.status}." if doc.status else "."))


def _page_number(c, page: int, pages: int | None) -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    label = f"Page {page}" if pages is None else f"Page {page} of {pages}"
    c.drawRightString(PAGE_W - MARGIN, MARGIN - 30, label)


def _draw(doc: InvoiceDocument, pages: int | None) -> tuple[bytes, int]:
    """One pass. `pages` is the total to print in the page numbers, or None
    on the counting pass when it is not yet known."""
    buf = BytesIO()
    # `invariant` stops reportlab stamping a creation date and a random
    # document id. Without it two renders of the same invoice are two
    # different documents, every regeneration content-addresses to a new
    # evidence row, and the volume fills with copies that differ only in
    # when somebody pressed the button.
    c = pdfcanvas.Canvas(buf, pagesize=LETTER, invariant=1)
    c.setTitle(f"Invoice {doc.number}")
    c.setAuthor(doc.remit_to.name)
    c.setSubject(doc.objective or "")
    c.setCreator("YBI cost allocation")

    lines = _label_the_category(doc.lines)
    page = 1
    y = _masthead(c, doc, PAGE_H - MARGIN)
    y = _parties(c, doc, y)
    y = _column_heads(c, y)

    for i, line in enumerate(lines):
        need = _line_height(c, line)
        # Reserve room for the total block only on what will be the last
        # page; a row that would collide with it starts a new page instead,
        # so a total never sits alone under a page of nothing.
        reserve = 40.0 if lines[i + 1:] else FOOT_RESERVE
        if y - need < MARGIN + reserve:
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(MARGIN, y - 12, "continued \u2192")
            _provenance(c, doc)
            _page_number(c, page, pages)
            c.showPage()
            page += 1
            y = _masthead(c, doc, PAGE_H - MARGIN)
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(MARGIN, y - 8, f"Invoice {doc.number}, continued")
            y = _column_heads(c, y - 22)
        y = _draw_line(c, line, y, shade=bool(i % 2))

    _foot(c, doc, y - 26)
    _provenance(c, doc)
    _page_number(c, page, pages)
    c.showPage()
    c.save()
    return buf.getvalue(), page


def render(doc: InvoiceDocument) -> bytes:
    """The invoice, as a PDF.

    Two passes, because "Page 2 of 5" cannot be written until the fifth page
    exists and an invoice that says "Page 2" with no total is one a reader
    has to count for themselves to know they have it all. The first pass is
    thrown away; it exists only to learn how many pages there are.

    Deterministic: the same document renders to the same bytes, so a
    regenerated invoice content-addresses to the same evidence row and a
    second run files nothing twice.
    """
    _, pages = _draw(doc, None)
    body, _ = _draw(doc, pages)
    return body
