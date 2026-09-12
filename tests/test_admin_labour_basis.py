"""Administrative labour: in the base, or in the G&A pool.

Migration `068`. `YBI-GA` carries $264,444.90 of wages ($322,358.33 with
fringe) and the model has always treated it as a **cost objective**, so it
takes a $100,013.06 allocation of indirect rather than forming part of it.
2 CFR 200 Appendix IV B puts the director's office, accounting and personnel
administration *in* the G&A pool; modelling it as an objective allocates the
indirect pool to its own administration, which recovers from nobody.

The counter-argument is real and does not apply: FUNDRAISING and
UNALLOWABLE-ACTIVITY *are* deliberately benefiting objectives, because
200.413 and Appendix IV B.3.d make them bear indirect while recovering
nothing. General administration is the opposite case.

It is worth 34.82% against 43.99% on the same sealed judgments — too large to
be a property of whichever code happened to be deployed, and a judgment
rather than arithmetic. So the rate records which basis produced it, and the
build-up has to tie under either.

Own rows, own transaction, rolled back.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2093"


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


def a_sealed_set(cur):
    cur.execute("""INSERT INTO decision_set (period, label, seal_hash,
                                             sealed_at, sealed_by)
                   VALUES (%s,'test',md5(random()::text),now(),'test')
                RETURNING set_id, seal_hash""", (PERIOD,))
    row = cur.fetchone()
    return row["set_id"], row["seal_hash"]


def an_administrative_distribution(cur, wages="100000.00"):
    """A real YBI-GA labour distribution, because a period with none makes
    `pool_admin_labour` zero however the view is written — and a test over
    nothing is the empty set matching the empty set."""
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('YBI-GA',%s,'Administration','INDIRECT',false)
                   ON CONFLICT DO NOTHING""", (PERIOD,))
    cur.execute("""INSERT INTO labor_allocation
                     (period, employee_key, employee_name, objective_id,
                      payroll_wages, original_units, reconstructed_units,
                      evidence_quality, rationale, loaded_by)
                   VALUES (%s,'ADMIN','Admin','YBI-GA',%s,0,1,
                           'MANAGEMENT_RECONSTRUCTION','test','test')""",
                (PERIOD, wages))


def a_fringe_rate(cur, set_id, seal, rate="0.2000", *, later=False):
    """`later` stamps a visibly newer `computed_at`. Two rows inserted in one
    transaction share `now()`, so a test meaning "the newest" against the
    default would be deciding a tie — flaky rather than wrong, which is the
    harder kind to notice."""
    cur.execute("""INSERT INTO rate (period, set_id, seal_hash, kind,
                                     pool_amount, base_type, base_amount,
                                     rate, computed_by, computed_at)
                   VALUES (%s,%s,%s,'FRINGE','200.00','SALARIES_WAGES',
                           '1000.00',%s,'test',
                           now() + CASE WHEN %s THEN interval '1 hour'
                                        ELSE interval '0' END)""",
                (PERIOD, set_id, seal, rate, later))


def a_recorded_rate(cur, kind="INDIRECT_COMBINED", *, basis=None,
                    pool="1000.00", base="10000.00", rate="0.1000"):
    set_id, seal = a_sealed_set(cur)
    cols = ["period", "set_id", "seal_hash", "kind", "pool_amount",
            "base_type", "base_amount", "rate", "computed_by"]
    args = [PERIOD, set_id, seal, kind, pool, "MTDC", base, rate, "test"]
    if basis is not None:
        cols.append("admin_labour_basis")
        args.append(basis)
    cur.execute(f"""INSERT INTO rate ({','.join(cols)})
                    VALUES ({','.join(['%s'] * len(cols))})
                 RETURNING rate_id""", args)
    return cur.fetchone()["rate_id"], set_id, seal


# ── the choice is on the rate ────────────────────────────────────────

@pytest.mark.parametrize("basis", ["OBJECTIVE", "POOL"])
def test_a_rate_records_which_basis_produced_it(cur, basis):
    rid, _sid, _seal = a_recorded_rate(cur, basis=basis)
    cur.execute("SELECT admin_labour_basis FROM rate WHERE rate_id = %s", (rid,))
    assert cur.fetchone()["admin_labour_basis"] == basis


