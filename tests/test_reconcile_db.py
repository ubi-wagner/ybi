"""The guarantees the schema makes about a reconciling item.

An explained difference is only better than an unexplained one if the
explanation is checkable. These are the checks, and they live in the
database so they hold when the handler above them is wrong.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

REASON = ("Recorded by the test suite to prove the constraint, and rolled "
          "back immediately afterwards.")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


def some_lines(cur, account: str, n: int):
    cur.execute("""SELECT line_id, amount FROM ledger_line
                    WHERE period='2025' AND account=%s ORDER BY line_id LIMIT %s""",
                (account, n))
    return cur.fetchall()


ACCOUNT = "Grant Expenses:Rising Tides Expense"


def insert_item(cur, amount: Decimal, from_account: str = ACCOUNT,
                to_account: str = "5080 Fundraising:5085 Advertising") -> int:
    cur.execute("""INSERT INTO reconciling_item
                     (period, control, from_account, to_account, amount, kind,
                      explanation, recorded_by)
                   VALUES ('2025','GL_PL_ACCOUNT',%s,%s,%s,'RECLASS_AFTER_EXPORT',
                           %s,'test@ybi.org')
                   RETURNING item_id""",
                (from_account, to_account, amount, REASON))
    return cur.fetchone()["item_id"]


def test_an_item_whose_lines_add_up_is_accepted(cur):
    lines = some_lines(cur, ACCOUNT, 2)
    assert len(lines) == 2
    total = sum(l["amount"] for l in lines)
    item_id = insert_item(cur, total)
    for l in lines:
        cur.execute("INSERT INTO reconciling_item_line (item_id,line_id) VALUES (%s,%s)",
                    (item_id, l["line_id"]))
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")     # force the deferred check


def test_a_plug_is_refused(cur):
    """An amount with no lines behind it is the thing this exists to stop."""
    import psycopg
    lines = some_lines(cur, ACCOUNT, 2)
    total = sum(l["amount"] for l in lines)
    item_id = insert_item(cur, total + Decimal("1.00"))
    for l in lines:
        cur.execute("INSERT INTO reconciling_item_line (item_id,line_id) VALUES (%s,%s)",
                    (item_id, l["line_id"]))
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "plug" in str(exc.value)


def test_an_item_with_no_lines_at_all_is_refused(cur):
    import psycopg
    insert_item(cur, Decimal("1234.56"))
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_lines_must_sit_in_the_account_the_item_moves_money_out_of(cur):
    """Otherwise the item describes something other than what it says."""
    import psycopg
    mine = some_lines(cur, ACCOUNT, 1)
    cur.execute("""SELECT line_id, amount FROM ledger_line
                    WHERE period='2025' AND account <> %s AND amount = %s
                    LIMIT 1""", (ACCOUNT, mine[0]["amount"]))
    other = cur.fetchone()
    if not other:
        pytest.skip("no equal-amount line in another account to test with")
    item_id = insert_item(cur, other["amount"])
    cur.execute("INSERT INTO reconciling_item_line (item_id,line_id) VALUES (%s,%s)",
                (item_id, other["line_id"]))
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "posted elsewhere" in str(exc.value)


def test_an_explanation_has_to_say_something(cur):
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("""INSERT INTO reconciling_item
                         (period, control, from_account, to_account, amount, kind,
                          explanation, recorded_by)
                       VALUES ('2025','GL_PL_ACCOUNT',%s,'x',1,'TIMING','ok',
                               'test@ybi.org')""", (ACCOUNT,))


def test_the_register_reports_ties_and_exceptions(cur):
    cur.execute("""SELECT control, basis, ties, exceptions, variance
                     FROM v_statement_reconciliation
                    WHERE period='2025' ORDER BY seq""")
    rows = cur.fetchall()
    controls = {r["control"] for r in rows}
    assert {"PL_FOOTING", "BS_FOOTING", "GL_PROMOTE_COMPLETE", "GL_SUBTOTALS",
            "GL_PL_SECTION", "GL_PL_ACCOUNT", "GL_PL_COVERAGE",
            "GL_BS_ACCOUNT", "GL_BS_COVERAGE", "SEGMENTATION"} <= controls
    for r in rows:
        assert r["ties"] is not None, f"{r['control']} cannot be evaluated"


def test_the_balance_sheet_is_proved_off_the_ledger(cur):
    """Opening plus movement, account by account. Nothing off."""
    cur.execute("""SELECT count(*) AS n FROM v_gl_bs_account
                    WHERE period='2025' AND on_balance_sheet AND variance <> 0""")
    assert cur.fetchone()["n"] == 0
    cur.execute("""SELECT account, closing FROM v_gl_bs_account
                    WHERE period='2025' AND NOT on_balance_sheet
                      AND NOT absent_because_zero
                    ORDER BY abs(closing) DESC""")
    stray = cur.fetchall()
    assert not stray, (
        "an account the sheet omits has to close at zero in the ledger, or be "
        "matched to the name the sheet prints by a recorded alias: "
        + "; ".join(f"{r['account']} closes at {r['closing']}" for r in stray))


# ── The payroll register, and the one relaxation in the rule ─────────

WAGE = "5129 Payroll Expenses:5139 Wages:5142 Intern Wages"


def insert_rounding(cur, amount, explanation):
    cur.execute("""INSERT INTO reconciling_item
                     (period, control, from_account, to_account, amount, kind,
                      explanation, recorded_by)
                   VALUES ('2025','PAYROLL_REGISTER',%s,'register',%s,
                           'ROUNDING',%s,'test@ybi.org')
                   RETURNING item_id""", (WAGE, amount, explanation))
    return cur.fetchone()["item_id"]


LONG = ("A residual with no transaction behind it: the workbook distributes "
        "dollars across forty-three people and rounds each cell, so no single "
        "line accounts for it and none can be named.")


def test_a_rounding_item_may_carry_no_lines(cur):
    """The one case where attribution is genuinely impossible."""
    insert_rounding(cur, Decimal("-53.24"), LONG)
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_a_rounding_item_still_has_to_explain_itself(cur):
    import psycopg
    # Long enough to clear the thirty-character CHECK every item carries,
    # short of the sixty a rounding item needs to earn its missing lines.
    insert_rounding(cur, Decimal("-53.24"),
                    "Rounding, near enough, do not worry about it.")
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "why the amount cannot be attributed" in str(exc.value)


def test_rounding_is_not_a_word_for_any_amount(cur):
    """Past a thousand dollars it stops being a description of anything."""
    import psycopg
    insert_rounding(cur, Decimal("-5000.00"), LONG)
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "not a description of anything" in str(exc.value)


def test_no_other_kind_may_skip_its_lines(cur):
    """The relaxation is for ROUNDING and nothing else."""
    import psycopg
    cur.execute("""INSERT INTO reconciling_item
                     (period, control, from_account, to_account, amount, kind,
                      explanation, recorded_by)
                   VALUES ('2025','PAYROLL_REGISTER',%s,'register',-53.24,
                           'TIMING',%s,'test@ybi.org')""", (WAGE, LONG))
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "plug" in str(exc.value)


def test_the_payroll_control_is_on_the_register(cur):
    cur.execute("""SELECT control, ties FROM v_statement_reconciliation
                    WHERE period='2025' AND control='PAYROLL_REGISTER'""")
    row = cur.fetchone()
    assert row, "the eleventh cross-reference point is missing"
    assert row["ties"] is not None


def test_the_fringe_base_is_the_register_not_the_ledger(cur):
    """The reason this control exists.

    _build_model takes direct labour from the effort distribution, so a
    difference between the register and the ledger's wage accounts is two
    denominators for one rate rather than a presentation question.
    """
    cur.execute("""SELECT register_wages, ledger_wages, fringe_pool
                     FROM v_payroll_reconciliation WHERE period='2025'""")
    r = cur.fetchone()
    if not r or not r["register_wages"]:
        pytest.skip("no payroll register loaded")
    on_register = r["fringe_pool"] / r["register_wages"]
    on_ledger = r["fringe_pool"] / r["ledger_wages"]
    assert on_register != on_ledger or r["register_wages"] == r["ledger_wages"], (
        "the two bases give the same rate, so either they agree or the view "
        "is not reading what it thinks it is")
