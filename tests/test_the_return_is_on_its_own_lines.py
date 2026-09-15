"""Form 990 on the return's own numbered lines, and everything on one of them.

`092` made the compensation rows cross-foot and left the sheet organised by
**natural category** — the bookkeeper's ten top-level account groups. That is
the right shape for reading the ledger and it is not the Statement of
Functional Expenses: Part IX has twenty-five numbered lines and a preparer has
to put every account on one. So the comparison this repository had never been
able to make — this year's return against last year's, line for line — could
not be made at all.

`094`–`096` are the map, the two views and the prior year transcribed as
printed. What is a judgment here is *which* line an account belongs on, which
is why the map is data rather than a CASE. What is not a judgment is
**completeness**, and that is what these hold: an account on no line is money
that falls off the return with nothing saying so.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2025"
D = lambda x: Decimal(str(x or 0))                                # noqa: E731


@pytest.fixture(scope="module")
def q():
    from app.db import query
    return query


def loaded(q) -> bool:
    return bool(q("""SELECT 1 FROM ledger_line WHERE period = %s LIMIT 1""",
                  (PERIOD,)))


# ── Everything lands on a line ────────────────────────────────────────

def test_every_expense_account_is_on_exactly_one_line(q):
    row = q("SELECT * FROM v_form_990_line_check WHERE period = %s",
            (PERIOD,))[0]
    if row["state"] == "NO DATA":
        pytest.skip("no ledger on this record")
    assert row["unmapped_accounts"] == 0, row["needs"]
    assert D(row["variance"]) == 0, (
        "the lines of the return do not add back to the profit and loss: "
        f"{row['ledger_expense']} of expense against "
        f"{row['part_ix_total']} on Part IX and "
        f"{row['netted_in_part_viii']} netted in Part VIII")
    assert row["state"] == "TIES"


def test_every_income_account_is_on_exactly_one_line(q):
    row = q("SELECT * FROM v_form_990_revenue_check WHERE period = %s",
            (PERIOD,))[0]
    if row["state"] == "NO DATA":
        pytest.skip("no ledger on this record")
    assert row["unmapped_accounts"] == 0, row["needs"]
    assert D(row["variance"]) == 0
    assert row["state"] == "TIES"


def test_the_two_presentations_of_part_ix_agree(q):
    """`v_form_990_functional` is the return by natural category and
    `v_form_990_part_ix` is the same money on the return's own lines. They
    are two cuts of one ledger and the only difference between their totals
    is the fundraising-event expense the form takes out of Part IX."""
    if not loaded(q):
        pytest.skip("no ledger on this record")
    by_category = D(q("""SELECT sum(amount) AS a FROM v_form_990_functional
                          WHERE period = %s""", (PERIOD,))[0]["a"])
    by_line = q("""SELECT sum(total) FILTER (WHERE part = 'IX')   AS ix,
                          sum(total) FILTER (WHERE part = 'VIII') AS netted
                     FROM v_form_990_part_ix WHERE period = %s""",
                (PERIOD,))[0]
    assert by_category == D(by_line["ix"]) + D(by_line["netted"]), (
        "the return by natural category and the return by line disagree")


def test_part_ix_cross_foots_on_every_line(q):
    """Program plus management plus fundraising is the line's total, or the
    row does not foot on a tax return — `092`'s rule, per line."""
    if not loaded(q):
        pytest.skip("no ledger on this record")
    for r in q("""SELECT * FROM v_form_990_part_ix WHERE period = %s""",
               (PERIOD,)):
        assert D(r["total"]) == (D(r["program"]) + D(r["management"])
                                 + D(r["fundraising"]) + D(r["unjudged"])
                                 + D(r["not_applicable"])), (
            f"line {r['line_id']} does not cross-foot")


# ── The expense view is not the revenue view ──────────────────────────

def test_the_expense_view_emits_no_revenue_line(q):
    """`094` cross-joined every row of `form_990_line` so that an empty Part
    IX line still prints — which is right. `095` then put Part VIII's eight
    revenue lines in the same table, and the expense view began answering
    with `V1` at 0.00 beside $5,866,141.77 of contributions.

    Nothing refused it. The first reader was the comparison report, which
    printed **total revenue of −154,663.63**."""
    lines = {r["line_id"] for r in
             q("""SELECT DISTINCT line_id FROM v_form_990_part_ix
                   WHERE period = %s""", (PERIOD,))}
    revenue = {r["line_id"] for r in
               q("""SELECT line_id FROM form_990_line
                     WHERE part = 'VIII' AND line_id <> '8b'""")}
    assert not (lines & revenue), (
        "the Part IX view is answering with Part VIII's revenue lines: "
        f"{sorted(lines & revenue)}")
    assert "8b" in lines, (
        "the one Part VIII line the form takes *out* of Part IX belongs here")


def test_every_part_ix_line_prints_even_when_empty(q):
    """An empty line is a fact about the year. 2025 reports nothing on line 3
    (foreign grants) and the 2024 return reported $63,568 — a reader has to
    be able to see that it is zero rather than absent."""
    got = {r["line_id"] for r in
           q("""SELECT line_id FROM v_form_990_part_ix WHERE period = %s""",
             (PERIOD,))}
    want = {r["line_id"] for r in
            q("SELECT line_id FROM form_990_line WHERE part = 'IX'")}
    assert want <= got, f"lines missing from the return: {sorted(want - got)}"


# ── The prior year is a transcription and it foots ────────────────────

def test_the_prior_year_transcription_foots_the_way_the_return_does(q):
    """A transcription nobody checked is a recollection with a citation on
    it. The 2024 return prints its own totals and this reproduces them."""
    rows = q("SELECT * FROM v_form_990_prior_check")
    if not rows:
        pytest.skip("no prior year on this record")
    for r in rows:
        assert r["state"] == "TIES", (
            f"the {r['period']} transcription does not foot: "
            f"{r['part_ix_total']} against "
            f"{D(r['part_ix_program']) + D(r['part_ix_management']) + D(r['part_ix_fundraising'])}")


def test_the_2024_return_reproduces_the_figures_it_prints(q):
    """The four totals the filed return prints on its own face."""
    rows = q("SELECT * FROM v_form_990_prior_check WHERE period = '2024'")
    if not rows:
        pytest.skip("2024 not transcribed on this record")
    r = rows[0]
    assert D(r["part_ix_total"]) == Decimal("4919001")
    assert D(r["part_ix_program"]) == Decimal("4119113")
    assert D(r["part_ix_management"]) == Decimal("561339")
    assert D(r["part_ix_fundraising"]) == Decimal("238549")
    assert D(r["total_revenue"]) == Decimal("7546159")


def test_the_map_routes_by_longest_prefix(q):
    """`5080 Fundraising:5089 Special Events` has to beat `5080 Fundraising`,
    or the cost of the Shark Tank lands in Part IX instead of being netted
    against the event's own receipts in Part VIII."""
    if not loaded(q):
        pytest.skip("no ledger on this record")
    netted = q("""SELECT total FROM v_form_990_part_ix
                   WHERE period = %s AND line_id = '8b'""", (PERIOD,))
    events = q("""SELECT sum(amount) AS a FROM ledger_line
                   WHERE period = %s
                     AND account LIKE '5080 Fundraising:5089 Special Events%%'
               """, (PERIOD,))[0]
    if D(events["a"]) == 0:
        pytest.skip("no fundraising events on this record")
    assert D(netted[0]["total"]) == D(events["a"]), (
        "the special-event accounts did not reach line 8b, so their parent's "
        "mapping won and the return over-reports Part IX by their cost")
