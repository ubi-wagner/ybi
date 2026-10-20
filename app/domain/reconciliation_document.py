"""One page, every contract NCDMM administers, and one signature.

`amendment_document.py` renders the two papers **one award** cannot travel
without: why this invoice differs from the one NCDMM paid, and how to say
yes. That is the right unit for a change of basis, and it is the wrong unit
for the conversation actually being had. YBI is not asking NCDMM three
separate questions about three agreements; it is asking one question — *was
the rate acceptable, and will you settle 2025 on it* — and a sponsor handed
three memoranda has to work out that they are one ask, then sign three times.

So: one page, every award NCDMM administers on it, one signature.

Five things it does that a stack of memoranda does not:

  * **It puts the rate at the top, with what stands behind it.** The
    reconciliation is arithmetic once the rate is agreed, and the rate is the
    only thing on the page that anybody can disagree with. Burying it under
    the figures it produces invites a reader to argue with the total.
  * **It shows both directions, side by side, and never nets them.** `061`
    removed `net_movement` from `v_restatement` because *$120,000 to ask for
    and $120,000 to give back is not a quiet year*. Here the temptation is
    worse, because three awards on one page make a single net figure look
    like the natural summary. Two columns, a subtotal under each, and a
    sentence saying they are not meant to add up.
  * **It raises the give-back first.** Two of these three run against YBI,
    and a page that led with the claim and mentioned the credits underneath
    would be read exactly once. `AMERICA_MAKES_RESTATEMENT.md` already does
    this in prose and records why: it is what makes the ask credible.
  * **It groups by prime rather than dropping what does not fit.** Digital
    Engineering is NCDMM-administered and its prime is *not* America Makes:
    it flows from N00174-20-1-0031 through Energetics Technology Center and
    NSWC Indian Head, where the other three flow from AFRL
    FA8650-20-2-5700. Federal award funds are not fungible between
    programmes — but the entity on the other side of all four is the same
    one, and YBI and NCDMM are closing 2025 across the relationship. The
    first draft of this page left Digital Engineering off and named it as
    excluded, which is three quarters of the conversation on a page
    pretending to be the whole of it. It carries all four now, in two
    groups with a subtotal each, so a reader can settle one programme
    without the other and can see that the two are different money.
  * **It offers the offset, and says it is a mechanism.** The year closes
    in one movement rather than two cheques crossing, which is what the
    parties are actually doing. `061` took `net_movement` off
    `v_restatement` because a single figure hides both directions, and
    that still governs the **record**: the table prints both in full,
    award by award and prime by prime, and never nets. The single movement
    is in the ask, *after* them — `SETTLEMENT_2025.md`'s rule, which
    `test_both_directions_appear_before_any_aggregate` already holds for
    the memorandum. An offset within a prime is arithmetic; an offset
    across two is something NCDMM has to agree to, and the page asks for
    it in those words instead of quietly adding the columns up.

Everything is **passed in, read from the record by the caller**. The two
rules that decide whether this paper can be trusted are the two that already
decide it for every other paper here:

  * **The ask is the recorded position, never the sum of the lines.** A
    `restatement_line` is the as-billed reading of one invoice; the position
    is the objective rebuilt against the cost record, and on these awards
    they run opposite ways. `amendment_document.py` records what summing the
    lines did the first time.
  * **The band prints in both directions.** A rate nobody has signed says so
    on its face, per `082`, and `certification_lines()` is the one
    sentence-maker — this module composes no sentence of its own about who
    signed what.

Pure, like the other two: no database, and deterministic so a filing route
can content-address what it produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.pdfgen import canvas

from app.domain.amendment_document import BAND, RULE, WARN_BG, WARN_INK, standing_band
from app.domain.core import money
from app.domain.invoice_document import (INK, MARGIN, MUTED, PAGE_H, PAGE_W,
                                         Party, _fmt_date, _fmt_money,
                                         _page_number, _wrap)

WIDTH = PAGE_W - 2 * MARGIN


@dataclass(frozen=True)
class Contract:
    """One award's position, as the restatement register recorded it.

    `to_return` and `to_claim` are two fields and never a signed third, for
    the reason `Movement` is: the direction is the finding. Unlike
    `Movement` — which covers one invoice and so may only run one way — an
    award can carry more than one objective, and one under-recovering while
    another over-collects is exactly the case two columns exist for.
    """

    award_id: str
    objective_id: str
    title: str
    invoices: int
    billed: Decimal
    direct_supported: Decimal
    indirect_supported: Decimal
    supported: Decimal
    to_return: Decimal = Decimal("0")
    to_claim: Decimal = Decimal("0")
    #: What the invoices said about indirect on their own face. Nought on
    #: three of these four, which is not a saving — it is the finding, and it
    #: is why the rebuild finds more was collected than the year supports.
    indirect_billed: Decimal = Decimal("0")
    #: The prime agreement this award flows down from. Federal award funds
    #: are not fungible between programmes, so two awards under different
    #: primes are two pots of money however one sponsor administers them —
    #: and the page says which is which rather than leaving a reader to
    #: infer it from an award id.
    prime: str = ""
    #: Where this award's restatement stands with the sponsor.
    status: str = "PROPOSED"
    #: When the sponsor answered, where they have.
    accepted_on: date | None = None
    #: The instrument an acceptance is recorded against, once there is one.
    modification_ref: str = ""


@dataclass(frozen=True)
class RateLine:
    """One row of the build-up, read from the rate the restatement used."""

    kind: str
    rate: Decimal
    pool: Decimal
    base: Decimal
    base_says: str = ""


@dataclass(frozen=True)
class Reconciliation:
    """Everything the page prints."""

    period: str
    issued_on: date
    remit_to: Party
    bill_to: Party
    programme: str
    contracts: tuple[Contract, ...]
    rates: tuple[RateLine, ...] = ()
    #: The rate the reconciliation is measured on, named so the reader can
    #: tie the table to it without adding the rows up themselves.
    combined_kind: str = "INDIRECT_COMBINED"
    basis: str = ""
    admin_labour_basis: str = ""
    seal_hash: str = ""
    judgments: int = 0
    #: The clause that authorises the change of basis, quoted from
    #: `award_term` with its citation — per award, because they differ and
    #: one of these three carries none at all.
    clauses: tuple[tuple[str, str, str], ...] = ()
    #: Why the rate is acceptable: each a statement the record can be asked
    #: to prove, never an adjective.
    grounds: tuple[str, ...] = ()
    #: **Above the figures**, in the warning colour: anything that makes the
    #: table itself untrustworthy. A rate that has since been superseded is
    #: the case `132` exists for — it moves every figure on the page, where
    #: everything under `caveats` moves none of them — and a reader who has
    #: to reach the last section to learn that has already formed a view.
    warnings: tuple[str, ...] = ()
    #: What is unfinished, under the figures, as everywhere else here.
    caveats: tuple[str, ...] = ()
    #: Awards deliberately not on the page, and why.
    excluded: tuple[tuple[str, str], ...] = ()
    certified: bool = False
    certification_line: str = ""
    reference: str = ""

    # ── the two directions, added within each and never across ──────

    @property
    def total_return(self) -> Decimal:
        return money(sum((c.to_return for c in self.contracts), Decimal("0")))

    @property
    def total_claim(self) -> Decimal:
        return money(sum((c.to_claim for c in self.contracts), Decimal("0")))

    @property
    def total_billed(self) -> Decimal:
        return money(sum((c.billed for c in self.contracts), Decimal("0")))

    @property
    def total_supported(self) -> Decimal:
        return money(sum((c.supported for c in self.contracts), Decimal("0")))

    @property
    def total_direct(self) -> Decimal:
        return money(sum((c.direct_supported for c in self.contracts),
                         Decimal("0")))

    @property
    def total_indirect(self) -> Decimal:
        return money(sum((c.indirect_supported for c in self.contracts),
                         Decimal("0")))

    @property
    def total_invoices(self) -> int:
        return sum(c.invoices for c in self.contracts)

    # ── grouped by prime, because the money is ───────────────────────

    @property
    def by_prime(self) -> tuple[tuple[str, tuple[Contract, ...]], ...]:
        """The contracts, grouped by the prime they flow down from.

        One sponsor administers all of these and that is an administrative
        fact, not a financial one: `N00174-20-1-0031` is Navy money through
        Energetics Technology Center and the rest is AFRL
        `FA8650-20-2-5700`, and an offset that crossed them would move
        federal award funds between programmes. So the grouping is on the
        page, with a subtotal each, and a reader can settle one group
        without the other.

        Groups are ordered by their own give-back, largest first, for the
        same reason the rows are: a page that led with the claim is read
        once. The order is a property of the figures rather than of a list
        written here.
        """
        order: list[str] = []
        groups: dict[str, list[Contract]] = {}
        for c in self.contracts:
            if c.prime not in groups:
                groups[c.prime] = []
                order.append(c.prime)
            groups[c.prime].append(c)
        order.sort(key=lambda p: -sum(c.to_return for c in groups[p]))
        return tuple((p, tuple(groups[p])) for p in order)

    @property
    def multi_prime(self) -> bool:
        return len(self.by_prime) > 1

    # ── the settlement, which is a mechanism and not a reading ───────
    #
    # `061` took `net_movement` off `v_restatement` because *$120,000 to
    # ask for and $120,000 to give back is not a quiet year*, and that is
    # still true of the **record**: the register holds two directions and
    # the table above prints both in full, award by award, never netted.
    #
    # What follows is a different thing wearing a similar shape. YBI and
    # NCDMM are closing 2025 at the organisational level, which means the
    # two directions are discharged against each other rather than by two
    # cheques. That is a settlement mechanism the parties agree to, and a
    # page that made a sponsor derive it themselves is a page that gets a
    # telephone call. It is printed **after** both directions and never in
    # place of them — `SETTLEMENT_2025.md`'s rule, which
    # `test_both_directions_appear_before_any_aggregate` already holds for
    # the memorandum.

    def settles_to(self, contracts: tuple[Contract, ...]) -> Decimal:
        """One movement, positive where YBI pays NCDMM."""
        return money(sum((c.to_return - c.to_claim for c in contracts),
                         Decimal("0")))

    @property
    def settlement(self) -> Decimal:
        return self.settles_to(self.contracts)

    @property
    def standing(self) -> str:
        """The least advanced of the three.

        An award whose objectives stand differently has not been accepted as
        a whole, and three awards standing differently have not been settled
        as one — the same direction of error the certification band refuses.
        """
        order = ("PROPOSED", "SUBMITTED", "ACCEPTED")
        return min((c.status for c in self.contracts),
                   key=lambda s: order.index(s) if s in order else -1,
                   default="PROPOSED")

    @property
    def accepted_on(self) -> date | None:
        """The latest of the sponsor's answers, where every award has one."""
        dates = [c.accepted_on for c in self.contracts]
        return max(dates) if dates and all(dates) else None

    @property
    def modification_reference(self) -> str:
        """The instrument an acceptance is recorded against.

        `acceptance_names_its_modification` refuses an acceptance that names
        none, so a band printing a clean acceptance with nothing behind it
        would hide the finding rather than show it. Empty until one of the
        three carries one.
        """
        return next((c.modification_ref for c in self.contracts
                     if (c.modification_ref or "").strip()), "")


