"""The two papers that close 2025 with the sponsor: an MOU and an amendment.

`amendment_document.py` is **per award** — the right unit for a change of
basis and the wrong one for the conversation actually being had.
`reconciliation_document.py` is every contract on one page, grouped by prime,
and is a *reading of the register*. Neither is the thing a sponsor signs to
end the year.

These two are. They differ from everything above in one way that governs the
whole module: **they are put to NCDMM for signature, so they never assert
that NCDMM has answered.**

  * **The record says ACCEPTED on all four restatements and NCDMM has
    accepted nothing.** `drive_the_close.py --rehearsal` wrote
    *"Accepted by NCDMM on the acceptance form returned with the amendment
    memorandum"* against every one of them at 15 Sep 14:43, and `122`
    records that the reference record is a *simulated* closed year. So
    `standing_band()` — which reads `status` and is right for the papers it
    was written for — must not be called from here: it would print ACCEPTED
    on the document whose entire purpose is to obtain the acceptance.
    `no_paper_here_claims_an_acceptance()` is the property, and a test holds
    it, because this is the fourth place `122`'s defect has been available.
  * **Both directions in full, then the single movement**, which is
    `SETTLEMENT_2025.md`'s own resolution of `061`: the register holds two
    directions and never nets them; the *parties* settle by one figure, and
    the rule saying which is which is written on the paper. The net is the
    thing being released, so it is printed once, after both columns, and
    labelled as a mutual waiver rather than as a summary of the table.
  * **One prime per amendment.** Federal award funds are not fungible
    between programmes, so an instrument covering the three AFRL
    FA8650-20-2-5700 awards may not carry the Navy-primed one.
    `SettlementPapers` refuses a mixed set rather than leaving the caller to
    remember — and the prime is matched on *containment* because the register
    spells it two ways, `FA8650-20-2-5700` and `AFRL FA8650-20-2-5700`.
  * **The signature on the rate is `certification_lines()`'s to describe**,
    as `122` requires of everything that leaves the building, and the
    supersession of the rate the positions were measured against is `132`'s
    notice — above the figures, not under them.

Pure: no database, deterministic, and rendered on the face
`invoice_document.py` establishes, because three faces from one organisation
read as three organisations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdfcanvas

from app.domain.core import money
from app.domain.invoice_document import (INK, MARGIN, MUTED, PAGE_H, PAGE_W,
                                         TABLE_W, Party, _fmt_date,
                                         _fmt_money, _wrap)

BAND = colors.HexColor("#F3F1EC")
RULE = colors.HexColor("#D8D4CC")
WARN_BG = colors.HexColor("#F8E7E4")
WARN_INK = colors.HexColor("#8C2A1E")
DRAFT_BG = colors.HexColor("#EFEAD8")
DRAFT_INK = colors.HexColor("#6B5A1E")

#: The widest figure any money column on these papers could carry. A column
#: narrower than this prints one figure over its neighbour, which
#: `reconciliation_document.py` shipped once in the one row a reader takes
#: the settlement from — and `pypdf` reads the two strings without reading
#: where they landed, so every text assertion passed over it.
WIDEST_MONEY = "(9,999,999.99)"


@dataclass(frozen=True)
class AwardPosition:
    """One award's 2025 position: what was billed, and what the rate supports.

    Two direction fields and never a third signed one, which is `061`'s rule
    and the reason `v_restatement` has no `net_movement` column. The identity
    between them is checked here rather than trusted, because the whole
    amendment is four columns and a reader will add them up.
    """

    award: str
    title: str
    objective: str
    prime: str
    invoices: int
    #: What YBI invoiced NCDMM against this award for 2025, as issued.
    billed: Decimal
    #: Direct cost the record supports plus indirect at the restated rate.
    restated: Decimal
    #: Billed above what the restated basis supports — money to give back.
    over_collected: Decimal
    #: Supported above what was billed — money to ask for.
    under_recovered: Decimal
    #: Indirect actually stated as a line on the invoices as issued. Read
    #: rather than assumed: a first draft of the memorandum said all three
    #: projects carried no indirect line, and Last Tactical Mile carried
    #: $44,400.00 of it. A count is not a finding — `086` on a paper going
    #: to a sponsor.
    indirect_billed: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.over_collected and self.under_recovered:
            raise ValueError(
                f"{self.award} runs both ways at once: "
                f"{_fmt_money(self.over_collected)} to return and "
                f"{_fmt_money(self.under_recovered)} to claim. One award's "
                f"2025 position runs one way; two is a netting error.")
        if self.over_collected < 0 or self.under_recovered < 0:
            raise ValueError(f"{self.award}: a direction is a magnitude, "
                             f"never a signed figure.")
        gap = money(self.billed - self.restated)
        stated = money(self.over_collected - self.under_recovered)
        if gap != stated:
            raise ValueError(
                f"{self.award} does not foot: billed {_fmt_money(self.billed)} "
                f"less restated {_fmt_money(self.restated)} is "
                f"{_fmt_money(gap)}, and the position says "
                f"{_fmt_money(stated)}.")


@dataclass(frozen=True)
class SettlementPapers:
    """Everything both papers print, read from the record by the caller."""

    remit_to: Party
    bill_to: Party
    period: str
    issued_on: date
    reference: str

    #: The awards settled. One prime only — see the module docstring.
    positions: tuple[AwardPosition, ...]

    #: The rate the positions were measured on, read by `rate_id` and not
    #: "the live rate": a paper printing today's rate over yesterday's
    #: settlement is `088`'s overtaken claim with the halves swapped.
    rate_kind: str
    rate_applied: Decimal
    fringe_rate: Decimal
    overhead_rate: Decimal
    ga_rate: Decimal
    rate_pool: Decimal
    rate_base: Decimal
    #: False where that rate has since been superseded (`132`).
    rate_is_live: bool
    rate_status: str

    #: What `v_rate_certified` answered. `certification_lines()` turns it
    #: into the band; nothing here composes a second sentence about it.
    certification: dict | None

    #: The clause each agreement gives for a change of basis, read out of
    #: `award_term`. An award with none is named once — one sentence per
    #: fact, not one per award, which is what the one-page guard taught the
    #: reconciliation page.
    basis_clauses: tuple[tuple[str, str], ...] = ()
    awards_without_a_clause: tuple[str, ...] = ()

    #: The two pools the combined rate rolls up, and the payroll the fringe
    #: pool is spread over. **The paper prints these rather than the two
    #: component percentages**, because each component is rounded to four
    #: places independently of the other: overhead reads 12.35% and G&A
    #: 12.37%, which sum to 24.72% against a combined rate of 24.71%. All
    #: three figures are right and printing them together puts an apparent
    #: arithmetic error on a sponsor's instrument — `069`'s rounding lesson
    #: in a presentation. The pools add exactly, and `__post_init__` checks
    #: that they do.
    overhead_pool: Decimal = Decimal("0")
    ga_pool: Decimal = Decimal("0")
    fringe_pool: Decimal = Decimal("0")
    fringe_base: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.positions:
            raise ValueError("a settlement over no awards is not a settlement.")
        if self.overhead_pool or self.ga_pool:
            parts = money(self.overhead_pool + self.ga_pool)
            if parts != money(self.rate_pool):
                raise ValueError(
                    f"the indirect pools do not add to the pool the rate was "
                    f"taken over: {_fmt_money(self.overhead_pool)} and "
                    f"{_fmt_money(self.ga_pool)} make {_fmt_money(parts)} "
                    f"against {_fmt_money(self.rate_pool)}.")
        primes = {_prime_key(p.prime) for p in self.positions}
        if len(primes) > 1:
            raise ValueError(
                f"these papers cover one prime agreement and were given "
                f"{len(primes)}: {', '.join(sorted(primes))}. Federal award "
                f"funds are not fungible between programmes, so one "
                f"instrument may not settle two.")

    @property
    def prime(self) -> str:
        return self.positions[0].prime

    @property
    def billed_total(self) -> Decimal:
        return money(sum((p.billed for p in self.positions), Decimal("0")))

    @property
    def restated_total(self) -> Decimal:
        return money(sum((p.restated for p in self.positions), Decimal("0")))

    @property
    def to_return(self) -> Decimal:
        return money(sum((p.over_collected for p in self.positions),
                         Decimal("0")))

    @property
    def to_claim(self) -> Decimal:
        return money(sum((p.under_recovered for p in self.positions),
                         Decimal("0")))

    @property
    def net(self) -> Decimal:
        """The one movement the parties would otherwise settle by.

        Positive where YBI has collected more than the restated basis
        supports across the set, which is money that would run to NCDMM.
        It is printed **after** both directions in full, and only ever as
        the amount being released.
        """
        return money(self.to_return - self.to_claim)

    @property
    def net_runs_to(self) -> str:
        if self.net > 0:
            return self.bill_to.name
        if self.net < 0:
            return self.remit_to.name
        return ""

    @property
    def awards(self) -> str:
        return _and_list([p.title for p in self.positions])

    @property
    def rate_label(self) -> str:
        """The kind, as a reader says it rather than as the database does.

        `107` found the tie register printing `WAGE_BASE_IS_THE_REGISTER` on
        the panel a reviewer reads first; an enum on a sponsor's instrument
        is the same defect one audience further out.
        """
        return self.rate_kind.replace("_", " ").lower()

    @property
    def without_an_indirect_line(self) -> int:
        return sum(1 for p in self.positions if not p.indirect_billed)

    @property
    def indirect_billed_note(self) -> str:
        """Name what the others did bill, rather than leaving it to a reader.

        One sentence per fact: where some awards billed indirect and some did
        not, saying only how many did not invites the reader to assume the
        rest billed at the elected rate.
        """
        billed = [p for p in self.positions if p.indirect_billed]
        if not billed:
            return ""
        return (", and " + _and_list(
            [f"{p.title} stated {_fmt_money(p.indirect_billed)}"
             for p in billed]))


def _prime_key(prime: str) -> str:
    """The prime, as a key rather than as it was typed.

    The register spells one agreement two ways — `FA8650-20-2-5700` and
    `AFRL FA8650-20-2-5700` — so equality on the string would report one
    programme as two and refuse a legitimate set. *Never join on a name that
    can repeat*; this is the same rule where a key does not exist.
    """
    return "".join(ch for ch in prime.upper()
                   if ch.isalnum() or ch == "-").replace("AFRL", "").strip("-")


def _and_list(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _pct(rate: Decimal) -> str:
    return f"{Decimal(rate) * 100:.2f}%"


def no_paper_here_claims_an_acceptance(pdf_text: str) -> bool:
    """A document sent for signature must not say it was already signed.

    The reference record carries `status = 'ACCEPTED'` on all four
    restatements because a rehearsal drive wrote it, so a renderer that read
    the status would print NCDMM's agreement onto the paper asking for it.
    Held as a property both papers are checked against.
    """
    low = pdf_text.lower()
    return not any(phrase in low for phrase in (
        "accepted by", "has accepted", "ncdmm accepted", "accepted on"))


# ─────────────────────────────── drawing ────────────────────────────────

def _title_size(c, title: str) -> float:
    """The largest size at which the title clears the masthead beside it."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    room = (PAGE_W - MARGIN) - (MARGIN + stringWidth(
        "Youngstown Business Incubator", "Helvetica-Bold", 11)) - 12
    for size in (15, 14, 13, 12):
        if stringWidth(title, "Helvetica-Bold", size) <= room:
            return size
    raise ValueError(f"{title!r} does not fit beside the masthead at any "
                     f"readable size; shorten it rather than overlapping.")


