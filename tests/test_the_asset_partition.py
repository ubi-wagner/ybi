"""The asset partition counts dollars, and says what it needs.

`v_partition_coverage` built the ASSETS row as `gross_cost - funding_unknown`
— **dollars minus a count**. It never showed, because `asset` had been empty
for the life of the system and `0 - 0` is 0: `029`'s lesson once more, an
empty register making a wrong expression look right.

Load the 263-asset schedule YBI has had all along and it reads *$23,419,310.64
of $23,419,573.64 covered — 100.0%*, on the partition screen and on the walk,
when the true answer is nought. A screen that reports the largest open
question in the file as finished is worse than one that says nothing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "app" / "sql" / "085_the_asset_partition_counts_dollars.sql"
LOADER = ROOT / "scripts" / "load_assets.py"


def body() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text())


def test_covered_is_dollars():
    b = body()
    assert "funded_cost" in b, "v_asset_control no longer says what is answered"
    assert not re.search(r"gross_cost\s*-\s*\w*funding_unknown", b), (
        "the partition still subtracts a count of assets from a sum of money")


def test_open_says_what_it_needs():
    """`needs` was set only where the register is absent, so the moment it
    landed the partition printed OPEN with an empty reason — *cannot be
    classified with no reason is a dead end*, in a new place. There are two
    asks and they lead to different work."""
    b = body()
    assert "the asset register, with a funding source per asset" in b
    assert "the funding source per asset" in b


def test_the_loader_leaves_the_funding_column_blank():
    """The schedule does not carry one; that absence is 200.313(d)(1)
    unanswered and is the column Heidi fills in. A loader that wrote 0.00
    would turn *nobody has looked* into *there is no federal money in this*,
    which the intake keeps apart all the way down."""
    src = LOADER.read_text()
    assert "INSERT INTO asset_funding" not in src, (
        "the loader invents funding the schedule does not carry")
    assert "200.313(d)(1)" in src


def test_the_loader_checks_what_it_wrote_against_what_it_read():
    """The printed subtotals tie at *parse* time, so they cannot see a key
    collision — the parser holds both rows and only the database collapses
    them. This is the control that can, and it caught system number 165 being
    two assets in two accounts: 262 rows loaded from 263, $35,414.95 of cost
    gone, every subtotal still tying."""
    src = LOADER.read_text()
    assert "parsed_cost" in src and "collided on its key" in src


def test_the_asset_key_is_the_whole_natural_key():
    """The depreciation software numbers assets *within* a GL account."""
    schedule = (ROOT / "app" / "domain" / "asset_schedule.py").read_text()
    assert 'f"FA-{self.gl_account}-{self.system_no}"' in schedule, (
        "the asset id is the system number alone, which is not unique across "
        "accounts — 71 lines worth $24,082.67 in a new register")


@pytest.fixture
def cur():
    from app.db import conn

    with conn() as c:
        with c.transaction(force_rollback=True):
            with c.cursor() as cursor:
                yield cursor


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_a_register_nobody_has_answered_reports_nought_covered(cur):
    """The assertion that actually discriminates, and the first version did
    not have it.

    Watched: putting the defect back into the live view reproduced
    *$23,419,311.64 of $23,419,573.64 — 100.0%* and the test still passed,
    because one asset had been funded by then and the end-anchors only bite
    at nought and at all. A count subtracted from dollars is invisible in the
    middle; it is only visible at the end it was hiding behind, so the test
    has to make that end itself.

    So it clears the funding inside a transaction it rolls back, which is the
    state the register is actually in — 263 assets and nobody has looked.
    """
    cur.execute("SELECT count(*) AS n FROM asset")
    if cur.fetchone()["n"] == 0:
        pytest.skip("no asset register loaded; scripts/load_assets.py fills it")

    cur.execute("DELETE FROM asset_funding")
    cur.execute("""SELECT covered, whole, parts, parts_done, pct
                     FROM v_partition_coverage
                    WHERE partition = 'ASSETS' AND whole > 0""")
    row = cur.fetchone()
    assert row is not None, "the asset partition has gone"
    assert row["parts"] > 0 and row["parts_done"] == 0
    assert row["covered"] == 0, (
        f"nobody has answered any of {row['parts']} assets and the partition "
        f"reports {row['covered']} of {row['whole']} covered ({row['pct']}%) "
        f"— dollars minus a count")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_partition_agrees_with_itself():
    """Covered can never exceed the whole, and where nothing is answered it
    is nought — which is the assertion the count-minus-dollars version failed
    the moment there was anything to count."""
    from app.db import query

    for r in query("SELECT * FROM v_partition_coverage"):
        if r["whole"] is None:
            continue
        assert r["covered"] <= r["whole"], (
            f"{r['partition']}: {r['covered']} covered of {r['whole']}")
        if r["parts_done"] == 0:
            assert r["covered"] == 0, (
                f"{r['partition']} has answered none of its {r['parts']} parts "
                f"and reports {r['covered']} covered")
        if r["state"] == "OPEN":
            assert (r["needs"] or "").strip(), (
                f"{r['partition']} is OPEN and does not say what it needs")