# ── the page ─────────────────────────────────────────────────────────

def _rule(c, y: float, width: float = WIDTH) -> None:
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(MARGIN, y, MARGIN + width, y)


def _section(c, text: str, y: float) -> float:
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(MARGIN, y, text.upper())
    return y - 10


def _para(c, text: str, y: float, *, size: float = 8.2,
          colour=INK, indent: float = 0.0) -> float:
    c.setFillColor(colour)
    c.setFont("Helvetica", size)
    for line in _wrap(c, text, WIDTH - indent, "Helvetica", size):
        c.drawString(MARGIN + indent, y, line)
        y -= size + 1.9
    return y


def _head(c, r: Reconciliation, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, y, r.remit_to.name)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(PAGE_W - MARGIN, y, f"{r.period} CONTRACT RECONCILIATION")
    y -= 13

    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    for line in (r.remit_to.address or "").split("\n"):
        c.drawString(MARGIN, y, line)
        y -= 9.6
    right = y + 9.6 * len((r.remit_to.address or "").split("\n"))
    c.drawRightString(PAGE_W - MARGIN, right, r.programme)
    c.drawRightString(PAGE_W - MARGIN, right - 9.6,
                      f"To: {r.bill_to.name} · issued {_fmt_date(r.issued_on)}")
    if r.reference:
        c.drawRightString(PAGE_W - MARGIN, right - 19.2, r.reference)
    y = min(y, right - 28)
    y -= 4
    _rule(c, y)
    return y - 14


