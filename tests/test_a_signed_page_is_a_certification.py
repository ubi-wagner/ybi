"""A page somebody signed is a certification, and it names the page.

`labor_certification` had sixteen columns and **not one pointed at a
document**. The signature it recorded was a click — `signed_by` was the
calling actor's display name — so a page a person physically signed could be
uploaded, land in the library attached to nothing, and leave
`v_certification_status` reading *0 of 43 certified*. Forty signed pages on
file and forty uncertified people, at the same moment, on two screens.

The only alternative was signing `as_supervisor`, which writes a **different
assertion** — *I have firsthand knowledge of the work performed* — over
forty-three people including those on projects the signer does not run.

Migration `120` adds the third role. What it has to hold:

  * a PAPER row **names its page**, and nothing else may;
  * a PAPER row carries the date **on the page**, which is not the date it
    was filed;
  * that date is inside the period and not in the future;
  * `v_certification_status` counts it, and says which kind it was;
  * and the person's name is **read from the record, never taken from the
    request** — `test_a_name_in_the_request_is_only_ever_a_label` in a new
    place, and the one that would be unfindable afterwards.

Driven against a database inside a transaction that is rolled back, and the
rows are made here rather than selected: CI runs against an empty database,
and *a test that reads whatever happens to be in the database passes for a
developer and fails in CI*.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


@pytest.fixture()
def cur():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        with _cur(con) as c:
            yield c
        con.rollback()


def _scaffold(cur) -> tuple[str, str, str]:
    """An actor to file as, a document to name, and an employee key."""
    tag = uuid.uuid4().hex[:8]
    cur.execute("""INSERT INTO actor (email, display_name, role, password_hash,
                                      employee_key)
                   VALUES (%s, %s, 'CONTROLLER', 'x', %s)
                RETURNING actor_id""",
                (f"filer-{tag}@ybi.org", f"Filer {tag}", f"FILER{tag}"))
    actor_id = cur.fetchone()["actor_id"]
    eid = f"EV-test-{tag}"
    cur.execute("""INSERT INTO evidence (evidence_id, period, kind, uri,
                                         sha256, filename)
                   VALUES (%s, '2025', 'certification', %s, %s, 'signed.pdf')""",
                (eid, f"evidence/2025/certification/{tag}.pdf", tag * 8))
    return str(actor_id), eid, f"EMP{tag}"


def _row(actor_id: str, employee_key: str, **over) -> tuple:
    body = dict(period="2025", employee_key=employee_key,
                certifier_role="PAPER", actor_id=actor_id,
                signed_by="Somebody Real", period_start="2025-01-01",
                period_end="2025-12-31",
                statement="I certify that the distribution of effort shown "
                          "above is a reasonable reflection of total activity.",
                distribution=json.dumps([]), distribution_hash="d41d8",
                evidence_id=None, paper_signed_on=None)
    body.update(over)
    return body


def _insert(cur, body: dict):
    cols = ", ".join(body)
    marks = ", ".join(["%s"] * len(body))
    cur.execute(f"INSERT INTO labor_certification ({cols}) VALUES ({marks})",
                tuple(body.values()))


# ── the page ─────────────────────────────────────────────────────────

def test_a_filed_certification_names_the_page_it_was_read_off(cur):
    """A claim that somebody signed, with nothing to check it against, is
    worth less than no row: it reads as a certification on every screen."""
    actor_id, _eid, key = _scaffold(cur)
    with pytest.raises(Exception) as e:
        _insert(cur, _row(actor_id, key, paper_signed_on="2026-01-31"))
    assert "paper_names_its_page" in str(e.value)


def test_only_a_filed_certification_names_a_page(cur):
    """An EMPLOYEE row carrying a document would claim a scan behind a click.
    The fence is an equivalence rather than two one-way checks, which is
    `direct_needs_objective`'s shape for the same reason."""
    actor_id, eid, key = _scaffold(cur)
    with pytest.raises(Exception) as e:
        _insert(cur, _row(actor_id, key, certifier_role="EMPLOYEE",
                          evidence_id=eid))
    assert "paper_names_its_page" in str(e.value)


