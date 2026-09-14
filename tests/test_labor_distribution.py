"""The distribution has to add back to the payroll register.

`v_labor_effective.distributed_wages` was `round(payroll_wages * share, 2)`
computed per row, independently, so a person's distributed wages did not have
to add back to their payroll wages — the residual was lost or gained a cent
at a time. Six of the forty-three people on the live 2025 record already
drifted before any timesheet existed, and the eleventh statement control tied
anyway because the cents happened to net out.

That figure is the fringe denominator, anchored to the payroll register. A
denominator that moves by cents for reasons nobody chose is the register
disagreeing with itself, and it is what `WAGE_BASE_IS_THE_REGISTER` exists to
say. Migration `069` allocates by largest remainder so it adds back by
construction.

Own rows, own transaction, rolled back, so this runs against the bare
database CI builds from the migrations.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2094"


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
                yield cursor


def an_objective(cur, oid):
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES (%s,%s,%s,'PROGRAM',false)
                   ON CONFLICT DO NOTHING""", (oid, PERIOD, oid))
    return oid


def distribute(cur, key, wages, units):
    """One person, their whole wages, split across `units` by objective."""
    for oid, u in units.items():
        an_objective(cur, oid)
        cur.execute(
            """INSERT INTO labor_allocation
                 (period, employee_key, employee_name, objective_id,
                  payroll_wages, original_units, reconstructed_units,
                  evidence_quality, rationale, loaded_by)
               VALUES (%s,%s,%s,%s,%s,0,%s,'MANAGEMENT_RECONSTRUCTION',
                       'test','test')""",
            (PERIOD, key, key, oid, wages, u))


def distributed(cur, key):
    cur.execute("""SELECT sum(distributed_wages) AS d, max(payroll_wages) AS w
                     FROM v_labor_effective
                    WHERE period = %s AND employee_key = %s""", (PERIOD, key))
    return cur.fetchone()


# ── the property ─────────────────────────────────────────────────────

@pytest.mark.parametrize("wages,units", [
    # Three ways into thirds, which no number of cents divides evenly.
    ("100.00", {"A": 1, "B": 1, "C": 1}),
    # The live shape: seven objectives on a real salary.
    ("171799.06", {"A": 231, "B": 206, "C": 163, "D": 129, "E": 106,
                   "F": 98, "G": 67}),
    # A single objective, which must stay exact.
    ("61232.00", {"A": 1}),
    # Nine objectives, the most anybody on the 2025 register carries.
    ("192087.13", {c: i + 1 for i, c in enumerate("ABCDEFGHI")}),
    # A cent, split nine ways: every share rounds to nothing but one.
    ("0.01", {c: 1 for c in "ABCDEFGHI"}),
])
def test_a_persons_wages_are_distributed_in_full(cur, wages, units):
    distribute(cur, "PERSON", wages, units)
    row = distributed(cur, "PERSON")
    assert row["d"] == Decimal(wages), (
        f"{row['d']} distributed against {wages} on the register")
    assert row["w"] == Decimal(wages)


def test_the_register_is_the_sum_of_what_each_person_was_paid(cur):
    """The figure the fringe rate is taken over, across everybody."""
    people = {"ALPHA": ("78492.76", {"A": 7, "B": 5, "C": 3, "D": 2,
                                     "E": 2, "F": 1, "G": 1}),
              "BRAVO": ("59850.00", {"A": 4, "B": 3, "C": 2, "D": 1}),
              "CHARLIE": ("68284.80", {"A": 3, "B": 2, "C": 1})}
    for key, (wages, units) in people.items():
        distribute(cur, key, wages, units)
    cur.execute("""SELECT sum(distributed_wages) AS d FROM v_labor_effective
                    WHERE period = %s""", (PERIOD,))
    expected = sum(Decimal(w) for w, _ in people.values())
    assert cur.fetchone()["d"] == expected


def test_the_spare_cents_go_to_the_largest_remainders(cur):
    """Not to whoever sorts first, and not all to one row — otherwise the
    distribution is exact and still not the best split available."""
    distribute(cur, "PERSON", "100.00", {"A": 1, "B": 1, "C": 1})
    cur.execute("""SELECT objective_id, distributed_wages
                     FROM v_labor_effective
                    WHERE period = %s AND employee_key = 'PERSON'
                    ORDER BY objective_id""", (PERIOD,))
    got = {r["objective_id"]: r["distributed_wages"] for r in cur.fetchall()}
    assert sum(got.values()) == Decimal("100.00")
    # 33.33 three times leaves a cent; exactly one row carries it, and no
    # row is more than a cent from the even split.
    assert sorted(got.values()) == [Decimal("33.33"), Decimal("33.33"),
                                    Decimal("33.34")]


def test_it_is_the_same_answer_every_time(cur):
    """Ties in the remainder are broken by objective, so the same rows come
    back with the same cents. A distribution that depended on the planner's
    row order would move the fringe base between two reads of one record."""
    distribute(cur, "PERSON", "100.00", {"A": 1, "B": 1, "C": 1})
    reads = []
    for _ in range(3):
        cur.execute("""SELECT objective_id, distributed_wages
                         FROM v_labor_effective
                        WHERE period = %s AND employee_key = 'PERSON'
                        ORDER BY objective_id""", (PERIOD,))
        reads.append([(r["objective_id"], r["distributed_wages"])
                      for r in cur.fetchall()])
    assert reads[0] == reads[1] == reads[2]


def test_a_person_with_no_wages_distributes_nothing_rather_than_failing(cur):
    """Somebody on the distribution at zero is a real state — a volunteer, or
    a leaver paid in the prior period — and must not divide by zero."""
    distribute(cur, "PERSON", "0.00", {"A": 1, "B": 1})
    row = distributed(cur, "PERSON")
    assert row["d"] == Decimal("0.00")
