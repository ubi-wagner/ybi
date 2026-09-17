"""The database has what `app/sql` says it has.

`084` declares `subject_merged()`, `enum_or_refuse()`, the current
`recommendation_is_well_formed()` and a `merged` column on
`v_recommendation`. **No running database had any of them.** They were added
to the file after the file had been applied, so the runner — which skips a
migration it has already recorded — never looked at it again, and
`POST /positions/recommendations/{id}/accept` answered 500 with
`KeyError: 'usable_sqft'` on every FACILITY, SPACE_UNIT and ASSET_FUNDING
recommendation, for as long as that mechanism had existed.

Nothing in the suite could see it, and the reason is the point of this file:
**every other database test builds its schema from the same migrations it is
testing.** CI drops a database, applies `app/sql/*.sql`, and passes — the
schema and the files agree because one made the other. The only place the two
can disagree is a database that has been *running*, which is the one nobody
tests against.

So this applies the migrations to a scratch database and compares it with the
one `DATABASE_URL` points at. Three comparisons, chosen because each is
stable across a dump and restore:

* every (table, column), which is what caught `merged`;
* every function's identity and body, which is what caught the other three —
  a function is stored as its own source text, so the comparison is exact;
* every trigger by name.

View *bodies* are deliberately not compared. Postgres re-renders a view when
it is dumped and restored — a `VALUES` list comes back with `AS text` labels
it did not have — so comparing the text reports drift on two views that are
identical. A sweep that cries wolf teaches the reader to dismiss the next
real one.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"

COLUMNS = """SELECT table_name || '.' || column_name
               FROM information_schema.columns
              WHERE table_schema = 'public'"""
FUNCTIONS = """SELECT p.proname || '(' ||
                      pg_get_function_identity_arguments(p.oid) || ')',
                      md5(pg_get_functiondef(p.oid))
                 FROM pg_proc p
                 JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'"""
TRIGGERS = """SELECT c.relname || '.' || t.tgname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND NOT t.tgisinternal"""


@pytest.fixture(scope="module")
def scratch():
    """A database built from `app/sql` alone, dropped afterwards."""
    import psycopg
    from app.settings import settings

    url = settings.database_url
    name = f"ybi_schema_check_{uuid.uuid4().hex[:8]}"
    try:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute(f'CREATE DATABASE "{name}"')
    except psycopg.Error as e:                       # no rights, no check
        pytest.skip(f"cannot create a scratch database: {e}")
    target = url.rsplit("/", 1)[0] + "/" + name
    try:
        with psycopg.connect(target, autocommit=True) as c:
            for path in sorted(SQL.glob("*.sql")):
                c.execute(path.read_text())
        yield target
    finally:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def read(url: str, sql: str) -> set:
    import psycopg
    with psycopg.connect(url) as c, c.cursor() as cur:
        cur.execute(sql)
        return {r if len(r) > 1 else r[0] for r in cur.fetchall()}


@pytest.fixture(scope="module")
def live():
    from app.settings import settings
    return settings.database_url


def test_every_column_the_migrations_declare_is_on_the_database(scratch, live):
    missing = read(scratch, COLUMNS) - read(live, COLUMNS)
    assert not missing, (
        "app/sql declares these and the database does not have them, which "
        "means a migration file was edited after it was applied. Ship the "
        "change as a new migration; editing an applied one mutates nothing. "
        f"Missing: {sorted(missing)}")


#: `schema_migration` is the runner's own bookkeeping — `app/db.py` creates
#: it, no migration does, and a scratch database built by executing the files
#: directly therefore does not have it.
NOT_FROM_A_MIGRATION = {"schema_migration"}


def test_no_column_is_on_the_database_that_the_migrations_do_not_declare(
        scratch, live):
    extra = {c for c in read(live, COLUMNS) - read(scratch, COLUMNS)
             if c.split(".")[0] not in NOT_FROM_A_MIGRATION}
    assert not extra, (
        "the database carries these and no migration creates them, so a "
        "rebuild would not reproduce it. "
        f"Extra: {sorted(extra)}")


def test_every_function_matches_the_migration_that_declares_it(scratch, live):
    want, got = read(scratch, FUNCTIONS), read(live, FUNCTIONS)
    absent = {n for n, _ in want} - {n for n, _ in got}
    assert not absent, (
        "app/sql declares these functions and the database does not have "
        f"them: {sorted(absent)}")
    differs = sorted(n for n, h in want
                     if (n, h) not in got and n in {x for x, _ in got})
    assert not differs, (
        "these functions have a different body on the database from the one "
        "app/sql declares, which is an applied migration that was edited "
        f"afterwards: {differs}")


def test_every_trigger_the_migrations_declare_is_on_the_database(scratch, live):
    missing = read(scratch, TRIGGERS) - read(live, TRIGGERS)
    assert not missing, f"triggers declared and not present: {sorted(missing)}"
