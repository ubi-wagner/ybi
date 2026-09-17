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

import inspect
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


# ── One sentence-maker, and the proof that it is one ──────────────────────

def test_no_paper_names_a_person_as_signatory_over_a_drive_s_signature():
    """The property, asserted over what runs rather than over words.

    Five places branched on `cert["certified"]` and composed their own
    sentence — the amendment memorandum and acceptance form, the publication
    README and its console summary, the run sheet and the Form 990
    comparison. This file's own prose claimed *"both papers print it"*, which
    was false of the two papers that go to a sponsor. So when
    `drive_the_close.py` typed a controller's name into the certify route,
    `docs/SETTLEMENT_2025.md` opened on *"certified by Tom Metzinger,
    Controller"* over a rate nobody has signed, and the same words reached
    eight rendered PDFs.

    **The first two versions of this test were source sweeps and both were
    wrong.** The first excused any file that merely *imported*
    `certification_lines` — and the offending file did, two lines above the
    composed sentence, so it passed with the defect restored. The second
    tried to tell *saying* from *asserting* by regex and reported six drives
    that were doing neither. A test that argues with correct code is worse
    than no test, and a test that cannot fail for the thing it names is the
    fifth instance of that shape here.

    So it asserts the behaviour: render every paper against a rehearsal
    signature and check that not one of them prints the signatory's name as
    though a person had signed. That cannot be satisfied by an import.
    """
    from app.domain.amendment_document import render_memo, render_acceptance
    from app.domain.audit_package import certification_lines

    rehearsal = {"certified": True, "certified_by": "A Person",
                 "certified_at": None, "outstanding": [], "rehearsal": True,
                 "why_not": None}
    line = " ".join(certification_lines(rehearsal))
    assert "A Person" not in line

    papers = _rehearsal_papers(line)
    for name, pdf in papers.items():
        text = _pdf_text(pdf)
        assert "A Person" not in text, (
            f"{name} names the signatory over a drive's signature")
        assert "REHEARSAL" in text.upper(), (
            f"{name} does not say the signature is a rehearsal")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    import io
    return "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _rehearsal_papers(line: str) -> dict:
    """Both sponsor-facing papers, rendered against a rehearsal signature.

    Built from the dataclass rather than from a remembered shape — every
    field is read off `AmendmentPapers`, so a field that moves fails here
    rather than silently rendering a paper this test is not about.
    """
    from datetime import date
    from decimal import Decimal as D

    from app.domain.amendment_document import (AmendmentPapers, Movement,
                                               Party, render_acceptance,
                                               render_memo)
    who = Party(name="YBI", address="Youngstown", detail="")
    p = AmendmentPapers(
        period="2025", issued_on=date(2026, 9, 17), remit_to=who, bill_to=who,
        award="AM-TEST", award_title="A test award",
        modification_clause="§4.4", modification_citation="",
        as_billed_basis="DE_MINIMIS_10", proposed_basis="NEGOTIATED",
        rate_kind="INDIRECT_COMBINED", rate=D("0.2471"),
        base_type="MTDC", seal_hash="deadbeef",
        movements=(Movement(covers="2025", objective="TEST", award="AM-TEST",
                            as_billed=D("1000.00"), invoice_count=1,
                            invoice_numbers="1", under_recovered=D("0.00"),
                            over_collected=D("1000.00"), finding="a finding"),),
        position_under=D("0.00"), position_over=D("1000.00"),
        caveats=(), certified=False, certification_line=line,
        status="PROPOSED", modification_ref="", reference="AM-TEST · 2025")
    return {"memorandum": render_memo(p),
            "acceptance form": render_acceptance(p)}


def test_a_rehearsal_signature_never_prints_as_a_signature():
    """A drive's signature is not a signature, in every direction the band
    prints.

    `122` gives the row a value for the kind of act — the fifth time this
    schema has needed one — and the whole value of it is that the sentence
    changes. A band that printed CERTIFIED over `origin = 'REHEARSAL'` would
    be the column existing and answering nothing, which is the dead-register
    shape pointed at a signature.
    """
    from app.domain.audit_package import certification_lines

    real = certification_lines({"certified": True, "certified_by": "A Person",
                                "certified_at": None, "outstanding": [],
                                "rehearsal": False})
    assert real[0].startswith("CERTIFIED —")
    assert "REHEARSAL" not in " ".join(real)

    drive = certification_lines({"certified": True, "certified_by": "A Person",
                                 "certified_at": None, "outstanding": [],
                                 "rehearsal": True})
    assert drive[0].startswith("REHEARSAL — NOT CERTIFIED")
    assert "A Person" not in " ".join(drive), (
        "a rehearsal band must not name a person as the signatory")

    unsigned = certification_lines({"certified": False, "rehearsal": False,
                                    "why_not": "nobody has signed"})
    assert unsigned[0].startswith("NOT CERTIFIED")
    assert certification_lines(None)[0].startswith("NOT CERTIFIED")


def test_the_two_sponsor_papers_ask_the_sentence_maker():
    """And the handler that builds them does not compose its own.

    The test above renders `AmendmentPapers` directly, so it proves the
    *renderer* honours a rehearsal line and proves nothing about who supplied
    that line — it passed with `restate.py` composing `f"Certified by
    {cert['certified_by']}."` again. Third time in this change that a test did
    not touch the thing it names, found the same way as the other two.

    This is the missing half, and it is deliberately narrow: one function,
    named, on the one path whose output goes to NCDMM. A wide source sweep
    was tried twice here and was wrong both times — once too loose to fail,
    once so tight it argued with six correct drives.
    """
    src = inspect.getsource(__import__("app.routers.restate",
                                       fromlist=["_papers"])._papers)
    # Comments out first. The note explaining this very defect quotes the
    # sentence it is about, and matched — which is `test_no_screen_renders_a_
    # worklist_kind_raw` in as many words: assert over what runs, not over
    # the prose beside it.
    code = re.sub(r"#.*", "", src)
    assert "certification_lines(" in src, (
        "_papers must ask certification_lines() for the band; composing the "
        "sentence here is what put a person's name on a memorandum to NCDMM "
        "over a signature a drive made")
    assert not re.search(r'["\']Certified by', code), (
        "_papers is composing its own certification sentence again")
