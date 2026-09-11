"""Connection pool and a very small migration runner.

Deliberately no ORM. The schema is the design document, the invariants live
in constraints and triggers, and hand-written SQL keeps both visible.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from psycopg_pool import ConnectionPool
import psycopg

from app.settings import settings

log = logging.getLogger("ybi.db")
SQL_DIR = Path(__file__).resolve().parent / "sql"
_pool: ConnectionPool | None = None


class Row(dict):
    """A database row that says what it holds when asked for what it does not.

    ``KeyError: 'amount'`` is a true statement and a useless one. It was a 500
    on ``POST /api/classify/decide``: the query selected ``line_id`` and the
    handler summed ``row["amount"]`` off it. The SQL was valid, so nothing
    that reads the schema could have caught it, and nothing that reads the
    source could either — the mistake is only visible where the two meet.

    So the row answers with both halves:

        KeyError: "'amount' is not in this row. The query selected 'line_id'.
                   Either the column is named something else — `python
                   scripts/schema.py <table>` prints what is actually there —
                   or the SELECT list does not reach far enough."

    ``.get()`` is untouched on purpose. Subscripting says *this column is
    there*; ``.get()`` says *it might not be*, and only the first is a claim
    worth checking.
    """

    __slots__ = ()

    def __missing__(self, key):
        held = ", ".join(repr(k) for k in self) or "nothing"
        raise KeyError(
            f"{key!r} is not in this row. The query selected {held}. Either "
            f"the column is named something else — `python scripts/schema.py "
            f"<table>` prints what is actually there — or the SELECT list "
            f"does not reach far enough.")


def row_factory(cursor):
    """``psycopg.rows.dict_row``, returning :class:`Row` instead of ``dict``.

    Same shape and same cost — the column names are read once per result set,
    not once per row. Everything that took a dict still does; ``Row`` is one.
    """
    desc = cursor.description
    if desc is None:
        def no_result(values):
            raise psycopg.ProgrammingError("the cursor doesn't have a result")
        return no_result
    names = [c.name for c in desc]

    def make(values):
        return Row(zip(names, values))

    return make


def open_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10,
                               kwargs={"row_factory": row_factory}, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def conn():
    if _pool is None:
        open_pool()
    with _pool.connection() as c:  # type: ignore[union-attr]
        yield c


def query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def one(sql: str, params: tuple | dict | None = None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | dict | None = None) -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)


MIGRATION_LOCK = 8_142_025          # arbitrary, but stable across deploys


def run_migrations() -> list[str]:
    """Apply app/sql/*.sql in filename order, once each.

    Held under a session advisory lock for the duration. Railway starts the
    new container before it stops the old one, so two processes can reach
    this function against one database within the same second; without the
    lock they race on the same file. The second waits, sees the file already
    in schema_migration, and applies nothing.
    """
    applied: list[str] = []
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migration (
              filename    text PRIMARY KEY,
              applied_at  timestamptz NOT NULL DEFAULT now())
        """)
        cur.execute("SELECT filename FROM schema_migration")
        done = {r["filename"] for r in cur.fetchall()}
        for path in sorted(SQL_DIR.glob("*.sql")):
            if path.name in done:
                continue
            log.info("migrating %s", path.name)
            cur.execute(path.read_text())
            cur.execute("INSERT INTO schema_migration (filename) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


@contextmanager
def transaction():
    """One connection, one transaction, for a multi-statement write.

    ``execute`` and ``query`` each take their own pooled connection and commit
    on exit, which is right for single statements and wrong for anything whose
    invariants are checked at COMMIT. A DEFERRABLE INITIALLY DEFERRED trigger
    fires at the end of the transaction, so a decision and the evidence it
    cites have to be written inside one — otherwise the gate sees an
    unevidenced decision and refuses a judgment that was in fact supported.

        with transaction() as cur:
            cur.execute(...)
            cur.execute(...)
    """
    with conn() as c, c.transaction(), c.cursor() as cur:
        yield cur
