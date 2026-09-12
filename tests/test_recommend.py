"""A helper recommends; the controller verifies and seals.

Three guarantees, and each is the thing that would go wrong if it were built
the obvious way instead:

  * a recommendation is a `todo` and never a row in the register it points
    at, because `PROPOSED` on a restatement already means *the sponsor has
    not answered*;
  * one live job per outstanding item, because two is two people each told
    to clear it and each assuming the other has;
  * `/worklist/mine` is not gated on reading the cost record, because a
    portfolio is not a rank and the screen is written for people who hold
    one and nothing else.

Own rows, own transaction, rolled back, so they run against the bare database
CI builds from the migrations.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = Path(__file__).resolve().parent.parent
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


def a_todo(cur, *, kind="UNCLASSIFIED", entity="E-1", status="OPEN",
           period=PERIOD, opened_by="Somebody"):
    cur.execute("""INSERT INTO todo (period, title, worklist_kind,
                                     worklist_entity_id, status, opened_by,
                                     done_at, done_by)
                   VALUES (%s,'A job',%s,%s,%s,%s,
                           CASE WHEN %s='DONE' THEN now() END,
                           CASE WHEN %s='DONE' THEN 'Somebody' END)
                RETURNING todo_id""",
                (period, kind, entity, status, opened_by, status, status))
    return cur.fetchone()["todo_id"]


def test_one_live_job_per_worklist_item(cur):
    """Two open todos on one item is two people each assuming the other has
    it — the `one_live_manager_per_code` failure in a new place."""
    a_todo(cur)
    with pytest.raises(psycopg.errors.UniqueViolation):
        a_todo(cur)


def test_a_finished_job_does_not_block_the_item_coming_back(cur):
    """The index is partial on purpose. An item that returns is a new job and
    the finished one is part of the trail, so DONE must not hold the gate."""
    a_todo(cur, status="DONE")
    a_todo(cur, status="OPEN")          # no raise: this is the guarantee


def test_the_same_item_in_another_period_is_another_item(cur):
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES ('2093','2093-01-01','2093-12-31')
                   ON CONFLICT DO NOTHING""")
    a_todo(cur)
    a_todo(cur, period="2093")          # no raise


def test_todos_with_no_worklist_reference_do_not_collide(cur):
    """The index must not turn every unlinked todo into one todo. Both halves
    of `todo_check3` are NULL here, which the partial index excludes."""
    for _ in range(3):
        cur.execute("""INSERT INTO todo (period, title, opened_by)
                       VALUES (%s,'Free-standing','Somebody')""", (PERIOD,))


def test_the_covered_view_matches_the_period_too(cur):
    """`060` joined on kind and entity alone, so a job in one period reported
    an item in another as taken — and taken by somebody not working on it."""
    body = view_body("v_worklist_covered")
    assert re.search(r"tt\.period\s*=\s*w\.period", body), (
        "v_worklist_covered joins todo to the worklist without matching the "
        "period, so a 2026 job marks a 2025 item as taken")


def handler_body(fn: str) -> str:
    """A handler's source *after* its docstring.

    The first draft of this searched the whole function and matched the
    docstring's own mention of `v_worklist_owned`, reporting that a correct
    handler read the worklist outside the lock. A test that argues against
    working code is worse than no test, and the prose in these files names
    the things the code touches on purpose.
    """
    src = (ROOT / "app/routers/dashboard.py").read_text()
    body = src[src.index(f"def {fn}("):]
    opened = body.index('"""')
    return body[body.index('"""', opened + 3) + 3:]


def view_body(name: str) -> str:
    from app.db import one
    row = one("SELECT pg_get_viewdef(%s::regclass, true) AS body", (name,))
    return row["body"]


def test_the_covered_view_says_who_noticed(cur):
    """`audit_log` says who decided. Until `062` nothing said who noticed,
    which is the question an auditor actually asks about triage."""
    assert "opened_by" in view_body("v_worklist_covered")


# --- the shape of the thing, checked in the source ------------------------

def test_a_recommendation_is_a_todo_and_never_a_register_row():
    """The obvious build is a helper writing a PROPOSED restatement for the
    controller to confirm, and it is the wrong one: PROPOSED already means
    *YBI has put this to NCDMM and they have not answered*, so an auditor
    reading `restatement` could not tell a position from a suggestion.

    Asserted against the handler rather than described in a comment, because
    a rule nobody tests is a rule somebody rewrites.
    """
    body = handler_body("recommend")
    for register in ("restatement", "decision", "rate", "project_claim",
                     "invoice"):
        assert not re.search(rf"INSERT\s+INTO\s+{register}\b", body), (
            f"the recommend route writes {register}. A recommendation raises "
            f"work, never a number — it must only ever insert a todo")
    assert re.search(r"INSERT\s+INTO\s+todo\b", body)


def test_the_route_takes_the_lock_and_reads_the_item_inside_it():
    """"Read what you are about to depend on inside the turn." A
    recommendation naming an item that has since been cleared is the failure
    this prevents, and the lookup has to be under the lock to prevent it."""
    body = handler_body("recommend")
    lock = body.index("turn(period)")
    assert lock < body.index("FROM v_worklist_owned"), (
        "the recommend route reads the worklist before taking the turn")


def test_my_worklist_is_not_gated_on_reading_the_cost_record():
    """A portfolio is not a rank. `/worklist/mine` sat under a router-level
    `require_reader`, so the endpoint whose own docstring is about Heidi
    would have answered Heidi 403 the day she held FACILITIES and nothing
    else. It never showed because every portfolio holder in the seeded
    record also holds CONTROLLER rank — a defect masked by data.
    """
    src = (ROOT / "app/routers/dashboard.py").read_text()
    assert "dependencies=[Depends(require_reader)]" not in src, (
        "a router-level gate cannot be relaxed by a route, and one of these "
        "routes is a person's own list rather than the cost record")
    head = src[src.index("def my_worklist("):]
    assert "require_own_work" in head[:300]


def test_the_two_worklist_endpoints_read_the_same_view():
    """`/worklist` read `v_worklist` while `/worklist/mine` read
    `v_worklist_owned`, so four kinds answered `total = 0` on one endpoint
    and appeared on the other at the same moment. 13.0% and 2.2% in a
    smaller place."""
    src = (ROOT / "app/routers/dashboard.py").read_text()
    body = src[src.index("def worklist("):src.index("def activity(")]
    assert "v_worklist_owned" in body
    assert not re.search(r"FROM\s+v_worklist\s", body), (
        "the paged worklist reads the half of the list that predates "
        "v_worklist_extra")


def test_the_screen_offers_recommend_only_to_somebody_who_holds_something():
    """The auditor reads every one of these rows and holds no portfolio.
    A button that answers 403 is the Requests screen's lesson."""
    src = (ROOT / "web/src/pages/Worklist.jsx").read_text()
    assert "mayRecommend" in src and "actor?.portfolios" in src
    assert re.search(r"mayRecommend\s*&&", src), (
        "the Recommend button is rendered unconditionally")
