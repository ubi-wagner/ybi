"""A lane can say something, and it can never say it about the baseline.

`lane_decision_override`, `lane_override_line` and `lane_assumption` were
created in the first migrations and **nothing wrote any of them**. So every
lane's build-up was identical to the baseline's by construction, and
`GET /lanes/compare` could only ever answer with zeroes. Building the
side-by-side screen over that would have produced a screen that cannot say
anything — the `FACILITY_UNPARTITIONED` mistake, where an item doing the work
cannot clear teaches the reader that the list is wrong.

These hold the two halves of what the machinery is for: a lane *can* differ,
and a lane can **never** be the way somebody changes what will be submitted.

Own rows, own transaction, rolled back — so they run on the bare database CI
builds from the migrations.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2096"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.fixture
def world(cur):
    """A period, two ledger lines, a decision on one of them, and two lanes."""
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES (%s,'2096-01-01','2096-12-31')
                   ON CONFLICT DO NOTHING""", (PERIOD,))
    cur.execute("""INSERT INTO ledger_import (period, source_name, sha256,
                                              row_count, imported_by)
                   VALUES (%s,'lanes.csv',%s,2,'test')
                   RETURNING import_id""", (PERIOD, "ab" * 32))
    import_id = cur.fetchone()["import_id"]
    for i, (account, amount) in enumerate(
            [("Expenses:5227 Portfolio consulting", Decimal("588539.00")),
             ("Expenses:5300 Rent", Decimal("60000.00"))], start=1):
        cur.execute("""INSERT INTO ledger_line (line_id, import_id, period,
                                                account, txn_date, payee,
                                                description, amount, statement,
                                                section, source_key)
                       VALUES (%s,%s,%s,%s,'2096-06-30','A payee','',%s,
                               'P&L','Expense',%s)""",
                    (f"LANE-{PERIOD}-{i:03d}", import_id, PERIOD, account,
                     amount, f"{PERIOD}-{i:04d}"))

    cur.execute("""INSERT INTO decision_set (period, label)
                   VALUES (%s,'lane test') RETURNING set_id""", (PERIOD,))
    set_id = cur.fetchone()["set_id"]
    # Only the rent is judged. The consulting is the open question a lane
    # exists to ask about.
    cur.execute("""INSERT INTO decision (set_id, scope, pool, function_990,
                                         federal, grade, rationale, decided_by)
                   VALUES (%s,'test','OVERHEAD','MANAGEMENT_AND_GENERAL',
                           'ALLOWABLE','CORROBORATED','rent','test')
                   RETURNING decision_id""", (set_id,))
    decision_id = cur.fetchone()["decision_id"]
    cur.execute("""INSERT INTO decision_line (decision_id, line_id)
                   VALUES (%s,%s)""", (decision_id, f"LANE-{PERIOD}-002"))

    lanes = {}
    for name, kind in (("baseline", "BASELINE"), ("sandbox", "SANDBOX")):
        cur.execute("""INSERT INTO lane (period, name, kind, set_id, purpose,
                                         created_by)
                       VALUES (%s,%s,%s,%s,'a purpose','test')
                       RETURNING lane_id""", (PERIOD, name, kind, set_id))
        lanes[name] = cur.fetchone()["lane_id"]
    return {"set_id": set_id, "lanes": lanes}


def override(cur, lane_id, pool, line_ids, reason="a reason"):
    cur.execute("""INSERT INTO lane_decision_override
                     (lane_id, pool, function_990, federal, grade, reason,
                      created_by)
                   VALUES (%s,%s,'MANAGEMENT_AND_GENERAL','ALLOWABLE',
                           'TEST_ASSUMPTION',%s,'test')
                   RETURNING override_id""", (lane_id, pool, reason))
    oid = cur.fetchone()["override_id"]
    for line_id in line_ids:
        cur.execute("""INSERT INTO lane_override_line (override_id, lane_id,
                                                       line_id)
                       VALUES (%s,%s,%s)""", (oid, lane_id, line_id))
    return oid


def buildup(cur, lane_id) -> dict[str, dict]:
    cur.execute("""SELECT pool::text AS pool, amount, lines, from_unjudged
                     FROM v_lane_buildup WHERE lane_id = %s""", (lane_id,))
    return {r["pool"]: r for r in cur.fetchall()}


# ── A lane can differ ─────────────────────────────────────────────────

def test_a_lane_with_no_overrides_reads_as_the_baseline(cur, world):
    assert (buildup(cur, world["lanes"]["sandbox"])
            == buildup(cur, world["lanes"]["baseline"]))


def test_an_override_moves_cost_between_pools(cur, world):
    sandbox = world["lanes"]["sandbox"]
    override(cur, sandbox, "G&A", [f"LANE-{PERIOD}-002"])
    got = buildup(cur, sandbox)
    assert "OVERHEAD" not in got, (
        "the rent is still in the pool the sealed set put it in, so the "
        "override did not win — v_lane_buildup reads "
        "COALESCE(override.pool, decision.pool)")
    assert got["G&A"]["amount"] == Decimal("60000.00")
    # And the baseline is untouched, which is the entire point.
    assert buildup(cur, world["lanes"]["baseline"])["OVERHEAD"]["amount"] \
        == Decimal("60000.00")


