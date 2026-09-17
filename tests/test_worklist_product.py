"""Every worklist kind belongs to one of the two products, and nothing falls
off the end.

The tabs were split into a year being closed and a company being run, and the
worklist was not — so the controller's audit home opened on 43 uncertified
timesheets and 43 missing employment terms. Two of its six rows were work
behind the other door, and neither was work a controller may do at all:
2 CFR 200.430(i) wants the signature of the person whose effort it was.

**This test keeps no list of the kinds.** `test_worklist_ownership.py` is the
test written about exactly that and its own hand-kept `KINDS` was missing two,
so both sat on the `ELSE` for as long as the list did. Everything here is
derived from the view.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.db import query

# Everything here is derived from the views, which means it needs the views.
# Without a database it failed with a connection error rather than skipping,
# which is a test arguing against working code: a fresh clone has no Postgres
# on the default port and seven reds said nothing about the code. CI sets
# DATABASE_URL against a bare Postgres with the migrations applied, which is
# exactly what these read.
pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

SQL = Path(__file__).resolve().parent.parent / "app" / "sql"
PRODUCTS = {"audit", "fcs"}


def routing() -> dict[str, str]:
    """Every kind the view routes to a product, read out of the view itself."""
    body = query("SELECT pg_get_viewdef('v_worklist_owned', true) AS d")[0]["d"]
    block = body[body.index("END AS goes_to"):body.index("AS owner_product")]
    return dict(re.findall(r"WHEN '([A-Z_]+)'::text THEN '(\w+)'::text", block))


def kinds_in_the_view() -> set[str]:
    """Every kind either worklist view can actually raise."""
    found: set[str] = set()
    for view in ("v_worklist", "v_worklist_extra"):
        body = query("SELECT pg_get_viewdef(%s, true) AS d", (view,))[0]["d"]
        # One pattern, tolerant of the whitespace pg_get_viewdef chooses.
        # There were two and the first was a strict subset of the second —
        # a line that looks like it is doing something and is not.
        found |= set(re.findall(r"'([A-Z][A-Z_]{4,})'::text\s+AS\s+kind", body))
    return found


def test_every_routed_kind_names_a_real_product():
    for kind, product in routing().items():
        assert product in PRODUCTS, f"{kind} routes to {product!r}"


def test_no_kind_falls_on_the_else_by_accident():
    """The `ELSE` is a safety net, not a destination. A kind that reaches it
    is one nobody decided about — which for a product split means outstanding
    work quietly appearing behind whichever door the ELSE happens to name."""
    routed = set(routing())
    raised = kinds_in_the_view()
    assert raised, "no kinds were found in the worklist views at all"
    missing = raised - routed
    assert not missing, (
        f"these kinds are raised and not routed to a product, so they land on "
        f"the ELSE: {sorted(missing)}")


def test_certification_is_not_audit_work():
    """The specific thing that was wrong. A controller cannot sign somebody
    else's effort, so it must not appear on their audit list."""
    r = routing()
    for kind in ("NEEDS_CERTIFICATION", "STALE_CERTIFICATION",
                 "EMPLOYMENT_UNKNOWN"):
        assert r.get(kind) == "fcs", (
            f"{kind} is routed to {r.get(kind)!r}; certification is the "
            f"ongoing system's job and 200.430(i) wants the person whose "
            f"effort it was")


def test_the_rate_blockers_are_audit_work():
    r = routing()
    for kind in ("UNCLASSIFIED", "BLOCKS_SEAL", "NEEDS_EVIDENCE",
                 "SPACE_UNMEASURED", "ASSET_FUNDING_UNKNOWN"):
        assert r.get(kind) == "audit", f"{kind} is routed to {r.get(kind)!r}"


def test_the_handler_filters_and_an_unknown_product_does_not_empty_the_list():
    """Unfiltered is the honest answer to a caller that did not say which
    product it is — `/worklist` has always returned everything, and a script
    reading the whole list would otherwise silently get nothing."""
    src = (Path(__file__).resolve().parent.parent / "app" / "routers"
           / "dashboard.py").read_text()
    body = src[src.index("def my_worklist"):src.index("def my_worklist") + 3000]
    assert 'product in ("audit", "fcs")' in body, (
        "the handler does not check the product against the known set")
    assert "owner_product = %s" in body