def _party_lines(party: Party) -> list[str]:
    """`Party` carries `address` and `detail`, not a list of lines.

    Written from memory the first time as `party.lines`, and the dataclass
    disagreed on the first render — which is *read the schema, never recall
    it* pointed at a value object.
    """
    out: list[str] = []
    for part in (party.address, party.detail):
        out.extend(part.split("\n") if part else [])
    return out


def _masthead(c, p: SettlementPapers, title: str, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, p.remit_to.name)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    for row in _party_lines(p.remit_to):
        y -= 11
        c.drawString(MARGIN, y, row)
    right = PAGE_W - MARGIN
    c.setFillColor(INK)
    # The title is sized to the space the masthead leaves it rather than set
    # at 15pt and hoped for: "COLLABORATIVE AGREEMENT AMENDMENT" is 330.8pt
    # there and the gap is 320.9pt, so the first draft ran the instrument's
    # own name into the organisation's.
    c.setFont("Helvetica-Bold", _title_size(c, title))
    c.drawRightString(right, PAGE_H - MARGIN, title)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    c.drawRightString(right, PAGE_H - MARGIN - 16, _fmt_date(p.issued_on))
    c.drawRightString(right, PAGE_H - MARGIN - 28, p.reference)
    return min(y, PAGE_H - MARGIN - 42) - 16


