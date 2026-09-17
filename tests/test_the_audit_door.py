"""Eight tabs behind the 2025 audit door, and none of them costs reach.

Sixteen tabs reached that door and the controller's screen was two rows of
them — Import beside Reconcile beside Chart beside Classify beside Space
beside Inventory beside Rates beside Review, which is one job dealt out as
eight errands. The eight that remain are the year being closed, in the order
it is closed in.

**A fold is only safe if it removes nav and not capability.** Two rules hold
that, and the second is the one the fold nearly broke:

  * every folded screen still has a route, because this repository's own rule
    is that the nav shows what is *yours to do* and some screens are reached
    by URL with no tab at all;
  * the classification screen reaches **every group in the ledger**. It asked
    for one page of 80 against 757 groups and sent no `offset`, which the
    handler has always taken — so the screen the whole engagement is worked
    from reached 10.6% of it, and the other 677 could only be found by
    guessing a vendor name into the search box. The top of the list carries
    most of the dollars, which is exactly why nobody noticed: coverage climbs
    fast and then stops.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "src" / "App.jsx"
QUEUE = ROOT / "web" / "src" / "pages" / "ClassifyQueue.jsx"

#: The eight, in the order the file is closed in. This list is the agreement
#: and is meant to be read — it is not a map of what the code does, it is the
#: requirement the code is checked against, which is the one case where
#: writing it down twice is the point.
AGREED = ["Audit", "Books", "Classify", "Evidence", "Rate", "Restate",
          "Reports", "Requests"]


def audit_tabs() -> list[tuple[str, str]]:
    src = APP.read_text()
    block = src[src.index("const ALL_TABS"):src.index("function tabsFor")]
    out = []
    for path, label, _sched, _needs, product in re.findall(
            r'\["(/[^"]*)",\s*"([^"]+)",\s*"([^"]*)",\s*([^,]+),\s*"(\w+)"\]',
            block):
        if product in ("audit", "both"):
            out.append((path, label))
    return out


def test_the_audit_door_is_the_eight_we_agreed():
    labels = [label for _, label in audit_tabs()]
    assert labels == AGREED, (
        f"the 2025 audit door offers {labels}, and the agreement is {AGREED}")


def test_every_folded_screen_still_has_a_route():
    """Folding a tab removes nav, never capability.

    `/space`, `/inventory`, `/library`, `/imports`, `/reconcile` and `/review`
    all left the audit nav and all still answer — a bookmark, a link from the
    worklist and the runbook's own addresses still land. A fold that deleted
    the routes would be the nav-stricter-than-the-API defect with the evidence
    removed.
    """
    src = APP.read_text()
    routed = set(re.findall(r'<Route path="([^"]+)"', src))
    for path in ("/space", "/inventory", "/library", "/imports", "/reconcile",
                 "/review", "/rates", "/guidebook", "/help",
                 "/classify/space", "/classify/assets", "/books"):
        assert path in routed, (
            f"{path} has no route. Folding a tab takes it out of the nav; it "
            f"must not take the screen out of the building.")


def test_the_guide_is_reachable_now_it_is_not_a_tab():
    """Guidebook left the nav with the fold and must not leave the building.

    The everybody manual is written for somebody with a timesheet and no
    portfolio. A shelf they cannot see is the capability-with-no-door shape
    one step along, which is the defect the shelf was built to answer.
    """
    src = APP.read_text()
    # Asserted as a *link somebody can click*, not by slicing between two
    # markers: there are two `topbar-actor` blocks in this file and the first
    # draft sliced to the wrong one, failing against a masthead that carries
    # the link perfectly well. A test that argues with correct code is worse
    # than no test.
    assert re.search(r'<Link[^>]*to="/guidebook"', src), (
        "the guide is neither a tab nor a link in the shell, so nothing "
        "reaches it — and the everybody manual is written for the person "
        "with the fewest ways to find things")


def test_the_queue_can_reach_every_group():
    """One page of 80 against 757 groups, and no offset was ever sent."""
    # Asserted on the call, not on the word. The first draft was
    # `"offset" in src`, which the comment above `fetchMore` satisfies
    # perfectly — so it passed with the paging deleted. A test that asserts
    # prose rather than code is one that cannot fail for the thing it names,
    # and this file is the third place that shape has turned up in a day.
    src = re.sub(r"/\*.*?\*/|//[^\n]*|\{/\*.*?\*/\}", "", QUEUE.read_text(),
                 flags=re.S)
    calls = re.findall(r"api\.queue\(\{([^}]*)\}", src)
    assert calls, "the classification screen no longer asks for the queue"
    assert any("offset" in c for c in calls), (
        "no call to api.queue sends an offset, so the screen reaches one page "
        "of 80 against 757 groups and the rest of the ledger cannot be opened "
        "at all")
    # And the count it prints has to come from the coverage row rather than
    # from the length of the list on the screen, which is the wrong number by
    # construction.
    assert "cov.groups_total" in src, (
        "the screen counts its own rows instead of reading the one definition "
        "of how many groups there are")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database")
def test_the_nav_marks_are_the_walk_s_step_numbers():
    """The nav and the walk are one map, or they are two.

    The mark beside each tab used to be the schedule letter the tab prints as
    in the audit package — right when the nav was twenty unordered tabs, wrong
    once the eight *are* the order of operations: they read `· A B E D F G E`,
    with E before D and E twice, which looks like a sequence and is not one.

    So the mark is the step number. It is deliberately **the walk's** number
    and not a fresh 1–8: Books covers steps 1 and 2, Classify 3 to 5, Rate 7
    and 8. A plain 1–8 would put "Rate = 5" in the nav beside a landing page
    saying the rate is step 8 — two numberings of one order, which is the
    defect this repository is mostly about.

    This derives both sides. There is no list of marks in it and no list of
    steps: the nav comes from `ALL_TABS` and the steps from `v_audit_walk`,
    so a step that moves, or a tab that is renumbered by hand, fails here.
    """
    from app.db import query

    steps = query("""SELECT seq, goes_to FROM v_audit_walk
                      WHERE period = %s ORDER BY seq""", ("2025",))
    if not steps:
        pytest.skip("no period loaded")

    tabs = audit_tabs()          # [(path, label)] in nav order
    marks = dict(re.findall(
        r'\["(/[^"]*)",\s*"[^"]+",\s*"([^"]*)"', APP.read_text()))

    # Which tab does a step's destination land on? The longest tab path that
    # the destination starts with — `/classify/space` belongs to `/classify`,
    # and `/` would otherwise swallow everything.
    paths = sorted((p for p, _ in tabs), key=len, reverse=True)

    def owner(dest: str) -> str | None:
        for p in paths:
            if p != "/" and (dest == p or dest.startswith(p.rstrip("/") + "/")):
                return p
        return None

    covers: dict[str, set[int]] = {}
    for s in steps:
        p = owner(s["goes_to"])
        assert p, (
            f"walk step {s['seq']} goes to {s['goes_to']}, which is behind no "
            f"tab on the audit door — a step nobody can reach from the nav")
        covers.setdefault(p, set()).add(s["seq"])

    for path, seqs in sorted(covers.items()):
        mark = marks.get(path, "")
        want = (str(min(seqs)) if len(seqs) == 1
                else f"{min(seqs)}–{max(seqs)}")
        assert mark == want, (
            f"the {path} tab is marked {mark!r}; it covers walk step(s) "
            f"{sorted(seqs)}, so the mark is {want!r}. The nav and the walk "
            f"have to be one map or they are two.")

    # And a tab covering no step carries no number rather than a wrong one.
    # Audit *is* the walk; Requests runs alongside the sequence, not inside it.
    for path, _label in tabs:
        if path not in covers:
            assert not marks.get(path, "").strip("· "), (
                f"the {path} tab carries the number {marks[path]!r} and is "
                f"not a step of the walk")
