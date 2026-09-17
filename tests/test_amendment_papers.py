"""The memo and the form a restated invoice cannot travel without.

Pure, so this needs no database — which is the point of keeping `domain/`
free of `app.db`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from io import BytesIO

from app.domain.amendment_document import (AmendmentPapers, Movement,
                                           render_acceptance, render_memo)
from app.domain.invoice_document import Party

YBI = Party("Youngstown Business Incubator", "241 W Federal St\nYoungstown, OH 44503")
NCDMM = Party("NCDMM", "6800 Innovation Blvd\nJohnstown, PA 15904")


def papers(**over) -> AmendmentPapers:
    base = dict(
        period="2025", issued_on=date(2026, 9, 15), remit_to=YBI, bill_to=NCDMM,
        award="AM-LTM-PROJ88", award_title="Last Tactical Mile",
        modification_clause="A change in the scope of work that increases cost "
                            "requires the parties to execute a written "
                            "modification.",
        modification_citation="§4.4 Expense Changes; §4.7",
        as_billed_basis="A flat $3,000 a month, eleven months of twelve.",
        proposed_basis="The negotiated indirect rate on modified total direct cost.",
        rate_kind="INDIRECT_COMBINED", rate=Decimal("0.4399"),
        base_type="MTDC", seal_hash="60fb3f4b52219514d8f0dc8d20c962ad",
        movements=(Movement("LTM", "LTM", "AM-LTM-PROJ88",
                            Decimal("16500.00"),
                            under_recovered=Decimal("107683.52")),),
    )
    base.update(over)
    return AmendmentPapers(**base)


def text_of(pdf: bytes) -> str:
    """PDF text is compressed — searching the bytes for a phrase plainly on
    the page finds nothing. This repository has made that mistake twice."""
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


def test_one_invoice_never_runs_both_ways():
    """The netting `061` took out of the view, refused at the type.

    An invoice that both over-collected and under-recovered is not a fact
    about the record; it is two facts stapled together, and the only way to
    print it is as a net.
    """
    with pytest.raises(ValueError, match="two directions"):
        Movement("DRIVE-AM", "DRIVE-AM", "AM-DRIVE-AM", Decimal("37593.90"),
                 under_recovered=Decimal("100.00"),
                 over_collected=Decimal("50.00"))


def test_the_form_prints_two_totals_and_never_their_difference():
    """$120,000 to ask for and $120,000 to give back is not a quiet year."""
    p = papers(position_under=Decimal("107683.52"),
               position_over=Decimal("58786.31"),
               movements=(
        Movement("LTM", "LTM", "AM-LTM-PROJ88", Decimal("16500.00"),
                 under_recovered=Decimal("107683.52")),
        Movement("DRIVE-AM", "DRIVE-AM", "AM-DRIVE-AM", Decimal("37593.90"),
                 over_collected=Decimal("58786.31")),
    ))
    assert p.to_claim == Decimal("107683.52")
    assert p.to_return == Decimal("58786.31")

    body = text_of(render_acceptance(p))
    assert "107,683.52" in body and "58,786.31" in body, body[:400]

    # The difference must appear nowhere — that is the whole rule.
    net = "48,897.21"
    assert net not in body, (
        f"the acceptance form prints {net}, which is the two directions "
        f"netted. `v_restatement` carried exactly that figure in a column "
        f"named as though it were the summary and `061` removed it.")
    assert "not added together" in body, body[-600:]


def test_the_memo_quotes_the_clause_and_does_not_recall_one():
    """`056` found three provisions cited to clauses the agreement does not
    contain. A memo that recited one from memory would be that on a
    sponsor's desk."""
    body = text_of(render_memo(papers()))
    assert "written modification" in body, body[:600]
    assert "§4.4" in body or "4.4" in body, body[:600]

    # And where the record carries none, it says so rather than inventing.
    silent = text_of(render_memo(papers(modification_clause="",
                                        modification_citation="")))
    assert "carries no clause on record" in silent, silent[:800]
    assert "4.4" not in silent, (
        "the memo invented a clause citation for an award whose agreement "
        "carries none: " + silent[:600])


def test_both_papers_say_they_are_a_proposal():
    for render in (render_memo, render_acceptance):
        body = text_of(render(papers()))
        assert "PROPOSED" in body, body[:300]
        assert "until NCDMM accepts it in writing" in body, body[:400]


