"""What the rate is made of has to add back to the rate.

`GET /api/review/rate/composition` is the drill-down a negotiation opens
with: the pool by account, every transaction under it, what sized each
carve-out, and the base. It is the one screen in this system whose whole
value is arithmetic a sponsor can check by hand — so a breakdown that does
not add back to the figure on the workpaper is worse than no breakdown. The
screen and the workbook both print whether each partition foots; this is the
check that they can.

**Three states, not two.** `_part` answers `NO DATA` where there is no
breakdown to draw rather than reporting a failed tie, because the
per-objective base is recorded once — against the rate it was computed on —
so asking OVERHEAD for its own objective base would print a five-million
dollar variance over a table that was never meant to exist. A control that
cries wolf teaches the reader to dismiss the next real one, so the state is
asserted rather than only the tie.

And the kind-to-pool map is **derived from the view that already holds it**.
`v_rate_buildup` carries `pool_for_kind` and a second copy of it in Python is
free to drift — INDIRECT_COMBINED is OVERHEAD plus G&A, and `065` records
what one wrong join on that fact cost: the one rate that leaves the building
was the one with nothing behind it.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ROOT / "web" / "src" / "pages"
PERIOD = "2025"


def _balanced(body: str, start: int) -> str:
    """The text inside the parenthesis opening at `start`."""
    depth = 0
    for i in range(start, len(body)):
        if body[i] == "(":
            depth += 1
        elif body[i] == ")":
            depth -= 1
            if depth == 0:
                return body[start + 1:i]
    raise AssertionError("unbalanced parentheses in the view body")


@pytest.fixture()
def composition():
    """The live composition, and the premise every check on it depends on.

    Stated by dependency rather than by a list of which tests need a rate: a
    check that reads the record takes this and one that reads source does
    not. On an empty database there is no rate, so there is nothing for a
    breakdown to add back to — which is a premise the environment cannot
    meet, not a passing test. `prove.sh` covers the other direction.
    """
    from app.routers.review import rate_composition

    comp = rate_composition(PERIOD)
    if not comp.get("rates"):
        pytest.skip("no rate stands on this database, so there is no "
                    "composition to add back to anything. Covered by "
                    "prove.sh against a loaded record.")
    return comp


def test_every_partition_of_every_rate_foots(composition):
    """Each part either ties to the figure the rate carries, or says why not.

    `OPEN` is the failure. `TIES` is the pass. `NO DATA` is neither and is
    allowed — a partition nobody can draw is a different fact — but it has to
    say what is missing, because *"cannot be broken down" on its own is a
    dead end*.
    """
    checked = 0
    for rate in composition["rates"]:
        for name in ("gross", "carved", "base"):
            part = rate.get(name)
            assert part is not None, f"{rate['kind']} has no {name} partition"
            checked += 1
            assert part["state"] in ("TIES", "NO DATA"), (
                f"{rate['kind']}'s {name} does not add back to the rate: "
                f"{part['total']} against {part['recorded']} on file, out by "
                f"{part['variance']}. A breakdown that does not foot is "
                f"worse than no breakdown, in a negotiation most of all.")
            if part["state"] == "NO DATA":
                assert len(part.get("needs") or "") > 25, (
                    f"{rate['kind']}'s {name} cannot be drawn and does not "
                    f"say what is missing. A reader cannot act on that.")
    assert checked >= 3, ("no partition was examined, so this test asserted "
                          "nothing — the shape it exists to catch")


def test_the_transactions_add_back_to_the_pools(composition):
    """Every ledger line in every rate pool, against the pools' own gross.

    This is the detail Tom asked for, and the half most easily wrong is a
    line counted twice: `042`, `044` and `045` are what one missing
    `AND dl.live` cost in three places, one of them a tax return.

    **What watching it fail showed is that the two guards here are
    independently sufficient, so neither mutation alone expresses the
    defect.** Driven against a record carrying a real superseded group — the
    janitorial contract at 22,712.00, reclassified through the API and
    re-sealed — dropping `AND dl.live` ties, dropping
    `d.reversed_at IS NULL` ties, and dropping *both* fails at exactly
    22,712.00. Reclassifying reverses the judgment it replaces, so the
    second predicate already excludes the row the first one does. The belt
    and the braces are both kept — *a rule with an exception is one somebody
    gets wrong the day they change that join* — and this test is honest
    about catching the pair rather than claiming to catch either.
    """
    from app.routers.review import rate_lines

    part = rate_lines(PERIOD)["part"]
    assert part["rows"], "no transaction was read, so nothing was compared"
    assert part["state"] == "TIES", (
        f"the transactions come to {part['total']} against the "
        f"{part['recorded']} the pools hold, out by {part['variance']}. "
        f"A line counted twice is a reclassified line reached through "
        f"both a dead judgment and a live one.")


def test_the_kind_to_pool_map_is_the_view_s_own():
    """Derived from `v_rate_buildup`, never a second copy of it.

    Pure literals in a CTE, so this runs against an empty database: the view
    is in the schema whether or not a rate is.
    """
    from app.db import query
    from app.routers.review import KIND_POOLS

    body = query("SELECT pg_get_viewdef('v_rate_buildup'::regclass, true) "
                 "AS b")[0]["b"]
    at = body.find("pool_for_kind AS ")
    assert at > 0, ("v_rate_buildup no longer carries pool_for_kind, so the "
                    "map in review.py has nothing holding it honest")
    cte = _balanced(body, body.index("(", at))

    theirs: dict[str, set[str]] = {}
    for row in query(f"SELECT kind, pool FROM ({cte}) x"):
        theirs.setdefault(row["kind"], set()).add(row["pool"])
    mine = {k: set(v) for k, v in KIND_POOLS.items()}
    assert mine == theirs, (
        f"review.py's KIND_POOLS and v_rate_buildup's pool_for_kind "
        f"disagree: {mine} against {theirs}. The composition would then "
        f"total a different set of pools from the gross it checks itself "
        f"against, and report a variance that is its own.")


def test_the_screen_prints_the_unit_the_base_was_taken_over():
    """A wage base is people and an MTDC base is objectives.

    The fringe denominator *is* the payroll register — the eleventh control's
    whole point — so printing 43 people under objective headings would say
    the rate was taken over the ledger's wage accounts instead, which is the
    other denominator and 22.45% rather than 21.90%. The count confusion is
    recorded on the run sheet, where `v_labor_effective` read 97.
    """
    src = (PAGES / "RateComposition.jsx").read_text()
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    assert 'base.by === "PERSON"' in src, (
        "the composition screen renders one set of base columns, so a wage "
        "base prints into objective headings with every cell but the amount "
        "blank")
    for word in ("people", "objectives"):
        assert word in src, f"the screen never says {word!r} as a unit"


def test_the_workbook_prints_the_unit_too():
    """The same question one layer out, where the workbook travels."""
    src = (ROOT / "app" / "domain" / "review_workbooks.py").read_text()
    assert 'base.get("by") == "PERSON"' in src, (
        "the Base sheet prints objective headings over whatever the "
        "endpoint gave it, so 43 people read as 43 objectives on a "
        "workbook that leaves the building")
    assert '"people on the payroll register"' in src, (
        "the footing line on the Base sheet counts people as objectives")