def _draft_band(c, y: float) -> float:
    """What this is, before anything it says.

    `invoice_document.py`'s rule — *a reproduction says it is one* — pointed
    at an instrument: an unsigned agreement circulating without a band is one
    a reader cannot tell from an executed one.
    """
    c.setFillColor(DRAFT_BG)
    c.rect(MARGIN, y - 7, TABLE_W, 23, stroke=0, fill=1)
    c.setFillColor(DRAFT_INK)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN + 6, y + 3, "FOR SIGNATURE — NOT YET EXECUTED")
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN + 186, y + 3,
                 "Nothing here binds either party until both have signed below.")
    return y - 20


def _rate_notice(c, p: SettlementPapers, y: float) -> float:
    """`132`, above the figures rather than under them."""
    if p.rate_is_live:
        return y
    c.setFillColor(WARN_BG)
    c.rect(MARGIN, y - 18, TABLE_W, 34, stroke=0, fill=1)
    c.setFillColor(WARN_INK)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN + 6, y + 4, "THE RATE BELOW HAS BEEN SUPERSEDED")
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN + 6, y - 7,
                 f"These positions were measured on an "
                 f"{p.rate_label} rate of {_pct(p.rate_applied)}, which the "
                 f"record now carries as {p.rate_status.lower()}. Recompute "
                 f"before issuing.")
    return y - 31


