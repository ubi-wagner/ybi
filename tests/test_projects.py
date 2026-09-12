"""Setting a piece of work up, and the list a person can actually write.

Read across from the RFP pipeline's post-award module. Two things were taken
— a project and a todo — and a dozen registers were deliberately not, because
they already exist here under other names. These hold both halves: that the
taken shapes carry their invariants, and that the untaken ones did not quietly
grow a second register.

Own rows, own transaction, rolled back — so they run on the bare database CI
builds from the migrations.
"""

from __future__ import annotations

import contextlib
import os

import psycopg
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

PERIOD = "2095"


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.fixture
def code(cur):
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES (%s,'2095-01-01','2095-12-31')
                   ON CONFLICT DO NOTHING""", (PERIOD,))
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('P-TEST',%s,'A code','PROGRAM',false)
                   ON CONFLICT DO NOTHING""", (PERIOD,))
    return "P-TEST"


@pytest.fixture
def proj(cur, code):
    """A code that has been set up, because a todo hangs off a project.

    A todo naming a charge code nobody set up would be work against a code
    with no contract, no people and no dates — which is the state this whole
    thing exists to replace.
    """
    cur.execute("""INSERT INTO project (objective_id, name, opened_by)
                   VALUES (%s,'A project','test')""", (code,))
    return code


@contextlib.contextmanager
def refused(cur, error):
    """An expected refusal, inside a savepoint.

    A failed statement aborts its transaction, so a test that proves a
    constraint refuses one thing and *accepts* another has to take the
    refusal on a savepoint or everything after it fails for the wrong reason.
    The alternative — one expected failure per test, at the end — makes the
    accepting direction somebody else's test, and a constraint proved only in
    the refusing direction is one that could be refusing everything.
    """
    with pytest.raises(error):
        with cur.connection.transaction():
            yield


def project(cur, code, **kw):
    cur.execute("""INSERT INTO project (objective_id, name, opened_by, status,
                                        closed_at, closed_by, closeout_note)
                   VALUES (%s,%s,'test',%s,%s,%s,%s)""",
                (code, kw.get("name", "A project"), kw.get("status", "PLANNING"),
                 kw.get("closed_at"), kw.get("closed_by"),
                 kw.get("closeout_note")))


def todo(cur, code=None, **kw):
    cur.execute("""INSERT INTO todo (period, objective_id, title, assignee,
                                     due_on, status, blocked_reason, done_at,
                                     done_by, worklist_kind,
                                     worklist_entity_id, opened_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'test')
                   RETURNING todo_id""",
                (PERIOD, code, kw.get("title", "Do the thing"),
                 kw.get("assignee"), kw.get("due_on"),
                 kw.get("status", "OPEN"), kw.get("blocked_reason"),
                 kw.get("done_at"), kw.get("done_by"),
                 kw.get("worklist_kind"), kw.get("worklist_entity_id")))
    return cur.fetchone()["todo_id"]


# ── The charge code is the project ────────────────────────────────────

def test_a_project_is_keyed_on_the_charge_code(cur, code):
    """The rule the contracts section opens with, and the one the RFP
    pipeline learned the hard way: they built a WBS node tree beside a
    milestone list, found it was *two structures describing one thing*
    producing two answers to the same question, and collapsed it.

    A project id that could differ from an objective id is two names for one
    thing, and somebody would eventually ask which is right.
    """
    project(cur, code)
    with refused(cur, psycopg.errors.UniqueViolation):
        project(cur, code, name="A second project on one code")


def test_a_project_needs_a_charge_code_that_exists(cur, code):
    with refused(cur, psycopg.errors.ForeignKeyViolation):
        cur.execute("""INSERT INTO project (objective_id, name, opened_by)
                       VALUES ('NOT-A-CODE','x','test')""")


