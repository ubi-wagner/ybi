"""Form 990 rendered on the face the filed return uses.

`invoice_document.py` renders the register onto the face NCDMM's payables
recognises, and its rule is the one this follows: **a reproduction says it is
one.** This is not a filing and must never be mistaken for one, so every page
carries a band saying what it is, and every field carries how it was answered.

Three rules, each already kept somewhere in this repository:

  - **Nothing is computed here.** Every figure arrives resolved. A renderer
    that summed a column would be a second derivation of a figure the record
    already holds, and the two would eventually disagree.
  - **A carried answer says so, and an unanswered one says what it wants.**
    A return that printed the 2024 answer as though it were this year's would
    be the generous assumption a reader makes about a figure on a letterhead.
  - **Deterministic.** `invariant=1`, so the same record renders to the same
    bytes and a digest that moves means a figure moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas

PAGE_W, PAGE_H = LETTER
MARGIN = 0.7 * inch
BODY = PAGE_W - 2 * MARGIN
LEAD = 11.5

INK = colors.HexColor("#111111")
QUIET = colors.HexColor("#6b6b6b")
RULE = colors.HexColor("#c9c9c9")
BAND = colors.HexColor("#8a5a12")          # pencil, not traffic light
CARRIED = colors.HexColor("#7a6a45")
ASKED = colors.HexColor("#8a2f2f")


def money(x) -> str:
    """The house spelling, and a blank prints as a blank. `api.js::money()`'s
    rule in the domain: *there is no amount* and *nobody has read one off* are
    different facts and must not be the same pixel.

    A carried value is **text as the filed return printed it** and is passed
    through rather than re-formatted. Re-reading "7,685,898" as a number and
    printing it to the cent would put two decimal places on a figure the
    filed return does not carry them on, which is this document quietly
    disagreeing with the one it replicates.
    """
    if x is None or x == "":
        return ""
    if isinstance(x, (Decimal, int, float)):
        return f"{Decimal(str(x)):,.2f}"
    return str(x)


def part_label(part: str, line_no: str = "") -> str:
    """How a part is named to a reader. `SCH_A` is what the register calls it
    and `Schedule A` is what the form does — a screen that starts speaking
    SQL is this repository's own phrase for the difference."""
    name = ("Schedule " + part[4:]) if part.startswith("SCH_") else (
        "Part " + part if part not in ("HEAD",) else "Header")
    return f"{name} {line_no}".strip()


@dataclass
class Section:
    key: str
    title: str
    rows: list = dc_field(default_factory=list)      # of Answer
    note: str = ""


@dataclass
class Statement:
    """One of the three financial statements, already added up elsewhere."""
    title: str
    columns: list
    rows: list                                       # (label, [values])
    total: tuple | None = None
    note: str = ""


@dataclass
class Return:
    period: str
    organisation: str
    ein: str
    sections: list                                   # of Section
    statements: list                                 # of Statement
    officers: list                                   # of dict
    outstanding: list                                # of Answer
    carried: list                                    # of Answer
    certification: list                              # of str
    controls: list                                   # of (name, state, said)
    prior_period: str = "2024"


class _Page:
    """A cursor down the page that knows when to start another one."""

    def __init__(self, c: pdfcanvas.Canvas, doc: Return):
        self.c, self.doc, self.page = c, doc, 0
        self._new()

    def _new(self):
        if self.page:
            self.c.showPage()
        self.page += 1
        c = self.c
        c.setFillColor(BAND)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGIN, PAGE_H - MARGIN + 16,
                     "NOT A FILING — PREPARED FROM THE COST RECORD")
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN, PAGE_H - MARGIN + 10, PAGE_W - MARGIN,
               PAGE_H - MARGIN + 10)
        c.setFillColor(QUIET)
        c.setFont("Helvetica", 7)
        c.drawString(MARGIN, MARGIN - 22,
                     f"Form 990 ({self.doc.period}) · "
                     f"{self.doc.organisation} · EIN {self.doc.ein}")
        c.drawRightString(PAGE_W - MARGIN, MARGIN - 22, f"Page {self.page}")
        self.y = PAGE_H - MARGIN - 6

    def space(self, need: float):
        if self.y - need < MARGIN:
            self._new()

    def down(self, n: float = LEAD):
        self.y -= n
        self.space(0)


def _wrap(c, text: str, width: float, font: str, size: float) -> list[str]:
    words, lines, line = str(text).split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines or [""]


def _heading(p: _Page, title: str, note: str = ""):
    p.space(46)
    p.down(16)
    p.c.setFillColor(INK)
    p.c.setFont("Helvetica-Bold", 10.5)
    p.c.drawString(MARGIN, p.y, title)
    p.down(4)
    p.c.setStrokeColor(INK)
    p.c.setLineWidth(0.9)
    p.c.line(MARGIN, p.y, PAGE_W - MARGIN, p.y)
    p.down(10)
    if note:
        p.c.setFillColor(QUIET)
        p.c.setFont("Helvetica-Oblique", 7.5)
        for ln in _wrap(p.c, note, BODY, "Helvetica-Oblique", 7.5):
            p.c.drawString(MARGIN, p.y, ln)
            p.down(9)
        p.down(2)


