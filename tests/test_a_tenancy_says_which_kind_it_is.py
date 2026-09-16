"""A paid tenancy called programme space names the agreement that says so.

`SPACE_INVENTORY` v1 explained TENANT as *leased to a third party*, which is
literally true of an incubator's own portfolio company paying rent — so all
twenty-six tenancies on Heidi's floor plan came back TENANT and every one of
them left the federal overhead pool under 200.465. Reading the client
companies as programme space instead is worth **2.72 points of combined
rate** with their rent credited under 200.406 and is the largest single
reading still open on the 2025 rate.

So v2 asks the question that actually decides it, and asks for the document.
`space_unit.occupancy_basis` (migration `116`) is that document, and the fence
around it is deliberately narrow: space YBI's own team occupies is PROGRAM
and has no agreement to name. What must name one is the case that moves the
rate — space somebody is **charged rent for** and which is nonetheless called
programme space.

Three properties, each driven against a database inside a transaction that is
rolled back, and each watched failing:

  * **the schema refuses it**, so `PUT /api/facilities/space` cannot write one;
  * **the recommendation validator refuses it too** (`117`), because a
    recommendation the server would refuse is a screen offering what the API
    will not take — which shipped once on twenty-four accounts, and which
    here would tell Heidi her proposal was fine and hand Tom a raw constraint
    violation with her name on it;
  * **the control reports three states**, and a period with no charged space
    is `NO DATA` rather than a pass, which is `029`.

And one property of the second pass itself, held on the source: the workbook
that goes back out carries **every** row of the reply, not only the rows a
person changed.
"""

from __future__ import annotations

import ast
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


def _scaffold(cur) -> str:
    """A building and an objective to hang a paid programme space off.

    Made here rather than selected: CI runs against an empty database, and a
    test that reads whatever happens to be there passes for a developer and
    fails in CI — which `test_reconcile_db.py` paid for.
    """
    cur.execute("SELECT 1 FROM fiscal_period WHERE period = '2025'")
    if not cur.fetchone():
        pytest.skip("this database has no 2025 period")
    cur.execute("""INSERT INTO cost_objective (objective_id, period, label,
                                               objective_type, is_federal)
                   VALUES ('T116-OBJ', '2025', 'Tenancy kind', 'PROGRAM', false)
                   ON CONFLICT DO NOTHING""")
    cur.execute("""INSERT INTO facility (facility_id, period, name, usable_sqft,
                                         source_document, evidence_grade)
                   VALUES ('T116-BLD', '2025', 'Tenancy kind building', 10000,
                           'a test', 'TEST_ASSUMPTION')
                   ON CONFLICT (facility_id) DO NOTHING""")
    return "T116-BLD"