def _band(c, r: Reconciliation, y: float) -> float:
    """What this is and is not, and whether anybody has signed the rate.

    Two statements and they answer different questions — where the
    settlement stands with the sponsor, and whether the controller has put
    his name to the arithmetic. `082` is why the second one is here at all,
    and `122` is why it is never composed from a name: a drive typed one in
    once and sixteen rendered PDFs said a rate had been certified that
    nobody had signed.
    """
    heading, sub = standing_band(r.standing, r.modification_reference)
    height = 26 if sub else 17
    c.setFillColor(WARN_BG if r.standing == "PROPOSED" else BAND)
    c.rect(MARGIN, y - height + 12, WIDTH, height, stroke=0, fill=1)
    c.setFillColor(WARN_INK if r.standing == "PROPOSED" else INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN + 6, y + 2, heading)
    if sub:
        c.setFont("Helvetica", 7.6)
        c.drawString(MARGIN + 6, y - 7.5, sub)
    y -= height + 3

    for w in r.warnings:
        c.setFillColor(WARN_BG)
        lines = _wrap(c, w, WIDTH - 12, "Helvetica-Bold", 7.8)
        h = 7.5 + 10.4 * len(lines)
        c.rect(MARGIN, y - h + 10, WIDTH, h, stroke=0, fill=1)
        c.setFillColor(WARN_INK)
        c.setFont("Helvetica-Bold", 7.8)
        for line in lines:
            c.drawString(MARGIN + 6, y, line)
            y -= 10.4
        y -= 3

    if r.certification_line:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 7.6)
        for line in _wrap(c, r.certification_line, WIDTH, "Helvetica-Oblique", 7.6):
            c.drawString(MARGIN, y, line)
            y -= 9.4
    return y - 6


