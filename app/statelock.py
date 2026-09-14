"""One turn at a time.

The cost record is a state machine and its actions are chain reactions: a
classification moves the pools, the pools feed the rate, the rate feeds the
allocation and the restatement. Two of those running at once over the same
period is not a rare edge — it is Tom and Barb working the queue on a Tuesday
— and the system is fast enough that they will almost never collide, which is
precisely what makes the collision worth guarding. A defect that appears once
a month and cannot be reproduced is one people learn to explain away.

What was actually at risk, before this:

**The seal did not cover what it sealed.** `seal()` ran four separate
statements on four pooled connections: find the open set, hash every live
judgment in it, count them, write the hash. A classification committing
between the hash and the write landed in a set whose `seal_hash` does not
include it — a sealed set that is silently wrong, and the seal is the one
thing the whole engagement rests on. Nothing would ever have shown it: the
hash is only recomputed when somebody unseals.

**A reclassification could lose a judgment.** Two controllers judging the same
group at once both reverse what they found and both insert. One wins the
unique index and the other is refused — correctly, but with a message about
lines and conflicts rather than "Barb judged this ninety seconds ago".

So every action that changes the cost record takes a lock on the period
first, and holds it until its transaction ends. Postgres queues the waiters,
which is the queue — there is no second one to keep alive, nothing to drain
on restart, and it works across processes, which an in-memory queue would not
on a deployment that runs more than one.

It costs nothing when uncontended: an advisory lock nobody else wants is a
hash table insert.
"""

from __future__ import annotations

import logging
import zlib
from contextlib import contextmanager

log = logging.getLogger("ybi.statelock")

#: Namespace for every lock this system takes, so an advisory lock somebody
#: else's extension takes cannot collide with ours. Arbitrary and fixed.
COST_RECORD = 0x59424900          # "YBI\0"


def _key(period: str) -> int:
    """A stable signed 32-bit key for a period.

    crc32 rather than hash(): Python's hash is salted per process, so two
    workers would take different locks for the same period and serialise
    nothing at all.
    """
    return zlib.crc32(period.encode()) - 0x80000000


def serialise(cur, period: str) -> None:
    """Hold the cost record for this period until the transaction ends.

    Must be called inside `transaction()`. `pg_advisory_xact_lock` releases at
    COMMIT or ROLLBACK with no unlock to forget and nothing left held by a
    process that died — which is the whole reason for choosing the
    transaction-scoped form over the session-scoped one.

    Blocking is deliberate. The alternative, `pg_try_advisory_xact_lock`,
    would refuse the second person instead of making them wait, and being
    told "somebody else is classifying, try again" for the two milliseconds
    the first action takes is worse than waiting two milliseconds.
    """
    cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (COST_RECORD, _key(period)))


def held_by_anybody(cur, period: str) -> bool:
    """Is somebody else mid-turn? For diagnostics, never for a decision.

    Reading a lock and then acting on the answer is a race of its own — the
    state can change between the read and the act. Taking the lock is the
    only safe way to depend on it.
    """
    cur.execute("""SELECT count(*) AS n FROM pg_locks
                    WHERE locktype = 'advisory'
                      AND classid = %s AND objid = %s AND granted""",
                (COST_RECORD, _key(period) + 0x80000000))
    return bool(cur.fetchone()["n"])


@contextmanager
def turn(period: str):
    """One turn over the cost record for `period`, as a single transaction.

    Everything inside happens with the period held, and commits or rolls back
    as one act. Reads taken on *other* pooled connections while this is open
    are safe for the same reason the lock exists: no other turn can commit
    while this one holds it, so what they see cannot move underneath.

    Use it wherever `transaction()` was used for a cost-record mutation. The
    only difference is the wait, and the wait is the point.
    """
    from app.db import transaction

    with transaction() as cur:
        serialise(cur, period)
        yield cur