def test_closing_claims_a_date_and_says_something(cur, code):
    """Their `projects_closed_has_time`, which is this schema's
    `milestone_check` in another accent: a state that claims a date carries
    one."""
    project(cur, code)
    with refused(cur, psycopg.errors.CheckViolation):
        cur.execute("""UPDATE project SET status = 'CLOSED'
                        WHERE objective_id = %s""", (code,))
    with refused(cur, psycopg.errors.CheckViolation):
        cur.execute("""UPDATE project SET status='CLOSED', closed_at=now(),
                              closed_by='test', closeout_note='done'
                        WHERE objective_id = %s""", (code,))
    cur.execute("""UPDATE project SET status='CLOSED', closed_at=now(),
                          closed_by='test',
                          closeout_note='Delivered and closed out in full.'
                    WHERE objective_id = %s""", (code,))


# ── The todo, and the two rules taken from project_milestone_tasks ────

def test_blocked_says_what_is_blocking(cur, proj):
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, status="BLOCKED")
    todo(cur, proj, status="BLOCKED", blocked_reason="NCDMM has not replied.")


def test_a_reason_without_being_blocked_is_refused_too(cur, proj):
    """The pair is `(status = BLOCKED) = (reason IS NOT NULL)`, both ways.
    A stale reason on an unblocked item is a sentence that reads as current
    and is not."""
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, status="OPEN", blocked_reason="left over")


def test_done_carries_when_and_who(cur, proj):
    import datetime as dt
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, status="DONE")
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, status="DONE", done_at=dt.datetime.now(dt.timezone.utc))
    todo(cur, proj, status="DONE",
         done_at=dt.datetime.now(dt.timezone.utc), done_by="somebody")


def test_a_todo_may_belong_to_no_project(cur, proj):
    """"Chase NCDMM for a readable agreement" belongs to the engagement and
    to no charge code. Refusing it would push the most useful todos off the
    list entirely."""
    todo(cur, None, title="Chase NCDMM for a text-bearing agreement")
    # Scoped to this test's own period. Counting every row in the database
    # passes on a bare one and fails on a seeded one — the defect
    # `test_reconcile_db.py` had, in the other direction.
    cur.execute("""SELECT count(*) AS n FROM v_todo_live
                    WHERE objective_id IS NULL AND period = %s""", (PERIOD,))
    assert cur.fetchone()["n"] == 1


def test_unassigned_is_a_state_and_not_a_gap(cur, proj):
    """On the list and nobody has it is a different fact from nobody having
    written it down — the intake rule, applied to work."""
    todo(cur, proj, assignee=None)
    cur.execute("SELECT assignee FROM v_todo_live")
    assert cur.fetchone()["assignee"] is None


def test_done_drops_out_of_the_live_list_and_stays_on_the_record(cur, proj):
    import datetime as dt
    todo(cur, proj, title="finished",
         status="DONE", done_at=dt.datetime.now(dt.timezone.utc),
         done_by="somebody")
    cur.execute("""SELECT count(*) AS n FROM v_todo_live
                    WHERE objective_id = %s""", (proj,))
    assert cur.fetchone()["n"] == 0
    cur.execute("""SELECT count(*) AS n FROM todo
                    WHERE objective_id = %s AND status = 'DONE'""", (proj,))
    assert cur.fetchone()["n"] == 1, (
        "a finished todo is not deleted — the row is the trail")


def test_overdue_is_read_from_the_date_rather_than_stored(cur, proj):
    import datetime as dt
    today = dt.date.today()
    todo(cur, proj, title="late", due_on=today - dt.timedelta(days=3))
    todo(cur, proj, title="soon", due_on=today + dt.timedelta(days=3))
    todo(cur, proj, title="undated")
    cur.execute("SELECT title, overdue, days_to_due FROM v_todo_live "
                "ORDER BY title")
    got = {r["title"]: r for r in cur.fetchall()}
    assert got["late"]["overdue"] and got["late"]["days_to_due"] == -3
    assert not got["soon"]["overdue"] and got["soon"]["days_to_due"] == 3
    assert not got["undated"]["overdue"], (
        "a todo with no date is not overdue — it is undated, which is a "
        "different thing and a common one")


