"""The restatement, and the three things it will not do.

`app/routers/restate.py` opens by naming them. Two are held by the schema and
by the handler; the third was held by neither, and this is where it lives now.

    It will not net an over-collection against an under-recovery. They are
    two different conversations: one is money to ask for, the other is money
    to give back, and a single net figure hides both.

`v_restatement` carried `under_recovered - over_collected AS net_movement`
until migration `061`. Nothing read it — because **nothing could**: the five
restate routes have been complete since they were written and there was no
page, no route in `App.jsx` and no call in `api.js`. The point of the whole
system had no door, so the trap in front of it was never sprung.

These are source sweeps and need no database, like `test_review.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
PAGES = ROOT / "web" / "src" / "pages"
ROUTERS = ROOT / "app" / "routers"


def _views() -> dict[str, str]:
    """Every view, last definition winning — a migration is never edited once
    applied, so the superseded text stays on disk."""
    out: dict[str, str] = {}
    for path in sorted(SQL.glob("*.sql")):
        src = path.read_text()
        marks = [(m.start(), m.group(1)) for m in
                 re.finditer(r"CREATE (?:OR REPLACE )?VIEW (\w+) AS", src)]
        for i, (start, name) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
            # Comments explain a choice; they are not the choice.
            out[name] = re.sub(r"--[^\n]*", "", src[start:end])
    return out


#: The two figures, however they are spelled.
UNDER = r"under_recovered|under_recovery|underRecovered"
OVER = r"over_collected|over_collection|overCollected"
#: One subtracted from the other, in SQL or in JavaScript, in either order.
#:
#: The gap in the middle is the part that matters and the first draft did not
#: have it: it allowed only whitespace and brackets, so it matched neither
#: `r.under_recovered - r.over_collected` nor
#: `Number(r.under_recovered) - Number(r.over_collected)` — the two spellings
#: the defect actually appears in. It passed against both, which is the
#: failure mode this repository keeps finding: a test that cannot fail for
#: the thing it names. Verified against both spellings before it was kept.
_GAP = r"[^;\n]{0,40}?"
NETTED = re.compile(
    rf"(?:{UNDER}){_GAP}\s-\s{_GAP}(?:{OVER})"
    rf"|(?:{OVER}){_GAP}\s-\s{_GAP}(?:{UNDER})")


def test_no_view_nets_the_two_conversations():
    """The defect `061` closed, held so it cannot come back.

    A net figure is not a smaller answer, it is a different one: $120,000 to
    ask NCDMM for and $120,000 to give back is not a quiet year.
    """
    offenders = [name for name, body in _views().items() if NETTED.search(body)]
    assert not offenders, (
        f"these subtract an over-collection from an under-recovery: "
        f"{offenders}. They are two conversations — money to ask for and "
        f"money to give back — and one figure hides both. See migration 061.")


def test_no_screen_nets_them_either():
    """A view that refuses to net is no use if a page does the arithmetic on
    the way past. The same rule `test_review.py` holds against a screen that
    starts dividing a pool by a base."""
    offenders = []
    for path in sorted(PAGES.glob("*.jsx")):
        src = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
        src = re.sub(r"//[^\n]*", "", src)
        if NETTED.search(src):
            offenders.append(path.name)
    assert not offenders, (
        f"these net an over-collection against an under-recovery: "
        f"{offenders}. Show them side by side.")


def test_the_restatement_screen_exists_and_is_reachable():
    """The reason `061` was ever found.

    Five complete routes and no way in. A capability with no door is one
    nobody exercises, which is how the trap in front of it survived — and it
    is the same shape as the lane tables that no route could write.
    """
    page = PAGES / "Restate.jsx"
    assert page.exists(), "the restatement has no screen"
    app = (ROOT / "web" / "src" / "App.jsx").read_text()
    assert "/restate" in app, "no route reaches the restatement screen"
    assert "Restate" in app, "the restatement screen is not imported"
    api = (ROOT / "web" / "src" / "api.js").read_text()
    for call in ("restateCandidates", "restatements", "restate:", "restateStatus"):
        assert call.rstrip(":") in api, f"api.js cannot call {call}"


def test_accepting_says_what_is_missing_rather_than_naming_a_constraint():
    """`acceptance_names_its_modification` belongs in the schema — it has to
    hold when a handler is wrong. But its refusal reached the person as the
    constraint's own name:

        The database refused this write: acceptance_names_its_modification.

    in the one place the router's docstring calls *the most likely thing in
    this whole exercise to become a finding*. The handler answers first now,
    and the schema still stands behind it.
    """
    src = (ROUTERS / "restate.py").read_text()
    assert "acceptance_names_its_modification" in src, (
        "the handler no longer mentions the constraint it is fronting, so "
        "nobody reading it will know the schema is still the guarantee")
    said = re.search(r"if \(body\.status == \"ACCEPTED\"(.*?)\n\n", src, re.S)
    assert said, "no handler-side check for the modification reference"
    assert "§4.4" in said.group(1) or "4.4" in said.group(1), (
        "the refusal does not name the clause that makes the modification "
        "necessary, which is the one thing the person needs")