def _row(p: _Page, a):
    """One field: its line number, its label, its answer, and how it was
    answered. The fourth column is the one that matters."""
    c = p.c
    f = a.field
    num_x, lab_x = MARGIN, MARGIN + 34
    val_x = PAGE_W - MARGIN - 128
    prov_x = PAGE_W - MARGIN - 118

    label_w = val_x - lab_x - 8
    lines = _wrap(c, f.label, label_w, "Helvetica", 8)
    p.space(len(lines) * 10 + 14)

    c.setFillColor(QUIET)
    c.setFont("Helvetica", 7.5)
    c.drawString(num_x, p.y, f.line_no)

    c.setFillColor(INK)
    c.setFont("Helvetica", 8)
    top = p.y
    for i, ln in enumerate(lines):
        c.drawString(lab_x, p.y, ln)
        if i < len(lines) - 1:
            p.down(9.5)

    if a.field.answer == "ask":
        c.setFillColor(ASKED)
        c.setFont("Helvetica-Oblique", 7.5)
        for ln in _wrap(c, "needs " + a.says, PAGE_W - MARGIN - prov_x,
                        "Helvetica-Oblique", 7.5):
            c.drawString(prov_x, top, ln)
            top -= 8.5
        p.y = min(p.y, top + 8.5)
    else:
        shown = a.value
        if f.kind == "MONEY" and shown not in (None, ""):
            c.setFillColor(INK)
            c.setFont("Helvetica", 8.5)
            c.drawRightString(val_x + 92, p.y, money(shown))
        elif shown not in (None, ""):
            c.setFillColor(INK)
            c.setFont("Helvetica", 8)
            txt = str(shown)
            wrapped = _wrap(c, txt, PAGE_W - MARGIN - val_x, "Helvetica", 8)
            yy = p.y
            for ln in wrapped:
                c.drawString(val_x, yy, ln)
                yy -= 9
            p.y = min(p.y, yy + 9)
        if f.answer == "carried":
            c.setFillColor(CARRIED)
            c.setFont("Helvetica-Oblique", 6.5)
            c.drawRightString(PAGE_W - MARGIN, p.y - 8, "carried · confirm")
            p.down(8)
    p.down(11)

    if f.note:
        c.setFillColor(QUIET)
        c.setFont("Helvetica-Oblique", 6.8)
        for ln in _wrap(c, f.note, BODY - 40, "Helvetica-Oblique", 6.8):
            c.drawString(lab_x, p.y, ln)
            p.down(8)
        p.down(2)


def _statement(p: _Page, s: Statement):
    c = p.c
    _heading(p, s.title, s.note)
    cols = len(s.columns)
    right = PAGE_W - MARGIN
    w = 92
    xs = [right - w * (cols - i - 1) for i in range(cols)]

    c.setFillColor(QUIET)
    c.setFont("Helvetica-Bold", 7)
    for x, col in zip(xs, s.columns):
        c.drawRightString(x, p.y, col)
    p.down(10)

    for label, values in s.rows:
        # The whole label. A statement line clipped at two lines reads as a
        # different line — "Grants and other assistance to domestic
        # organizations and domestic" is not what the form says.
        lines = _wrap(c, label, xs[0] - MARGIN - w - 8, "Helvetica", 8)
        p.space(len(lines) * 10 + 8)
        c.setFillColor(INK)
        c.setFont("Helvetica", 8.5)
        for x, v in zip(xs, values):
            c.drawRightString(x, p.y, money(v))
        c.setFont("Helvetica", 8)
        for ln in lines:
            c.drawString(MARGIN, p.y, ln)
            p.down(9.5)
        p.down(2)

    if s.total:
        c.setStrokeColor(INK)
        c.setLineWidth(0.7)
        c.line(xs[0] - w, p.y + 7, right, p.y + 7)
        p.down(3)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGIN, p.y, s.total[0])
        for x, v in zip(xs, s.total[1]):
            c.drawRightString(x, p.y, money(v))
        p.down(12)


