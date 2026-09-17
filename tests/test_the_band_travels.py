"""Everything that leaves the building says whether the rate was signed.

`082` put the band on a rendered invoice and said why: *a document silent
either way leaves the reader to assume, and the assumption made about a
figure on a letterhead is the generous one.* It then recorded, in as many
words, what had not been done — *the workbook first sheets carry their own
caveats and not yet this one.*

So a controller could hand somebody the rate build-up and the invoice built
on the same rate, at the same moment, and exactly one of them would say
whether anybody had signed it. That is the shape this repository calls 13.0%
and 2.2%, in the place a figure is quoted from.

Two halves, and the second is the one that decays:

  * every builder that produces a document somebody forwards takes the fact
    and prints it — derived from the signatures, not from a list here;
  * the fact is read **once**, from `v_rate_certified`, so a workbook and the
    screen that produced it cannot hold two opinions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = ROOT / "app" / "domain"

#: Builders that produce something a person forwards. Each takes the fact and
#: prints it above its figures.
#:
#: Not a hand-kept list of *files* — it is derived below from the functions
#: that actually call `_caveat`/`_caveats`, which is what "states what is
#: unfinished at the top" means in this codebase. A new workbook that states
#: its caveats and skips the band fails here without anybody adding it.
CAVEAT_HELPERS = ("_caveat", "_caveats")


def builders_that_caveat() -> dict[str, ast.FunctionDef]:
    found = {}
    for path in sorted(DOMAIN.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("build_"):
                continue
            calls = {c.func.id for c in ast.walk(node)
                     if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            if calls & set(CAVEAT_HELPERS):
                found[f"{path.name}::{node.name}"] = node
    return found


def test_every_workbook_that_states_its_caveats_states_the_signature():
    """A caveat about the classification and none about the signature is a
    workbook answering the easier of the two questions a reader has."""
    builders = builders_that_caveat()
    assert builders, (
        "no builder calls _caveat any more — either the helper was renamed or "
        "the workbooks stopped saying what is unfinished, and this test can no "
        "longer see the population it is about.")

    missing = []
    for name, node in builders.items():
        calls = {c.func.id for c in ast.walk(node)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        if "certification_lines" not in calls:
            missing.append(name)
    assert not missing, (
        "these state what is unfinished and say nothing about whether the "
        "rate was signed — so they travel, get quoted, and the reader "
        "assumes:\n  " + "\n  ".join(sorted(missing)))


def test_the_band_prints_in_both_directions():
    """Silent-when-certified is the same defect as silent-when-not.

    The invoice renderer's own comment is the rule: *it prints in both
    directions on purpose.* Asserted on behaviour rather than on the source,
    because the first draft of this checked that the word CERTIFIED appeared
    in the function and `NOT CERTIFIED` satisfied it perfectly.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.domain.audit_package import certification_lines

    signed = certification_lines(
        {"certified": True, "certified_by": "Tom Metzinger",
         "certified_at": None, "outstanding": []})
    assert signed and signed[0].startswith("CERTIFIED"), signed
    assert not any("NOT CERTIFIED" in line for line in signed), (
        "a certified rate must not carry the refusal band: " + str(signed))

    unsigned = certification_lines(
        {"certified": False, "why_not": "A rate stands and nobody has "
                                        "put their name to it."})
    assert unsigned and unsigned[0].startswith("NOT CERTIFIED"), unsigned
    assert any("nobody has put their name" in line for line in unsigned), (
        "the refusal has to carry the server's own reason, or the reader has "
        "to go and ask: " + str(unsigned))

    # And the case that is neither: nothing was read. Printing nothing there
    # is how a document comes to be read generously.
    unknown = certification_lines(None)
    assert unknown and "NOT CERTIFIED" in unknown[0], unknown


def test_the_signature_carries_what_was_unfinished_when_it_was_given():
    """`082`: the certificate records the walk's open steps as they stood.

    A band that says CERTIFIED and drops them turns a signature given over
    three named gaps into one given over nothing.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.domain.audit_package import certification_lines

    lines = certification_lines({
        "certified": True, "certified_by": "Tom Metzinger", "certified_at": None,
        "outstanding": [{"step": "Every square foot accounted for"},
                        {"step": "Every asset's funding source"}]})
    body = " ".join(lines)
    assert "Every square foot accounted for" in body, body
    assert "Every asset's funding source" in body, body


def test_the_fact_is_read_once():
    """Three copies of one predicate is what `087` was for, one week ago.

    Every router that prints a band reads `rate_certification()`; none of them
    carries its own `v_rate_certified` query.
    """
    routers = ROOT / "app" / "routers"
    own = []
    for path in sorted(routers.glob("*.py")):
        src = re.sub(r"#.*", "", path.read_text())
        if "v_rate_certified" not in src:
            continue
        if path.name == "rates.py":
            continue                       # where the one reading lives
        own.append(path.name)
    assert not own, (
        "these read v_rate_certified directly instead of calling "
        "rates.rate_certification(), so the band and the screen can drift:\n  "
        + "\n  ".join(own))


# ── And the amendment papers say where they stand ─────────────────────
#
# `_proposed_band` printed "PROPOSED — NOT A CLAIM · Nothing here is billed
# until NCDMM accepts it in writing" unconditionally — so an acceptance form
# NCDMM had **already signed** came back saying it was not a claim, on the one
# page whose whole job is to record that they said yes. The status could not
# reach the paper at all: `AmendmentPapers` had no field for it.

def test_the_amendment_band_says_where_the_restatement_stands():
    from app.domain.amendment_document import standing_band

    headline, sub = standing_band("PROPOSED")
    assert headline == "PROPOSED — NOT A CLAIM"
    assert "accepts it in writing" in sub

    headline, sub = standing_band("SUBMITTED")
    assert "SUBMITTED" in headline
    assert "accepted in writing" in sub

    headline, sub = standing_band("ACCEPTED", "Modification 001, 22 Jan 2026")
    assert headline == "ACCEPTED BY NCDMM"
    assert "Modification 001, 22 Jan 2026" in sub
    assert "not a claim" not in sub.lower()
    assert "NOT A CLAIM" not in headline


def test_an_accepted_paper_never_calls_itself_a_proposal():
    """The defect, as a property. Every state but PROPOSED must drop the
    sentence that says nothing is billed yet."""
    from app.domain.amendment_document import standing_band

    for status in ("SUBMITTED", "ACCEPTED"):
        headline, _ = standing_band(status, "Modification 001")
        assert "PROPOSED" not in headline, status


def test_an_acceptance_with_no_modification_says_so_rather_than_asserting_one():
    """`acceptance_names_its_modification` refuses this in the schema, so it
    should not be reachable — and a paper that printed a clean acceptance
    anyway would hide the finding rather than show it."""
    from app.domain.amendment_document import standing_band

    _, sub = standing_band("ACCEPTED", "   ")
    assert "without a modification named" in sub
