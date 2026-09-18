"""A helper in the request layer that no screen calls.

`api.js` is the one door to the server — `test_no_screen_reaches_past_the_
request_layer` holds that — so a helper written there and called by nothing
is a capability with its door half-hung: the wiring exists, and the person it
was written for cannot reach it.

It has been found twice by reading, which is the hand-kept map applied to
defects. `subjectNotes` was *"defined and called by nothing, an hour old"*.
Then `putAssetFunding`, which cost more: the asset screen offered only
Propose, and a controller may not dispose of his own recommendation — so the
one person the register was waiting on could propose an answer, be refused
his own acceptance, and read a refusal naming a door (*record the change
directly*) that the screen did not have.

`test_every_capability_has_a_door` asks the same question one level up, of
the routes. This asks it of the helpers, because a route can have a helper
and still have no screen.

The allowlist can only shrink: an entry that gains a caller fails here until
it is removed, and an entry with no real reason fails too.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web/src"

#: Never needs a screen.
NO_CALLER_ON_PURPOSE = {
    "health": "FastAPI's own healthcheck — the deployment reads it, not a person",
}

#: Real gaps, each naming the screen it belongs on. Written down rather than
#: fixed blind, because what each should look like is a design decision and
#: several are somebody else's area.
NO_CALLER_YET = {
    "activity": "effort by objective — /timesheet, beside the roster",
    "attachDocument": "attaching one document to one cost — /evidence",
    "certificationFor": "one person's 200.430(i) state — /timesheet's roster panel",
    "certificationStatus": "the same, as a list — /timesheet",
    "claims": "a project's claims — /projects, where the handoff already lives",
    "documentFacts": "amount, date and vendor off a document's face — /library",
    "evidenceCoverage": "how much of the record is cited — /evidence",
    "evidenceFor": "the documents behind one judgment — /classify's focus card",
    "putEquipmentUse": "lending a machine out — /classify/assets, Equipment tab",
    "putInKind": "space or equipment given to YBI — /classify/assets, In kind tab",
    "resetActorPassword": "the administrator's own act — /people",
    "segments": "split judgments within a group — /classify",
    "setMilestoneState": "delivering a milestone — /contracts",
    "setRecordAccess": "granting somebody the cost record — /people",
    "timesheetCoverage": "contracted against recorded hours — /timesheet",
    "timesheetMonths": "the months behind a person's distribution — /timesheet",
    "withdrawRecommendation": "taking back your own ask — /classify/review",
}


def helpers() -> set[str]:
    api = (ROOT / "api.js").read_text()
    return set(re.findall(r"^  (\w+):\s*(?:\(|async)", api, re.M))


def callers() -> str:
    out = []
    for p in list(ROOT.rglob("*.jsx")) + list(ROOT.rglob("*.js")):
        if p.name == "api.js":
            continue
        out.append(p.read_text())
    return "\n".join(out)


def test_every_request_helper_has_a_screen_that_calls_it():
    src = callers()
    dead = {n for n in helpers() if not re.search(rf"\bapi\.{n}\b", src)}
    unexplained = sorted(dead - set(NO_CALLER_ON_PURPOSE) - set(NO_CALLER_YET))
    assert not unexplained, (
        f"{unexplained} are in api.js and no screen calls them — a capability "
        "whose door is half-hung. Build the screen, or name the gap on the "
        "list in this file.")


def test_the_allowlist_can_only_shrink():
    """An entry that has gained a caller is a permission slip for nothing."""
    src = callers()
    named = set(NO_CALLER_ON_PURPOSE) | set(NO_CALLER_YET)
    live = sorted(n for n in named if re.search(rf"\bapi\.{n}\b", src))
    assert not live, (
        f"{live} now have callers and must come off the list in this file")
    gone = sorted(n for n in named if n not in helpers())
    assert not gone, f"{gone} are no longer helpers at all — drop them"


def test_every_entry_says_something():
    for name, why in {**NO_CALLER_ON_PURPOSE, **NO_CALLER_YET}.items():
        assert len(why) >= 25, f"{name}: an allowlist entry with no reason"