def _rates(c, r: Reconciliation, y: float) -> float:
    y = _section(c, "The rate, and what stands behind it", y)
    cols = (0.0, 128.0, 186.0, 268.0, 350.0)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.8)
    for label, x, align in (("POOL", cols[0], "l"), ("RATE", cols[1], "r"),
                            ("POOL AMOUNT", cols[2], "r"),
                            ("BASE", cols[3], "r"), ("OVER", cols[4], "l")):
        if align == "l":
            c.drawString(MARGIN + x, y, label)
        else:
            c.drawRightString(MARGIN + x, y, label)
    y -= 9
    _rule(c, y + 2)
    y -= 2

    for line in r.rates:
        combined = line.kind == r.combined_kind
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold" if combined else "Helvetica", 8.2)
        c.drawString(MARGIN + cols[0], y, line.kind.replace("_", " ").title())
        c.drawRightString(MARGIN + cols[1], y, f"{line.rate * 100:,.2f}%")
        c.drawRightString(MARGIN + cols[2], y, _fmt_money(line.pool))
        c.drawRightString(MARGIN + cols[3], y, _fmt_money(line.base))
        c.setFont("Helvetica", 7.4)
        c.setFillColor(MUTED)
        c.drawString(MARGIN + cols[4], y, line.base_says)
        y -= 11
    y -= 2

    provenance = []
    if r.basis:
        provenance.append(r.basis)
    if r.admin_labour_basis:
        provenance.append(
            "General administration is "
            + ("in the indirect pool it pays for"
               if r.admin_labour_basis == "POOL"
               else "treated as a benefiting cost objective")
            + f" ({r.admin_labour_basis.lower()} basis).")
    if r.seal_hash:
        # *The 0 classifications were sealed* is what a count printed without
        # asking whether there is one to print says — `086`'s defect in a
        # sentence rather than a state, and it reached a rendered page on a
        # clone whose set had since been unsealed. Where the judgment count
        # is not in hand the seal is still named, because the rate carries it
        # either way and the hash is what a reviewer ties to.
        counted = (f"The {r.judgments:,} classifications were sealed before "
                   f"any rate was computed"
                   if r.judgments else
                   "The classifications were sealed before any rate was "
                   "computed")
        provenance.append(
            f"{counted} — seal {r.seal_hash[:12]} — and the rate carries "
            f"that seal. A database trigger refuses a rate whose seal does "
            f"not match a sealed set, and changing a classification "
            f"afterwards takes an unsealing with a written reason, which "
            f"supersedes the rate.")
    if provenance:
        y = _para(c, " ".join(provenance), y, size=7.6, colour=MUTED)
    return y - 6


