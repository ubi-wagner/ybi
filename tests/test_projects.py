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
def somebody(cur):
    """An account, because a todo reaches a person rather than a payroll key.

    `060` moved `todo.assignee` to `assignee_actor` for one reason: Tom holds
    CONTROLLER and is not on the payroll register, so the handoff this whole
    mechanism exists for could never have reached him.
    """
    # CONTROLLER rather than EMPLOYEE: `employee_needs_key` requires an
    # EMPLOYEE to be on the payroll register, and the point of this fixture
    # is the person who is *not* — which is Tom exactly.
    cur.execute("""INSERT INTO actor (email, display_name, password_hash, role)
                   VALUES ('somebody@test.invalid','Somebody','x','CONTROLLER')
                   RETURNING actor_id""")
    return cur.fetchone()["actor_id"]


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
    cur.execute("""INSERT INTO todo (period, objective_id, title,
                                     assignee_actor, due_on, status,
                                     blocked_reason, done_at, done_by,
                                     worklist_kind, worklist_entity_id,
                                     opened_by)
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

def test_an_item_nobody_has_taken_is_the_interesting_row(cur, proj, somebody):
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
    todo(cur, None, assignee=somebody, worklist_kind=item["kind"],
         worklist_entity_id=item["entity_id"])
    cur.execute("""SELECT taken, assignee FROM v_worklist_covered
                    WHERE kind = %s AND entity_id = %s""",
                (item["kind"], item["entity_id"]))
    row = cur.fetchone()
    assert row["taken"] and row["assignee"] == "Somebody"


def test_a_finished_todo_stops_covering_its_item(cur, proj, somebody):
    """Otherwise an item stays "taken" for ever on the strength of work that
    finished without clearing it."""
    import datetime as dt
    cur.execute("SELECT kind, entity_id FROM v_worklist_owned LIMIT 1")
    item = cur.fetchone()
    if not item:
        pytest.skip("nothing outstanding on this database to take")
    todo(cur, None, assignee=somebody, worklist_kind=item["kind"],
         worklist_entity_id=item["entity_id"], status="DONE",
         done_at=dt.datetime.now(dt.timezone.utc), done_by="Somebody")
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


# ── The handoff ───────────────────────────────────────────────────────

def claim(cur, code, somebody, **kw):
    cur.execute("""INSERT INTO project_claim
                     (objective_id, period, covers_from, covers_to, state,
                      approved_by, note, saw_hours, saw_amount, saw_lines,
                      saw_documents, invoice_id, invoiced_at, invoiced_by,
                      queried_reason, queried_at, queried_by,
                      withdrawn_reason)
                   VALUES (%s,%s,'2095-01-01','2095-12-31',%s,%s,%s,
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING claim_id""",
                (code, PERIOD, kw.get("state", "APPROVED"), somebody,
                 kw.get("note", "The 2095 work as distributed."),
                 kw.get("saw_hours", 0), kw.get("saw_amount", 0),
                 kw.get("saw_lines", 0), kw.get("saw_documents", 0),
                 kw.get("invoice_id"), kw.get("invoiced_at"),
                 kw.get("invoiced_by"), kw.get("queried_reason"),
                 kw.get("queried_at"), kw.get("queried_by"),
                 kw.get("withdrawn_reason")))
    return cur.fetchone()["claim_id"]


def test_a_todo_reaches_somebody_who_is_not_on_the_payroll(cur, proj, somebody):
    """The reason `060` exists at all.

    `todo.assignee` was an `employee_key`, and **Tom holds CONTROLLER and is
    not on the payroll register** — so the very thing the handoff exists to
    do, hand him a job to invoice, could not have reached him. An employee
    key says whose effort something was; an account says who is doing the
    work, and a list of jobs wants the second.
    """
    cur.execute("SELECT employee_key FROM actor WHERE actor_id = %s", (somebody,))
    assert cur.fetchone()["employee_key"] is None, (
        "the fixture has grown a payroll key, so it no longer stands for the "
        "person this test is about")
    todo(cur, proj, assignee=somebody, title="Invoice it")
    cur.execute("""SELECT assignee, assignee_actor FROM v_todo_live
                    WHERE title = 'Invoice it'""")
    got = cur.fetchone()
    assert got["assignee_actor"] == somebody
    assert got["assignee"] == "Somebody", (
        "the live list resolves the account to a name, so a screen never has "
        "to print a uuid at a person")


def test_a_claim_records_what_was_approved_and_notices_it_moving(cur, proj,
                                                                 somebody):
    """The four `saw_` columns are the seal, not a second register.

    A claim names a project and a span; what that span contains is read from
    the registers that hold it. But an approval has to be *of something* or
    the record moves underneath it and the approval silently comes to cover
    something else — which is exactly what `decision_set.seal_hash` is for.
    """
    claim(cur, proj, somebody, saw_documents=0)
    cur.execute("""SELECT still_agrees, saw_documents, documents
                     FROM v_project_claim WHERE objective_id = %s""", (proj,))
    got = cur.fetchone()
    assert got["still_agrees"], f"nothing has changed and it reads as moved: {got}"

    # File a document against the project — the record has now moved.
    cur.execute("""INSERT INTO evidence (evidence_id, period, kind, uri,
                                         sha256, filename)
                   VALUES ('EV-claimtest',%s,'other','/tmp/x.pdf','ab','x.pdf')""",
                (PERIOD,))
    cur.execute("""INSERT INTO attachment (evidence_id, target_type, target_id,
                                           attached_by)
                   VALUES ('EV-claimtest','OBJECTIVE',%s,'test')""", (proj,))
    cur.execute("""SELECT still_agrees, saw_documents, documents
                     FROM v_project_claim WHERE objective_id = %s""", (proj,))
    got = cur.fetchone()
    assert not got["still_agrees"], (
        "a document was filed against the project after the approval and the "
        "claim still reads as agreeing — which is the approval quietly coming "
        "to cover something it was never shown")
    assert got["saw_documents"] == 0 and got["documents"] == 1


def test_invoiced_carries_the_invoice_and_nothing_else_does(cur, proj, somebody):
    """`(state = 'INVOICED') = (invoice_id IS NOT NULL)`, both ways. A claim
    marked settled against nothing is a status somebody set."""
    with refused(cur, psycopg.errors.CheckViolation):
        claim(cur, proj, somebody, state="INVOICED")


def test_a_query_says_what_is_wrong_with_it(cur, proj, somebody):
    """A query with no reason is one nobody can answer — the blocked-todo
    rule, in the place it matters most."""
    with refused(cur, psycopg.errors.CheckViolation):
        claim(cur, proj, somebody, state="QUERIED")
    claim(cur, proj, somebody, state="QUERIED",
          queried_reason="No ledger line is classified to this objective yet.")


def test_withdrawing_says_why_too(cur, proj, somebody):
    with refused(cur, psycopg.errors.CheckViolation):
        claim(cur, proj, somebody, state="WITHDRAWN")


def test_approving_takes_a_sentence(cur, proj, somebody):
    """Ten characters is what the schema asks and a reader asks for more. An
    approval a reviewer reads beside the invoice it led to is worth a
    sentence."""
    with refused(cur, psycopg.errors.CheckViolation):
        claim(cur, proj, somebody, note="ok")


def test_one_live_manager_per_code(cur, code):
    """The rule every other grant here already follows: an amendment
    supersedes rather than sitting beside. Two live managers on one code is
    two people each believing the other is watching it."""
    cur.execute("""INSERT INTO labor_allocation (period, employee_key,
                                                 objective_id, payroll_wages)
                   VALUES (%s,'ONE',%s,1000), (%s,'TWO',%s,1000)""",
                (PERIOD, code, PERIOD, code))
    cur.execute("""INSERT INTO charge_authority (period, objective_id,
                                                 employee_key, role_on_project,
                                                 granted_by, reason)
                   VALUES (%s,%s,'ONE','MANAGER','test','runs it')""",
                (PERIOD, code))
    with refused(cur, psycopg.errors.UniqueViolation):
        cur.execute("""INSERT INTO charge_authority (period, objective_id,
                                                     employee_key,
                                                     role_on_project,
                                                     granted_by, reason)
                       VALUES (%s,%s,'TWO','MANAGER','test','because')""",
                    (PERIOD, code))
    # And a second person in any other role is fine — the constraint is about
    # the role, not about the code.
    cur.execute("""INSERT INTO charge_authority (period, objective_id,
                                                 employee_key, role_on_project,
                                                 granted_by, reason)
                   VALUES (%s,%s,'TWO','','test','on the distribution')""",
                (PERIOD, code))


def test_the_manager_reaches_the_overview_from_the_grant(cur, code):
    """Read off `role_on_project` rather than a column of its own, because a
    manager is somebody on the project with a role and that register already
    exists."""
    cur.execute("""INSERT INTO project (objective_id, name, opened_by)
                   VALUES (%s,'A project','test')""", (code,))
    cur.execute("SELECT manager FROM v_project_overview WHERE objective_id = %s",
                (code,))
    assert cur.fetchone()["manager"] is None
    cur.execute("""INSERT INTO labor_allocation (period, employee_key,
                                                 objective_id, payroll_wages)
                   VALUES (%s,'BOSS',%s,1000)""", (PERIOD, code))
    cur.execute("""INSERT INTO charge_authority (period, objective_id,
                                                 employee_key, role_on_project,
                                                 granted_by, reason)
                   VALUES (%s,%s,'BOSS','MANAGER','test','runs it')""",
                (PERIOD, code))
    cur.execute("SELECT manager FROM v_project_overview WHERE objective_id = %s",
                (code,))
    assert cur.fetchone()["manager"] == "BOSS"