# ── the date on it ───────────────────────────────────────────────────

def test_a_filed_certification_carries_the_date_the_page_carries(cur):
    """`signed_at` is when the row was written. The page has its own date and
    the gap between them is the filing lag, which a reviewer is entitled to
    see rather than having it collapsed into one column."""
    actor_id, eid, key = _scaffold(cur)
    with pytest.raises(Exception) as e:
        _insert(cur, _row(actor_id, key, evidence_id=eid))
    assert "paper_carries_the_date_on_the_page" in str(e.value)


def test_a_page_cannot_predate_the_effort_it_certifies(cur):
    actor_id, eid, key = _scaffold(cur)
    with pytest.raises(Exception) as e:
        _insert(cur, _row(actor_id, key, evidence_id=eid,
                          paper_signed_on="2024-12-31"))
    assert "paper_is_dated_within_reason" in str(e.value)


def test_a_page_dated_after_it_was_filed_is_a_transcription_error(cur):
    actor_id, eid, key = _scaffold(cur)
    with pytest.raises(Exception) as e:
        _insert(cur, _row(actor_id, key, evidence_id=eid,
                          paper_signed_on="2099-01-01"))
    assert "paper_is_dated_within_reason" in str(e.value)


# ── what the register then says ──────────────────────────────────────

def test_a_good_filing_is_accepted_and_the_register_says_which_kind(cur):
    """The positive case, because a file of refusals proves only that nothing
    can be written. `by_paper` is what lets a screen tell a person who signed
    here from a page somebody else filed."""
    actor_id, eid, key = _scaffold(cur)
    _insert(cur, _row(actor_id, key, evidence_id=eid,
                      paper_signed_on="2026-02-14"))
    cur.execute("""SELECT certifier_role::text AS role, signed_by, evidence_id,
                          paper_signed_on, actor_id
                     FROM labor_certification
                    WHERE employee_key = %s""", (key,))
    row = cur.fetchone()
    assert row["role"] == "PAPER"
    assert row["evidence_id"] == eid
    assert str(row["paper_signed_on"]) == "2026-02-14"
    # The two facts the row exists to keep apart.
    assert row["signed_by"] == "Somebody Real"
    assert str(row["actor_id"]) == actor_id


def test_the_status_view_carries_the_kind_of_signature(cur):
    """Read off the view rather than the table: `v_certification_status` is
    what every screen and both workbooks ask, and a column added to the table
    and not carried through is the capability-with-no-door shape."""
    cur.execute("SELECT * FROM v_certification_status LIMIT 0")
    columns = {d.name for d in cur.description}
    assert {"by_employee", "by_supervisor", "by_paper", "paper_signed_on"} \
        <= columns, (
        "the register has to say which kind of signature it counted; "
        f"it carries {sorted(columns)}")


# ── the name is never typed ──────────────────────────────────────────

def test_the_request_cannot_name_the_person_who_signed():
    """The filer does not type a name.

    `signed_by` is read off the record for the `employee_key`, because a name
    box would let a typo put one person's signature against another's year
    and **nothing downstream could catch it** — the row would be internally
    consistent and about the wrong person. Same rule as
    `test_a_name_in_the_request_is_only_ever_a_label`, at the one place where
    the caller is deliberately not the signer.
    """
    from app.routers.certify import SignIn_
    offered = set(SignIn_.model_fields)
    named = {f for f in offered
             if "name" in f or f in {"signed_by", "signer", "display_name"}}
    assert not named, (
        f"the filing body offers {sorted(named)}, so the name on a "
        f"certification could come from the request rather than the record")


def test_filing_and_asserting_are_not_the_same_act():
    """`as_supervisor` and `on_paper` are different claims and the route
    refuses both at once rather than silently preferring one."""
    import inspect
    from app.routers import certify
    src = inspect.getsource(certify.sign)
    assert "body.as_supervisor and body.on_paper" in src, (
        "a request carrying both flags has to be refused, not resolved by "
        "whichever branch is tested first")