#: Where each column's right edge sits, measured rather than guessed.
#:
#: The first spelling put TO RETURN at 470 and TO CLAIM at the margin, 34pt
#: apart, and the totals row printed `201,421.30` over `43,960.60` — the two
#: directions this page exists to keep apart, overlapping, in the one row a
#: reader takes the settlement from. It renders as a single run of digits
#: that is neither figure. Invisible to a text extraction, because `pypdf`
#: reads the two strings and not where they landed; found by looking at the
#: page, which is the only way any of these are found.
#:
#: The six money columns are 66pt each, which is `(99,999,999.99)` in bold
#: at 8.2pt with room to spare — eight figures, on awards whose ceilings are
#: six. `test_no_two_columns_can_print_over_each_other` holds the property,
#: so the next engagement's larger figures fail there rather than printing
#: over each other.
_TCOLS = (0.0, 100.0, 108.0, 174.0, 240.0, 306.0, 372.0, 438.0)


def _table_head(c, y: float) -> float:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.8)
    c.drawString(MARGIN + _TCOLS[0], y, "AWARD")
    c.drawRightString(MARGIN + _TCOLS[2], y, "INV")
    for label, x in (("BILLED", _TCOLS[3]), ("DIRECT", _TCOLS[4]),
                     ("INDIRECT", _TCOLS[5]), ("SUPPORTED", _TCOLS[6])):
        c.drawRightString(MARGIN + x, y, label)
    c.setFillColor(WARN_INK)
    c.drawRightString(MARGIN + _TCOLS[7], y, "TO RETURN")
    c.setFillColor(MUTED)
    c.drawRightString(PAGE_W - MARGIN, y, "TO CLAIM")
    y -= 9
    _rule(c, y + 2)
    return y - 3