def _first_page(p: _Page, doc: Return):
    c = p.c
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 19)
    c.drawString(MARGIN, p.y - 14, "Form 990")
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN + 92, p.y - 14,
                 "Return of Organization Exempt From Income Tax")
    c.setFont("Helvetica-Bold", 19)
    c.drawRightString(PAGE_W - MARGIN, p.y - 14, doc.period)
    p.down(24)
    c.setFillColor(QUIET)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, p.y,
                 "Under section 501(c), 527, or 4947(a)(1) of the Internal "
                 "Revenue Code (except private foundations)")
    p.down(16)

    # The band. It is the first thing on the document because a reader who
    # reaches a footnote has already formed a view.
    wrapped = [w for ln in doc.certification
               for w in _wrap(c, ln, BODY - 20, "Helvetica", 7.5)]
    box_h = 22 + 9.5 * len(wrapped)
    p.space(box_h + 12)
    c.setFillColor(colors.HexColor("#fdf6e8"))
    c.setStrokeColor(BAND)
    c.setLineWidth(0.7)
    c.rect(MARGIN, p.y - box_h + 6, BODY, box_h, fill=1, stroke=1)
    c.setFillColor(BAND)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 8, p.y - 6,
                 "THIS IS NOT A FILED RETURN AND MUST NOT BE FILED")
    p.down(15)
    c.setFont("Helvetica", 7.5)
    for w in wrapped:
        c.drawString(MARGIN + 8, p.y, w)
        p.down(9.5)
    p.down(14)


def _outstanding(p: _Page, doc: Return):
    if not doc.outstanding:
        return
    _heading(p, f"What this return does not answer — "
                f"{len(doc.outstanding)} field(s)",
             "Each one names what it needs. Nothing here is guessed at and "
             "nothing is carried from last year in its place, because an "
             "answer nobody gave and an answer somebody gave are different "
             "facts.")
    c = p.c
    for a in doc.outstanding:
        p.space(22)
        c.setFillColor(ASKED)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGIN, p.y, part_label(a.field.part, a.field.line_no))
        c.setFillColor(INK)
        c.setFont("Helvetica", 8)
        for ln in _wrap(c, a.field.label, BODY - 70, "Helvetica", 8):
            c.drawString(MARGIN + 62, p.y, ln)
            p.down(9.5)
        c.setFillColor(QUIET)
        c.setFont("Helvetica-Oblique", 7.5)
        for ln in _wrap(c, "needs " + a.says, BODY - 70,
                        "Helvetica-Oblique", 7.5):
            c.drawString(MARGIN + 62, p.y, ln)
            p.down(9)
        p.down(4)


def _controls(p: _Page, doc: Return):
    if not doc.controls:
        return
    _heading(p, "Controls on this return",
             "Whether the statements this return prints tie to the books "
             "underneath them. Read from the control that owns each figure; "
             "nothing here is computed on the page.")
    c = p.c
    for name, state, said in doc.controls:
        p.space(20)
        c.setFillColor(INK if state == "TIES" else ASKED)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGIN, p.y, state)
        c.setFillColor(INK)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN + 52, p.y, name)
        p.down(10)
        if said:
            c.setFillColor(QUIET)
            c.setFont("Helvetica-Oblique", 7.5)
            for ln in _wrap(c, said, BODY - 52, "Helvetica-Oblique", 7.5):
                c.drawString(MARGIN + 52, p.y, ln)
                p.down(9)
        p.down(3)


def _officers(p: _Page, doc: Return):
    if not doc.officers:
        return
    _heading(p, "Part VII Section A — Officers, Directors, Trustees, Key "
                "Employees and Highest Compensated Employees",
             "The roster carries forward from the filed 2024 return on the "
             "organisation's own instruction. The compensation does not: it "
             "is read from the payroll register, because a carried roster is "
             "not a carried salary.")
    c = p.c
    right = PAGE_W - MARGIN
    c.setFillColor(QUIET)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(MARGIN, p.y, "(A) Name")
    c.drawString(MARGIN + 150, p.y, "(B) Title")
    c.drawString(MARGIN + 296, p.y, "(C) Position")
    c.drawRightString(right - 70, p.y, "(D) Reportable")
    c.drawRightString(right, p.y, "(F) Other")
    p.down(10)
    for o in doc.officers:
        p.space(14)
        c.setFillColor(INK)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, p.y, str(o["name"])[:34])
        c.drawString(MARGIN + 150, p.y, str(o["title"])[:32])
        c.setFillColor(QUIET)
        c.setFont("Helvetica", 7)
        c.drawString(MARGIN + 296, p.y,
                     str(o["position"]).replace("_", " ").title()[:24])
        c.setFillColor(INK)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(right - 70, p.y, money(o.get("reportable")))
        c.drawRightString(right, p.y, money(o.get("other")))
        p.down(10.5)


def render(doc: Return) -> bytes:
    buf = BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=LETTER, invariant=1)
    c.setTitle(f"Form 990 ({doc.period}) — {doc.organisation}")
    c.setAuthor(doc.organisation)
    c.setSubject("Prepared from the cost record. Not a filed return.")

    p = _Page(c, doc)
    _first_page(p, doc)

    for s in doc.sections:
        _heading(p, s.title, s.note)
        for a in s.rows:
            _row(p, a)
        if s.key == "VII":
            _officers(p, doc)

    for s in doc.statements:
        _statement(p, s)

    _outstanding(p, doc)
    _controls(p, doc)

    c.showPage()
    c.save()
    return buf.getvalue()
