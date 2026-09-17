"""The facilities carve-out is weighted by the estate, not by the building.

`POST /api/rates/compute` built the 2 CFR 200.465 carve-out one facility at a
time as ``overhead_gross * (excluded_f / usable_f)`` and summed the rows. With
one building that is exactly right; with five it carves five shares of the
*whole* pool. An estate half let building by building would have removed 250%
of overhead and left the rate negative.

Nothing could have caught it. `v_pool_balance.allocable` is gross less carved
and `v_rate_buildup` ties `rate.pool_amount` to that, so both sides of the
control agree however large the carve-out is — and the reference record has
carried exactly one building for the life of the rate engine, so the shape had
no instance to be wrong in.

Two halves, and the first is what makes the fix safe to ship:

* with one facility the new arithmetic is the old arithmetic, to the cent, so
  every rate ever published is unchanged;
* with five facilities the carve-out is the estate's excluded share and never
  more than the pool.

The third test is the control `090` adds, driven against a database.
"""

from __future__ import annotations

import ast
import os
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PERIOD = "2093"


# ── The arithmetic, with no database ──────────────────────────────────

def carve(facilities: list[tuple[str, Decimal, Decimal]],
          overhead_gross: Decimal) -> list[Decimal]:
    """The handler's arithmetic, lifted so it can be exercised directly.

    Lifted rather than imported because the handler reads a view and builds a
    whole PoolModel around this; what is under test is the weighting. Each
    tuple is (name, the building's usable square feet, its excluded square
    feet) and `rental_share` is taken as excluded/usable, which is what
    `v_facility_occupancy` answers where no space is COMMON.
    """
    estate = sum((usable for _, usable, _ in facilities), Decimal(0))
    out = []
    for _name, usable, excluded in facilities:
        rental = (excluded / usable) if usable else Decimal(0)
        if usable <= 0 or estate <= 0 or overhead_gross <= 0 or rental <= 0:
            continue
        share = ((usable / estate) * rental).quantize(Decimal("0.000001"))
        out.append((overhead_gross * share).quantize(Decimal("0.01")))
    return out


def test_one_building_is_unchanged():
    """The reference record's own case: 3,000 of 5,400 square feet tenant and
    vacant at Tech Block 5, against a $1,678,057.27 overhead pool. This is the
    figure `063` recorded and it must not move."""
    gross = Decimal("1678057.27")
    old = (gross * (Decimal(3000) / Decimal(5400)).quantize(Decimal("0.000001"))
           ).quantize(Decimal("0.01"))
    new = sum(carve([("Tech Block 5", Decimal(5400), Decimal(3000))], gross))
    assert new == old == Decimal("932254.78")


def test_five_buildings_carve_the_estate_s_share_and_not_five_of_them():
    """The defect. Five buildings each half let: the old arithmetic carves
    2.5x the pool, the new one carves half of it."""
    gross = Decimal("1000000.00")
    estate = [(f"B{i}", Decimal(10000), Decimal(5000)) for i in range(5)]

    old = sum((gross * (e / u).quantize(Decimal("0.000001"))
               ).quantize(Decimal("0.01")) for _, u, e in estate)
    assert old == Decimal("2500000.00")          # 250% of the pool

    new = sum(carve(estate, gross))
    assert new == Decimal("500000.00")           # the estate's excluded half
    assert new < gross


def test_a_building_that_is_wholly_let_does_not_carve_the_whole_pool():
    """The case that reads most plausibly and is most wrong: one small
    building fully let beside a large one that is not let at all."""
    gross = Decimal("1000000.00")
    estate = [("Small", Decimal(2000), Decimal(2000)),
              ("Large", Decimal(18000), Decimal(0))]
    assert sum(carve(estate, gross)) == Decimal("100000.00")