def _row(c, t: Contract, y: float) -> float:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN + _TCOLS[0], y, t.objective_id)
    c.setFont("Helvetica", 8.2)
    c.drawRightString(MARGIN + _TCOLS[2], y, str(t.invoices))
    for value, x in ((t.billed, _TCOLS[3]), (t.direct_supported, _TCOLS[4]),
                     (t.indirect_supported, _TCOLS[5]),
                     (t.supported, _TCOLS[6])):
        c.drawRightString(MARGIN + x, y, _fmt_money(value))
    # A blank, not a nought. *There is nothing to return* and *the return is
    # zero* are the same figure and different facts, and this page is read by
    # somebody deciding which of two cheques to write.
    c.setFillColor(WARN_INK if t.to_return else MUTED)
    c.drawRightString(MARGIN + _TCOLS[7], y,
                      _fmt_money(t.to_return) if t.to_return else "—")
    c.setFillColor(INK if t.to_claim else MUTED)
    c.drawRightString(PAGE_W - MARGIN, y,
                      _fmt_money(t.to_claim) if t.to_claim else "—")
    y -= 10.5

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.0)
    c.drawString(MARGIN + _TCOLS[0] + 6, y, t.title[:72])
    note = ("no indirect line on any invoice"
            if not t.indirect_billed
            else f"indirect billed {_fmt_money(t.indirect_billed)}")
    c.drawRightString(MARGIN + _TCOLS[6], y, note)
    # Which pot of money this award is, on the award rather than in a
    # heading over a block of them: a heading costs a line per group and
    # says nothing the row cannot say for itself.
    if t.prime:
        c.drawRightString(PAGE_W - MARGIN, y, t.prime)
    return y - 11


def _subtotal(c, prime: str, group: tuple[Contract, ...], y: float) -> float:
    """What this prime comes to, in both directions and never netted here.

    The single movement is in the ask below, after both directions have
    been printed in full — a subtotal that netted on the way past would
    put the aggregate above the figures it is an aggregate of.
    """
    _rule(c, y + 7, WIDTH)
    ret = money(sum((t.to_return for t in group), Decimal("0")))
    claim = money(sum((t.to_claim for t in group), Decimal("0")))
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 7.6)
    c.drawString(MARGIN + _TCOLS[0] + 6, y,
                 f"{prime} · {len(group)} award"
                 f"{'s' if len(group) != 1 else ''}")
    for field, x in (("billed", _TCOLS[3]), ("direct_supported", _TCOLS[4]),
                     ("indirect_supported", _TCOLS[5]),
                     ("supported", _TCOLS[6])):
        total = money(sum((getattr(t, field) for t in group), Decimal("0")))
        c.drawRightString(MARGIN + x, y, _fmt_money(total))
    c.setFillColor(WARN_INK if ret else MUTED)
    c.drawRightString(MARGIN + _TCOLS[7], y, _fmt_money(ret) if ret else "—")
    c.setFillColor(INK if claim else MUTED)
    c.drawRightString(PAGE_W - MARGIN, y, _fmt_money(claim) if claim else "—")
    return y - 12


def _totals(c, r: Reconciliation, y: float) -> float:
    _rule(c, y + 7)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN + _TCOLS[0], y,
                 f"{len(r.contracts)} awards")
    c.drawRightString(MARGIN + _TCOLS[2], y, str(r.total_invoices))
    for value, x in ((r.total_billed, _TCOLS[3]), (r.total_direct, _TCOLS[4]),
                     (r.total_indirect, _TCOLS[5]),
                     (r.total_supported, _TCOLS[6])):
        c.drawRightString(MARGIN + x, y, _fmt_money(value))
    c.setFillColor(WARN_INK)
    c.drawRightString(MARGIN + _TCOLS[7], y, _fmt_money(r.total_return))
    c.setFillColor(INK)
    c.drawRightString(PAGE_W - MARGIN, y, _fmt_money(r.total_claim))
    y -= 12

    y = _para(
        c,
        "The two columns are not netted here and do not add up. "
        f"{_fmt_money(r.total_return)} is money YBI is returning and "
        f"{_fmt_money(r.total_claim)} is money YBI is asking for — two "
        "directions, each measured on its own award's invoices and its own "
        "classified cost. The single movement they are settled by is "
        "below, after both.", y, size=7.6, colour=MUTED)
    return y - 4


