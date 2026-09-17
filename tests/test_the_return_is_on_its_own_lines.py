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


# ── Line 5 is a person, not an account ────────────────────────────────

def test_line_5_comes_out_of_line_7_and_the_two_still_tie(q):
    """Line 5 is the only line of this return that is not a routing. The
    officers' wages and everybody else's are the same account — payroll posts
    as lump journal entries with no employee dimension — so line 5 is an
    amount lifted out of line 7 *by person*, from the payroll register.

    What must hold is that nothing is created or lost doing it."""
    if not loaded(q):
        pytest.skip("no ledger on this record")
    rows = {r["line_id"]: r for r in
            q("""SELECT line_id, total FROM v_form_990_part_ix
                  WHERE period = %s AND line_id IN ('5', '7')""", (PERIOD,))}
    wages = D(q("""SELECT sum(amount) AS a FROM ledger_line
                    WHERE period = %s
                      AND account LIKE '5129 Payroll Expenses:5139 Wages%%'""",
                (PERIOD,))[0]["a"])
    if wages == 0:
        pytest.skip("no wage accounts on this record")
    assert D(rows["5"]["total"]) + D(rows["7"]["total"]) == wages, (
        "line 5 plus line 7 is not the wage accounts: "
        f"{rows['5']['total']} + {rows['7']['total']} against {wages}")


def test_line_5_is_officers_and_key_employees_and_nobody_else(q):
    """The 2024 return's own answer: three people were paid over $100,000 and
    only one of them reached line 5, because the other two are marked
    *highest compensated employee* and hold no office. Getting this wrong
    would have put $233,693 on line 5 instead of $167,967."""
    reach = {r["position"] for r in
             q("SELECT DISTINCT position FROM v_form_990_officer "
               "WHERE on_line_5")}
    assert reach <= {"OFFICER", "OFFICER_AND_DIRECTOR", "KEY_EMPLOYEE"}
    assert "HIGHEST_COMPENSATED" not in reach, (
        "a highest compensated employee who holds no office is on line 7")
    assert "DIRECTOR" not in reach


def test_the_2024_roster_reproduces_the_line_5_the_return_filed(q):
    """Reportable plus other compensation, for the people who reach line 5,
    is $167,967 — the figure on the face of the filed return. It is the
    check that the roster was read correctly rather than plausibly."""
    rows = q("""SELECT COALESCE(sum(reportable), 0) AS r,
                       COALESCE(sum(other), 0) AS o
                  FROM v_form_990_officer
                 WHERE period = '2024' AND on_line_5""")
    if not rows or D(rows[0]["r"]) == 0:
        pytest.skip("2024 roster not on this record")
    filed = D(q("""SELECT total FROM form_990_prior_year
                    WHERE period = '2024' AND line_id = '5'""")[0]["total"])
    assert D(rows[0]["r"]) + D(rows[0]["o"]) == filed, (
        f"the roster gives {rows[0]['r']} + {rows[0]['o']} against the "
        f"return's own {filed}")


def test_line_5_is_split_by_its_own_effort_and_not_the_estate_s(q):
    """`092` splits the compensation block by the estate-wide distribution,
    which is right for forty-three people and wrong for one. Line 5 is one
    person and her own distribution is on the record."""
    if not loaded(q):
        pytest.skip("no ledger on this record")
    cohorts = {(r["cohort"], r["function_990"]): D(r["share"]) for r in
               q("""SELECT cohort, function_990, share
                      FROM v_labour_function_share_by_cohort
                     WHERE period = %s""", (PERIOD,))}
    if not cohorts:
        pytest.skip("no effort distribution on this record")
    line5 = q("""SELECT total, management FROM v_form_990_part_ix
                  WHERE period = %s AND line_id = '5'""", (PERIOD,))[0]
    if D(line5["total"]) == 0:
        pytest.skip("no compensated officer on this record")
    want = (D(line5["total"])
            * cohorts[("OFFICER", "MANAGEMENT_AND_GENERAL")]).quantize(
                Decimal("0.01"))
    assert D(line5["management"]) == want, (
        "line 5's management and general column is not the officer cohort's "
        "own share of her effort")
    assert (cohorts[("OFFICER", "MANAGEMENT_AND_GENERAL")]
            != cohorts[("STAFF", "MANAGEMENT_AND_GENERAL")]), (
        "the two cohorts have the same share, so this test cannot tell them "
        "apart — it is passing over the thing it names")


