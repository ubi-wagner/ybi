"""A line at zero is a line, and the check has to know it too.

Migration `074`. `040` exempted INDIRECT from `billed_not_budgeted` and read
`funded` as `federal + cost_share > 0`, and both were right about the record
they were written against. Neither is right now:

- `052` transcribed all four America Makes schedules and **two of them budget
  INDIRECT**, ICAM at $27,500 and LTM at $81,772.76, while Drive AM's and
  Hybrid's contain no INDIRECT category at all. Exempting the category means
  the check cannot say which of those is true — on the single largest thing
  a restatement puts on an invoice.
- Reading `funded` as `> 0` made a category the schedule *names at zero*
  indistinguishable from one it never names, which is the exception to a rule
  this repository states plainly and follows everywhere else.

Own rows, own transaction, rolled back.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2094"
AWARD = "TEST-BUDGET-CHECK"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2094-01-01','2094-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                cursor.execute(
                    """INSERT INTO cost_objective
                         (objective_id, period, label, objective_type, is_federal)
                       VALUES (%s,%s,'Test objective','PROGRAM',true)
                       ON CONFLICT DO NOTHING""", ("TEST-OBJ", PERIOD))
                cursor.execute(
                    """INSERT INTO award (award_id, objective_id, sponsor,
                                          instrument, ceiling_federal,
                                          period_start, period_end, rate_method)
                       VALUES (%s,'TEST-OBJ','Test sponsor','SUBAWARD',
                               100000.00,'2094-01-01','2094-12-31',
                               'DE_MINIMIS_10')""", (AWARD,))
                yield cursor


def budget(cur, **categories):
    for category, federal in categories.items():
        cur.execute("""INSERT INTO award_budget
                         (award_id, category, federal, citation)
                       VALUES (%s,%s,%s,'Test Schedule B')""",
                    (AWARD, category, federal))


def an_invoice(cur, **lines):
    cur.execute("""INSERT INTO invoice (award_id, period, seq, invoice_date,
                                        invoice_number, objective_id, status)
                   VALUES (%s,%s,1,'2094-06-01','T-001','TEST-OBJ','ISSUED')
                RETURNING invoice_id""", (AWARD, PERIOD))
    invoice_id = cur.fetchone()["invoice_id"]
    for n, (category, amount) in enumerate(lines.items(), start=1):
        cur.execute("""INSERT INTO invoice_line
                         (invoice_id, sequence, category, amount)
                       VALUES (%s,%s,%s,%s)""", (invoice_id, n, category, amount))
    return invoice_id


def check(cur, invoice_id):
    cur.execute("""SELECT * FROM v_invoice_budget_check
                    WHERE invoice_id = %s""", (invoice_id,))
    return cur.fetchone()


def claims(cur):
    cur.execute("""SELECT category::text AS category, budgeted, claimed,
                          headroom, evaluable, state
                     FROM v_award_claim_check WHERE award_id = %s""", (AWARD,))
    return {r["category"]: r for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# The one it was blind to


def test_an_indirect_line_on_a_schedule_with_no_indirect_category_is_a_finding(cur):
    """The defect `074` exists for, measured rather than argued.

    Drive AM's and Hybrid's Schedule B contain no INDIRECT category, so the
    indirect line a restatement adds is claimed under a category the
    agreement does not have. `040` exempted INDIRECT outright, so a
    $16,537.56 line on invoice 10018 produced an empty list.
    """
    budget(cur, LABOR="50000.00", ODC="20000.00")
    inv = an_invoice(cur, LABOR="1000.00", INDIRECT="440.00")
    row = check(cur, inv)
    assert row["evaluable"]
    assert row["billed_outside_the_schedule"] == ["INDIRECT"], row


def test_an_indirect_line_inside_a_budgeted_indirect_category_is_not(cur):
    """The other half, or the test above passes with the category simply
    added to a blocklist in the other direction.

    LTM budgets $81,772.76 of indirect, so restating its invoice raises a
    line the schedule already carries rather than inventing one.
    """
    budget(cur, LABOR="50000.00", INDIRECT="5000.00")
    inv = an_invoice(cur, LABOR="1000.00", INDIRECT="440.00")
    assert check(cur, inv)["billed_outside_the_schedule"] is None


# ---------------------------------------------------------------------------
# A line at zero is a line


def test_a_category_named_at_zero_and_billed_at_zero_is_not_a_finding(cur):
    """Invoice 10039 reported `{MATERIALS, TRAVEL}` — two categories LTM's
    schedule *does* name, at zero, with $0.00 against them.

    A flag with no money behind it, on the one invoice with a real exposure.
    The America Makes invoices print the categories the contract allows, not
    the month's activity, so this is the ordinary case and must stay silent.
    """
    budget(cur, LABOR="50000.00", TRAVEL="0.00", MATERIALS="0.00")
    inv = an_invoice(cur, LABOR="1000.00", TRAVEL="0.00", MATERIALS="0.00")
    row = check(cur, inv)
    assert row["billed_outside_the_schedule"] is None, row
    assert row["billed_against_a_zero_line"] is None, row
    assert row["named_categories"] == 3
    assert row["funded_categories"] == 1


def test_a_category_named_at_zero_with_money_against_it_is_a_finding(cur):
    """And a different one from absent. The category was available and
    unfunded, which is a budget question; absent is a scope question.
    """
    budget(cur, LABOR="50000.00", TRAVEL="0.00")
    inv = an_invoice(cur, LABOR="1000.00", TRAVEL="250.00")
    row = check(cur, inv)
    assert row["billed_against_a_zero_line"] == ["TRAVEL"], row
    assert row["billed_outside_the_schedule"] is None, row


def test_a_project_title_in_other_is_not_a_claim(cur):
    """These invoices use OTHER to print a project title rather than a cost.
    At zero it is not a claim; with money against it, it is one like any
    other.
    """
    budget(cur, LABOR="50000.00")
    quiet = an_invoice(cur, LABOR="1000.00", OTHER="0.00")
    assert check(cur, quiet)["billed_outside_the_schedule"] is None
    cur.execute("UPDATE invoice_line SET amount = 500 WHERE category = 'OTHER'")
    assert check(cur, quiet)["billed_outside_the_schedule"] == ["OTHER"]


# ---------------------------------------------------------------------------
# Money, cumulatively


def test_the_claim_check_reports_over_against_the_schedule(cur):
    """The per-invoice check compares sets of categories and can never say
    that a category has been billed for more than the schedule funds."""
    budget(cur, LABOR="1000.00", ODC="5000.00")
    an_invoice(cur, LABOR="1500.00", ODC="100.00")
    rows = claims(cur)
    assert rows["LABOR"]["state"] == "OVER", rows["LABOR"]
    assert rows["ODC"]["state"] == "WITHIN", rows["ODC"]


def test_an_award_with_no_schedule_read_is_not_a_pass(cur):
    """`029` in a new place: both sides of the comparison are empty sets on
    an award nobody has transcribed, and an empty set matches an empty set
    perfectly."""
    an_invoice(cur, LABOR="1500.00")
    rows = claims(cur)
    assert rows, "an unread award reports nothing at all, so nobody is told"
    assert all(r["state"] == "NOT READ" for r in rows.values()), rows
    assert not any(r["evaluable"] for r in rows.values()), rows


def test_a_category_claimed_that_the_schedule_never_names(cur):
    budget(cur, LABOR="1000.00")
    an_invoice(cur, LABOR="100.00", EQUIPMENT="900.00")
    rows = claims(cur)
    assert rows["EQUIPMENT"]["state"] == "OUTSIDE SCHEDULE", rows["EQUIPMENT"]
    assert rows["EQUIPMENT"]["budgeted"] is None
