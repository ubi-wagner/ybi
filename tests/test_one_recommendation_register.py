"""One register for a recommendation, whatever it is about.

`083` built *somebody who may read the cost record proposes a change and the
controller disposes of it* and pointed it at classification. `084` generalises
it to the two partitions the walk reports as NO DATA — no building carries
square footage, no asset carries a funding source — and the shape of that
generalisation is the whole point: **one register with a subject, not three
registers side by side.**

Three beside each other is this repository's most expensive lesson in somebody
else's words (`project_wbs_nodes` beside `project_milestones`, collapsed and
dropped) and in its own (`space_partition` beside `space_unit`; *the cost
objective is the charge code and there is deliberately no second register of
codes*). It would also mean three review lists when the point is that the
controller has one.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "084_one_register_for_a_recommendation.sql"
POSITIONS = ROOT / "app" / "routers" / "positions.py"
FACILITIES = ROOT / "app" / "routers" / "facilities.py"
SQL_DIR = ROOT / "app" / "sql"


def body() -> str:
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


# ------------------------------------------------------------ one register --

def test_there_is_one_recommendation_register():
    """A sibling table per subject is the defect this migration exists to
    avoid, so a migration that creates one fails here."""
    made: dict[str, str] = {}
    dropped: set[str] = set()
    for f in sorted(SQL_DIR.glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", f.read_text())
        for m in re.finditer(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", sql):
            made.setdefault(m.group(1), f.name)
        for m in re.finditer(r"DROP TABLE (?:IF EXISTS )?(\w+)", sql):
            dropped.add(m.group(1))
    # A table that was created and later dropped is history, not a second
    # register: `083` built `reclass_recommendation` and `084` supersedes it,
    # which is this system's own model of change and must not read as the
    # defect it is the fix for.
    standing = [f"{v}: {k}" for k, v in made.items()
                if "recommendation" in k and k != "recommendation"
                and k not in dropped]
    assert not standing, (
        "a second recommendation register — the subject belongs on the row, "
        "not in the table name:\n  " + "\n  ".join(standing))


def test_every_subject_names_one_register_and_one_door():
    b = body()
    assert "CREATE TYPE recommendation_subject" in b
    for subject in ("CLASSIFICATION", "FACILITY", "SPACE_UNIT",
                    "ASSET_FUNDING"):
        assert subject in b, f"{subject} is not a subject"
    fn = _code(POSITIONS, "accept")
    # One door per register: the route that owns it, never an INSERT here.
    for door in ("decide(", "put_facility(", "put_unit(", "put_asset_funding("):
        assert door in fn, f"accepting no longer goes through {door}"
    assert not re.search(r"INSERT INTO (?:decision|facility|space_unit|asset_funding)\b",
                         fn), "accepting writes a register behind its route's back"


def test_the_payload_is_checked_against_the_schema_not_a_copy_of_it():
    """A `jsonb` proposal with no checking would be a register that takes
    anything and fails at the moment somebody presses Accept. Every enum is
    cast to its real type, and the allowed values in a refusal are read out of
    `pg_enum` rather than listed — a hand-kept copy of an enum is the map this
    repository has been wrong about four times in one run."""
    b = body()
    assert "recommendation_is_well_formed" in b
    assert "enum_or_refuse" in b
    assert "pg_enum" in b, (
        "the refusal lists the allowed values from somewhere other than the "
        "database")
    for cast in ("::pool_type", "::space_use", "::occupancy_status",
                 "::funding_kind", "::function_990", "::federal_treatment"):
        assert cast in b, f"{cast} is not checked on the way in"


def test_a_bad_enum_is_a_refusal_and_not_a_fault():
    """`(p->>'use')::space_use` raises `invalid_text_representation`, which the
    API's schema-gate handler does not recognise — so a typo in a space use
    answered 500, telling a person the system broke when they had picked
    something that does not exist."""
    b = body()
    assert "invalid_text_representation" in b, (
        "the enum cast no longer turns a bad value into a readable refusal")


def test_the_proposal_is_validated_as_what_would_be_written():
    """Two mistakes, one cause. Merging naively invented a combination nobody
    proposed — a DIRECT objective carried into a G&A proposal, refused by
    `direct_needs_objective` at the last step. Validating the proposal alone
    refused legitimate partial changes — `status: OCCUPIED` on a space that
    already names its occupant. Both are checking something other than what
    would be written."""
    b = body()
    assert "subject_merged" in b
    assert "subject_merged(NEW.subject, NEW.subject_id, NEW.period, NEW.proposal)" in b, (
        "the validator reads the proposal rather than the merged row")
    fn = _code(POSITIONS, "_merged")
    assert "merged" in fn and "update(" not in fn, (
        "the handler merges again in Python, which is a second opinion about "
        "what a partial proposal means")


def test_the_merge_is_defined_once():
    """A second copy of a merge rule is a second thing to be wrong."""
    src = POSITIONS.read_text()
    assert src.count("subject_merged") <= 1 or "def _merged" in src
    fn = _code(POSITIONS, "_merged")
    assert "objective_id" not in fn, (
        "the handler carries its own copy of the classification objective "
        "rule, which belongs with the merge in the database")


def test_saw_is_null_where_the_row_is_not_on_the_record():
    """For space and assets this is the normal case, not an edge: both
    registers are empty, so a recommendation is usually the first thing
    anybody has said about that row."""
    b = body()
    assert "subject_digest" in b
    assert "is_new" in b, (
        "nothing distinguishes a proposal that would create a row from one "
        "that would change one")


def test_a_recommendation_still_cannot_be_disposed_of_by_its_author():
    b = body()
    assert "recommendation_disposed_by_another" in b
    fn = _code(POSITIONS, "accept")
    # And the handler answers first. Heidi holds CONTROLLER, so her own accept
    # passed the portfolio gate, ran the dispatch, created the building, and
    # only then met the trigger — a refusal that arrived one write too late.
    i = fn.index("raised_by_actor")
    for door in ("decide(", "put_facility(", "put_unit(", "put_asset_funding("):
        assert fn.index(door) > i, (
            f"{door} runs before the check that the disposer is not the "
            f"recommender, so a refused accept writes the row anyway")


def test_the_asset_funding_register_has_a_door():
    """It was written by exactly one thing — the workbook that comes back
    through `/requests` — so the only way to answer 200.313(d)(1) for a single
    asset was a spreadsheet round trip."""
    src = FACILITIES.read_text()
    assert '@router.put("/asset-funding")' in src
    assert '@router.get("/asset-funding")' in src
    fn = _code(FACILITIES, "put_asset_funding")
    assert "require_inventory" not in fn
    tree = ast.parse(src)
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "put_asset_funding")
    assert "require_inventory" in ast.unparse(node.args), (
        "the asset funding door is not gated on the portfolio that owns the "
        "asset register")


def test_one_worklist_kind_not_three():
    """Three kinds with one owner and one destination is three copies of one
    fact. What differs between them is the subject, which is on the row."""
    b = body()
    assert "RECOMMENDATION_OPEN" in b
    assert "RECLASS_RECOMMENDED" not in b, (
        "the classification-only kind survives beside the general one")
    kinds = (ROOT / "web" / "src" / "worklistKinds.js").read_text()
    assert "RECOMMENDATION_OPEN" in kinds
    assert "RECLASS_RECOMMENDED" not in kinds


# --------------------------------------------------------- against a DB -----

@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_walk_speaks_its_own_language():
    """`v_partition_coverage.state` is the control register's vocabulary —
    TIES, OPEN, NO DATA — and the walk's is DONE, OPEN, NO DATA, WAITING. The
    difference had never shown, because with no building on the record the
    partition was NO DATA in every run there has ever been."""
    from app.db import query

    defn = query("SELECT pg_get_viewdef('v_audit_walk', true) AS d")[0]["d"]
    assert "'TIES'" in defn, (
        "the walk no longer maps the register's word onto one of its own, so "
        "the first square footage anybody enters prints a state nothing "
        "renders")
    states = {r["state"] for r in query("SELECT DISTINCT state FROM v_audit_walk")}
    assert states <= {"DONE", "OPEN", "NO DATA", "WAITING"}, (
        f"the walk reports {states - {'DONE', 'OPEN', 'NO DATA', 'WAITING'}}")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_old_registers_are_gone():
    from app.db import query

    left = query("""SELECT tablename FROM pg_tables
                     WHERE tablename IN ('reclass_recommendation',
                                         'classification_note')""")
    assert not left, f"superseded registers still stand: {left}"