def test_a_lane_can_try_a_line_nobody_has_judged(cur, world):
    """The question `v_lane_buildup` could not be asked before `057`.

    5227 Portfolio consulting is the largest single open judgment in the
    ledger, and what the rate looks like if it is G&A is exactly what a lane
    is for. It was invisible: the view started FROM lane JOIN decision, so a
    line with no decision was not in the build-up at all.
    """
    sandbox = world["lanes"]["sandbox"]
    assert "G&A" not in buildup(cur, sandbox)
    override(cur, sandbox, "G&A", [f"LANE-{PERIOD}-001"])
    got = buildup(cur, sandbox)
    assert got["G&A"]["amount"] == Decimal("588539.00")
    assert got["G&A"]["from_unjudged"] == Decimal("588539.00"), (
        "cost pulled out of the queue is counted separately from cost moved "
        "between pools — only the first changes how much there is left to "
        "judge")


def test_cost_moved_between_pools_is_not_counted_as_unjudged(cur, world):
    """So the previous assertion is about the line, not about overrides in
    general."""
    sandbox = world["lanes"]["sandbox"]
    override(cur, sandbox, "G&A", [f"LANE-{PERIOD}-002"])
    assert buildup(cur, sandbox)["G&A"]["from_unjudged"] == Decimal("0.00")


# ── And a lane can never be the way the baseline changes ──────────────

def test_an_override_does_not_touch_the_decision(cur, world):
    """The guarantee. A lane is a question; the sealed set is the answer."""
    cur.execute("""SELECT pool::text AS pool, reversed_at FROM decision
                    WHERE set_id = %s""", (world["set_id"],))
    before = cur.fetchall()
    override(cur, world["lanes"]["sandbox"], "G&A", [f"LANE-{PERIOD}-002"])
    cur.execute("""SELECT pool::text AS pool, reversed_at FROM decision
                    WHERE set_id = %s""", (world["set_id"],))
    assert cur.fetchall() == before, (
        "trying a reading in a lane changed the sealed set, which is the one "
        "thing the whole seal guarantee rests on not happening")
    cur.execute("""SELECT count(*) AS n FROM decision_line dl
                     JOIN decision d ON d.decision_id = dl.decision_id
                    WHERE d.set_id = %s AND NOT dl.live""", (world["set_id"],))
    assert cur.fetchone()["n"] == 0


def test_one_line_carries_one_reading_per_lane(cur, world):
    """Two readings of one line in one lane would count it twice in that
    lane's own build-up — the supersession defect in a new place."""
    import psycopg
    sandbox = world["lanes"]["sandbox"]
    override(cur, sandbox, "G&A", [f"LANE-{PERIOD}-002"])
    with pytest.raises(psycopg.errors.UniqueViolation):
        override(cur, sandbox, "FRINGE", [f"LANE-{PERIOD}-002"])


def test_the_same_line_may_be_read_differently_in_a_different_lane(cur, world):
    """Otherwise the constraint would make two lanes unable to disagree,
    which is the only thing lanes are for."""
    cur.execute("""INSERT INTO lane (period, name, kind, set_id, purpose,
                                     created_by)
                   VALUES (%s,'other','SANDBOX',%s,'p','test')
                   RETURNING lane_id""", (PERIOD, world["set_id"]))
    other = cur.fetchone()["lane_id"]
    override(cur, world["lanes"]["sandbox"], "G&A", [f"LANE-{PERIOD}-002"])
    override(cur, other, "FRINGE", [f"LANE-{PERIOD}-002"])
    assert "G&A" in buildup(cur, world["lanes"]["sandbox"])
    assert "FRINGE" in buildup(cur, other)


def test_an_override_line_cannot_name_another_lane(cur, world):
    """`lane_id` is carried on the line for the unique index, so it has to be
    kept honest — by a composite foreign key rather than a trigger."""
    import psycopg
    cur.execute("""INSERT INTO lane_decision_override
                     (lane_id, pool, function_990, federal, grade, reason,
                      created_by)
                   VALUES (%s,'G&A','MANAGEMENT_AND_GENERAL','ALLOWABLE',
                           'TEST_ASSUMPTION','r','test')
                   RETURNING override_id""", (world["lanes"]["sandbox"],))
    oid = cur.fetchone()["override_id"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute("""INSERT INTO lane_override_line (override_id, lane_id,
                                                       line_id)
                       VALUES (%s,%s,%s)""",
                    (oid, world["lanes"]["baseline"], f"LANE-{PERIOD}-002"))


def test_an_override_must_say_why(cur, world):
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        override(cur, world["lanes"]["sandbox"], "G&A",
                 [f"LANE-{PERIOD}-002"], reason="   ")


def test_a_direct_reading_names_its_objective(cur, world):
    """The same rule `direct_needs_objective` puts on a decision, so a lane
    cannot try something the sealed set could not have said."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        override(cur, world["lanes"]["sandbox"], "DIRECT",
                 [f"LANE-{PERIOD}-002"])
