"""The controller's answers coming back in, and the two rules that guard them.

The nineteen items are the ones the record cannot settle on its own. Their
answers are judgments with a person's name on them, so they follow the rules
every other judgment here follows: append-only, a status that claims a
settlement carries words, and nothing is written that the preview did not
warn about.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.domain.request_forms import FORMS, verification_rows
from app.domain.request_intake import _cell
from app.domain.verification_items import ITEMS, STATUS

ROOT = Path(__file__).resolve().parent.parent
FORM = FORMS["VERIFICATION"]


def col(key: str):
    return next(c for c in FORM.columns if c.key == key)


def test_the_form_and_the_sheet_read_one_list():
    """Two copies of one list is the shape that produced 13.0% and 2.2% at
    the same moment. A third — workbook, worksheet, and a form that takes the
    answers back — would have been worse, because it would stop matching the
    day somebody added an item."""
    assert [r["ref"] for r in verification_rows()] == [i.ref for i in ITEMS]
    sheet = (ROOT / "scripts" / "verification_sheet.py").read_text()
    assert "from app.domain.verification_items import" in sheet, (
        "the sheet script has its own copy of the items again")
    assert not re.search(r"^ITEMS\s*[:=]", sheet, re.M), (
        "ITEMS is defined in the sheet script as well as in the domain")


def test_a_choice_is_matched_as_the_column_declares_it():
    """`_cell` normalised every choice to UPPER_SNAKE before comparing, which
    silently assumed choice lists are identifier-shaped.

    True of FULL_TIME and TENANT; false the moment a form offers a sentence.
    Every verification status came back as "is not one of" a list it was
    plainly in.
    """
    status = col("status")
    for choice in STATUS:
        assert _cell(status, choice) == choice
        # Case and stray whitespace are the same answer, and the declared
        # spelling is what lands — two spellings of one status on the record
        # is two answers to a question that has one.
        assert _cell(status, f"  {choice.lower()}  ") == choice


def test_the_identifier_reading_still_works():
    """Somebody typing "part time" into a column offering PART_TIME."""
    people = FORMS["PEOPLE_ROSTER"]
    kind = next(c for c in people.columns if c.key == "status")
    assert _cell(kind, "part time") == "PART_TIME"


def test_a_status_that_claims_a_settlement_carries_words():
    """The DELIVERED-with-no-delivery-date rule. A status somebody picked
    from a dropdown is not a thing that happened."""
    rule = col("answer").substantial_when
    assert rule, "the answer column no longer asks for anything substantial"
    other, triggers, least = rule
    assert other == "status" and least >= 10
    assert set(triggers) == {STATUS[0], STATUS[1]}, (
        "the statuses that assert somebody went and looked are CONFIRMED and "
        "CORRECTED. STILL CHECKING and SOMEBODY ELSE HAS TO ANSWER are "
        "honest with nothing attached — demanding prose for those would "
        "produce 'still checking' twice.")


def test_the_question_columns_go_out_locked():
    """A reference that changes is a row nobody can match back, and the
    question is ours to ask rather than theirs to restate."""
    for key in ("ref", "area", "title", "figure", "found", "asks", "moves"):
        assert col(key).known, f"{key} is not sent pre-filled"
        assert key in FORM.prefilled, f"{key} is not marked as ours"
    for key in ("status", "answer", "answered_by"):
        assert not col(key).known, f"{key} goes out filled in"
        assert key not in FORM.prefilled


def test_the_worked_example_goes_out_answered():
    """It *is* the example: it shows what a settled row looks like rather
    than describing one."""
    first = verification_rows()[0]
    assert first["ref"] == "0"
    assert first.get("status") in STATUS and len(first.get("answer", "")) > 10
    assert sum(1 for r in verification_rows() if r.get("status")) == 1, (
        "more than one item goes out already answered; only the worked "
        "example should")


# ── The schema's half ─────────────────────────────────────────────────

pytestmark_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                   reason="needs a database")


@pytest.fixture
def cur():
    from app.db import conn
    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


def _answer(cur, ref="1.1", status=STATUS[0], answer="Checked and correct."):
    cur.execute("""INSERT INTO verification_answer
                     (period, ref, status, answer, answered_by, accepted_by)
                   VALUES ('2025',%s,%s,%s,'test','test')
                   RETURNING answer_id""", (ref, status, answer))
    return cur.fetchone()["answer_id"]


@pytestmark_db
def test_a_settlement_with_nothing_behind_it_is_refused(cur):
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        _answer(cur, answer="ok")


@pytestmark_db
def test_a_report_of_not_knowing_yet_needs_no_words(cur):
    """STILL CHECKING is a real answer and demanding prose for it would
    produce 'still checking' twice."""
    _answer(cur, status="STILL CHECKING", answer="")


@pytestmark_db
def test_one_live_answer_per_item(cur):
    import psycopg
    _answer(cur, ref="2.3")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _answer(cur, ref="2.3", answer="A second live answer.")


@pytestmark_db
def test_superseding_keeps_both(cur):
    """Several of these are expected to change answer, and the sequence is
    what an auditor is reconstructing."""
    first = _answer(cur, ref="3.1", answer="First reading of it.")
    cur.execute("UPDATE verification_answer SET superseded_at = now() "
                "WHERE answer_id = %s", (first,))
    _answer(cur, ref="3.1", answer="Second reading of it.")
    cur.execute("""SELECT count(*) AS n FROM verification_answer
                    WHERE period = '2025' AND ref = '3.1'""")
    assert cur.fetchone()["n"] == 2
    cur.execute("""SELECT answer, answers FROM v_verification_status
                    WHERE period = '2025' AND ref = '3.1'""")
    row = cur.fetchone()
    assert row["answer"] == "Second reading of it."
    assert row["answers"] == 2, (
        "the view does not say how many times this item has been answered, "
        "and a ref answered three times is one somebody has been round twice")


@pytestmark_db
def test_there_is_no_superseded_by_column(cur):
    """It would have been the fifth instance of the dead-column shape, and it
    made its own invariant unsatisfiable: the successor cannot be inserted
    while the predecessor is live, and the predecessor cannot be superseded
    until the successor exists to be named. `ORDER BY answer_id` already
    carries the sequence."""
    cur.execute("""SELECT count(*) AS n FROM information_schema.columns
                    WHERE table_name = 'verification_answer'
                      AND column_name = 'superseded_by'""")
    assert cur.fetchone()["n"] == 0
