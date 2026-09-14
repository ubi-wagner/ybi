"""The person the money paid, and where their hours went.

Migration `073`. `v_labor_hours_check` reported Tom Metzinger as HOURS
WITHOUT WAGES — 781 hours across all twelve months of 2025, no row in the
payroll distribution, and no payment to "Metzinger" anywhere in the general
ledger. He is 1099, and a contractor is paid as a company: the expense is
`5202 Accounting` / **`Metz Consulting, LLC.`**, $73,024.44.

A surname search could never have found it, which is why the link is a table
rather than a join on a name. And with the hours loaded there is a question
underneath it: his log puts 35.47% of his effort on ESP, Hybrid II and Rising
Tides while the whole retainer sits in G&A.

Own rows, own transaction, rolled back.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2097"
NOTE = "A contractor paid as a company, recorded so nobody searches a surname"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2097-01-01','2097-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                # `ADMINISTRATION`, read from the schema — the first draft said
                # INDIRECT from memory and the view correctly disagreed.
                for oid, kind in (("T-ADMIN", "ADMINISTRATION"),
                                  ("T-PROJ", "PROGRAM")):
                    cursor.execute(
                        """INSERT INTO cost_objective (objective_id, period,
                               label, objective_type, is_federal)
                           VALUES (%s,%s,%s,%s,false)
                           ON CONFLICT DO NOTHING""", (oid, PERIOD, oid, kind))
                yield cursor


def identity(cur, key="TESTER", payee="Test Consulting, LLC.", note=NOTE):
    cur.execute("""INSERT INTO contractor_identity
                     (period, employee_key, payee, basis, note)
                   VALUES (%s,%s,%s,'W9_1099',%s)""",
                (PERIOD, key, payee, note))


def an_expense(cur, payee, account, amount, pool=None):
    cur.execute("""INSERT INTO ledger_import (period, source_name, sha256,
                                              row_count, imported_by)
                   VALUES (%s,'t',md5(random()::text),1,'test')
                RETURNING import_id""", (PERIOD,))
    imp = cur.fetchone()["import_id"]
    cur.execute("""INSERT INTO ledger_line (line_id, import_id, period,
                       txn_date, account, payee, amount, statement, section,
                       source_key)
                   VALUES (md5(random()::text),%s,%s,'2097-06-01',%s,%s,%s,
                           'P&L','Expense',md5(random()::text))
                RETURNING line_id""",
                (imp, PERIOD, account, payee, amount))
    line = cur.fetchone()["line_id"]
    if pool:
        cur.execute("""INSERT INTO decision_set (period, label)
                       VALUES (%s,'t') RETURNING set_id""", (PERIOD,))
        sid = cur.fetchone()["set_id"]
        cur.execute("""INSERT INTO decision (set_id, scope, pool, function_990,
                           federal, grade, rationale, decided_by, objective_id)
                       VALUES (%s,'t',%s,'MANAGEMENT_AND_GENERAL','ALLOWABLE',
                               'TEST_ASSUMPTION','t','t',%s)
                    RETURNING decision_id""",
                    (sid, pool, "T-PROJ" if pool == "DIRECT" else None))
        did = cur.fetchone()["decision_id"]
        cur.execute("""INSERT INTO decision_line (decision_id, line_id, live)
                       VALUES (%s,%s,true)""", (did, line))
    return line


def hours(cur, key, objective, amount, month=6):
    cur.execute("""INSERT INTO labor_month (period, employee_key, month_start,
                       objective_id, logged_hours, adjusted_hours)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (PERIOD, key, date(2097, month, 1), objective, amount, amount))


def check(cur, account=None):
    # `%s IS NULL` leaves Postgres with no type to infer; the filter is
    # done here instead rather than decorated with a cast that exists only
    # to satisfy the planner.
    cur.execute("""SELECT account, expense, pools, hours, project_hours,
                          project_pct, at_stake, objectives, state
                     FROM v_contractor_effort_check
                    WHERE period = %s ORDER BY expense DESC""", (PERIOD,))
    rows = cur.fetchall()
    return [r for r in rows if account is None or r["account"] == account]


# ── the link itself ──────────────────────────────────────────────────

def test_a_link_with_no_reason_is_refused(cur):
    """A key with no explanation is the next person's puzzle again."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        identity(cur, note="1099")


def test_one_row_per_group_not_one_per_payee(cur):
    """Metz Consulting is paid three ways that mean three different things —
    a retainer, software he rebills, and EIR work already on a cost
    objective. Rolling them together would put a share of a subscription on
    a programme and hide that YBI already direct-charges his project work."""
    identity(cur)
    for account, amount, pool in (
            ("M&A:5202 Accounting", "73024.44", "G&A"),
            ("M&A:5215 Dues", "4909.82", "G&A"),
            ("Program:5221 EIR", "4880.00", "DIRECT")):
        an_expense(cur, "Test Consulting, LLC.", account, amount, pool)
    assert len(check(cur)) == 3


# ── the question the hours raise ─────────────────────────────────────

def test_effort_on_a_cost_objective_against_an_indirect_pool_is_open(cur):
    identity(cur)
    an_expense(cur, "Test Consulting, LLC.", "M&A:5202 Accounting",
               "100000.00", "G&A")
    # Within a month: `month_hours_sane` caps a row at 744, and putting a
    # year in one month is the shape that caught the summary block on load.
    hours(cur, "TESTER", "T-ADMIN", 130)
    hours(cur, "TESTER", "T-PROJ", 70)
    row = check(cur)[0]
    assert row["state"] == "OPEN"
    assert row["project_pct"] == Decimal("35.00")
    assert row["at_stake"] == Decimal("35000.00")
    assert row["objectives"] == "T-PROJ"


def test_a_group_already_on_a_cost_objective_has_been_answered(cur):
    """It carries no figure either: a number against a settled question is a
    number in a control that means nothing."""
    identity(cur)
    an_expense(cur, "Test Consulting, LLC.", "Program:5221 EIR",
               "4880.00", "DIRECT")
    hours(cur, "TESTER", "T-ADMIN", 130)
    hours(cur, "TESTER", "T-PROJ", 70)
    row = check(cur)[0]
    assert row["state"] == "TIES"
    assert row["at_stake"] is None


def test_all_administrative_effort_ties(cur):
    """Somebody whose hours are entirely general administration is where the
    G&A classification already says they are, and raises no question."""
    identity(cur)
    an_expense(cur, "Test Consulting, LLC.", "M&A:5202 Accounting",
               "50000.00", "G&A")
    hours(cur, "TESTER", "T-ADMIN", 160)
    assert check(cur)[0]["state"] == "TIES"


def test_a_contractor_with_no_hours_log_is_not_a_pass(cur):
    """Thirty-six of the forty-five have no monthly record, so for most
    people this question cannot be asked at all — and saying TIES over it
    would be `029` one more time."""
    identity(cur)
    an_expense(cur, "Test Consulting, LLC.", "M&A:5202 Accounting",
               "50000.00", "G&A")
    row = check(cur)[0]
    assert row["state"] == "NO HOURS LOG"
    assert row["at_stake"] is None


def test_cost_nobody_has_judged_says_so_rather_than_tying(cur):
    identity(cur)
    an_expense(cur, "Test Consulting, LLC.", "M&A:5202 Accounting", "50000.00")
    hours(cur, "TESTER", "T-PROJ", 100)
    assert check(cur)[0]["state"] == "NOT CLASSIFIED"