def test_the_handler_divides_by_the_estate():
    """The rule, in the code that ships. Asserted on the parsed source rather
    than on a line of text, because a test that matches a spelling passes with
    the rule deleted and the comment kept."""
    src = (ROOT / "app" / "routers" / "rates.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_build_model")
    divisors = {ast.unparse(n.right) for n in ast.walk(fn)
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)}
    assert "estate" in divisors, (
        "the carve-out share must be taken over the estate's usable square "
        f"footage, not one building's; divisors seen: {sorted(divisors)}")


# ── The control, against a database ───────────────────────────────────

pytestmark_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                   reason="needs a database")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO fiscal_period (period, start_date, end_date)
                       VALUES (%s,'2093-01-01','2093-12-31')
                       ON CONFLICT DO NOTHING""", (PERIOD,))
                yield cursor


def an_overhead_pool(cur, amount):
    cur.execute("""INSERT INTO ledger_import (period, source_name, sha256,
                                              row_count, imported_by)
                   VALUES (%s,'t',md5(random()::text),1,'test')
                RETURNING import_id""", (PERIOD,))
    imp = cur.fetchone()["import_id"]
    cur.execute("""INSERT INTO ledger_line (line_id, import_id, period,
                                            txn_date, account, amount,
                                            statement, section, source_key)
                   VALUES (md5(random()::text), %s, %s, '2093-06-01',
                           '5300 Occupancy', %s, 'P&L', 'Expense',
                           md5(random()::text))
                RETURNING line_id""", (imp, PERIOD, amount))
    line = cur.fetchone()["line_id"]
    cur.execute("""INSERT INTO decision_set (period, label)
                   VALUES (%s,'test set') RETURNING set_id""", (PERIOD,))
    sid = cur.fetchone()["set_id"]
    cur.execute("""INSERT INTO decision (set_id, scope, pool, function_990,
                                         federal, grade, rationale, decided_by)
                   VALUES (%s,'test','OVERHEAD','MANAGEMENT_AND_GENERAL',
                           'ALLOWABLE','TEST_ASSUMPTION','test','test')
                RETURNING decision_id""", (sid,))
    did = cur.fetchone()["decision_id"]
    cur.execute("""INSERT INTO decision_line (decision_id, line_id, live)
                   VALUES (%s,%s,true)""", (did, line))


def carve_state(cur):
    cur.execute("""SELECT state, needs, carved, allocable
                     FROM v_carve_out_check
                    WHERE period = %s AND pool = 'OVERHEAD'""", (PERIOD,))
    return cur.fetchone()


@pytestmark_db
def test_no_carve_out_is_not_a_pass(cur):
    """An unfired carve-out and an estate with no rental space look identical
    from here. `029`'s rule: a control that cannot be evaluated has not
    passed."""
    an_overhead_pool(cur, "1000000.00")
    assert carve_state(cur)["state"] == "NO DATA"


@pytestmark_db
def test_a_carve_out_inside_the_pool_ties(cur):
    an_overhead_pool(cur, "1000000.00")
    cur.execute("""INSERT INTO carve_out (period, pool, name, citation, amount,
                                          driver, grade, created_by)
                   VALUES (%s,'OVERHEAD','Rental','2 CFR 200.465',500000.00,
                           'half the estate','TEST_ASSUMPTION','test')""",
                (PERIOD,))
    row = carve_state(cur)
    assert row["state"] == "TIES"
    assert row["allocable"] == Decimal("500000.00")


@pytestmark_db
def test_a_carve_out_that_swallows_the_pool_is_open(cur):
    """What the per-building weighting produced on a five-building estate,
    and what every other control reported TIES on."""
    an_overhead_pool(cur, "1000000.00")
    for i in range(5):
        cur.execute("""INSERT INTO carve_out (period, pool, name, citation,
                                              amount, driver, grade, created_by)
                       VALUES (%s,'OVERHEAD',%s,'2 CFR 200.465',500000.00,
                               'half of this building','TEST_ASSUMPTION',
                               'test')""",
                    (PERIOD, f"Rental — B{i}"))
    row = carve_state(cur)
    assert row["state"] == "OPEN"
    assert row["allocable"] < 0
    assert "meet or exceed" in row["needs"]