def test_naming_a_worklist_item_takes_both_halves(cur, proj):
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, worklist_kind="UNCLASSIFIED")
    with refused(cur, psycopg.errors.CheckViolation):
        todo(cur, proj, worklist_entity_id="5227")
    # And both together is fine, so the pair is what is being tested rather
    # than the columns being unusable.
    todo(cur, proj, worklist_kind="UNCLASSIFIED", worklist_entity_id="5227")


# ── The machine's list and a person's, joined ─────────────────────────

def test_an_item_nobody_has_taken_is_the_interesting_row(cur, proj):
    """`v_worklist` has always known *what* is outstanding and
    `v_worklist_owned` added *which portfolio*. Neither could say **who** or
    **by when**, because nothing in the system could write that down."""
    cur.execute("""SELECT kind, entity_id FROM v_worklist_owned LIMIT 1""")
    item = cur.fetchone()
    if not item:
        pytest.skip("nothing outstanding on this database to take")
    cur.execute("""SELECT taken FROM v_worklist_covered
                    WHERE kind = %s AND entity_id = %s""",
                (item["kind"], item["entity_id"]))
    assert cur.fetchone()["taken"] is False
    todo(cur, None, assignee="SOMEBODY", worklist_kind=item["kind"],
         worklist_entity_id=item["entity_id"])
    cur.execute("""SELECT taken, assignee FROM v_worklist_covered
                    WHERE kind = %s AND entity_id = %s""",
                (item["kind"], item["entity_id"]))
    row = cur.fetchone()
    assert row["taken"] and row["assignee"] == "SOMEBODY"


def test_a_finished_todo_stops_covering_its_item(cur, proj):
    """Otherwise an item stays "taken" for ever on the strength of work that
    finished without clearing it."""
    import datetime as dt
    cur.execute("SELECT kind, entity_id FROM v_worklist_owned LIMIT 1")
    item = cur.fetchone()
    if not item:
        pytest.skip("nothing outstanding on this database to take")
    todo(cur, None, assignee="SOMEBODY", worklist_kind=item["kind"],
         worklist_entity_id=item["entity_id"], status="DONE",
         done_at=dt.datetime.now(dt.timezone.utc), done_by="SOMEBODY")
    cur.execute("""SELECT taken FROM v_worklist_covered
                    WHERE kind = %s AND entity_id = %s""",
                (item["kind"], item["entity_id"]))
    assert cur.fetchone()["taken"] is False


# ── And the registers that were deliberately not taken ────────────────

NOT_TAKEN = ("project_assignments", "project_clins", "project_milestones",
             "project_deliverables", "project_invoices",
             "project_invoice_lines", "project_time_entries",
             "project_modifications", "project_risks", "project_reviews",
             "project_meetings", "project_comments", "project_tasks")


def test_no_second_register_grew_beside_the_ones_that_exist(cur):
    """Twelve tables were read across and not taken, each because the
    register already exists here: `charge_authority` holds who may charge a
    code, `award_budget` holds what an award funds, `milestone` holds a
    deliverable, `invoice` and `receipt` hold the money, `timesheet_entry`
    holds the hours, `award_term` holds a modification and cites the clause.

    This is the same test `test_contracts.py` runs against a `charge_code`
    table, for the same reason: the cost objective is the charge code and
    there is deliberately no second register of codes.
    """
    cur.execute("""SELECT c.relname FROM pg_class c
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                      AND c.relname = ANY(%s)""", (list(NOT_TAKEN),))
    grew = [r["relname"] for r in cur.fetchall()]
    assert not grew, (
        f"these duplicate a register that already exists: {grew}. See "
        f"migration 059 for which one each of them would be a second copy of.")
