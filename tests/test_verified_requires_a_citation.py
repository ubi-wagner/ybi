"""The grade the whole matcher exists to make reachable.

Twenty-one documents on file and none attached to anything, so the ceiling on
every one of the controller's two hundred judgments was `CORROBORATED`. What
the ceiling actually is, in the schema, is this trigger — and it is worth
knowing precisely, because the loose version of the sentence is wrong in a
way that matters.

**`VERIFIED` requires a document *cited on the judgment*, not merely attached
to the cost.** `decision_verified_check` counts `decision_evidence`, not
`attachment`. Attaching says "this paper is about that money"; citing says
"this paper is why I judged it the way I did". The queue's `NEEDS_EVIDENCE`
item says the same thing in the other direction — attaching a document is not
the same as citing it, and the gate reads the citation.

So the matcher does not grade anything. It makes the document findable, and
`decide()` carries `evidence_ids` from there. These tests hold the trigger
itself, in the database, so they are true when the handler above is wrong.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.fixture
def scaffold(cur):
    """A period, a set and a document of this test's own making.

    Never the real ones. A test that reads whatever is in the database passes
    on a seeded copy and fails in CI over an empty one, which is how three
    reconciliation tests came to be red on main for long enough that nobody
    was reading it.
    """
    period = "2099"
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES (%s, '2099-01-01', '2099-12-31')
                   ON CONFLICT DO NOTHING""", (period,))
    set_id = uuid.uuid4()
    cur.execute("""INSERT INTO decision_set (set_id, period, label)
                   VALUES (%s,%s,'trigger test')""", (set_id, period))
    eid = f"EV-{uuid.uuid4().hex[:12]}"
    cur.execute("""INSERT INTO evidence (evidence_id, period, kind, uri,
                                         sha256, received_from, byte_size,
                                         mime_type, ingest_channel)
                   VALUES (%s,%s,'invoice','/dev/null',%s,'test',1,
                           'application/pdf','UPLOAD')""",
                (eid, period, uuid.uuid4().hex))
    return {"period": period, "set_id": set_id, "evidence_id": eid}


def _decide(cur, scaffold, grade: str) -> uuid.UUID:
    did = uuid.uuid4()
    cur.execute("""INSERT INTO decision (decision_id, set_id, scope, pool,
                                         function_990, federal, grade,
                                         rationale, decided_by)
                   VALUES (%s,%s,'9999 test','OVERHEAD',
                           'MANAGEMENT_AND_GENERAL','ALLOWABLE',%s,
                           'Recorded by the test suite to prove the trigger, '
                           'and rolled back immediately afterwards.','test')""",
                (did, scaffold["set_id"], grade))
    return did


def test_a_corroborated_judgment_needs_no_document(cur, scaffold):
    """The grade two hundred judgments were capped at. It is a real grade —
    a judgment with reasoning and no paper — and it must stay reachable."""
    _decide(cur, scaffold, "CORROBORATED")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")   # fire the deferred trigger


def test_verified_with_nothing_cited_is_refused(cur, scaffold):
    """The ceiling itself."""
    import psycopg
    _decide(cur, scaffold, "VERIFIED")
    with pytest.raises(psycopg.errors.RaiseException) as e:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert "requires at least one attached document" in str(e.value)


def test_attaching_a_document_to_the_cost_is_not_citing_it(cur, scaffold):
    """The distinction the loose sentence loses.

    A document attached to the ledger group says "this paper is about that
    money". The grade asks a different question — "this paper is why I judged
    it the way I did" — and the trigger counts the second. A matcher that
    attached in bulk and left somebody believing the grade had risen would
    be telling them something that did not happen.
    """
    import psycopg
    cur.execute("""INSERT INTO attachment (evidence_id, target_type, target_id,
                                           relevance, attached_by)
                   VALUES (%s,'LEDGER_GROUP','9999 test',
                           'Vendor invoice for this group.','test')""",
                (scaffold["evidence_id"],))
    _decide(cur, scaffold, "VERIFIED")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_verified_citing_the_document_stands(cur, scaffold):
    """And the other end of it: cited, and the grade holds.

    This is what the matcher is for. It does not grade anything — it makes
    the document findable, and `decide()` carries evidence_ids from there.
    """
    did = _decide(cur, scaffold, "VERIFIED")
    cur.execute("""INSERT INTO decision_evidence (decision_id, evidence_id)
                   VALUES (%s,%s)""", (did, scaffold["evidence_id"]))
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    cur.execute("SELECT grade::text FROM decision WHERE decision_id = %s", (did,))
    assert cur.fetchone()["grade"] == "VERIFIED"
