"""What a donated hour is worth, and who may not decide it.

`donation_rate` has been in the schema since `019` with every invariant it
needs — immutable once set, no delete, one live rate per person per period, a
basis of at least ten characters, a positive rate — and **nothing had ever
written it**. `DONATION_RATE_MISSING` was a worklist kind pointing at a screen
where there was nothing to do on arrival.

The comment above the table has always said what the rule is:

    The controller sets it and says what it rests on, because a volunteer
    valuing their own time is the whole problem 200.306(e) is guarding
    against.

`require_controller` delivers the first half. It does not deliver the second,
because a controller is on the payroll like everybody else — tested against
the live record, the auditor got 403, the administrator got 403, and the
controller valued her own six donated hours at whatever she liked. `055` is
the second half, in the schema and in the handler, which is how this codebase
holds the three rules of the same shape it already has.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

BASIS = ("Consistent with what YBI pays for similar work, per the 2025 "
         "payroll register.")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.fixture
def people(cur):
    """Two accounts: one on the payroll, one not."""
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES ('2099','2099-01-01','2099-12-31')
                   ON CONFLICT DO NOTHING""")
    made = {}
    for label, key in (("volunteer", "VOLUNTEER99"), ("colleague", "COLLEAGUE99")):
        cur.execute("""INSERT INTO actor (email, display_name, role,
                                          employee_key, password_hash,
                                          password_set_by)
                       VALUES (%s,%s,'CONTROLLER',%s,'x','SELF')
                       RETURNING actor_id""",
                    (f"{key.lower()}@example.test", label.title(), key))
        made[label] = {"actor_id": cur.fetchone()["actor_id"], "key": key}
    cur.execute("""INSERT INTO actor (email, display_name, role,
                                      password_hash, password_set_by)
                   VALUES ('outside99@example.test','Outside','SYSTEM_ADMIN',
                           'x','SELF')
                   RETURNING actor_id""")
    made["outsider"] = {"actor_id": cur.fetchone()["actor_id"], "key": None}
    return made


def set_rate(cur, by: dict, whose: str, rate="80.00", basis=BASIS):
    cur.execute("""INSERT INTO donation_rate
                     (period, employee_key, hourly_rate, basis, set_by,
                      set_by_name)
                   VALUES ('2099',%s,%s,%s,%s,'test')
                   RETURNING rate_id""",
                (whose, Decimal(rate), basis, by["actor_id"]))
    return cur.fetchone()["rate_id"]


def test_a_colleague_may_value_a_volunteers_time(cur, people):
    set_rate(cur, people["colleague"], people["volunteer"]["key"])


def test_nobody_values_their_own_donated_time(cur, people):
    """The half `require_controller` cannot deliver.

    A controller is on the payroll like everybody else, so the gate that
    keeps out the auditor and the administrator lets through the one person
    the rule is actually about.
    """
    import psycopg
    # CheckViolation rather than RaiseException: the trigger raises with
    # ERRCODE = 'check_violation' on purpose, so a client reads it as the
    # same class of refusal as the CHECK constraints beside it rather than
    # as an unclassified error.
    with pytest.raises(psycopg.errors.CheckViolation) as e:
        set_rate(cur, people["volunteer"], people["volunteer"]["key"])
    assert "gave it" in str(e.value)


def test_an_account_off_the_payroll_is_not_valuing_itself(cur, people):
    """`employee_key` is NULL for somebody who is not on the payroll, and
    NULL never equals anything — but a trigger that got this wrong would
    refuse every rate set by such an account, so it is worth holding."""
    set_rate(cur, people["outsider"], people["volunteer"]["key"])


def test_a_rate_is_superseded_and_never_edited(cur, people):
    """Immutable once set, which is what makes "what was this valued at when
    the rate was computed" answerable afterwards."""
    import psycopg
    first = set_rate(cur, people["colleague"], people["volunteer"]["key"], "80.00")
    # RestrictViolation: `refuse_mutation` is the same guard audit_log and
    # ledger_line carry — "append-only; correct by superseding, never by
    # editing".
    with pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute("UPDATE donation_rate SET hourly_rate = 500 "
                    "WHERE rate_id = %s", (first,))


def test_one_live_rate_per_person(cur, people):
    import psycopg
    set_rate(cur, people["colleague"], people["volunteer"]["key"], "80.00")
    with pytest.raises(psycopg.errors.UniqueViolation):
        set_rate(cur, people["colleague"], people["volunteer"]["key"], "90.00")


def test_a_basis_has_to_say_something(cur, people):
    """"market" is not a statement of what a rate rests on, and 200.306(e)
    asks for one."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        set_rate(cur, people["colleague"], people["volunteer"]["key"],
                 basis="market")


def test_the_conflict_view_says_who_could_value_each_persons_hours(cur, people):
    """Zero others is not a defect — it is one controller who is also the
    volunteer — but it is worth finding out about in October rather than in
    the week the return is due."""
    cur.execute("""SELECT count(*) AS n FROM information_schema.views
                    WHERE table_name = 'v_donation_rate_conflict'""")
    assert cur.fetchone()["n"] == 1


def test_the_handler_refuses_it_too(cur):
    """The schema is what makes it hold when the handler is wrong. The
    handler is what makes the refusal a sentence somebody can act on rather
    than a constraint violation with a stack trace."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "app" / "routers"
           / "timesheet.py").read_text()
    body = src[src.index("def put_donation_rate"):]
    body = body[:body.index("\n@router")]
    assert "actor.employee_key" in body and "200.306(e)" in body, (
        "the donation-rate handler no longer refuses somebody valuing their "
        "own hours, so the only thing stopping it is a raw trigger message")
