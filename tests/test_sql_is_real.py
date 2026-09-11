"""Every statement the code sends is parsed by the database before it ships.

This test exists because of a defect I made six times in one week, in six
shapes that look different and are not:

    ledger_import.loaded_by            the column is imported_by
    audit_log.actor_name               the column is actor
    award_term.key                     the column is term_key
    decision.period                    the column is scope
    evidence_grade 'RECONSTRUCTED'     the value is MANAGEMENT_RECONSTRUCTION
    pool_type 'DIRECT_PROGRAM'         the value is DIRECT, and it must
                                       carry an objective

Every one is the same mistake: a name recalled rather than read. And every
one is invisible to a test that reads the source, because the source is
syntactically perfect — it is *the database* that disagrees with it, and it
only says so on the line of code that runs.

`PREPARE` is the whole answer. Postgres parses, resolves every relation and
column, and coerces every inline literal to the column's type, without
executing anything. So the schema checks the code rather than the code
asserting things about the schema, which is the rule this repository already
follows everywhere else: **no hand-kept list of what the code does.** There
is no list here to fall out of date — add a query with a misremembered column
and this fails on the next run, naming the column.

What it does not cover, said plainly rather than left to be discovered:

  * A query built by interpolation. Those are checked one level down — every
    relation named in the static parts has to exist — because guessing what
    a `{where}` fragment expands to would be a test arguing with correct
    code, and this repository has been bitten by those.
  * Reading a key off a row the query did not select. `PREPARE` cannot see
    that: the SQL is valid and the *Python* is wrong. `app/db.py` answers
    that one at runtime, in the row itself.

Skipped without a database, like the rest of the database suite. CI applies
the migrations to a bare Postgres, which is exactly the right authority:
the migrations and nothing else.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = Path(__file__).resolve().parent.parent
TREES = ("app", "scripts", "tests")

#: The functions that hand a string to the database. `query` and `one` are
#: `app/db.py`'s helpers and take SQL in the same position as psycopg's own.
SENDERS = {"execute", "executemany", "query", "one"}

#: What PREPARE accepts (Postgres: SELECT, INSERT, UPDATE, DELETE, MERGE,
#: VALUES). Anything else in the source is a utility statement — CREATE, SET,
#: TRUNCATE — and is skipped for a reason that is checked below rather than
#: assumed, so a skip can never quietly swallow a real query.
PREPARABLE = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "VALUES", "WITH"}

#: A floor, so a broken walk cannot pass by finding nothing. It was 632 when
#: this was written; it only ever goes up.
FLOOR = 550


def _sources() -> list[Path]:
    out: list[Path] = []
    for tree in TREES:
        out += sorted((ROOT / tree).rglob("*.py"))
    return out


def _head(sql: str) -> str:
    """The first real keyword, past any leading comment lines."""
    for line in sql.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        return line.split(None, 1)[0].upper().lstrip("(")
    return ""


def _static_parts(node: ast.JoinedStr) -> str:
    """An interpolated query with every `{...}` blanked out.

    Not runnable and not meant to be — it is read only for the names of the
    relations it mentions, which are in the literal halves.
    """
    return " ".join(p.value for p in node.values
                    if isinstance(p, ast.Constant) and isinstance(p.value, str))


def _sql_sites() -> tuple[list, list]:
    """(constant, interpolated) — each entry (path, lineno, text)."""
    constant, interpolated = [], []
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else getattr(func, "id", None))
            if name not in SENDERS:
                continue
            arg = node.args[0]
            where = (path.relative_to(ROOT), node.lineno)
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                constant.append((*where, arg.value))
            elif isinstance(arg, ast.JoinedStr):
                interpolated.append((*where, _static_parts(arg)))
    return constant, interpolated


def _to_dollar(sql: str) -> str:
    """psycopg's `%s` and `%(name)s` into Postgres's own `$1`.

    A repeated named parameter takes the number it was first given, which is
    what psycopg does with it too.
    """
    out: list[str] = []
    seen: dict[str, int] = {}
    n = 0
    i = 0
    while i < len(sql):
        if sql[i] == "%":
            if sql[i + 1:i + 2] == "%":
                out.append("%")
                i += 2
                continue
            if sql[i + 1:i + 2] == "s":
                n += 1
                out.append(f"${n}")
                i += 2
                continue
            named = re.match(r"%\((\w+)\)s", sql[i:])
            if named:
                key = named.group(1)
                if key not in seen:
                    n += 1
                    seen[key] = n
                out.append(f"${seen[key]}")
                i += named.end()
                continue
        out.append(sql[i])
        i += 1
    return "".join(out)


@pytest.fixture(scope="module")
def db():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        yield c


def test_every_literal_statement_parses_against_the_real_schema(db):
    constant, _ = _sql_sites()
    prepared, failures, skipped = 0, [], []
    for i, (path, line, sql) in enumerate(constant):
        if not sql.strip():
            continue
        if _head(sql) not in PREPARABLE:
            skipped.append((path, line, _head(sql)))
            continue
        try:
            with db.cursor() as cur:
                cur.execute(f"PREPARE _sql_is_real_{i} AS {_to_dollar(sql)}")
            prepared += 1
        except Exception as exc:                       # noqa: BLE001
            failures.append(f"{path}:{line}  {str(exc).splitlines()[0]}\n"
                            f"    {' '.join(sql.split())[:160]}")

    assert not failures, (
        "the database refused SQL this code sends:\n\n" + "\n\n".join(failures)
        + "\n\nA name recalled rather than read. `python scripts/schema.py "
          "<table>` prints what is actually there.")
    assert prepared >= FLOOR, (
        f"only {prepared} statements were checked against a floor of {FLOOR}. "
        f"Either a lot of SQL moved out of literals — which is worth knowing, "
        f"because interpolated SQL is checked far more weakly below — or the "
        f"walk over the source has stopped finding call sites.")
    # A skip must be a utility statement PREPARE genuinely refuses, not a
    # query that fell out of the sweep. Checked against Postgres rather than
    # believed: the whole point of this file.
    for path, line, head in skipped:
        assert head in {"CREATE", "SET", "DROP", "ALTER", "TRUNCATE",
                        "COMMENT", "ANALYZE", "VACUUM", "GRANT", "REVOKE",
                        "LISTEN", "NOTIFY", "BEGIN", "COMMIT", "ROLLBACK",
                        "PREPARE", "DEALLOCATE", "REFRESH"}, (
            f"{path}:{line} was skipped for leading keyword {head!r}, which "
            f"is not a utility verb. It is a query that escaped the sweep.")


def test_interpolated_sql_names_relations_that_exist(db):
    """The weaker half, for the queries that assemble a WHERE clause.

    A `{where}` fragment cannot be reconstructed without guessing, and a test
    that guesses at correct code is worse than no test. But the *relation* is
    always in the literal half — `FROM v_document_library`, `UPDATE evidence`
    — and a view renamed in a migration while a router still names the old
    one is exactly the failure this class produces. That much is checkable
    without inventing anything.
    """
    _, interpolated = _sql_sites()
    assert interpolated, "no interpolated SQL found at all; the walk is broken"

    with db.cursor() as cur:
        cur.execute("""SELECT c.relname FROM pg_class c
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public'
                          AND c.relkind IN ('r','v','m','p','f')""")
        real = {r[0] for r in cur.fetchall()}

    pattern = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)\b",
                         re.IGNORECASE)
    # SQL keywords that can follow FROM/JOIN and are not relations.
    noise = {"lateral", "only", "select", "values", "unnest", "generate_series",
             "set", "public"}
    missing = []
    for path, line, static in interpolated:
        for name in pattern.findall(static):
            low = name.lower()
            if low in noise or low in real:
                continue
            missing.append(f"{path}:{line} names {name!r}, which is not a "
                           f"table or view in this database")
    assert not missing, "\n".join(missing)
