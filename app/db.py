"""Connection pool and a very small migration runner.

Deliberately no ORM. The schema is the design document, the invariants live
in constraints and triggers, and hand-written SQL keeps both visible.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.settings import settings

log = logging.getLogger("ybi.db")
SQL_DIR = Path(__file__).resolve().parent / "sql"
_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10,
                               kwargs={"row_factory": dict_row}, open=True)


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