# ── the three partitions ─────────────────────────────────────────────

def test_no_partition_reports_ties_over_nothing():
    """`029` in its newest place. An empty building list is not
    zero-equals-zero, it is the absence of the comparison."""
    rows = query("SELECT * FROM v_partition_coverage WHERE period = %s",
                 ("2025",))
    assert len(rows) == 3, f"expected three partitions, got {len(rows)}"
    for r in rows:
        if r["whole"] == 0:
            assert r["state"] == "NO DATA", (
                f"{r['partition']} divides nothing and reports {r['state']}")
        assert r["state"] in {"TIES", "OPEN", "NO DATA"}


def test_every_unfinished_partition_says_what_it_needs():
    """A control that cannot be evaluated has to say what would make it
    evaluable, or it is a dead end on a screen.

    **And a finished one must not.** This asked for a sentence
    unconditionally, so it failed the first time a partition was actually
    completed — with SPACE reading `TIES 100.0%` beside "the square footage
    per building", which is the finished partition asking for the thing it
    already has. A test that cannot pass for the state it is about is the
    mirror of one that cannot fail for the thing it names.
    """
    for r in query("SELECT * FROM v_partition_coverage WHERE period = %s",
                   ("2025",)):
        if r["state"] == "TIES":
            assert r["needs"].strip() == "", (
                f"{r['partition']} ties and still asks for "
                f"{r['needs']!r}")
        else:
            assert len(r["needs"].strip()) >= 20, (
                f"{r['partition']} is {r['state']} and says {r['needs']!r}, "
                f"which is not something anybody can go and do")
        assert r["goes_to"].startswith("/")


def test_space_is_a_row_even_where_no_building_exists():
    """`v_space_unit_control` returns no row at all on a record with no
    facility. Left as a join that would drop the partition off the screen
    entirely — which reads as *measured and fine* rather than *never
    measured*."""
    rows = {r["partition"] for r in
            query("SELECT partition FROM v_partition_coverage WHERE period=%s",
                  ("2025",))}
    assert rows == {"COST", "SPACE", "ASSETS"}



def _without_comments(src: str) -> str:
    """JSX with its comments removed.

    `//`, `/* */` and `{/* */}`. Strings are left alone, which is good enough
    here: what this has to stop is a sentence in a comment deciding what a
    test looks at.
    """
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"(?m)^\s*//.*$", "", src)

def test_no_screen_renders_a_worklist_kind_raw():
    """What a kind means is written down once, in `worklistKinds.js`.

    There were three hand-kept maps of it and every one fell back to the raw
    database name, so the failure was never a broken screen — it was a screen
    that starts speaking SQL. This found a **fourth**: the dashboard rollup on
    Home did not even reach for the map, it lowercased the enum, and the
    controller's audit home read `needs certification` and `employment
    unknown` in a table beside a list that read them properly.

    Anything holding a worklist row goes through `forKind`.
    """
    web = Path(__file__).resolve().parent.parent / "web" / "src"
    offenders: list[str] = []
    for path in sorted(web.rglob("*.jsx")):
        src = path.read_text()
        # Which files handle worklist rows, decided from code rather than from
        # prose. The first version searched the raw text for "worklist", so a
        # *comment* mentioning the worklist made `Facilities.jsx` eligible and
        # the sweep then reported its in-kind table — `in_kind_claim.kind`,
        # nothing to do with this — as a defect. A test that argues against
        # correct code is worse than no test, and it is the same root cause as
        # a test that passes over a defect: asserting over words rather than
        # over what runs.
        #
        # A screen that renders worklist kinds reads the one map. That is the
        # rule this test is about, so that is what decides whether it applies.
        code = _without_comments(src)
        if "worklistKinds" not in code and "forKind" not in code:
            continue
        for n, line in enumerate(src.splitlines(), 1):
            if re.search(r"\.kind\s*\.\s*(replaceAll|toLowerCase|replace)\(", line):
                offenders.append(f"{path.name}:{n}: {line.strip()[:70]}")
    assert not offenders, (
        "these render a worklist kind by reformatting the database name "
        "instead of reading worklistKinds.js:\n  " + "\n  ".join(offenders))
