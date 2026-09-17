"""Contractor or subrecipient: the register, the door, and what it moves.

Migration `115` opened a 2 CFR 200.331 determination for every party the
200.1 cap could bite and said, in its own words, that it was *"recorded with
the route and screen it stands in for"*. Neither was built. So six
determinations worth **$313,605.35 of MTDC** were answerable only by somebody
writing SQL — the capability-with-no-door shape, in the one register whose
answer changes the base every indirect rate is taken over.

What `121` and the two handlers have to hold:

  * **UNDETERMINED moves nothing.** It is `NO DATA`, not a number. A record
    where nobody has answered computes exactly the rate it computed before
    any of this existed, because defaulting it either way would decide a
    200.331 question by omission — and the contractor answer is the one that
    gets applied by accident, since MTDC takes an unflagged payment whole.
  * **A SUBRECIPIENT moves MTDC by exactly the payment less the cap.** Not
    approximately, and not by the whole payment: 200.1 takes the first
    $25,000 either way.
  * **The cap is defined once**, in the engine that applies it. Two spellings
    of $25,000 is how a handler and a model come to disagree about where the
    line is.
  * **A determination says who and why, or it says nothing.** Half a
    determination is the shape that reads as an answer and is not one, and
    the schema holds it whatever the handler does.
  * **The worklist carries `at_stake`, not the payment.** The first $25,000
    is in the base under either answer, so it is not in question.

Driven against a database inside a transaction that is rolled back, and the
rows are made here rather than selected: CI runs against an empty database,
and *a test that reads whatever happens to be in the database passes for a
developer and fails in CI*.
"""

from __future__ import annotations

import ast
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


@pytest.fixture()
def cur():
    import psycopg
    import psycopg.rows
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        with con.cursor(row_factory=psycopg.rows.dict_row) as c:
            yield c
        con.rollback()


def _party(cur, amount="102000.00", determination="UNDETERMINED", **over):
    """One party on a federal objective, over the cap."""
    tag = uuid.uuid4().hex[:8]
    cur.execute("""INSERT INTO fiscal_period (period, start_date, end_date)
                   VALUES ('2025', '2025-01-01', '2025-12-31')
                   ON CONFLICT DO NOTHING""")
    obj = f"OBJ-{tag}"
    cur.execute("""INSERT INTO cost_objective
                     (objective_id, period, label, objective_type, is_federal)
                   VALUES (%s, '2025', %s, 'PROGRAM', true)""",
                (obj, f"Objective {tag}"))
    body = dict(period="2025", objective_id=obj, payee=f"Party {tag}",
                amount=amount, determination=determination,
                basis="", agreement_ref="", decided_by="", decided_at=None)
    body.update(over)
    cols = ", ".join(body)
    marks = ", ".join(["%s"] * len(body))
    cur.execute(f"INSERT INTO party_determination ({cols}) VALUES ({marks})",
                tuple(body.values()))
    return obj, body["payee"]


# ── what the register says ────────────────────────────────────────────────

def test_undetermined_is_no_data_and_never_a_number(cur):
    """`in_mtdc` is NULL, not the payment and not zero.

    Both wrong answers are available and each is a different lie: zero says
    none of it reaches the base, the payment says all of it does, and the
    truth is that nobody has answered.
    """
    obj, payee = _party(cur)
    cur.execute("""SELECT in_mtdc, at_stake, state, needs
                     FROM v_subaward_exposure
                    WHERE objective_id = %s AND payee = %s""", (obj, payee))
    r = cur.fetchone()
    assert r["in_mtdc"] is None
    assert r["state"] == "NO DATA"
    assert r["needs"], "NO DATA with nothing saying what it wants is a dead end"
    assert Decimal(str(r["at_stake"])) == Decimal("77000.00")


def test_a_subrecipient_reaches_mtdc_only_to_the_cap(cur):
    obj, payee = _party(cur, determination="SUBRECIPIENT",
                        basis="x" * 60, decided_by="Somebody",
                        decided_at="2026-01-01")
    cur.execute("SELECT in_mtdc, state FROM v_subaward_exposure "
                "WHERE objective_id = %s AND payee = %s", (obj, payee))
    r = cur.fetchone()
    assert Decimal(str(r["in_mtdc"])) == Decimal("25000")
    assert r["state"] == "TIES"


def test_a_contractor_reaches_mtdc_whole(cur):
    obj, payee = _party(cur, determination="CONTRACTOR",
                        basis="y" * 60, decided_by="Somebody",
                        decided_at="2026-01-01")
    cur.execute("SELECT in_mtdc FROM v_subaward_exposure "
                "WHERE objective_id = %s AND payee = %s", (obj, payee))
    assert Decimal(str(cur.fetchone()["in_mtdc"])) == Decimal("102000.00")


def test_half_a_determination_is_refused(cur):
    """An answer with no name, and a name with no reasoning, are both refused.

    The shape that reads as an answer and is not one. The handler says so in
    a sentence and the CHECK is what holds when a handler is wrong — which is
    exactly the split `acceptance_names_its_modification` settled in `061`.
    """
    import psycopg
    for over, why in [
        (dict(determination="CONTRACTOR", basis="z" * 60), "no name"),
        (dict(determination="CONTRACTOR", decided_by="Somebody",
              decided_at="2026-01-01", basis="too short"), "a basis under 40"),
        (dict(determination="UNDETERMINED", decided_by="Somebody",
              decided_at="2026-01-01"), "withdrawn and still named"),
    ]:
        cur.execute("SAVEPOINT s")
        with pytest.raises(psycopg.errors.CheckViolation):
            _party(cur, **over)
        cur.execute("ROLLBACK TO SAVEPOINT s")


