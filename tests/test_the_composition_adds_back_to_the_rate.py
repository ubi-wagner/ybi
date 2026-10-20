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


def test_the_990_function_labels_name_every_value_the_enum_has():
    """The map is complete, and the database is what says so.

    `Form990.jsx` held a private map of three where `function_990` has four,
    which is harmless on that screen — it prints the three columns the return
    prints — and is not harmless anywhere else: `NOT_APPLICABLE` is the
    compensation block, cost lifted *out* of those three, and a screen that
    could not name it would print the enum at a controller. That is
    `worklistKinds.js`'s own lesson, where three hand-kept maps each missed
    different kinds and the failure mode was a screen that starts speaking
    SQL.

    Read from `pg_enum` rather than written down twice — a hand-kept copy of
    an enum is the map this repository has been wrong about four times in
    one run.
    """
    import re
    from app.db import query

    src = (ROOT / "web" / "src" / "functions990.js").read_text()
    want = {r["v"] for r in query(
        "SELECT e.enumlabel AS v FROM pg_enum e JOIN pg_type t "
        " ON t.oid = e.enumtypid WHERE t.typname = 'function_990'")}
    assert want, "the function_990 enum is not in this database"

    for const in ("FUNCTION_990", "FUNCTION_990_SHORT"):
        body = src[src.index(f"export const {const} = {{"):]
        body = body[:body.index("};")]
        named = set(re.findall(r"^\s*([A-Z_]+):", body, re.M))
        assert named == want, (
            f"{const} names {sorted(named)} where function_990 is "
            f"{sorted(want)}. A value the map does not hold prints as the "
            f"enum, which is the screen speaking SQL at the person who has "
            f"to put it in front of a sponsor.")


def test_the_990_label_map_is_the_only_one():
    """One definition, the way `money()` and `worklistKinds.js` are.

    Narrow on purpose: naming the enum as a *value to send* is correct and
    three screens legitimately do it. What must not reappear is a second
    object mapping those values to prose, which is what drifts.
    """
    import re
    pages = (ROOT / "web" / "src")
    offenders = []
    for f in pages.rglob("*.jsx"):
        src = re.sub(r"/\*.*?\*/", "", f.read_text(), flags=re.S)
        if re.search(r"MANAGEMENT_AND_GENERAL:\s*[\"']", src):
            offenders.append(f.name)
    assert not offenders, (
        f"{offenders} carry their own map of what a 990 function is called. "
        f"There were three maps of what a worklist kind means and every one "
        f"was missing different kinds; `functions990.js` is the one here.")


# ----------------------------------------------------------- the exports


def test_every_section_the_server_offers_has_a_button():
    """And every button asks for a section the server knows.

    Both directions, because both have cost this repository something. A
    section with no button is the capability-with-no-door shape, which has
    now appeared six times; a button naming a section the server does not
    have is a screen offering what the API will not take, which shipped once
    on 24 accounts. Neither side keeps a list — the server's is `SECTIONS`
    and the screen's is read out of its own `<Take section="…">` calls.
    """
    import re

    from app.domain.rate_export import SECTIONS

    src = (PAGES / "RateComposition.jsx").read_text()
    src = re.sub(r"\{?/\*.*?\*/\}?", "", src, flags=re.S)
    asked = set(re.findall(r'<Take\s+[^>]*?section="([^"]+)"', src))
    offered = set(SECTIONS)
    assert asked - offered == set(), (
        f"the pane offers {sorted(asked - offered)}, which the export route "
        f"does not know — a 422 behind a link somebody will click")
    assert offered - asked == set(), (
        f"{sorted(offered - asked)} can be exported and nothing on the "
        f"screen says so. A capability with no door is the shape this "
        f"repository has found six times.")