def test_the_band_prints_in_both_directions_on_paper():
    unsigned = text_of(render_memo(papers()))
    assert "NOT CERTIFIED" in unsigned, unsigned[:400]

    signed = text_of(render_memo(papers(
        certified=True,
        certification_line="Certified by Tom Metzinger, 15 Sep 2026.")))
    assert "Certified by Tom Metzinger" in signed, signed[:400]
    assert "NOT CERTIFIED" not in signed, signed[:400]


def test_rendering_is_deterministic():
    """`038`'s rule: the filing route content-addresses what it renders, so
    the same paper files once however often the button is pressed."""
    p = papers()
    assert render_memo(p) == render_memo(p)
    assert render_acceptance(p) == render_acceptance(p)


def test_the_form_carries_a_place_to_name_the_modification():
    """`acceptance_names_its_modification` refuses an acceptance that cannot
    name the instrument. A form with nowhere to write it sets the sponsor up
    to fail that refusal."""
    body = text_of(render_acceptance(papers()))
    assert "Modification this is made under".upper() in body.upper(), body[-900:]


def test_the_form_never_prints_a_count_where_a_number_belongs():
    """`v_restatement.invoices` is an integer count, and a first draft put it
    under a heading reading INVOICE — so the form told a payables clerk to
    match on invoice "1".

    The restatement's unit is the objective, not the invoice, and the form
    says so: what it covers, how many invoices that is, and the numbers
    themselves underneath where a clerk can read them.
    """
    p = papers(movements=(
        Movement("10039", "LTM", "AM-LTM-PROJ88", Decimal("18993.52"),
                 invoice_count=1,
                 invoice_numbers="Invoice dated 01 May 2026.",
                 under_recovered=Decimal("4035.55")),))
    body = text_of(render_acceptance(p))

    assert "INVOICE" in body.upper(), body[:400]
    assert "10039" in body, (
        "the form carries no invoice number, so nothing on it can be matched "
        "to what the sponsor paid: " + body[:600])
    # And the count must not be standing in for the number.
    assert "\n1\n" not in body, (
        "a bare count is printed where an invoice number belongs: "
        + body[:600])


def test_the_ask_is_the_recorded_position_and_never_the_sum_of_the_lines():
    """The defect this form shipped with, and the worst one available to it.

    A `restatement_line` is the **as-billed** reading of one invoice: the
    indirect on its face against what the rate supports on its own base. The
    position is the objective rebuilt against the cost record, and the engine
    records both because they differ. On Drive AM's real 2025 rows the lines
    add to $254,808.06 of forgone recovery while the position is $58,786.31
    **over-collected** — the indirect was recovered inside a loaded labour
    rate, so no invoice carries an indirect line at all.

    A form that summed the lines put a claim in front of the sponsor running
    the opposite way from what the record supports. So the totals are passed
    in, exactly as `invoice_document.py` takes its header total: *an invoice
    that does not foot prints both figures and says so, instead of agreeing
    with itself by construction.*
    """
    p = papers(position_over=Decimal("58786.31"),
               position_under=Decimal("0"),
               movements=tuple(
                   Movement(f"90{i:02d}", "DRIVE-AM", "AM-DRIVE-AM",
                            Decimal("48267.00"),
                            under_recovered=Decimal("21234.005"))
                   for i in range(12)))

    assert p.line_claim == Decimal("254808.06")
    assert p.to_claim == Decimal("0.00"), "the sum of the lines became the ask"
    assert p.to_return == Decimal("58786.31")
    assert not p.lines_foot_to_the_position

    body = text_of(render_acceptance(p))
    assert "THE POSITION" in body, body[:600]
    assert "58,786.31" in body and "254,808.06" in body, body[:900]
    # And it says why they differ, rather than leaving a reader to reconcile
    # two totals that are not meant to reconcile.
    assert "not meant to add to each other" in body, body[-900:]


def test_the_memo_says_which_direction_the_award_runs():
    """A sponsor reading the memo should know whether this is an ask or a
    refund before they reach the form, and an organisation that raises its
    own over-collection first is one the rest of the ask can be believed
    from."""
    def flat(pdf):
        # The renderer wraps, so a sentence is split across lines wherever it
        # happens to run out of width. Asserting on the raw text would pin the
        # wrap rather than the words.
        return " ".join(text_of(pdf).split())

    give_back = flat(render_memo(papers(position_over=Decimal("58786.31"))))
    assert "collected above what 2025 supports" in give_back, give_back[:900]
    assert "58,786.31" in give_back
    assert "proposes to return it" in give_back

    ask = flat(render_memo(papers(position_under=Decimal("107683.52"))))
    assert "supported by 2025 and not recovered" in ask, ask[:900]
    assert "107,683.52" in ask
