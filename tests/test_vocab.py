"""The Python enums have to say what the database says.

These mirror Postgres enums. A value added to one and not the other is a
class of bug that shows up as a 500 in front of a user — the request model
accepts something the column will refuse, or refuses something it would take.
The test needs a database; it skips without one rather than passing quietly.
"""

from __future__ import annotations

import os

import pytest

from app.vocab import MIRRORS

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database to compare against")


def db_enum(name: str) -> list[str]:
    from app.db import query
    rows = query("""SELECT e.enumlabel AS label
                      FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
                     WHERE t.typname = %s
                     ORDER BY e.enumsortorder""", (name,))
    return [r["label"] for r in rows]


@pytest.mark.parametrize("enum_name,mirror", sorted(MIRRORS.items()))
def test_mirror_matches_database(enum_name, mirror):
    in_db = db_enum(enum_name)
    assert in_db, f"no enum {enum_name} in the database"
    in_python = [m.value for m in mirror]
    assert in_python == in_db, (
        f"{mirror.__name__} and {enum_name} disagree:\n"
        f"  python:   {in_python}\n  database: {in_db}")