def test_a_per_rate_section_is_never_exported_without_its_rate():
    """`needs` is answered or the route refuses, never defaulted.

    A section of one rate exported without naming which would answer with
    whichever rate came first, which is `_build_model` reading the fringe
    rate off whatever was already on file: a figure chosen by the order of
    the rows rather than by a caller.
    """
    import re

    from app.domain.rate_export import SECTIONS

    src = (PAGES / "RateComposition.jsx").read_text()
    src = re.sub(r"\{?/\*.*?\*/\}?", "", src, flags=re.S)

    def resolve(expr: str) -> str:
        """One hop through a shorthand, and no further.

        The screen declares `const kp = { period, kind: shown.kind }` once
        and passes `kp`, which is better code and invisible to a regex. A
        test that read the literal and reported it missing would be arguing
        with correct code — the defect this repository calls worse than no
        test. Anything that is neither an object nor a resolvable `const`
        fails rather than passing quietly, because a shorthand this cannot
        follow is a property nobody is checking.
        """
        expr = expr.strip()
        if expr.startswith("{"):
            return expr
        name = re.fullmatch(r"\.\.\.?\s*([A-Za-z_$][\w$]*)|([A-Za-z_$][\w$]*)",
                            expr)
        assert name, f"cannot read the params passed to <Take>: {expr!r}"
        ident = name.group(1) or name.group(2)
        decl = re.search(rf"const\s+{re.escape(ident)}\s*=\s*(\{{[^}}]*\}})",
                         src)
        assert decl, (f"<Take params={{{ident}}}> and nothing in the file "
                      f"declares {ident}")
        return decl.group(1)

    for m in re.finditer(r'<Take\s+[^>]*?section="([^"]+)"[^>]*?'
                         r'params=\{(.*?)\}\s*/>', src, re.S):
        section, params = m.group(1), resolve(m.group(2))
        needs = SECTIONS[section].needs
        if needs == "kind":
            assert "kind" in params, (
                f"'{section}' is a section of one rate and the screen asks "
                f"for it without naming the rate: {params.strip()}")
        if needs == "account":
            assert "account" in params and "pool" in params, (
                f"'{section}' is a section of one account and the screen "
                f"asks for it without naming it: {params.strip()}")


def test_every_exported_section_carries_its_own_tie(composition):
    """A file travels further than the screen that said whether it foots.

    This is the whole point of the pane in a negotiation: a sponsor who adds
    the column up and gets a different answer stops reading. So the footing
    line is on the face of every partition exported, in the same words, and a
    `NO DATA` section says what is missing rather than printing a variance
    the width of the whole base.
    """
    from app.domain import rate_export as rx

    checked = 0
    for rate in composition["rates"]:
        for section in ("pool", "carve-outs", "base"):
            sheet = rx.build_sheet(section, comp=composition,
                                   kind=rate["kind"])
            assert sheet.foots, (
                f"{rate['kind']}'s {section} exports with no statement of "
                f"whether it adds back to the rate")
            assert "DOES NOT TIE" not in sheet.foots, (
                f"{rate['kind']}'s {section}: {sheet.foots}")
            checked += 1
    assert checked >= 3, "no section was examined, so this asserted nothing"


def test_a_section_that_cannot_be_drawn_prints_no_column_headings(composition):
    """Headings over nothing say less than the sentence above them.

    The Base sheet of the build-up workbook was corrected for exactly this,
    and a CSV repeats it one format along — where it is worse, because a
    reader pasting the file into a model gets a header row and no data and
    has to work out which of the two happened.
    """
    from app.domain import rate_export as rx
    from app.routers.rates import rate_certification

    empty = [r for r in composition["rates"]
             if (r.get("base") or {}).get("state") == "NO DATA"]
    if not empty:
        pytest.skip("every rate on this record carries a per-objective base, "
                    "so there is no undrawable section to check")
    for rate in empty:
        sheet = rx.build_sheet("base", comp=composition, kind=rate["kind"])
        body = rx.to_csv(sheet, period=PERIOD,
                         certification=rate_certification(PERIOD))
        assert sheet.columns[0] not in body, (
            f"{rate['kind']}'s base exports column headings over no rows")
        assert "Nothing breaks" in body, (
            f"{rate['kind']}'s base exports without saying why it is empty")


def test_a_figure_is_money_only_where_the_column_says_so():
    """Square feet are not dollars.

    `money()` and `count()` are two helpers in the SPA for this reason, and
    the first draft of `_cell` spelled every `Decimal` `{:,.2f}` — so the
    estate printed 54,308 square feet as `54,308.00` beside $850,382.89 in
    the same file.
    """
    from decimal import Decimal as D

    from app.domain.rate_export import _cell

    assert _cell(D("54308.00")) == "54,308"
    assert _cell(D("9326.50")) == "9,326.5"
    assert _cell(D("850382.89"), money=True) == "850,382.89"
    assert _cell(D("1"), rate=True) == "100.0000%"
    assert _cell(None) == "" and _cell(True) == "yes" and _cell(False) == "no"
