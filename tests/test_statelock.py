"""One turn at a time, and a list of what a turn is.

Two controllers work the queue. The system is fast enough that they will
almost never collide, which is what makes the collision worth a test: a defect
that appears once a month and cannot be reproduced is one people learn to
explain away.

`scripts/drive_concurrency.py` proves the behaviour against a running service
with genuinely parallel requests. This is the structural half — that a new
handler which changes the cost record cannot be written without taking the
lock, because the way that hole opened the first time was not carelessness.
`seal()` was four ordinary statements, each correct, written before anything
could supersede.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.statelock import COST_RECORD, _key

ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers"

#: The routes that move the cost record: what is classified, what that rolls
#: up to, whether it is frozen, and what is claimed off it. Each one takes the
#: period lock, so two of them over the same period happen in an order rather
#: than at once.
#:
#: A route joins this list by changing something a rate is computed from. A
#: timesheet entry does not — it is an employee's own record, it lands through
#: its own guards, and serialising every timesheet in the organisation behind
#: one lock would make the busiest screen in the system the slowest.
MUST_SERIALISE = {
    ("classify", "decide"),
    ("classify", "segment"),
    ("classify", "reverse_segment"),
    ("rates", "seal"),
    ("rates", "unseal"),
    ("rates", "compute"),
    ("restate", "restate"),
    ("undo", "undo"),
}


def handlers():
    for path in sorted(ROUTERS.glob("*.py")):
        src = path.read_text()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield path.stem, node.name, ast.get_source_segment(src, node) or ""


@pytest.mark.parametrize("module,name", sorted(MUST_SERIALISE))
def test_the_cost_record_is_taken_one_turn_at_a_time(module, name):
    body = next((b for m, n, b in handlers() if m == module and n == name), None)
    assert body is not None, f"{module}.{name} is gone — this list is stale"
    assert re.search(r"\b(turn|serialise)\s*\(", body), (
        f"{module}.{name} changes the cost record without holding the period. "
        f"Two of these running at once is not a rare edge — it is two "
        f"controllers on a Tuesday."
    )


def test_no_cost_record_write_sits_outside_the_turn():
    """A bare `transaction()` in one of these handlers is the shape the seal
    had: a correct statement, on its own connection, outside the lock."""
    for module, name in sorted(MUST_SERIALISE):
        body = next(b for m, n, b in handlers() if m == module and n == name)
        if module == "undo":
            continue    # it locks per entry, inside its own transaction
        assert "with transaction()" not in body, (
            f"{module}.{name} opens a transaction that is not a turn. "
            f"Use `turn(period)`."
        )


def test_the_key_is_stable_across_processes():
    """`hash()` is salted per process, so two workers would take different
    locks for the same period and serialise nothing at all. crc32 is not."""
    assert _key("2025") == 1691261684
    assert _key("2026") == -37237938
    assert _key("2025") != _key("2026")


def test_the_key_fits_a_signed_32_bit_lock():
    """`pg_advisory_xact_lock(int, int)` takes two signed 32-bit integers. A
    key outside that range is not a slow lock, it is an error at the point of
    taking it — which is to say, at the point of a write."""
    for period in ("2024", "2025", "2026", "2099", "FY2025-26", ""):
        assert -2_147_483_648 <= _key(period) <= 2_147_483_647
    assert -2_147_483_648 <= COST_RECORD <= 2_147_483_647


def test_the_lock_is_transaction_scoped():
    """Session-scoped locks have to be released by name, which means there is
    a path that forgets — an exception, a pool connection handed back still
    holding it. The transaction-scoped form releases at COMMIT or ROLLBACK
    and leaves nothing held by a process that died."""
    src = (Path(__file__).resolve().parent.parent / "app" / "statelock.py").read_text()
    assert "pg_advisory_xact_lock" in src
    assert "pg_advisory_lock(" not in src, (
        "a session-scoped advisory lock has to be released by name, and the "
        "path that forgets is the one that matters"
    )


def test_the_seal_is_one_statement_sequence():
    """The defect this whole module exists for.

    `seal()` ran four statements on four pooled connections: find the open
    set, hash every live judgment in it, count them, write the hash. A
    classification committing between the hash and the write landed in a set
    whose seal_hash does not cover it — and nothing would ever have shown it,
    because the hash is only recomputed when somebody unseals.
    """
    src = (ROUTERS / "rates.py").read_text()
    body = next(b for m, n, b in handlers() if m == "rates" and n == "seal")
    assert body.count("with turn(") == 1, "the seal must be one turn"
    # Every statement in it has to be on the turn's own cursor. `one(`,
    # `query(` and `execute(` each borrow a *different* pooled connection,
    # which is the whole defect — so they are matched at a word boundary,
    # where `cur.fetchone()` is not.
    for helper in ("one", "execute", "query"):
        assert not re.search(rf"(?<![.\w]){helper}\(", body), (
            f"seal() calls {helper}() — that is a second connection, and the "
            f"set can move between it and the write. cur.{helper}() is fine; "
            f"the bare module-level helper is not."
        )
    assert "from app.db import one, query" in src, (
        "execute() is gone from this module on purpose; if it is back, "
        "something is writing outside a turn"
    )


def test_a_sealed_set_is_frozen_in_the_schema_too():
    """Handlers are where a rule is convenient; the schema is where it holds
    when a handler is wrong or a new one is written next year."""
    sql = (Path(__file__).resolve().parent.parent / "app" / "sql"
           / "046_the_seal_freezes_the_set.sql").read_text()
    assert "CREATE TRIGGER decision_respects_the_seal" in sql
    assert "BEFORE INSERT OR UPDATE ON decision" in sql
    # It has to catch the reversal as well as the insert: undo reverses a
    # judgment by setting reversed_at, and a judgment reversed underneath a
    # seal breaks the hash exactly as an added one does.
    assert "NEW.reversed_at IS DISTINCT FROM OLD.reversed_at" in sql
