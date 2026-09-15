"""A working position is not a judgment.

The 757 live judgments on the 2025 record were written by
`scripts/classification_log.py --apply` in six seconds under the controller's
credentials, and every one of them reads `decided_by = 'Tom Metzinger'`. `083`
gives the schema a word for the kind of act that was, three registers for what
the team does about it, and one rule that decides whether the whole exercise is
honest: **adopting a working position moves no figure**.

Every source assertion here reads code with its comments and docstrings
stripped. Six of my own tests in this repository have passed over the defect
they named because the prose above the code satisfied the match, and the fix
is always the same — assert on what runs.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "083_a_working_position_is_not_a_judgment.sql"
POSITIONS = ROOT / "app" / "routers" / "positions.py"


def body() -> str:
    """The migration with its comments stripped.

    `081`'s test passed with the view renamed because the migration's own
    header names all three views in prose.
    """
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text())


def _code(path: Path, func: str) -> str:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == func:
            b = node.body
            if (b and isinstance(b[0], ast.Expr)
                    and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                b = b[1:]
            return "\n".join(ast.unparse(n) for n in b)
    raise AssertionError(f"{func}() is gone from {path.name}")


# ---------------------------------------------------------------- schema ----

def test_origin_is_a_new_value_and_not_a_rewrite_of_decided_by():
    """`decided_by` says who the API call was made as, and that is true.

    Rewriting it would be inventing a history — the thing `079` refused to do
    to 891 audit rows. What was missing is a value for the *kind* of act, the
    same gap `038` found in `ingest_channel` and `070` in `basis`.
    """
    b = body()
    assert "CREATE TYPE decision_origin" in b
    assert "MACHINE_PROPOSAL" in b
    assert not re.search(r"UPDATE\s+decision\s+SET\s+decided_by", b, re.I), (
        "the migration rewrites decided_by, which is who the call was made "
        "as and is not something a migration gets to change")


def test_the_backfill_reads_the_record_rather_than_asserting():
    """Which rows a script wrote is on the rows: the log stamps its own name
    into every rationale it writes. A migration that instead listed 757 ids,
    or marked everything in the period, would be a hand-kept map of what the
    log did."""
    b = body()
    assert "scripts/classification_log.py" in b, (
        "the backfill no longer reads the marker the log leaves behind")
    assert "origin = 'CONTROLLER'" in b, (
        "the backfill is not guarded on rows still carrying the default, so "
        "a second run could move something somebody set deliberately")


def test_origin_cannot_change_once_recorded():
    """It is outside the seal hash, which is what lets the backfill run under
    a seal — and would equally let a judgment be disowned after the fact
    without superseding it."""
    b = body()
    assert "decision_origin_write_once" in b
    assert "BEFORE UPDATE ON decision" in b


def test_a_confirmation_is_shaped_like_a_certificate():
    """Withdrawable with a reason, one live at a time, and liveness read from
    one view — `082` found two handlers each carrying their own
    `withdrawn_at IS NULL` and disagreeing about which signature was live."""
    b = body()
    assert "CREATE TABLE IF NOT EXISTS position_confirmation" in b
    assert "withdrawal_says_why" in b
    assert "v_position_confirmed" in b
    assert "FROM v_position_confirmed" in b, (
        "the one-live trigger no longer reads the view, so there are two "
        "definitions of live again")


def test_confirming_a_controller_s_own_judgment_is_refused():
    """A CONTROLLER-origin decision already carries a name. A signature on it
    would read as independent review of something nobody reviewed."""
    assert "confirmation_adopts_a_proposal" in body()


def test_a_note_is_never_edited_and_never_deleted():
    b = body()
    assert "note_is_append_only" in b
    assert "note_is_never_deleted" in b
    assert "BEFORE DELETE ON classification_note" in b


def test_changing_what_a_note_discloses_is_a_recorded_act():
    """The visibility setting is the one place this design could go wrong. A
    switch somebody can flip the day after an auditor asks for the file,
    leaving no trace, is worse than having no note at all."""
    b = body()
    assert "redesignated_reason" in b
    assert "redesignation_says_why" in b
    fn = _code(POSITIONS, "redesignate")
    assert "redesignated_at = now()" in fn
    assert "CLASSIFICATION_NOTE_REDESIGNATE" in fn, (
        "re-designating writes no audit row, so the row keeps only the last "
        "change and the history of them is gone")


def test_a_recommendation_is_not_a_decision():
    """`062` refused to express a helper's suggestion as a PROPOSED decision
    row, because PROPOSED already means a sponsor has been asked and has not
    answered. This register exists for the same reason and must not grow a
    path into `decision`."""
    b = body()
    assert "CREATE TABLE IF NOT EXISTS reclass_recommendation" in b
    assert not re.search(r"INSERT\s+INTO\s+decision\b", b, re.I), (
        "the migration writes a decision row, which is the mistake 062 was "
        "written to avoid")


def test_a_recommendation_carries_what_it_was_written_against():
    """`project_claim.saw_*`: an approval has to be of something specific, or
    the record moves underneath it and it silently comes to cover something
    else."""
    assert "saw_decision" in body()
    assert "still_agrees" in body(), (
        "nothing puts the recommendation beside what is there now")


def test_the_recommendation_register_refuses_what_the_queue_would():
    """A screen offering what the server will not take is the
    nav-stricter-than-the-API defect pointing the other way, and this
    repository has shipped it: the crosswalk proposed DIRECT with no
    objective on 24 accounts of the live ledger."""
    b = body()
    assert "recommended_direct_needs_objective" in b
    assert "recommended_unallowable_not_allowable" in b


def test_nobody_disposes_of_their_own_recommendation():
    assert "recommendation_disposed_by_another" in body()


def test_a_recommendation_has_to_propose_a_change():
    assert "recommendation_is_a_change" in body()


# -------------------------------------------------------------- handlers ----

def test_accepting_goes_through_the_one_door():
    """`classify.decide` holds the seal check, the stale-screen check, the
    supersession, the line-level fan-out and the proof that the lines landed.
    A second path to the cost record is a second place all of that can be
    missing — `test_no_screen_reaches_past_the_request_layer` for the SPA,
    `test_storage_paths` for the volume, this for an auditor's ask."""
    fn = _code(POSITIONS, "accept")
    assert "decide(" in fn, "accepting no longer goes through decide()"
    assert not re.search(r"INSERT INTO decision\b", fn), (
        "accepting writes a decision behind the classification route's back")