def test_a_roster_that_has_gone_stale_says_so(q):
    """A roster carried forward from last year is exactly the shape that goes
    stale. The control is not that it never does — Part VII also lists the
    five highest compensated employees, and that list moves — but that the
    two ways it matters are visible."""
    rows = q("SELECT * FROM v_form_990_officer_check WHERE period = %s",
             (PERIOD,))
    if not rows or rows[0]["state"] == "NO DATA":
        pytest.skip("no roster on this record")
    r = rows[0]
    assert r["on_the_roster_not_on_the_payroll"] == 0, r["needs"]
    assert r["paid_with_no_payroll_key"] == 0, r["needs"]
    # Not an assertion about the number: somebody crossing $100,000 is a fact
    # about the year, and the column exists so a preparer sees it.
    assert r["paid_over_100k_and_not_on_the_roster"] >= 0


# ── Line 5 appears with the block it is carved out of ─────────────────

def test_line_5_does_not_appear_without_the_line_7_it_is_lifted_out_of(q):
    """`098`'s rule is one act: line 5 is lifted out of line 7 and the two
    still add to the wage accounts. `099` let the two halves happen
    separately — the subtraction lived inside the compensation block (`WHERE
    function_990 = 'NOT_APPLICABLE'`, which needs somebody to have judged the
    payroll) and the addition needed nothing at all.

    So on every record with a ledger and no classifications, Part IX added
    the chief executive's $192,087.13 without taking it off line 7 and the
    return did not cross-foot. Worse than the arithmetic: line 5 splits by
    the OFFICER cohort's own effort shares, so it was the one line claiming
    a function allocation while every other dollar sat in
    `NOT_YET_CLASSIFIED`.

    Driven inside a rolled-back transaction: take the judgments off the wage
    accounts, and line 5 has to go with them while the return still foots.
    """
    from app.db import conn

    if not loaded(q):
        pytest.skip("needs a ledger to have a line 7 at all")

    with conn() as c, c.cursor() as cur:
        cur.execute("SAVEPOINT probe")
        cur.execute("""SELECT total FROM v_form_990_part_ix
                        WHERE period = %s AND line_id = '5'""", (PERIOD,))
        row = cur.fetchone()
        before = Decimal(str(row["total"])) if row else Decimal(0)
        if before <= 0:
            cur.execute("ROLLBACK TO SAVEPOINT probe")
            pytest.skip("no officer pay on this record, so there is nothing "
                        "for line 5 to carry either way")

        # Un-judge the compensation block, which is what a record looks
        # like between the ledger landing and the first judgment.
        #
        # The seal has to come off first, and that is the schema working:
        # `decision_set_is_frozen` refuses a change to a judgment inside a
        # sealed set, which is the guarantee the whole system rests on. It
        # refused this probe on the first run. Both statements are inside the
        # savepoint, so the seal is put back by the rollback and no record
        # this test touches is left unsealed.
        cur.execute("""UPDATE decision_set
                          SET seal_hash = NULL, sealed_at = NULL,
                              unsealed_reason = 'test probe, rolled back'
                        WHERE period = %s AND sealed_at IS NOT NULL""",
                    (PERIOD,))
        #
        # Every judgment, not just the wage accounts: line 7 carries intern
        # wages as well as employee wages, so un-judging one of the two left
        # the compensation block standing and the probe measured nothing. An
        # unclassified record has no judgments at all, which is the state
        # this is about.
        cur.execute("""UPDATE decision SET reversed_at = now(),
                              reversal_reason = 'test probe, rolled back'
                        WHERE reversed_at IS NULL
                          AND set_id IN (SELECT set_id FROM decision_set
                                          WHERE period = %s)""", (PERIOD,))
        cur.execute("""SELECT coalesce(sum(total), 0) AS n
                         FROM v_form_990_part_ix
                        WHERE period = %s AND line_id = '5'""", (PERIOD,))
        after = Decimal(str(cur.fetchone()["n"]))
        cur.execute("""SELECT variance FROM v_form_990_line_check
                        WHERE period = %s""", (PERIOD,))
        variance = Decimal(str(cur.fetchone()["variance"]))
        cur.execute("ROLLBACK TO SAVEPOINT probe")

    assert after == 0, (
        f"the wage accounts are unjudged, so there is no compensation block "
        f"for line 5 to be carved out of — and it still printed {after}. "
        f"That is added to a line 7 nothing was taken off.")
    assert variance == 0, (
        f"Part IX does not cross-foot by {variance} once the payroll is "
        f"unjudged, which is the defect 123 was written for")