def _certification(c, p: SettlementPapers, y: float) -> float:
    from app.domain.audit_package import certification_lines

    lines = certification_lines(p.certification)
    body = " ".join(lines)
    uncertified = body.upper().startswith(("NOT CERTIFIED", "REHEARSAL"))
    c.setFillColor(WARN_BG if uncertified else BAND)
    wrapped = _wrap(c, body, TABLE_W - 12, "Helvetica", 8)
    h = 11 * len(wrapped) + 8
    c.rect(MARGIN, y - h + 10, TABLE_W, h, stroke=0, fill=1)
    c.setFillColor(WARN_INK if uncertified else MUTED)
    c.setFont("Helvetica", 8)
    yy = y + 1
    for row in wrapped:
        c.drawString(MARGIN + 6, yy, row)
        yy -= 11
    return y - h - 4


def _label(c, text: str, y: float) -> float:
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(MARGIN, y, text.upper())
    return y - 13


def _para(c, text: str, y: float, *, size: float = 9, lead: float = 12.2,
          indent: float = 0.0) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica", size)
    for row in _wrap(c, text, TABLE_W - indent, "Helvetica", size):
        c.drawString(MARGIN + indent, y, row)
        y -= lead
    return y


def _numbered(c, n: int, head: str, text: str, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, y, f"{n}.")
    c.drawString(MARGIN + 16, y, head)
    y -= 12.2
    return _para(c, text, y, indent=16) - 5


def _parties(c, p: SettlementPapers, y: float) -> float:
    half = TABLE_W / 2 - 12
    top = y
    for i, (lab, party) in enumerate((("BETWEEN", p.remit_to),
                                      ("AND", p.bill_to))):
        x = MARGIN + i * (half + 24)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x, top, lab)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(x, top - 14, party.name)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(MUTED)
        yy = top - 26
        for row in _party_lines(party):
            c.drawString(x, yy, row)
            yy -= 10.5
    return top - 26 - 10.5 * max(len(_party_lines(p.remit_to)),
                                 len(_party_lines(p.bill_to))) - 6


def _signatures(c, p: SettlementPapers, y: float) -> float:
    """Ruled lines, and nothing pre-filled.

    `093` found the acceptance form printing PROPOSED over a signature NCDMM
    had given; the defect is available here in the other direction, as a
    name typed onto a line nobody has signed.
    """
    y = _label(c, "Agreed", y)
    half = TABLE_W / 2 - 16
    for i, party in enumerate((p.remit_to, p.bill_to)):
        x = MARGIN + i * (half + 32)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x, y, f"For {party.name}")
    y -= 34
    for i in range(2):
        x = MARGIN + i * (half + 32)
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.line(x, y, x + half, y)
        c.line(x, y - 34, x + half, y - 34)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(x, y - 10, "Signature")
        c.drawString(x, y - 44, "Name and title")
        c.setStrokeColor(INK)
        c.line(x + half * 0.62, y - 68, x + half, y - 68)
        c.drawString(x + half * 0.62, y - 78, "Date")
    return y - 86


def _page_foot(c, page: int, pages: int, note: str = "") -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, MARGIN - 20, note)
    c.drawRightString(PAGE_W - MARGIN, MARGIN - 20, f"Page {page} of {pages}")