# ── what reaches the worklist ─────────────────────────────────────────────

def test_the_worklist_carries_what_is_at_stake_and_not_the_payment(cur):
    """$25,000 is in the base under either answer, so it is not in question.

    A row carrying the gross would say half as much again is open as
    actually is.
    """
    obj, payee = _party(cur)
    cur.execute("""SELECT amount, owner_portfolio, goes_to, severity
                     FROM v_worklist_owned
                    WHERE kind = 'PARTY_UNDETERMINED' AND entity_id = %s""",
                (f"{obj}|{payee}",))
    r = cur.fetchone()
    assert r is not None, "an undetermined party reaches nobody's list"
    assert Decimal(str(r["amount"])) == Decimal("77000.00")
    # CONTROLLER, because 200.331 turns on the substance of a contractual
    # relationship and there is no narrower portfolio whose own area that is.
    assert r["owner_portfolio"] == "CONTROLLER"
    assert r["goes_to"] == "/classify/parties"


def test_a_determined_party_leaves_the_worklist(cur):
    """The list is what is outstanding. A control nobody can clear by doing
    the work is the defect `FACILITY_UNPARTITIONED` is named after."""
    obj, payee = _party(cur, determination="CONTRACTOR", basis="q" * 60,
                        decided_by="Somebody", decided_at="2026-01-01")
    cur.execute("SELECT 1 FROM v_worklist_owned WHERE kind = 'PARTY_UNDETERMINED'"
                " AND entity_id = %s", (f"{obj}|{payee}",))
    assert cur.fetchone() is None


# ── and what it does to the base ──────────────────────────────────────────

def test_the_engine_reads_the_register_and_undetermined_moves_nothing():
    """The wiring, asserted on the source rather than on a whole computation.

    `ObjectiveCost.subaward_excess` has been on the domain model since it was
    written and **nothing wrote it** — the fourteenth instance of the
    dead-register shape and the softest, because the table has a writer and
    only its answer reached no figure. What must stay true is that the query
    feeding it selects SUBRECIPIENT and nothing else: a filter that took
    every row would apply the cap to a determination nobody has made.
    """
    src = (ROOT / "app" / "routers" / "rates.py").read_text()
    body = src[src.index("def _build_model"):src.index("@router.post(\"/compute\")")]
    q = body[body.index("FROM party_determination"):]
    q = q[:q.index('"""')]
    assert "determination = 'SUBRECIPIENT'" in q, (
        "the engine must read only determinations somebody made")
    assert "UNDETERMINED" not in q


def test_the_cap_is_defined_once():
    """Two spellings of $25,000 is how a handler and a model come to disagree
    about where 200.1 draws the line."""
    from app.domain.pools import SUBAWARD_CAP
    from app.routers.classify import SUBAWARD_CAP as handler_cap
    assert SUBAWARD_CAP == Decimal("25000")
    assert handler_cap is SUBAWARD_CAP
    # And nowhere else spells it. `burdened_buildup.py` is the exception it
    # has always been: a standalone instrument that predates the register and
    # reads no database.
    spelt = []
    for p in list((ROOT / "app").rglob("*.py")):
        if p.name == "pools.py":
            continue
        t = re.sub(r"#.*", "", p.read_text())
        if re.search(r'Decimal\(\s*["\']25000', t) or re.search(r"\b25_000\b", t):
            spelt.append(p.relative_to(ROOT).as_posix())
    assert not spelt, f"a second spelling of the 200.1 cap: {spelt}"


# ── and the screen ────────────────────────────────────────────────────────

def test_the_screen_computes_nothing():
    """`in_mtdc` and `at_stake` are read from `v_subaward_exposure`, which is
    where the cap is applied. A screen that subtracted 25,000 itself would be
    a second implementation of 200.1, free to disagree with the engine that
    allocates the rate — which is the rule every review screen already keeps.
    """
    src = (ROOT / "web" / "src" / "pages" / "Parties.jsx").read_text()
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    assert "25000" not in src.replace("$25,000", ""), (
        "the cap is a figure the server supplies, not one the screen knows")
    for arith in (r"\.amount\s*-", r"-\s*Number\(", r"at_stake\s*="):
        assert not re.search(arith, src), f"the screen is computing: {arith}"


def test_the_screen_reads_the_portfolio_and_not_the_rank():
    """CONTROLLER is the name of a portfolio *and* of a rank, and reading the
    rank is the defect `Facilities.jsx` shipped — it hid the write forms from
    exactly the person holding the portfolio and nothing else."""
    src = (ROOT / "web" / "src" / "pages" / "Parties.jsx").read_text()
    assert 'actor?.portfolios' in src
    assert 'actor?.role' not in src and 'actor.role' not in src


def test_the_screen_goes_through_the_request_layer():
    """There is one door. `test_no_screen_reaches_past_the_request_layer`
    holds it for the SPA; this is the same question asked of the new page."""
    src = (ROOT / "web" / "src" / "pages" / "Parties.jsx").read_text()
    assert "fetch(" not in src
    assert "api.parties()" in src and "api.putDetermination(" in src


def test_the_kind_is_described_where_kinds_are_described():
    """A screen that starts speaking SQL is the failure mode, not a broken
    one: every map falls back to the raw database name."""
    src = (ROOT / "web" / "src" / "worklistKinds.js").read_text()
    assert "PARTY_UNDETERMINED" in src
    assert '"/classify/parties"' in src