def _asks(c, r: Reconciliation, y: float) -> float:
    """What is being asked for — or, once answered, what was agreed.

    A page that went on asking after the sponsor had said yes would be the
    acceptance form printing *"PROPOSED — NOT A CLAIM"* over a signature,
    which `093` found and fixed one paper along. The two readings are one
    fact read from `restatement.status`, not a second opinion about it.
    """
    settled = r.standing == "ACCEPTED"
    y = _section(c, ("What NCDMM accepted" if settled
                     else "What we are asking NCDMM to accept"), y)
    n = 0
    # One sentence per fact, not one per award. Two of these four carry no
    # change-of-basis clause at all, and two copies of *please name the
    # instrument* is the defect the evidence screen already learned —
    # thirty-two unread workbooks burying three real proposals. The awards
    # are named rather than counted.
    silent = [a for a, clause, citation in r.clauses if not citation]
    for award, clause, citation in r.clauses:
        if not citation:
            continue
        n += 1
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.2)
        c.drawString(MARGIN, y, f"{n}.")
        y = _para(c, (f"{award} — the change of basis under {citation}"
                      + (f". “{clause}”" if clause else ".")),
                  y, size=8.2, indent=14)
        y -= 1
    if silent:
        n += 1
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.2)
        c.drawString(MARGIN, y, f"{n}.")
        y = _para(c, (
            f"{', '.join(silent)} — the change of basis, for which the "
            f"executed agreement"
            f"{'s carry' if len(silent) > 1 else ' carries'} no clause. "
            f"Please name the instrument "
            f"{'each' if len(silent) > 1 else 'it'} is recorded against."),
            y, size=8.2, indent=14)
        y -= 1
    n += 1
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN, y, f"{n}.")
    y = _para(c, (
        f"The true-up in the table above: {_fmt_money(r.total_return)} "
        f"{'returned' if settled else 'to return'} to NCDMM and "
        f"{_fmt_money(r.total_claim)} {'claimed' if settled else 'to claim'}, "
        "award by award, each measured on its own invoices and its own "
        "classified cost."), y, size=8.2, indent=14)
    y -= 1

    # The offset, last, and only now — both directions are above it in
    # full, award by award and prime by prime. It is what YBI and NCDMM
    # are closing the year with rather than a reading of the register,
    # and the paper says which it is.
    n += 1
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN, y, f"{n}.")
    if r.multi_prime:
        parts = ", ".join(
            f"{_fmt_money(abs(r.settles_to(g)))} "
            f"{'to NCDMM' if r.settles_to(g) >= 0 else 'to YBI'} "
            f"under {prime}"
            for prime, g in r.by_prime)
        text = (
            f"Discharging those against each other, so 2025 closes in one "
            f"movement per programme: {parts}. Federal award funds are not "
            f"fungible between programmes, so each may be settled on its "
            f"own; taken together they come to "
            f"{_fmt_money(abs(r.settlement))} "
            f"{'to NCDMM' if r.settlement >= 0 else 'to YBI'}, which needs "
            f"NCDMM's agreement that an offset may cross the two.")
    else:
        text = (
            f"Discharging those against each other, so 2025 closes in one "
            f"movement of {_fmt_money(abs(r.settlement))} "
            f"{'to NCDMM' if r.settlement >= 0 else 'to YBI'} rather than "
            f"two transfers in opposite directions.")
    y = _para(c, text, y, size=8.2, indent=14)
    return y - 4


def _grounds(c, r: Reconciliation, y: float) -> float:
    if not r.grounds:
        return y
    y = _section(c, "Why the rate is acceptable", y)
    for i, g in enumerate(r.grounds, 1):
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.2)
        c.drawString(MARGIN, y, f"{i}.")
        y = _para(c, g, y, size=8.2, indent=14, colour=INK)
        y -= 1
    return y - 3