# ───────────────────────────── the amendment ─────────────────────────────

#: x offset from MARGIN, width, alignment. Checked against `WIDEST_MONEY`
#: by a test rather than by eye.
AMEND_COLS = (("AWARD", 0.0, 176.0, "l"),
              ("BILLED 2025", 176.0, 92.0, "r"),
              ("RESTATED", 268.0, 92.0, "r"),
              ("TO RETURN", 360.0, 84.0, "r"),
              ("TO CLAIM", 444.0, 84.0, "r"))


def _amend_heads(c, y: float) -> float:
    c.setFillColor(BAND)
    c.rect(MARGIN, y - 16, TABLE_W, 16, stroke=0, fill=1)
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 7)
    for head, x, w, align in AMEND_COLS:
        if align == "r":
            c.drawRightString(MARGIN + x + w - 5, y - 11, head)
        else:
            c.drawString(MARGIN + x + 5, y - 11, head)
    return y - 16


def _amend_row(c, pos: AwardPosition, y: float, shade: bool) -> float:
    h = 25.0
    if shade:
        c.setFillColor(colors.HexColor("#FAF9F6"))
        c.rect(MARGIN, y - h, TABLE_W, h, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN + 5, y - 11, pos.title)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN + 5, y - 20,
                 f"{pos.award} · {pos.invoices} invoice"
                 f"{'s' if pos.invoices != 1 else ''}")
    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    figures = ((176.0, 92.0, _fmt_money(pos.billed)),
               (268.0, 92.0, _fmt_money(pos.restated)),
               (360.0, 84.0, _fmt_money(pos.over_collected)
                if pos.over_collected else "—"),
               (444.0, 84.0, _fmt_money(pos.under_recovered)
                if pos.under_recovered else "—"))
    for x, w, text in figures:
        c.drawRightString(MARGIN + x + w - 5, y - 11, text)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.4)
    c.line(MARGIN, y - h, MARGIN + TABLE_W, y - h)
    return y - h


def _amend_total(c, p: SettlementPapers, y: float) -> float:
    """Every money column, or none.

    The reconciliation page printed two of its four on the subtotal, leaving
    a hole mid-row that reads as missing data rather than as a total.
    """
    h = 19.0
    c.setFillColor(BAND)
    c.rect(MARGIN, y - h, TABLE_W, h, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN + 5, y - 13, f"All {len(p.positions)} projects")
    for x, w, text in ((176.0, 92.0, _fmt_money(p.billed_total)),
                       (268.0, 92.0, _fmt_money(p.restated_total)),
                       (360.0, 84.0, _fmt_money(p.to_return)),
                       (444.0, 84.0, _fmt_money(p.to_claim))):
        c.drawRightString(MARGIN + x + w - 5, y - 13, text)
    return y - h - 12


