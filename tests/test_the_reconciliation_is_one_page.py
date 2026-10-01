"""One page, every contract NCDMM administers, and what it must never do.

`amendment_document.py` shipped the worst defect available to a paper that
leaves the building: it summed the per-invoice lines and printed the sum as
the ask, which on Drive AM is $254,808.06 *to claim* against a recorded
position of $58,786.31 *to give back* — $313,000 apart and pointing the
other way. This page carries every award instead of one, so the same
mistake is available four times over and a fifth way besides: printing the
single settlement figure *in place of* the two directions, which is the
summary a reader would find natural and which `061` removed from
`v_restatement` for exactly that reason. The movement the parties settle
by is on the page now — they are closing 2025 across the relationship —
and the rule that governs it is one of order: both directions in full
first, the aggregate after, the paper saying which is which.

So the assertions are about behaviour, not about source. Render the page,
read it back with `pypdf`, and ask what is printed on it — because a
renderer can import the right helper and still compose its own sentence two
lines down, which is how `122`'s rehearsal state reached sixteen PDFs as
*"Certified by Tom Metzinger"* over a rate nobody had signed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.invoice_document import Party
from app.domain.reconciliation_document import (Contract, RateLine,
                                                Reconciliation,
                                                render_reconciliation)

pypdf = pytest.importorskip("pypdf")

_YBI = Party("Youngstown Business Incubator",
             "241 W Federal St\nYoungstown, OH 44503", "ybi.org")
_NCDMM = Party("NCDMM / America Makes", "6800 Innovation Blvd\nJohnstown, PA")


def _contracts() -> tuple[Contract, ...]:
    """The three, in the directions the record actually holds them.

    Two give back and one claims. A fixture where all three ran the same way
    could not fail for the netting this file exists to refuse.
    """
    return (
        Contract("AM-DRIVE-AM", "DRIVE-AM", "Drive-AM", 12,
                 Decimal("579240.87"), Decimal("361451.88"),
                 Decimal("89314.76"), Decimal("450766.64"),
                 to_return=Decimal("128474.23")),
        Contract("AM-HYBRID-P2", "HYBRID-II", "Hybrid-Phase-2", 9,
                 Decimal("187416.05"), Decimal("91788.13"),
                 Decimal("22680.85"), Decimal("114468.98"),
                 to_return=Decimal("72947.07")),
        Contract("AM-LTM-PROJ88", "LTM", "Last-Tactical-Mile", 12,
                 Decimal("368222.24"), Decimal("330513.06"),
                 Decimal("81669.78"), Decimal("412182.84"),
                 to_claim=Decimal("43960.60"),
                 indirect_billed=Decimal("44400.00")),
    )


def _page(**over) -> Reconciliation:
    kw = dict(
        period="2025", issued_on=date(2026, 9, 29), remit_to=_YBI,
        bill_to=_NCDMM, programme="America Makes · prime FA8650-20-2-5700",
        contracts=_contracts(),
        rates=(RateLine("FRINGE", Decimal("0.2190"), Decimal("401783.60"),
                        Decimal("1835047.17"), "the payroll register's wages"),
               RateLine("OVERHEAD", Decimal("0.1235"), Decimal("584774.52"),
                        Decimal("4736602.11"), "modified total direct cost"),
               RateLine("G&A", Decimal("0.1237"), Decimal("585875.91"),
                        Decimal("4736602.11"), "modified total direct cost"),
               RateLine("INDIRECT_COMBINED", Decimal("0.2471"),
                        Decimal("1170650.43"), Decimal("4736602.11"),
                        "modified total direct cost")),
        basis="Indirect is applied to modified total direct cost.",
        admin_labour_basis="POOL",
        seal_hash="60fb3f4b5221aaaa", judgments=757,
        clauses=(("DRIVE-AM", "", ""),
                 ("HYBRID-II", "No change binding unless in writing", "§4.4")),
        grounds=("The classifications were sealed before any rate was "
                 "computed and the rate carries the seal.",),
        excluded=(("DIG-ENG", "primed elsewhere (N00174-20-1-0031)."),),
        certification_line="NOT CERTIFIED — nobody has put their name to it.",
        reference="America Makes · 2025")
    kw.update(over)
    return Reconciliation(**kw)


def _text(r: Reconciliation) -> tuple[str, int]:
    body = render_reconciliation(r)
    import io
    reader = pypdf.PdfReader(io.BytesIO(body))
    return "\n".join(p.extract_text() for p in reader.pages), len(reader.pages)


# ── it is one page, and says so rather than becoming two ─────────────

def test_it_is_one_page():
    _, pages = _text(_page())
    assert pages == 1


def test_it_refuses_to_become_two_rather_than_overrunning_quietly():
    """A reconciliation that quietly grew a second page is a document
    somebody sends having read the first one. The caller can shorten the
    caveats; they cannot un-send the paper."""
    with pytest.raises(ValueError, match="one page"):
        render_reconciliation(_page(
            caveats=tuple(f"Something outstanding, number {i}, at about the "
                          f"length these sentences actually run to."
                          for i in range(40))))


# ── the two directions, never netted ─────────────────────────────────

def test_both_directions_are_printed_in_full():
    text, _ = _text(_page())
    assert "201,421.30" in text, "the money going back to NCDMM is not on the page"
    assert "43,960.60" in text, "the money being claimed is not on the page"


def test_both_directions_are_printed_before_the_single_movement():
    """$201,421.30 to give back and $43,960.60 to claim is not a
    $157,460.70 year, and that is still what the **record** holds: `061`
    took `net_movement` off `v_restatement` because a single figure hides
    both directions.

    What the page now also carries is the movement YBI and NCDMM close the
    year **by**, which is a settlement mechanism rather than a reading of
    the register — `SETTLEMENT_2025.md` resolved the identical tension and
    its rule is the one held here: both directions in full first, the
    aggregate after, and the paper saying which is which. A draft that
    opened on the net would be the thing `061` refused.
    """
    text, _ = _text(_page())
    net = Decimal("201421.30") - Decimal("43960.60")
    assert f"{net:,.2f}" in text, "the single movement is not on the page"
    assert text.index("201,421.30") < text.index(f"{net:,.2f}"), (
        "the page prints the net before the money going back to NCDMM")
    assert text.index("43,960.60") < text.index(f"{net:,.2f}"), (
        "the page prints the net before the money being claimed")
    assert "not netted" in text.lower(), (
        "the page does not say the two columns are not meant to add up")
    # Once, in the ask. A second occurrence means it has leaked into the
    # table — a totals row or a subtotal quietly netting on the way past,
    # which puts the aggregate above the figures it is an aggregate of.
    assert text.count(f"{net:,.2f}") == 1, (
        f"{net:,.2f} is printed {text.count(f'{net:,.2f}')} times; the "
        f"single movement belongs in the ask and nowhere above it")


def test_the_single_movement_is_the_two_directions_and_nothing_else():
    """Derived from the columns, never recorded beside them.

    A stored net is a third figure free to disagree with the two it came
    from, which is what `rate.superseded_by` turned out to be.
    """
    r = _page()
    assert r.settlement == r.total_return - r.total_claim


# ── two primes are two pots of money ─────────────────────────────────

def _two_primes() -> tuple[Contract, ...]:
    """The three America Makes awards, and the one NCDMM primes elsewhere."""
    three = tuple(
        Contract(**{**c.__dict__, "prime": "FA8650-20-2-5700"})
        for c in _contracts())
    return (Contract("AM-ICAM-DIGENG", "DIG-ENG", "SRA-0350", 7,
                     Decimal("579074.25"), Decimal("207398.87"),
                     Decimal("51248.26"), Decimal("258647.13"),
                     to_return=Decimal("320427.12"),
                     prime="N00174-20-1-0031"),) + three


def test_two_primes_are_two_groups_with_a_subtotal_each():
    """Federal award funds are not fungible between programmes, so a reader
    has to be able to settle one group without the other."""
    r = _page(contracts=_two_primes(), excluded=())
    assert r.multi_prime
    primes = [p for p, _ in r.by_prime]
    assert primes == ["N00174-20-1-0031", "FA8650-20-2-5700"], (
        "the groups are not ordered with the larger give-back first")
    text, _ = _text(r)
    # the three-award group's subtotal, in both directions
    assert "201,421.30" in text, "the FA8650 group's give-back is not shown"
    assert "FA8650-20-2-5700 · 3 awards" in text


def test_a_group_of_one_prints_no_subtotal_of_itself():
    """A subtotal of one award is that award, printed twice."""
    text, _ = _text(_page(contracts=_two_primes(), excluded=()))
    assert "N00174-20-1-0031 · 1 award" not in text


def test_an_offset_across_two_primes_says_it_needs_agreement():
    """Within a prime an offset is arithmetic. Across two it is something
    NCDMM has to agree to, and a page that quietly added the columns up
    would be asking for that without saying so."""
    r = _page(contracts=_two_primes(), excluded=())
    text, _ = _text(r)
    assert f"{r.settles_to(r.by_prime[0][1]):,.2f}" in text
    assert f"{r.settles_to(r.by_prime[1][1]):,.2f}" in text
    assert "not fungible between programmes" in text
    assert "cross the two" in text


def test_the_prime_is_named_on_every_row():
    """Dropped from a heading onto the row it belongs to, because a reader
    looking at one award should not have to scroll up to learn which
    programme's money it is.

    Asserted by **count** rather than by presence. The first spelling asked
    whether each prime appeared anywhere on the page and passed with the
    row draw deleted, because the subtotal label and the ask both name them
    — the fifth instance here of a test that cannot fail for the thing it
    names, found the only way any of them are.
    """
    r = _page(contracts=_two_primes(), excluded=())
    text, _ = _text(r)
    for prime, group in r.by_prime:
        assert text.count(prime) >= len(group) + 1, (
            f"{prime} is named {text.count(prime)} time(s) for "
            f"{len(group)} award(s) — not once per row")


def test_the_give_back_is_not_buried():
    """Two of these three run against YBI, and a page that led with the
    claim and mentioned the credits underneath is read exactly once."""
    text, _ = _text(_page())
    assert text.index("128,474.23") < text.index("43,960.60"), (
        "the claim is printed above the larger give-back")


# ── the ask is the recorded position ─────────────────────────────────

def test_the_totals_are_the_awards_own_positions():
    r = _page()
    assert r.total_return == Decimal("201421.30")
    assert r.total_claim == Decimal("43960.60")


def test_an_award_may_run_either_way_and_the_page_still_adds_within_each():
    """`Movement` refuses two directions on one row because one invoice runs
    one way. A *page* covers three awards and must not: refusing here would
    force the caller to net them to get a document out."""
    r = _page()
    assert any(c.to_return for c in r.contracts)
    assert any(c.to_claim for c in r.contracts)


# ── the band prints in both directions ───────────────────────────────

def test_an_unsigned_rate_says_so_and_names_nobody():
    text, _ = _text(_page())
    assert "NOT CERTIFIED" in text
    assert "PROPOSED" in text, "an unanswered settlement does not say so"


def test_a_page_the_sponsor_has_answered_stops_asking():
    """`093` found the acceptance form printing *"PROPOSED — NOT A CLAIM"*
    over a signature NCDMM had already given. The same defect is available
    here in reverse: ruled signature lines under a band reading ACCEPTED
    invite a second signature on a settled matter."""
    settled = tuple(
        Contract(c.award_id, c.objective_id, c.title, c.invoices, c.billed,
                 c.direct_supported, c.indirect_supported, c.supported,
                 to_return=c.to_return, to_claim=c.to_claim,
                 indirect_billed=c.indirect_billed, status="ACCEPTED",
                 accepted_on=date(2026, 9, 15), modification_ref="Mod 002")
        for c in _contracts())
    text, pages = _text(_page(contracts=settled))
    assert pages == 1
    assert "accepted" in text.lower()
    assert "Name and title" not in text, (
        "a settled page still offers somewhere to sign it again")
    assert "Mod 002" in text, (
        "the acceptance does not name the instrument it is recorded "
        "against, which is what acceptance_names_its_modification exists "
        "to refuse")


# ── what it does not cover, it names ─────────────────────────────────

def test_an_award_left_off_the_page_is_named_on_it():
    text, _ = _text(_page())
    assert "DIG-ENG" in text, (
        "the fourth award is simply absent. A page three-quarters complete "
        "with no note is worse than one that says which quarter is missing.")


def test_a_clause_the_agreement_does_not_carry_is_asked_for_not_invented():
    """`056` found three provisions on two awards cited to clauses those
    agreements do not contain. Drive AM carries no change-of-basis clause,
    and the page says so rather than reciting one."""
    text, _ = _text(_page())
    assert "§4.4" in text, "the clause that is on the record is not quoted"
    body = text[text.lower().index("drive-am — the change of basis"):]
    assert "name the instrument" in body[:300], (
        "the award with no clause does not ask NCDMM to name one")


# ── every figure prints in the house spelling ────────────────────────

def test_no_bare_decimal_reaches_the_paper():
    """`money()`'s eight spellings, in the place a payables clerk is
    checking a figure against a figure."""
    text, _ = _text(_page())
    for bare in ("201421.30", "43960.60", "1170650.43", "4736602.11"):
        assert bare not in text, f"{bare} printed without the house spelling"


# ── against the record, rather than against a fixture ────────────────

import os  # noqa: E402

_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")


@_db
def test_the_page_prints_the_registers_own_positions():
    """The ask is the recorded position, never the sum of the lines.

    `amendment_document.py` records what summing them did: Drive AM's lines
    add to 254,808.06 *to claim* where the rebuilt position is 58,786.31 to
    **give back**, because the indirect was recovered inside a loaded labour
    rate and no invoice carries an indirect line at all. The register is
    asked here, and the page has to agree with it to the cent.
    """
    from decimal import Decimal as D

    from app.db import one, open_pool
    from app.routers.restate import STANDING, _reconciliation

    open_pool()
    held = one("""SELECT coalesce(sum(r.over_collected), 0) AS ret,
                         coalesce(sum(r.under_recovered), 0) AS claim,
                         count(*) AS n
                    FROM v_restatement r
                   WHERE r.period = '2025' AND r.status = ANY(%s)
                     AND upper(coalesce(r.sponsor, '')) LIKE '%%NCDMM%%'""",
               (list(STANDING),))
    if not held or not held["n"]:
        pytest.skip("no NCDMM restatement stands on this record")

    r = _reconciliation("2025")
    assert len(r.contracts) == held["n"]
    assert r.total_return == D(str(held["ret"]))
    assert r.total_claim == D(str(held["claim"]))
    assert len(r.contracts) == held["n"]


@_db
def test_the_rate_on_the_page_is_the_rate_the_restatement_used():
    """Not "the live rate".

    A restatement carries the rate it was measured on, and a page printing
    today's rate over yesterday's settlement would be `088`'s overtaken
    claim with the two halves swapped — the figures would be right about a
    rate the reader would then look up and fail to find.
    """
    from app.db import one, open_pool
    from app.routers.restate import STANDING, _reconciliation

    open_pool()
    row = one("""SELECT r.rate_id FROM v_restatement r
                  LEFT JOIN award a USING (award_id)
                 WHERE r.period = '2025' AND r.status = ANY(%s)
                   AND coalesce(a.prime_agreement, '')
                       LIKE '%%FA8650-20-2-5700%%'
                 LIMIT 1""", (list(STANDING),))
    if not row:
        pytest.skip("no America Makes restatement stands on this record")

    used = one("SELECT kind, rate FROM rate WHERE rate_id = %s",
               (row["rate_id"],))
    r = _reconciliation("2025")
    printed = {x.kind: x.rate for x in r.rates}
    assert used["kind"] in printed, (
        f"the page does not print {used['kind']}, which is the pool the "
        f"standing restatement was measured on")
    assert printed[used["kind"]] == used["rate"]


# ── two figures in one place is not a figure ─────────────────────────

def test_no_two_columns_can_print_over_each_other():
    """The first spelling put TO RETURN 34pt from TO CLAIM and the totals
    row printed `201,421.30` over `43,960.60` — the two directions this page
    exists to keep apart, overlapping, in the row a reader takes the
    settlement from. It renders as a run of digits that is neither figure.

    `pypdf` cannot see it: it reads the two strings and not where they
    landed, so every assertion above passed over it and only looking at the
    page found it. The geometry is checkable, though, which is what this is
    — each money column has to be at least as wide as the widest figure it
    could be asked to print.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from app.domain.reconciliation_document import _TCOLS

    # Wider than anything on these awards, and wide enough that the next
    # engagement's figures do not quietly reintroduce this.
    widest = stringWidth("(99,999,999.99)", "Helvetica-Bold", 8.2)
    money_edges = _TCOLS[3:] + (612.0 - 2 * 54.0,)   # through to the margin
    for left, right in zip(money_edges, money_edges[1:]):
        assert right - left >= widest, (
            f"a money column is {right - left:.0f}pt wide against a figure "
            f"that can run to {widest:.0f}pt — two figures will print over "
            f"each other, and the result is neither of them")
