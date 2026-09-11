"""The budget schedules, and the two questions a total has to answer.

`sum(award_budget.federal)` cannot tell apart "these categories do not add up
to the total printed above them" from "this schedule predates the
modification that moved the ceiling". The first is a transcription error or a
defect in the document; the second is the ordinary life of an award. Reading
the four America Makes schedules produced one of each.

These read the loader's own tables of figures — the thing a person would
check against the page — rather than the database, so they run in CI with no
Postgres and fail on a mistyped digit rather than on a missing fixture.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOADER = ROOT / "scripts" / "load_award_budgets.py"
SQL = ROOT / "app" / "sql"


def budgets():
    """The BUDGETS table, executed rather than parsed.

    Importing the module runs its dataclass-free constants and nothing else;
    `main()` is behind `if __name__`. A regex over the source would be a
    second reading of the same thing, which is the shape this codebase keeps
    finding on the wrong end of.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("load_award_budgets", LOADER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BUDGETS


BUDGETS = budgets()
IDS = [b[0] for b in BUDGETS]


def test_all_four_america_makes_schedules_are_transcribed():
    """Three of the four were missing, each for a different reason.

    Hybrid's is an image in the PDF; LTM's is plain text nobody had been to;
    Digital Engineering had no award row at all. "Only Drive AM's schedule is
    transcribed" was true for the whole engagement.
    """
    assert set(IDS) == {"AM-DRIVE-AM", "AM-HYBRID-P2", "AM-LTM-PROJ88",
                        "AM-ICAM-DIGENG"}, IDS


@pytest.mark.parametrize("award", BUDGETS, ids=IDS)
def test_the_transcription_says_whether_it_foots(award):
    """Every printed subtotal must equal what sits under it — the QuickBooks
    rule, applied to an agreement.

    Where it does not, the difference is named rather than smoothed. LTM's
    federal categories add to $899,500.76 against a printed $899,500, and a
    loader that adjusted a category to make the page come out would be
    inventing a budget.
    """
    _, _, note, lines, share, printed, printed_share, _ = award
    total = sum(Decimal(a) for _, a, _ in lines)
    share_total = sum(Decimal(v) for v in share.values())
    foots = total == Decimal(printed) and share_total == Decimal(printed_share)
    if not foots:
        assert "not foot" in note.lower(), (
            f"the categories add to {total} against a printed {printed} and "
            f"the note does not say so. A difference nobody named is a "
            f"difference somebody will later read as a transcription error.")


def test_last_tactical_mile_is_the_one_that_does_not_foot():
    """Named, so that fixing the arithmetic would fail here rather than
    quietly agreeing with a document that does not."""
    ltm = next(b for b in BUDGETS if b[0] == "AM-LTM-PROJ88")
    total = sum(Decimal(a) for _, a, _ in ltm[3])
    assert total - Decimal(ltm[5]) == Decimal("0.76")
    share = sum(Decimal(v) for v in ltm[4].values())
    assert share - Decimal(ltm[6]) == Decimal("0.12")


def test_a_schedule_that_misses_the_ceiling_says_why():
    """A modification moves a ceiling and leaves the schedule where it was.

    Hybrid's schedule is $500,043 and its ceiling $512,409 — the difference
    is Modification 001, and comparing the two without that explanation
    reports a $12,366 failure on a document that is simply older.
    """
    hybrid = next(b for b in BUDGETS if b[0] == "AM-HYBRID-P2")
    assert "Modification 001" in hybrid[7], (
        "Hybrid's schedule differs from its ceiling and nothing on the row "
        "says why")
    assert Decimal(hybrid[5]) == Decimal("500043")


def test_every_schedule_names_the_page_it_came_from():
    """A provision with no citation is somebody's recollection of a
    contract, which is worth nothing in a dispute."""
    for award_id, citation, *_ in BUDGETS:
        assert len(citation) > 20 and ("Schedule" in citation
                                       or "Attachment" in citation), (
            f"{award_id}'s budget citation does not name a page: {citation!r}")


def test_two_of_the_four_budget_no_indirect_at_all():
    """The restatement's case, stated on the face of the agreements.

    Drive AM budgets none against $583,594 of labour and Hybrid none against
    $449,043. ICAM budgets 10% of ODCs only — $27,500 — with $655,190 of
    labour carrying nothing. That absence is the strongest evidence in the
    file, because the documents YBI issued are themselves the record of what
    it was never budgeted to claim.
    """
    none_at_all = [b[0] for b in BUDGETS
                   if not any(c == "INDIRECT" for c, _, _ in b[3])]
    assert set(none_at_all) == {"AM-DRIVE-AM", "AM-HYBRID-P2"}, none_at_all

    icam = next(b for b in BUDGETS if b[0] == "AM-ICAM-DIGENG")
    indirect = next(Decimal(a) for c, a, _ in icam[3] if c == "INDIRECT")
    odc = next(Decimal(a) for c, a, _ in icam[3] if c == "ODC")
    labour = next(Decimal(a) for c, a, _ in icam[3] if c == "LABOR")
    assert indirect == odc / 10, "ICAM's indirect is no longer 10% of ODCs"
    assert labour > 0, "ICAM budgets no labour, which would change the point"


def test_a_category_at_zero_is_a_category():
    """A line at zero is a line, and must never be filtered.

    The schedules name categories the contract allows, not categories that
    had activity. Dropping an empty row produces a tidier document that says
    something different — that a category was unavailable, when it was
    available and unused.
    """
    for award_id, _, _, lines, *_ in BUDGETS:
        zeros = [c for c, a, _ in lines if Decimal(a) == 0]
        assert zeros, (
            f"{award_id} has no category at zero. Every one of these "
            f"schedules names at least one, so either the transcription "
            f"dropped them or the loader started filtering.")
        for category, amount, note in lines:
            if Decimal(amount) == 0:
                assert note, (
                    f"{award_id} {category} is at zero with no note saying "
                    f"it was named in the schedule with nothing against it")


def test_the_dead_third_register_is_dropped():
    """`award_budget_line` was written once in `004` and read by nothing.

    Hybrid's four Schedule B categories sat in it from the first migration
    while `v_invoice_budget_check` reported the award unevaluable. The third
    instance of this shape after `space_partition` and `rate.superseded_by`.
    """
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "DROP TABLE award_budget_line" in joined, (
        "award_budget_line is back. Two registers of one fact is how the "
        "facilities carve-out could never fire.")
    live = {}
    for path in sorted(SQL.glob("*.sql")):
        body = re.sub(r"--[^\n]*", "", path.read_text())
        for statement in body.split(";"):
            named = re.search(r"CREATE (?:OR REPLACE )?VIEW\s+(\w+)",
                              statement, re.I)
            if named:
                live[named.group(1)] = statement
    offenders = [n for n, b in sorted(live.items()) if "award_budget_line" in b]
    assert not offenders, f"these read the dropped table: {offenders}"