def render_amendment(p: SettlementPapers) -> bytes:
    """One page. It refuses to become two rather than overrunning quietly."""
    buf = BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    c.setTitle(f"Collaborative Agreement Amendment — {p.period}")

    y = _masthead(c, p, "COLLABORATIVE AGREEMENT AMENDMENT",
                  PAGE_H - MARGIN)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, f"{p.period} indirect cost basis — "
                            f"prime {p.prime}")
    y -= 22
    y = _draft_band(c, y)
    y = _parties(c, p, y)

    y = _para(c, (
        f"The parties amend the subrecipient agreements for {p.awards} to "
        f"settle {p.period} indirect cost on an actual indirect rate in "
        f"place of the de minimis basis elected under each agreement. The "
        f"restated column applies {p.rate_label} at "
        f"{_pct(p.rate_applied)} to modified total direct cost, with fringe "
        f"at {_pct(p.fringe_rate)} of the payroll register."), y) - 6

    y = _rate_notice(c, p, y)
    y = _amend_heads(c, y)
    for i, pos in enumerate(p.positions):
        y = _amend_row(c, pos, y, shade=bool(i % 2))
    y = _amend_total(c, p, y)

    y = _label(c, "Net difference, and its treatment", y)
    y = _para(c, (
        f"The two columns above are not netted in either party's records: "
        f"{_fmt_money(p.to_return)} over-collected and "
        f"{_fmt_money(p.to_claim)} under-recovered are separate findings and "
        f"each stands on its own award. For settlement only, the parties "
        f"note a net difference of {_fmt_money(abs(p.net))} across all "
        f"{len(p.positions)} projects."), y) - 4

    # The box is sized to the sentence rather than set at a height that
    # happened to fit this one: three awards wrap to three lines and four
    # would wrap to four, clipping the descenders of the clause the whole
    # instrument turns on.
    c.setFont("Helvetica", 8.5)
    waiver = _wrap(c, (
        f"The parties agree that the net difference of "
        f"{_fmt_money(abs(p.net))} arising across these "
        f"{len(p.positions)} projects shall be treated as unrecoverable "
        f"by either party for {p.period}. No invoice, credit, refund or "
        f"claim shall be issued by either party in respect of it, and "
        f"neither party waives any position on any other period."),
        TABLE_W - 14, "Helvetica", 8.5)
    h = 22 + 10.5 * len(waiver)
    c.setFillColor(BAND)
    c.rect(MARGIN, y + 6 - h, TABLE_W, h, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN + 7, y - 6, "Mutual waiver")
    c.setFont("Helvetica", 8.5)
    yy = y - 19
    for row in waiver:
        c.drawString(MARGIN + 7, yy, row)
        yy -= 10.5
    y = y + 2 - h

    if p.awards_without_a_clause:
        y -= 5
        y = _para(c, (
            f"No change-of-basis clause is on the record for "
            f"{_and_list(list(p.awards_without_a_clause))}; NCDMM is asked to "
            f"name the instrument under which this amendment is incorporated "
            f"for that award."), y, size=8.5, lead=11) - 2

    y = _certification(c, p, y)
    y = _signatures(c, p, y)
    _page_foot(c, 1, 1, f"{p.remit_to.name} · {p.reference}")

    c.showPage()
    c.save()
    out = buf.getvalue()
    if y < MARGIN - 26:
        raise ValueError(
            f"the amendment overran one page by {MARGIN - 26 - y:.0f}pt. "
            f"Cut the prose rather than letting it become two pages: a "
            f"one-page instrument is the thing that gets read and signed.")
    return out


# ──────────────────────────────── the MOU ────────────────────────────────