def _unfinished(c, r: Reconciliation, y: float) -> float:
    if not (r.caveats or r.excluded):
        return y
    y = _section(c, "What this page does not cover", y)
    for award, why in r.excluded:
        y = _para(c, f"{award} — {why}", y, size=7.6, colour=MUTED)
    for caveat in r.caveats:
        y = _para(c, caveat, y, size=7.6, colour=MUTED)
    return y - 3


def _signature(c, r: Reconciliation, y: float) -> float:
    """Somewhere to sign — or, where they already have, what they signed.

    Ruled lines under a page whose own band reads ACCEPTED invite a second
    signature on a settled matter, and a settlement signed twice is a
    settlement somebody will argue about. So the block is the record once
    there is one.
    """
    _rule(c, y + 6)
    y -= 4
    settled = r.standing == "ACCEPTED"
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.2)
    c.drawString(MARGIN, y, ("Accepted by " if settled else "Accepted for ")
                 + r.bill_to.name)
    y -= 12

    if settled:
        when = (f" on {_fmt_date(r.accepted_on)}" if r.accepted_on else "")
        y = _para(c, (
            f"{r.bill_to.name} accepted the rate stated above for the "
            f"{r.period} period, the award-by-award true-up in the table "
            f"and the single movement it is settled by{when}"
            + (f", recorded against {r.modification_reference}."
               if r.modification_reference else
               ". No written instrument is named on the record against this "
               "acceptance, which 2 CFR 200 expects and the agreements "
               "require; please supply the modification reference.")),
            y, size=7.6, colour=MUTED)
        return y - 6

    y = _para(c, (
        "Signing accepts the indirect cost rate stated above for the "
        f"{r.period} period, the award-by-award true-up in the table and "
        "the single movement it is settled by, and names the written "
        "instrument each change of basis is recorded against."),
        y, size=7.6, colour=MUTED)
    y -= 12

    half = (WIDTH - 24) / 2
    for x in (MARGIN, MARGIN + half + 24):
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.line(x, y, x + half, y)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, y - 9, "Signature")
    c.drawString(MARGIN + half + 24, y - 9, "Name and title")
    y -= 30
    for x in (MARGIN, MARGIN + half + 24):
        c.line(x, y, x + half, y)
    c.drawString(MARGIN, y - 9, "Date")
    c.drawString(MARGIN + half + 24, y - 9,
                 "Modification or instrument reference")
    return y - 20


def render_reconciliation(r: Reconciliation) -> bytes:
    """The page. One canvas, one page, and it says so if it overruns.

    A reconciliation that quietly became two pages would be a document
    somebody sends having read the first one. The overrun is a refusal
    rather than a second page, because the caller can shorten the caveats
    and cannot un-send the paper.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    c.setTitle(f"{r.remit_to.name} — {r.period} contract reconciliation")

    y = PAGE_H - MARGIN
    y = _head(c, r, y)
    y = _band(c, r, y)
    y = _rates(c, r, y)
    y = _section(c, "The reconciliation", y)
    y = _table_head(c, y)
    for prime, group in r.by_prime:
        for t in group:
            y = _row(c, t, y)
        # A subtotal of one award is that award, printed twice.
        if r.multi_prime and len(group) > 1:
            y = _subtotal(c, prime, group, y)
    y = _totals(c, r, y)
    y = _grounds(c, r, y)
    y = _asks(c, r, y)
    y = _unfinished(c, r, y)
    y = _signature(c, r, y)

    if y < MARGIN - 6:
        raise ValueError(
            f"the reconciliation overran one page by "
            f"{MARGIN - y:.0f}pt. It is a one-page document by design — "
            f"shorten the caveats or the grounds rather than letting it "
            f"become two, because a second page is a page nobody reads.")

    _page_number(c, 1, 1)
    c.showPage()
    c.save()
    return buf.getvalue()