def _somebody(cur) -> str:
    """Any account, read off the record rather than named.

    `recommended_by` is an actor id and a test that wrote a literal would be
    the thing this file is about — a name recalled instead of read.
    """
    cur.execute("SELECT actor_id FROM actor WHERE is_active LIMIT 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("this database has no accounts to recommend as")
    return row["actor_id"]


def _unit(cur, *, use: str, charge, basis: str):
    cur.execute("""INSERT INTO space_unit (unit_id, facility_id, period, label,
                                           usable_sqft, use, status,
                                           objective_id, occupant,
                                           actual_annual_charge,
                                           occupancy_basis)
                   VALUES ('T116-U', 'T116-BLD', '2025', 'suite 1', 500,
                           %s, 'OCCUPIED', %s, 'A client company', %s, %s)""",
                (use, "T116-OBJ" if use == "PROGRAM" else None, charge, basis))


def test_a_paid_programme_space_with_no_agreement_is_refused():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            with pytest.raises(psycopg.errors.CheckViolation) as e:
                _unit(cur, use="PROGRAM", charge="12000.00", basis="")
            assert "unit_paid_program_names_its_agreement" in str(e.value)
        finally:
            con.rollback()


def test_the_same_space_lands_once_it_names_one():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            _unit(cur, use="PROGRAM", charge="12000.00",
                  basis="Residency agreement, 2024-03-01, clause 2")
            cur.execute("SELECT occupancy_basis FROM space_unit "
                        "WHERE unit_id = 'T116-U'")
            assert cur.fetchone()["occupancy_basis"].startswith("Residency")
        finally:
            con.rollback()


def test_space_nobody_is_charged_for_needs_no_agreement():
    """The narrow half. YBI's own team occupying programme space has no
    agreement to name, and a blanket rule would refuse the rows already on
    every record."""
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            _unit(cur, use="PROGRAM", charge=None, basis="")
            cur.execute("SELECT count(*) AS n FROM space_unit "
                        "WHERE unit_id = 'T116-U'")
            assert cur.fetchone()["n"] == 1
        finally:
            con.rollback()


def test_a_letting_needs_no_agreement_either():
    """Only the reading that *moves* the rate is fenced. A tenancy left as
    TENANT takes its occupancy cost out of the federal pool, which is the
    conservative direction, and refusing it would stop somebody recording a
    letting they have not found the lease for."""
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            _unit(cur, use="TENANT", charge="12000.00", basis="")
            cur.execute("SELECT count(*) AS n FROM space_unit "
                        "WHERE unit_id = 'T116-U'")
            assert cur.fetchone()["n"] == 1
        finally:
            con.rollback()


def test_the_recommendation_door_refuses_the_same_thing():
    """`084`'s rule: a recommendation the register would refuse is refused
    when it is written, not at the moment somebody presses Accept."""
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            _unit(cur, use="TENANT", charge="12000.00", basis="")
            who = _somebody(cur)
            proposal = '{"use": "PROGRAM", "objective_id": "T116-OBJ"}'
            with pytest.raises(psycopg.errors.RaiseException) as e:
                cur.execute("""INSERT INTO recommendation
                                 (period, subject, subject_id, proposal,
                                  recommended_by, note)
                               VALUES ('2025', 'SPACE_UNIT', 'T116-U', %s, %s,
                                       'A proposal made by a test, long '
                                       'enough to pass the note check.')""",
                            (proposal, who))
            assert "names the agreement" in str(e.value)
        finally:
            con.rollback()

    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        try:
            _scaffold(cur)
            _unit(cur, use="TENANT", charge="12000.00", basis="")
            cur.execute("""INSERT INTO recommendation
                             (period, subject, subject_id, proposal,
                              recommended_by, note)
                           VALUES ('2025', 'SPACE_UNIT', 'T116-U',
                                   '{"use": "PROGRAM",
                                     "objective_id": "T116-OBJ",
                                     "occupancy_basis":
                                       "Residency agreement, clause 2"}',
                                   %s,
                                   'A proposal made by a test, long enough '
                                   'to pass the note check.')
                           RETURNING rec_id""", (_somebody(cur),))
            assert cur.fetchone()["rec_id"]
        finally:
            con.rollback()


def test_the_control_reports_no_data_over_no_charged_space():
    """`029`. A period nobody has measured has nothing to answer, and
    `0 of 0 named` is green over an empty set."""
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as con, _cur(con) as cur:
        cur.execute("""SELECT period, charged_units, state, needs
                         FROM v_tenancy_basis_check""")
        rows = cur.fetchall()
        assert rows, "the control answers for every period on the record"
        for r in rows:
            if r["charged_units"] == 0:
                assert r["state"] == "NO DATA", r
                assert r["needs"], "NO DATA says why it cannot be evaluated"
            else:
                assert r["state"] in ("TIES", "OPEN"), r


def test_the_second_pass_carries_every_row_of_the_reply():
    """Not only the rows somebody changed.

    `Row.touched` asks whether a person altered a row *relative to what we
    sent*, which is the right question for "did anybody get to this" and the
    wrong one for a second pass: twenty-seven of Heidi's thirty-eight rows
    matched the lease book we pre-filled, so filtering on it dropped two
    thirds of her estate and re-asked her to type it. Held on the source
    because the defect is a filter, and a filter that is not there cannot be
    driven.
    """
    src = (ROOT / "app" / "routers" / "requests.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_space_from_reply")
    body = ast.get_source_segment(src, fn)
    assert body
    stripped = "\n".join(l for l in body.splitlines()
                         if not l.lstrip().startswith("#"))
    assert "r.touched" not in stripped, (
        "_space_from_reply filters on `touched`, which drops every row the "
        "person left exactly as we pre-filled it — two thirds of the estate.")


def test_no_form_can_pre_fill_everything_it_asks_for():
    """Or nothing that comes back is usable, and nobody can tell why.

    `Row.touched` decides whether a row we sent is an answer, and its default
    rule is *did they answer a column we did not pre-fill*. That is a proxy
    for "the ask", and it stops being one the moment a form pre-fills every
    column — which is exactly what a second pass does, so that somebody is
    confirming rather than retyping.

    Measured, by driving it: `SPACE_INVENTORY` v2 came back with forty-two
    rows, **nought usable and forty-two untouched**, and accepting it would
    have written nothing while reporting success. `Form.asks` names the ask
    where the proxy cannot find it, and this is the sweep — over the forms
    themselves, with no list in it — that fails the next form to do it.
    """
    from app.domain.request_forms import FORMS
    for form in FORMS.values():
        prefilled = set(form.prefilled) | {c.key for c in form.columns if c.known}
        outside = [c.key for c in form.columns if c.key not in prefilled]
        assert outside or form.asks, (
            f"{form.name} v{form.version} pre-fills every column it has and "
            f"names no `asks`, so no row it sends can ever come back as an "
            f"answer — every reply reads as untouched and accepting writes "
            f"nothing.")


def test_every_column_a_form_asks_for_is_a_column_it_has():
    """`asks` is a list of keys and a typo in one is silent — it would simply
    never match, which puts the form straight back in the state above."""
    from app.domain.request_forms import FORMS
    for form in FORMS.values():
        keys = {c.key for c in form.columns}
        assert set(form.asks) <= keys, (
            f"{form.name} asks for {sorted(set(form.asks) - keys)}, which it "
            f"does not have.")


def test_no_form_text_carries_markdown():
    """It lands in a spreadsheet cell, and Excel has no idea what `**` means.

    Every string on a `Form` is written into the workbook as plain text — the
    purpose, the consequence, the instructions and every column's `why`. An
    emphasis marker reaches the person as literal asterisks in the middle of
    a sentence, which reads as a mistake and is one. The same string is *also*
    rendered in the SPA as text, so there is no reader that would ever resolve
    it.
    """
    from app.domain.request_forms import FORMS
    bad = []
    for form in FORMS.values():
        texts = {"purpose": form.purpose, "consequence": form.consequence,
                 "for_whom": form.for_whom, "title": form.title}
        for i, line in enumerate(form.instructions):
            texts[f"instruction {i + 1}"] = line
        for c in form.columns:
            texts[f"{c.key}.heading"] = c.heading
            texts[f"{c.key}.why"] = c.why or ""
        for where, text in texts.items():
            if "**" in text or "`" in text:
                bad.append(f"{form.name} {where}")
    assert not bad, ("markdown in text that is written into a spreadsheet "
                     "cell: " + ", ".join(bad))