def render_mou(p: SettlementPapers) -> bytes:
    """Exactly two pages, and it refuses to be three."""
    buf = BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    c.setTitle(f"Memorandum of Understanding — {p.period} indirect cost")

    # ── page one ──
    y = _masthead(c, p, "MEMORANDUM OF UNDERSTANDING", PAGE_H - MARGIN)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, f"{p.period} indirect cost recovery and "
                            f"year-end settlement")
    y -= 22
    y = _draft_band(c, y)
    y = _parties(c, p, y)

    y = _numbered(c, 1, "Purpose", (
        f"This memorandum records the parties' understanding of the basis on "
        f"which {p.remit_to.name} will recover indirect cost on the "
        f"{p.bill_to.name} subrecipient agreements primed through "
        f"{p.prime}, and the treatment of the difference between what was "
        f"invoiced for {p.period} and what that basis supports. It is "
        f"accompanied by an agreement amendment setting out the figures for "
        f"each project."), y)

    y = _numbered(c, 2, "Background", (
        f"{p.remit_to.name} invoiced {p.period} on a loaded labour rate, with "
        f"indirect cost recovered inside the labour line rather than stated "
        f"as an indirect line. Of the {len(p.positions)} projects covered "
        f"here, {_n(p.without_an_indirect_line)} carried no indirect line at "
        f"all{p.indirect_billed_note}. "
        f"2 CFR 200.414(f) charges a de minimis rate as a rate on modified "
        f"total direct cost and does not contemplate indirect embedded in an "
        f"undisclosed loaded labour rate, so the parties are correcting the "
        f"basis rather than the amount of any one invoice."), y)

    y = _numbered(c, 3, "Regulatory basis", (
        "The de minimis rate is an election, and 2 CFR 200.414(f) ends it on "
        "the recipient's own choice: once elected, a recipient or "
        "subrecipient must use it for all Federal awards until it chooses to "
        "receive a negotiated rate. No term of years, no award cycle and no "
        "Federal agency release conditions that choice. Where no federally "
        "negotiated rate exists, 2 CFR 200.332(a)(4) requires the "
        "pass-through entity to determine the appropriate rate in "
        "collaboration with the subrecipient, and names a rate negotiated "
        "between the two as one of the two available options. The parties "
        "proceed on that paragraph. Allowability throughout is governed by "
        "2 CFR 200 Subpart E, which each agreement names; FAR Part 31 does "
        "not apply to a subaward under Federal financial assistance."), y)

    y = _numbered(c, 4, "The rate structure", (
        f"{p.remit_to.name} classified its {p.period} general ledger into "
        f"cost pools and sealed the classification before any rate was "
        f"computed. Fringe is {_pct(p.fringe_rate)} — a pool of "
        f"{_fmt_money(p.fringe_pool)} over the payroll register's "
        f"{_fmt_money(p.fringe_base)}. Indirect is an overhead pool of "
        f"{_fmt_money(p.overhead_pool)} and a general and administrative "
        f"pool of {_fmt_money(p.ga_pool)}, together "
        f"{_fmt_money(p.rate_pool)} over modified total direct cost of "
        f"{_fmt_money(p.rate_base)}, giving {p.rate_label} of "
        f"{_pct(p.rate_applied)}. The occupancy cost of space let or "
        f"available to let is removed under 2 CFR 200.465, and depreciation "
        f"on federally funded assets under 2 CFR 200.436(b), before the pool "
        f"is allocated."), y)

    y = _numbered(c, 5, "Scope", (
        f"This memorandum covers the {len(p.positions)} subrecipient "
        f"agreements primed through {p.prime}: {p.awards}. Awards primed "
        f"through a different Federal instrument are deliberately excluded, "
        f"because Federal award funds are not fungible between programmes "
        f"and a difference arising on one programme may not be settled "
        f"against another."), y)

    _page_foot(c, 1, 2, f"{p.remit_to.name} · {p.reference}")
    c.showPage()

    # ── page two ──
    y = _masthead(c, p, "MEMORANDUM OF UNDERSTANDING", PAGE_H - MARGIN)
    y = _rate_notice(c, p, y + 4)

    y = _numbered(c, 6, f"The {p.period} positions", (
        f"Against {_fmt_money(p.billed_total)} invoiced across the "
        f"{len(p.positions)} projects, the restated basis supports "
        f"{_fmt_money(p.restated_total)}. Taken award by award and never "
        f"netted in either party's records, that is "
        f"{_fmt_money(p.to_return)} collected above what the basis supports "
        f"and {_fmt_money(p.to_claim)} of supported cost not recovered. The "
        f"accompanying amendment states each project separately."), y)

    y = _numbered(c, 7, "Treatment of the net difference", (
        f"For settlement purposes only, the parties note a net difference of "
        f"{_fmt_money(abs(p.net))} across all {len(p.positions)} projects "
        f"and agree to treat it as unrecoverable by either party for "
        f"{p.period}. Neither party will issue an invoice, credit, refund or "
        f"claim in respect of it. This is a settlement mechanism and not a "
        f"restatement of either party's books: each party's records continue "
        f"to carry both directions in full."), y)

    y = _numbered(c, 8, "What each party will do", (
        f"{p.remit_to.name} will provide the restated invoices for each "
        f"month of {p.period}, the indirect rate build-up and the "
        f"classification behind it, and will apply the restated basis "
        f"prospectively from 2026 on these agreements. {p.bill_to.name} will "
        f"countersign the accompanying amendment and name the modification "
        f"instrument for each agreement where one is required."), y)

    y = _numbered(c, 9, "What this is not", (
        f"This memorandum is not an admission by either party of an "
        f"overcharge or an underpayment, does not reopen or settle any period "
        f"other than {p.period}, and establishes no precedent for the rate "
        f"applicable to any other period. Nothing here alters the ceiling, "
        f"the period of performance, the statement of work or the cost share "
        f"obligation of any agreement."), y)

    if p.basis_clauses:
        y = _label(c, "Change-of-basis authority on the record", y)
        c.setFont("Helvetica", 8.5)
        for award, citation in p.basis_clauses:
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(MARGIN, y, award)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 8.5)
            c.drawString(MARGIN + 116, y, citation)
            y -= 11.5
        y -= 4

    y = _certification(c, p, y)
    y = _signatures(c, p, y)
    _page_foot(c, 2, 2, f"{p.remit_to.name} · {p.reference}")

    c.showPage()
    c.save()
    out = buf.getvalue()
    if y < MARGIN - 26:
        raise ValueError(
            f"the memorandum overran two pages by {MARGIN - 26 - y:.0f}pt. "
            f"Cut a paragraph rather than letting it run to three.")
    return out


_WORDS = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _n(count: int) -> str:
    return _WORDS.get(count, str(count))
