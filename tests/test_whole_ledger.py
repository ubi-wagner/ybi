"""Every general-ledger line in exactly one bucket, and the buckets are the book.

`v_classification_coverage` answers *how much of the cost has been judged*, over
the scope `064` narrowed to cost. That is the right denominator for a rate and
the wrong one for the question the controller is actually asked — **have you
been through the whole book?** On the live record those are 4,038 lines and
15,500.

Taking income out of scope was correct and it also took income out of *view*,
which this repository has already recorded costing it the America Makes
billing: thirty-six monthly postings in the Income section for a year, one join
away from every figure computed without them. So the out-of-scope buckets are
shown, and each says why it is out.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "080_the_whole_general_ledger.sql"

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def test_the_buckets_declare_themselves_rather_than_being_read_off_the_data():
    """A bucket at zero is a figure and has to print as one.

    The first draft built the bucket list with `SELECT DISTINCT seq FROM
    buckets`, which is circular: an empty bucket contributes no row, so it is
    absent from the list of buckets, so it is absent from the answer. The live
    record printed three rows and *the queue is empty* was indistinguishable
    from *there is no queue* — `029` reproduced inside the fix written for it.
    """
    body = re.sub(r"--[^\n]*", "", MIGRATION.read_text())
    assert "VALUES" in body, (
        "the buckets are no longer declared independently of what is in them, "
        "so an empty one will vanish from the answer")
    assert "SELECT DISTINCT seq" not in body, (
        "the bucket list is derived from the rows again, which cannot include "
        "a bucket that has no rows")


def test_every_bucket_is_present_even_when_empty():
    from app.db import query

    rows = query("""SELECT seq, bucket, lines FROM v_gl_accounted
                     WHERE period = %s ORDER BY seq""", ("2025",))
    if not rows:
        pytest.skip("no ledger loaded")
    assert [r["seq"] for r in rows] == [1, 2, 3, 4], (
        "a bucket is missing from the answer: " +
        ", ".join(f"{r['seq']}={r['bucket']}" for r in rows))


def test_the_buckets_add_to_the_ledger_they_came_from():
    """A line that falls between two WHERE clauses is one nobody is looking at."""
    from app.db import query

    rows = query("SELECT * FROM v_gl_accounted_check WHERE period = %s",
                 ("2025",))
    if not rows:
        pytest.skip("no ledger loaded")
    r = rows[0]
    if r["state"] == "NO DATA":
        pytest.skip("no ledger loaded for this period")
    assert r["state"] == "TIES", (
        f"the buckets do not add to the ledger: {r['line_difference']} line(s) "
        f"and {r['dollar_difference']} are in none of them")


def test_an_empty_period_is_no_data_and_not_a_pass():
    """An empty set matching an empty set perfectly is what `029` is about."""
    body = re.sub(r"--[^\n]*", "", MIGRATION.read_text())
    assert "'NO DATA'" in body, (
        "v_gl_accounted_check no longer reports NO DATA, so a period with no "
        "ledger compares zero against zero and reads green")


def test_the_out_of_scope_buckets_say_why():
    """"Cannot be classified" with no reason is the dead end this system keeps
    finding, and out-of-scope with no reason is that in a new place."""
    from app.db import query

    rows = query("""SELECT bucket, why FROM v_gl_accounted
                     WHERE period = %s AND NOT in_scope""", ("2025",))
    if not rows:
        pytest.skip("no ledger loaded")
    for r in rows:
        assert len(r["why"] or "") >= 60, (
            f"{r['bucket']} is out of scope and does not say why in enough "
            f"words to act on: {r['why']!r}")