def test_every_write_takes_the_period_turn():
    """Two controllers can act at the same instant, and every act here
    touches the cost record."""
    src = POSITIONS.read_text()
    tree = ast.parse(src)
    writers = [n.name for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and any(isinstance(d, ast.Call)
                       and getattr(d.func, "attr", "") in ("post", "patch")
                       for d in n.decorator_list)]
    assert writers, "no mutating routes found, which cannot be right"
    for w in writers:
        if w == "accept":
            continue          # it delegates to decide(), which takes the turn
        assert "turn(period)" in _code(POSITIONS, w), (
            f"{w}() writes to the cost record outside a period turn")


def test_a_write_that_landed_on_nothing_is_not_reported_as_success():
    """Five success toasts in this system could report a write that landed on
    nothing. Adopting is the same shape: a batch where every id was already
    adopted has changed nothing at all."""
    fn = _code(POSITIONS, "confirm")
    assert "NOTHING_CONFIRMED" in fn
    assert "confirmed == 0" in fn


def test_the_auditor_may_note_and_recommend():
    """`062` offered its Recommend button only to portfolio holders because a
    worklist item is work to do. This is the opposite case: the auditor
    requiring a new classification out of a sealed account is the exercise.
    """
    src = POSITIONS.read_text()
    tree = ast.parse(src)
    for name in ("write_note", "recommend"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        deps = ast.unparse(fn.args)
        assert "require_reader" in deps, (
            f"{name}() is gated on something narrower than reading the cost "
            f"record, which shuts the auditor out of the one act this is for")
    for name in ("confirm", "accept", "decline"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        assert "require_controller" in ast.unparse(fn.args), (
            f"{name}() no longer takes the controller's portfolio")


def test_a_working_note_is_undisclosed_and_never_concealed():
    """Two halves, and the second is what keeps this honest. The auditor is
    not shown the body; the auditor *is* shown that it exists. Dropping the
    row would make three notes look like one."""
    fn = _code(POSITIONS, "notes")
    assert "withheld" in fn, "the answer no longer says a note was withheld"
    assert "None" in fn and "readable" in fn, (
        "the body is not withheld from a reader who may not see it")
    assert "working_notes" in body(), (
        "v_classification_standing no longer carries the count, which is the "
        "half that makes this disclosure rather than concealment")


# ------------------------------------------------------------ against a DB --

@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_walk_asks_both_halves_of_its_own_question():
    """Step 3 is 'every cost judged'. On a restaged year every dollar carries
    a position and none of it is anybody's judgment, so a step reading
    coverage alone would print DONE over 757 rows nobody has looked at."""
    from app.db import query

    rows = query("SELECT period, state, detail FROM v_audit_walk "
                 "WHERE key = 'CLASSIFY'")
    assert rows, "the walk has no CLASSIFY step"
    defn = query("SELECT pg_get_viewdef('v_audit_walk', true) AS d")[0]["d"]
    assert "unadopted" in defn, (
        "the walk's CLASSIFY step no longer reads whether the positions have "
        "been adopted")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_no_new_worklist_kind_lands_on_the_else():
    """`test_worklist_ownership` holds this generally and kept its own list of
    the kinds, which is how two sat on the ELSE for as long as the list did.
    Both sides derived."""
    from app.db import query

    defn = query("SELECT pg_get_viewdef('v_worklist_owned', true) AS d")[0]["d"]
    for kind in ("POSITION_UNCONFIRMED", "RECLASS_RECOMMENDED"):
        assert defn.count(f"'{kind}'::text") == 3, (
            f"{kind} is not routed in all three of owner, destination and "
            f"product, so it falls onto an ELSE in whichever it is missing")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_a_confirmation_is_outside_what_the_seal_hashes():
    """The property the whole exercise rests on. Checked against the trigger
    that would refuse it rather than against a comment claiming it."""
    from app.db import query

    src = query("SELECT prosrc FROM pg_proc "
                "WHERE proname = 'decision_set_is_frozen'")
    assert src, "the seal trigger is gone"
    guarded = src[0]["prosrc"]
    assert "NEW.origin" not in guarded, (
        "origin is guarded by the seal, so the backfill — and any later "
        "correction of it — is refused inside a sealed set")
