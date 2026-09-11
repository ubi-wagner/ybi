"""Every kind the worklist emits reads as a sentence on every screen.

There were three maps of this — Worklist.jsx, Dashboard.jsx and Home.jsx —
each kept by hand and each missing different kinds. All three fall back to the
raw database name, so the failure mode is not a broken screen but a screen
that starts speaking SQL: the controller is shown `DONATION_RATE_MISSING` and
has to work out what it means and where to go.

Two kinds were in none of the three, which is the same list that let them go
unrouted in `v_worklist_owned` as well. The map is one file now and this test
derives the kinds from the migrations rather than keeping a fourth copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
KINDS_JS = (ROOT / "web" / "src" / "worklistKinds.js").read_text()

from test_worklist_ownership import KINDS  # derived from the views  # noqa: E402


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_a_sentence(kind):
    assert f"  {kind}: {{" in KINDS_JS, (
        f"{kind} has no entry in worklistKinds.js, so every screen shows the "
        f"database's name for it and no destination.")


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_says_where_it_is_resolved(kind):
    """`to: null` is allowed only where there is genuinely nowhere yet."""
    entry = KINDS_JS[KINDS_JS.index(f"  {kind}: {{"):]
    entry = entry[:entry.index("\n  },")]
    for field in ("title", "plural", "short", "why", "where", "to"):
        assert f"{field}:" in entry, f"{kind} has no {field}"
    assert 'to: "/' in entry, (
        f"{kind} points nowhere. Every kind the views emit is resolved on "
        f"some screen; if it truly is not, that is a gap to close rather "
        f"than a label to write.")


def test_no_screen_keeps_its_own_map():
    """The defect was three copies, not any one of them being wrong."""
    for page in ("Worklist.jsx", "Dashboard.jsx", "Home.jsx"):
        src = (ROOT / "web" / "src" / "pages" / page).read_text()
        assert "worklistKinds.js" in src, f"{page} does not read the one map"
        assert not re.search(r"^const KIND(_LABEL)? = \{", src, re.M), (
            f"{page} has grown its own map of the worklist kinds again. "
            f"Three copies is how two kinds came to be missing from all of "
            f"them at once.")


def test_nothing_reads_the_table_nothing_ever_wrote():
    """`space_partition` is dropped in 051.

    It held no row in its entire life. `v_facility_occupancy` read it until
    `048`, so the 200.465 carve-out could not fire however much space
    anybody entered, and the worklist read it until `051`, so a BLOCKING
    item fired on a building that was fully accounted for and doing the work
    could not clear it.
    """
    live: dict[str, str] = {}
    for path in sorted(SQL.glob("*.sql")):
        body = re.sub(r"--[^\n]*", "", path.read_text())
        for statement in body.split(";"):
            named = re.search(r"CREATE (?:OR REPLACE )?VIEW\s+(\w+)", statement, re.I)
            if named:
                live[named.group(1)] = statement
    offenders = [name for name, body in sorted(live.items())
                 if "space_partition" in body]
    assert not offenders, (
        "these still read space_partition, which 051 drops and nothing ever "
        "wrote: " + ", ".join(offenders))