def test_a_rate_written_before_the_choice_existed_is_not_relabelled(cur):
    """Every rate before `068` was computed on the OBJECTIVE basis. The
    default states that rather than leaving it NULL — a rate whose basis is
    unknown is one a reviewer cannot reproduce — and it has to be the basis
    those rates actually used, not the one somebody prefers now."""
    rid, _sid, _seal = a_recorded_rate(cur)
    cur.execute("SELECT admin_labour_basis FROM rate WHERE rate_id = %s", (rid,))
    assert cur.fetchone()["admin_labour_basis"] == "OBJECTIVE"


def test_a_basis_the_engine_cannot_apply_is_refused_by_the_schema(cur):
    """Two treatments exist and a third is a typo. In a CHECK for the reason
    every invariant here is: it has to hold when a handler is wrong."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        a_recorded_rate(cur, basis="POOLED")


# ── both answers on one row ──────────────────────────────────────────

def test_the_decision_view_reports_no_data_rather_than_a_movement(cur):
    """A rate with no YBI-GA allocation has nothing to move, and a choice
    that cannot be evaluated has not been made — the three-state rule the
    statement register follows."""
    a_recorded_rate(cur)  # noqa: the rate alone
    cur.execute("""SELECT state, admin_in_base, rate_if_pooled, movement
                     FROM v_admin_labour_decision WHERE period = %s""",
                (PERIOD,))
    row = cur.fetchone()
    assert row["state"] == "NO DATA"
    assert row["admin_in_base"] is None
    assert row["rate_if_pooled"] is None and row["movement"] is None


def test_the_alternative_is_computed_from_the_rate_that_was_recorded(cur):
    """The decision is taken with the alternative visible rather than
    against a number somebody remembers. The administrative objective's own
    base amount moves from the denominator to the numerator, which is the
    whole of the difference between the two treatments."""
    rid, _sid, _seal = a_recorded_rate(cur, pool="1000.00", base="10000.00", rate="0.1000")
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('YBI-GA',%s,'Administration','INDIRECT',false)
                   ON CONFLICT DO NOTHING""", (PERIOD,))
    cur.execute("""INSERT INTO allocation (rate_id, objective_id, base_amount,
                                           allocated)
                   VALUES (%s,'YBI-GA','2000.00','200.00')""", (rid,))
    cur.execute("""SELECT state, admin_in_base, rate_if_pooled, movement
                     FROM v_admin_labour_decision WHERE period = %s""",
                (PERIOD,))
    row = cur.fetchone()
    assert row["state"].startswith("OPEN")
    assert row["admin_in_base"] == Decimal("2000.00")
    # (1000 + 2000) / (10000 - 2000) = 0.375, and the movement is +0.275.
    assert row["rate_if_pooled"] == Decimal("0.375000")
    assert row["movement"] == Decimal("0.275000")


def test_a_rate_on_the_pool_basis_reports_the_choice_as_made(cur):
    """`DECIDED` and `OPEN` are different facts and a screen that prints
    them the same way cannot say whether anybody looked."""
    a_recorded_rate(cur, basis="POOL")
    cur.execute("SELECT state FROM v_admin_labour_decision WHERE period = %s",
                (PERIOD,))
    assert cur.fetchone()["state"].startswith("DECIDED")


# ── and the build-up has to tie under either ─────────────────────────

@pytest.mark.parametrize("basis,expected", [("OBJECTIVE", "0"),
                                            ("POOL", "120000.00")])
