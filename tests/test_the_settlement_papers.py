"""The MOU and the amendment that close a year with a sponsor.

These two papers go to NCDMM for signature, which makes one property
load-bearing above all the others: **they must not assert that NCDMM has
already answered.** The reference record carries `status = 'ACCEPTED'` on
every standing restatement because `drive_the_close.py --rehearsal` wrote it
there, so a renderer that read the status would print the sponsor's agreement
onto the document whose whole purpose is to obtain it — `122`'s defect, in
the fourth place it has been available.

Everything else here is a rule this repository already keeps somewhere and
has paid for once: both directions before the net, a column wide enough for
the figure it prints, a count that is read rather than assumed, and a page
guard that refuses rather than overrunning.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.domain.invoice_document import Party
from app.domain.settlement_document import (AMEND_COLS, WIDEST_MONEY,
                                            AwardPosition, SettlementPapers,
                                            _prime_key,
                                            no_paper_here_claims_an_acceptance,
                                            render_amendment, render_mou)

D = Decimal
YBI = Party("Youngstown Business Incubator",
            "241 W Federal St\nYoungstown, OH 44503", "ybi.org")
AM = Party("NCDMM / America Makes",
           "6800 Innovation Blvd\nJohnstown, PA 15904")


def position(award="AM-DRIVE-AM", title="Drive AM", billed="579240.87",
             restated="450766.64", over="128474.23", under="0.00",
             indirect="0.00", prime="FA8650-20-2-5700", invoices=12):
    return AwardPosition(award=award, title=title, objective=award,
                         prime=prime, invoices=invoices, billed=D(billed),
                         restated=D(restated), over_collected=D(over),
                         under_recovered=D(under),
                         indirect_billed=D(indirect))


THREE = (position(),
         position("AM-HYBRID-P2", "Hybrid Phase 2", "187416.05", "114468.98",
                  "72947.07", "0.00", "0.00", "AFRL FA8650-20-2-5700", 9),
         position("AM-LTM-PROJ88", "Last Tactical Mile", "368222.24",
                  "412182.84", "0.00", "43960.60", "44400.00"))


def papers(positions=THREE, *, certification=None, rate_is_live=False,
           without_clause=("Drive AM",)):
    return SettlementPapers(
        remit_to=YBI, bill_to=AM, period="2025", issued_on=date(2026, 10, 7),
        reference="2025 close-out · FA8650-20-2-5700", positions=positions,
        rate_kind="INDIRECT_COMBINED", rate_applied=D("0.2471"),
        fringe_rate=D("0.2190"), overhead_rate=D("0.1235"),
        ga_rate=D("0.1237"), rate_pool=D("1170650.43"),
        rate_base=D("4736602.11"), rate_is_live=rate_is_live,
        rate_status="SUPERSEDED",
        certification=certification or {"certified": False, "rehearsal": False,
                                        "why_not": "nobody has signed it"},
        basis_clauses=(("Drive AM", "no clause on the record"),
                       ("Hybrid Phase 2", "§4.4")),
        awards_without_a_clause=without_clause,
        overhead_pool=D("584774.52"), ga_pool=D("585875.91"),
        fringe_pool=D("401783.60"), fringe_base=D("1835047.17"))


def text_of(pdf: bytes) -> str:
    from io import BytesIO
    r = PdfReader(BytesIO(pdf))
    return "\n".join(p.extract_text() for p in r.pages)


def pages_of(pdf: bytes) -> int:
    from io import BytesIO
    return len(PdfReader(BytesIO(pdf)).pages)


# ───────────────── the one that matters ─────────────────

def test_neither_paper_claims_the_sponsor_has_accepted():
    """The record says ACCEPTED and the sponsor has answered nothing.

    Watched failing by handing the renderer a status and letting it print:
    the phrase list in `no_paper_here_claims_an_acceptance` is the assertion,
    and the papers carry a FOR SIGNATURE band instead.
    """
    p = papers()
    for pdf in (render_amendment(p), render_mou(p)):
        body = text_of(pdf)
        assert no_paper_here_claims_an_acceptance(body), body
        assert "FOR SIGNATURE — NOT YET EXECUTED" in body


def test_the_signature_block_is_ruled_and_nobody_is_named_on_it():
    body = text_of(render_amendment(papers()))
    assert body.count("Signature") == 2
    assert body.count("Name and title") == 2
    for name in ("Tom Metzinger", "Metzinger", "Heidi", "Barb"):
        assert name not in body


# ───────────────── length ─────────────────

def test_the_amendment_is_one_page_and_the_memorandum_is_two():
    p = papers()
    assert pages_of(render_amendment(p)) == 1
    assert pages_of(render_mou(p)) == 2


def test_the_amendment_refuses_to_become_two_pages():
    """A one-page instrument is the thing that gets read and signed.

    Six awards with long titles is what a next engagement looks like; the
    guard has to refuse rather than silently spill onto a second sheet.
    """
    many = tuple(position(f"AM-{i}", f"A Rather Long Project Name {i}")
                 for i in range(9))
    with pytest.raises(ValueError, match="overran one page"):
        render_amendment(papers(many, without_clause=()))


# ───────────────── both directions, then the net ─────────────────

def test_both_directions_are_printed_in_full_before_the_net():
    p = papers()
    body = text_of(render_amendment(p))
    ret, claim, net = "201,421.30", "43,960.60", "157,460.70"
    for figure in (ret, claim, net):
        assert figure in body, figure
    assert body.index(ret) < body.index(net)
    assert body.index(claim) < body.index(net)


def test_the_net_is_the_two_directions_and_nothing_else():
    p = papers()
    assert p.to_return == D("201421.30")
    assert p.to_claim == D("43960.60")
    assert p.net == p.to_return - p.to_claim
    assert p.net == p.billed_total - p.restated_total


def test_the_waiver_names_the_net_and_the_period_it_covers():
    body = text_of(render_amendment(papers()))
    assert "unrecoverable by either" in body
    assert "157,460.70" in body
    assert "no other period" not in body.lower()
    assert "any other period" in body


def test_a_position_that_runs_both_ways_is_refused():
    with pytest.raises(ValueError, match="runs both ways"):
        position(over="100.00", under="50.00")


def test_a_position_that_does_not_foot_is_refused():
    with pytest.raises(ValueError, match="does not foot"):
        position(billed="100.00", restated="90.00", over="5.00")


# ───────────────── one prime per instrument ─────────────────

def test_two_primes_in_one_instrument_are_refused():
    """Federal award funds are not fungible between programmes."""
    navy = position("AM-ICAM-DIGENG", "Digital Engineering", "579074.25",
                    "258647.13", "320427.12", "0.00", "0.00",
                    "N00174-20-1-0031", 7)
    with pytest.raises(ValueError, match="one prime agreement"):
        papers(THREE + (navy,))


def test_the_register_spells_one_prime_two_ways_and_that_is_one_prime():
    assert _prime_key("FA8650-20-2-5700") == _prime_key(
        "AFRL FA8650-20-2-5700")
    assert _prime_key("FA8650-20-2-5700") != _prime_key("N00174-20-1-0031")


def test_the_navy_award_is_not_on_the_air_force_amendment():
    body = text_of(render_amendment(papers()))
    for absent in ("Digital Engineering", "N00174", "320,427.12"):
        assert absent not in body, absent


# ───────────────── the figures a reader adds up ─────────────────

def test_no_money_column_can_print_over_its_neighbour():
    """`reconciliation_document.py` printed 201,421.30 over 43,960.60 once —
    in the one row a reader takes the settlement from, rendering as a run of
    digits that is neither figure. `pypdf` reads the strings and not where
    they landed, so no text assertion can see it. The geometry can.
    """
    widest = stringWidth(WIDEST_MONEY, "Helvetica", 9)
    for head, x, w, align in AMEND_COLS:
        if align != "r":
            continue
        assert w - 10 >= widest, (
            f"{head} is {w:.0f}pt and the widest figure it could print is "
            f"{widest:.0f}pt")


def test_the_component_percentages_are_never_printed_beside_the_combined():
    """Overhead 12.35% and G&A 12.37% sum to 24.72% against a combined
    24.71%. All three are right: each is its own pool over the base, rounded
    to four places independently. Printed together they put an apparent
    arithmetic error on a sponsor's instrument, so the papers print the
    **pools**, which add exactly.
    """
    p = papers()
    assert p.overhead_pool + p.ga_pool == p.rate_pool
    body = text_of(render_mou(p))
    assert "584,774.52" in body and "585,875.91" in body
    assert "1,170,650.43" in body
    for rounded in ("12.35%", "12.37%"):
        assert rounded not in body, (
            f"{rounded} is printed beside a combined 24.71% it does not "
            f"sum to")


def test_pools_that_do_not_add_to_the_rate_pool_are_refused():
    with pytest.raises(ValueError, match="do not add to the pool"):
        SettlementPapers(
            remit_to=YBI, bill_to=AM, period="2025",
            issued_on=date(2026, 10, 7), reference="x", positions=THREE,
            rate_kind="INDIRECT_COMBINED", rate_applied=D("0.2471"),
            fringe_rate=D("0.2190"), overhead_rate=D("0.1235"),
            ga_rate=D("0.1237"), rate_pool=D("1170650.43"),
            rate_base=D("4736602.11"), rate_is_live=False,
            rate_status="SUPERSEDED", certification=None,
            overhead_pool=D("584774.52"), ga_pool=D("1.00"))


def test_how_many_billed_no_indirect_is_read_and_never_counted():
    """A first draft said all three projects carried no indirect line and
    Last Tactical Mile carried $44,400.00 of it. A count is not a finding.
    """
    p = papers()
    assert p.without_an_indirect_line == 2
    body = text_of(render_mou(p))
    assert "two carried no indirect line" in body
    assert "44,400.00" in body
    assert "three carried no indirect line" not in body


# ───────────────── the bands ─────────────────

def test_the_band_says_the_rate_carries_no_signature():
    body = text_of(render_amendment(papers()))
    assert "NOT CERTIFIED" in body


def test_a_rehearsal_signature_is_not_a_signature_on_these_papers():
    cert = {"certified": True, "rehearsal": True,
            "certified_by": "Tom Metzinger", "why_not": ""}
    body = text_of(render_amendment(papers(certification=cert)))
    assert "REHEARSAL" in body
    assert "Metzinger" not in body


def test_a_superseded_rate_says_so_above_the_figures():
    p = papers(rate_is_live=False)
    body = text_of(render_amendment(p))
    assert "SUPERSEDED" in body.upper()
    assert body.index("SUPERSEDED") < body.index("201,421.30")


def test_a_live_rate_prints_no_supersession_notice():
    body = text_of(render_amendment(papers(rate_is_live=True)))
    assert "HAS BEEN SUPERSEDED" not in body


def test_the_paper_never_prints_the_enum_a_database_uses():
    """`107`: the tie register printed `WAGE_BASE_IS_THE_REGISTER` on the
    panel a reviewer reads first. An enum on a sponsor's instrument is the
    same defect one audience further out.
    """
    for pdf in (render_amendment(papers()), render_mou(papers())):
        assert "INDIRECT_COMBINED" not in text_of(pdf)


# ───────────────── the award with no clause ─────────────────

def test_an_award_with_no_change_of_basis_clause_is_named_once():
    body = text_of(render_amendment(papers()))
    assert body.count("name the instrument") == 1


def test_where_every_award_carries_a_clause_nothing_is_asked_for():
    body = text_of(render_amendment(papers(without_clause=())))
    assert "name the instrument" not in body


# ───────────────── the script and the router agree ─────────────────

def test_the_script_reads_the_same_standing_set_the_router_writes():
    """Two spellings of one predicate is how a script and a screen come to
    disagree about what is on the record.
    """
    import importlib.util
    from pathlib import Path

    from app.routers.restate import STANDING as ROUTER

    spec = importlib.util.spec_from_file_location(
        "settlement_papers",
        Path(__file__).resolve().parents[1] / "scripts/settlement_papers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod.STANDING) == tuple(ROUTER)


def test_rendering_is_deterministic():
    """A digest that moves means a figure moved."""
    p = papers()
    assert render_amendment(p) == render_amendment(p)
    assert render_mou(p) == render_mou(p)
