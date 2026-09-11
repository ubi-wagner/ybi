"""What the matcher may and may not say.

Every one of these is a way of getting it wrong that would look like working
software. A matcher that attaches the wrong invoice to the right amount does
not fail — it produces a judgment graded VERIFIED against a document nobody
checked, which is the one grade an auditor will pull.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.evidence_match import (
    DATE_WINDOW_DAYS, Document, Target, propose, propose_all, similarity,
    tokens, weigh,
)


def doc(**kw) -> Document:
    base = dict(evidence_id="EV-1", filename="invoice.pdf",
                doc_amount=Decimal("1200.00"), doc_date=date(2025, 3, 10),
                vendor_name="Acme Consulting LLC")
    return Document(**{**base, **kw})


def target(**kw) -> Target:
    base = dict(target_type="LEDGER_GROUP", target_id="5227\x1fAcme Consulting",
                label="5227 Portfolio consulting · Acme Consulting",
                amount=Decimal("1200.00"), payee="Acme Consulting",
                first_day=date(2025, 3, 1), last_day=date(2025, 3, 31), lines=3)
    return Target(**{**base, **kw})


# ── The vendor comparison ─────────────────────────────────────────────

def test_a_legal_form_is_not_part_of_a_name():
    """"Acme Inc" and "Acme LLC" are one signal about one party.

    Leaving the form in makes every limited company faintly similar to every
    other, which is a floor of noise under every comparison.
    """
    assert tokens("Acme Consulting, LLC") == tokens("ACME CONSULTING INC.")


def test_an_empty_name_matches_nothing():
    """Not a perfect match to nothing, which is what an empty intersection
    over an empty union would be if it were not guarded."""
    assert similarity("", "Acme") == 0.0
    assert similarity("Acme", "") == 0.0


def test_one_shared_word_is_not_a_vendor_match():
    """"Ohio" is in a great many of them."""
    m = weigh(doc(vendor_name="Ohio Aerospace Institute"),
              target(payee="Ohio Valley Machining"))
    assert m is not None                      # the amount still matches
    assert not [s for s in m.signals if s.name == "VENDOR"], (
        "a single word in common was treated as the same party")


# ── Amount is necessary ───────────────────────────────────────────────

def test_nothing_is_proposed_without_an_amount():
    """The column was NULL on all forty-three documents on file.

    A matcher that proposed anyway would be reading a filename.
    """
    p = propose(doc(doc_amount=None), [target()])
    assert not p.proposes
    assert "does not say what it is for" in p.why_not


def test_a_near_amount_is_not_a_match():
    """$1,200.00 and $1,200.50 are different costs. Tolerance here is how a
    system starts agreeing with itself."""
    assert weigh(doc(), target(amount=Decimal("1200.50"))) is None


def test_date_and_vendor_cannot_carry_a_proposal_alone():
    """Same vendor, same month, different money — that is not this invoice."""
    p = propose(doc(), [target(amount=Decimal("8400.00"))])
    assert not p.proposes
    assert "1200.00" in p.why_not


# ── Date proximity ────────────────────────────────────────────────────

def test_a_date_inside_the_period_counts_more_than_one_near_it():
    inside = weigh(doc(doc_date=date(2025, 3, 15)), target())
    near = weigh(doc(doc_date=date(2025, 2, 20)), target())
    assert inside.score > near.score


def test_a_date_far_away_is_no_signal_at_all():
    far = weigh(doc(doc_date=date(2025, 9, 1)), target())
    assert not [s for s in far.signals if s.name == "DATE"]


def test_the_window_is_the_one_the_module_publishes():
    """A test that hardcodes 31 goes stale the day somebody widens it, and
    then argues against correct code."""
    from datetime import timedelta
    last = date(2025, 3, 31)
    edge = weigh(doc(doc_date=last + timedelta(days=DATE_WINDOW_DAYS)), target())
    beyond = weigh(doc(doc_date=last + timedelta(days=DATE_WINDOW_DAYS + 1)), target())
    assert [s for s in edge.signals if s.name == "DATE"]
    assert not [s for s in beyond.signals if s.name == "DATE"]


# ── The rule that matters ─────────────────────────────────────────────

def test_two_costs_at_the_same_amount_propose_nothing():
    """The rule /api/reconcile/propose follows, and the asset schedule's.

    An attribution that could equally have been something else is not
    evidence. This is the single most important behaviour here: matching on
    amount alone will pair a $1,200 invoice with the wrong $1,200 line, and
    the honest answer is to say so rather than pick one.
    """
    a = target(target_id="A", label="A", payee="", first_day=None, last_day=None)
    b = target(target_id="B", label="B", payee="", first_day=None, last_day=None)
    p = propose(doc(vendor_name="", doc_date=None), [a, b])
    assert not p.proposes
    assert "2 different costs fit" in p.why_not
    assert len(p.runners_up) == 2, "the reader is not shown what tied"


def test_a_tie_is_broken_by_a_real_signal_not_by_order():
    """Two groups at $1,200; one is the same vendor. That is a difference."""
    right = target(target_id="A", label="A", payee="Acme Consulting")
    wrong = target(target_id="B", label="B", payee="Mahoning Valley Supply")
    assert propose(doc(), [right, wrong]).match.target.target_id == "A"
    # And the order it is handed them in changes nothing.
    assert propose(doc(), [wrong, right]).match.target.target_id == "A"


def test_the_proposal_says_why_in_words_somebody_can_check():
    p = propose(doc(), [target()])
    assert p.proposes
    assert "matches to the cent" in p.match.because
    assert "same party" in p.match.because
    for s in p.match.signals:
        assert s.says.endswith("."), f"{s.name} does not read as a sentence"


def test_nothing_matching_says_what_that_probably_means():
    """"No proposal" with no reason sends somebody looking for a bug."""
    p = propose(doc(doc_amount=Decimal("77.77")), [target()])
    assert not p.proposes and "not a ledger amount" in p.why_not


def test_a_document_may_support_more_than_one_cost():
    """One invoice can genuinely cover two groups. Withholding the second
    would be the matcher making the judgment rather than offering it."""
    a = target(target_id="A", label="A", payee="Acme Consulting")
    b = target(target_id="B", label="B", payee="Acme Consulting")
    ps = propose_all([doc(evidence_id="EV-1"), doc(evidence_id="EV-2")], [a, b])
    # Both tie, so neither proposes — but each was considered independently.
    assert [p.considered for p in ps] == [2, 2]


@pytest.mark.parametrize("lines,expected", [(1, "on the line"), (4, "across 4 lines")])
def test_the_amount_signal_says_what_it_matched(lines, expected):
    m = weigh(doc(), target(lines=lines))
    assert expected in m.because