def test_the_build_up_ties_under_either_basis(cur, basis, expected):
    """The `FACILITY_UNPARTITIONED` shape. Under POOL the G&A pool carries
    labour that came from the effort distribution rather than from a
    classification, so the build-up reported OPEN by exactly that amount the
    moment the choice was made — a control nobody can clear by doing the
    work teaches the reader the list is wrong, and the next real failure
    they see they will dismiss.

    $100,000 of administrative wages at a 20% fringe rate is $120,000 into
    the pool, and zero under OBJECTIVE, where it stays a benefiting
    objective in the base.
    """
    an_administrative_distribution(cur, "100000.00")
    rid, sid, seal = a_recorded_rate(cur, kind="G&A", basis=basis,
                                     pool=expected, base="10000.00",
                                     rate="0.0000")
    a_fringe_rate(cur, sid, seal, "0.2000")
    cur.execute("""SELECT pool_admin_labour, pool_variance, ties
                     FROM v_rate_buildup WHERE rate_id = %s""", (rid,))
    row = cur.fetchone()
    assert row["pool_admin_labour"] == Decimal(expected)
    assert row["pool_variance"] == Decimal("0.00"), (
        "the expected pool has to be read against the basis the rate used")
    assert row["ties"]


@pytest.mark.parametrize("kind", ["G&A", "INDIRECT_COMBINED", "OVERHEAD",
                                  "FRINGE"])
def test_one_row_per_rate_whatever_the_kind_rolls_up(cur, kind):
    """`pool_for_kind` has two rows for INDIRECT_COMBINED, so an add-back
    joined to it multiplied the pool and the build-up reported OPEN by
    exactly the G&A gross. Aggregate first, add once afterwards."""
    an_administrative_distribution(cur, "100000.00")
    rid, sid, seal = a_recorded_rate(cur, kind=kind, basis="POOL",
                                     pool="0.00", base="10000.00",
                                     rate="0.0000")
    a_fringe_rate(cur, sid, seal, "0.2000")
    cur.execute("""SELECT count(*) AS n, max(pool_admin_labour) AS adm
                     FROM v_rate_buildup WHERE rate_id = %s""", (rid,))
    row = cur.fetchone()
    assert row["n"] == 1
    # And the add-back is counted once, not once per pool the kind rolls up.
    if kind in ("G&A", "INDIRECT_COMBINED"):
        assert row["adm"] == Decimal("120000.00")


@pytest.mark.parametrize("kind", ["OVERHEAD", "FRINGE"])
def test_administrative_labour_reaches_only_the_pools_that_contain_it(cur, kind):
    """OVERHEAD and FRINGE do not contain G&A, so the add-back must not
    reach them however the basis is set — and the distribution here is real,
    because over a period with no administrative labour this passes whatever
    the view does."""
    an_administrative_distribution(cur, "100000.00")
    rid, sid, seal = a_recorded_rate(cur, kind=kind, basis="POOL",
                                     pool="0.00", base="10000.00",
                                     rate="0.0000")
    a_fringe_rate(cur, sid, seal, "0.2000")
    cur.execute("""SELECT pool_admin_labour FROM v_rate_buildup
                    WHERE rate_id = %s""", (rid,))
    assert cur.fetchone()["pool_admin_labour"] == Decimal("0")


def test_the_fringe_on_the_moved_wages_is_this_computations_own_rate(cur):
    """Read from the FRINGE rate of the same sealed set, not from whatever
    rate happens to be newest — the defect `apply_fringe` was written to
    close, one level up."""
    an_administrative_distribution(cur, "100000.00")
    rid, sid, seal = a_recorded_rate(cur, kind="G&A", basis="POOL",
                                     pool="110000.00", base="10000.00",
                                     rate="0.0000")
    a_fringe_rate(cur, sid, seal, "0.1000")
    # A newer FRINGE rate on a *different* sealed set, at a different rate.
    # Without this the period holds one fringe rate and the assertion cannot
    # tell "this set's" from "the latest" — it would pass with the set_id
    # filter deleted.
    other_set, other_seal = a_sealed_set(cur)
    a_fringe_rate(cur, other_set, other_seal, "0.9000", later=True)
    cur.execute("""SELECT pool_admin_labour FROM v_rate_buildup
                    WHERE rate_id = %s""", (rid,))
    assert cur.fetchone()["pool_admin_labour"] == Decimal("110000.00"), (
        "the add-back must use the FRINGE rate of the rate's own sealed set")
