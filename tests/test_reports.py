"""The two documents the reconciliation needs on paper.

Structural rules about the routes rather than the rendering, which
`test_invoice_document.py` covers.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "app" / "routers" / "reports.py"
SQL = ROOT / "app" / "sql"


def _route(name: str) -> str:
    src = REPORTS.read_text()
    m = re.search(rf'@router\.(?:get|post)\("{re.escape(name)}"[^)]*\)(.*?)'
                  rf'(?=\n@router\.|\Z)', src, re.S)
    assert m, f"the {name} route is gone"
    return m.group(1)


def test_reading_a_report_takes_the_reader_gate():
    """Both reports are the cost record in another shape, so they take the
    same gate the review screens and the library take."""
    for name in ("/timesheet", "/invoice/{invoice_id}", "/invoices"):
        body = _route(name)
        assert "require_reader" in body, (
            f"{name} is not gated on require_reader")


def test_filing_a_generated_invoice_is_not_a_read():
    """A read hands somebody a file. This puts an artefact in the evidence
    volume where an auditor will later find it, so it takes CONTROLLER and it
    is recorded."""
    body = _route("/invoice/{invoice_id}/file")
    assert "require_controller" in body, (
        "filing a regenerated invoice is gated on reading the record. It "
        "writes to the evidence volume.")
    assert "record(" in body, "filing an artefact records nothing"


def test_a_generated_document_is_marked_as_one():
    """Every other ingest channel means the document came from outside.

    A rendering of the register corroborates nothing the register does not
    already say, and filing it as UPLOAD would put it on the same shelf as
    the invoice the sponsor actually received, indistinguishable.
    """
    body = _route("/invoice/{invoice_id}/file")
    assert "'GENERATED'" in body, (
        "a regenerated invoice is being filed under a channel that means it "
        "came from outside")

    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "'GENERATED'" in joined, "the schema does not allow that channel"
    assert "is_generated" in joined, (
        "the library cannot tell a reader which documents this system made")


def test_the_generated_invoice_goes_through_storage():
    """`storage.place()` is the only thing that decides a path. A route that
    writes bytes anywhere else is what `tests/test_storage_paths.py` exists
    to catch, and this one writes bytes."""
    body = _route("/invoice/{invoice_id}/file")
    assert "storage.place(" in body and "storage.evidence_path(" in body


def test_filing_the_same_rendering_twice_files_one_document():
    """The render is deterministic and the volume is content-addressed.

    Without the check, every press of the button is another evidence row
    pointing at identical bytes.
    """
    body = _route("/invoice/{invoice_id}/file")
    assert "sha256" in body and "deduplicated" in body


def test_the_timesheet_report_states_what_is_unfinished():
    """A reviewer handed a distribution has formed a view before they reach a
    footnote. The same rule the review screens follow."""
    src = REPORTS.read_text()
    assert "_timesheet_caveats" in src
    m = re.search(r"def _timesheet_caveats\(.*?\n(?=\n\n@|\Z)", src, re.S)
    assert m, "the caveats are gone"
    body = m.group(0)
    for signal in ("certified", "reconstructed", "unexplained"):
        assert signal in body, (
            f"the timesheet report no longer says anything about {signal}")


def test_the_report_reads_views_rather_than_assembling_its_own_figures():
    """Every figure comes off the row it was recorded in.

    The four views below are where the labour position already lives. A
    report that went to `timesheet_entry` and summed it would be a second
    implementation of the distribution, and the two would eventually
    disagree — which is the whole argument the review screens rest on.

    Deliberately not a test that the route contains no division: a path join
    is a division operator in Python and the version of this test that
    checked for one failed on `Path(tempfile.gettempdir()) / name`. A test
    that argues against correct code is worse than no test.
    """
    body = _route("/timesheet")
    for view in ("v_timesheet_coverage", "v_labor_effective",
                 "v_certification_status", "v_payroll_reconciliation"):
        assert view in body, f"{view} is no longer read"
    assert "FROM timesheet_entry" not in body, (
        "the report is reading the entry table directly rather than the view "
        "that decides which entries are live")


def test_the_budget_decides_which_categories_may_appear():
    """An invoice lists the categories its contract funds.

    Drive AM's Schedule B funds five of its seven named categories —
    SUBCONTRACT and EQUIPMENT are in the schedule at zero — and invoice
    10018 carries exactly those five. That is a checkable property, so it is
    checked rather than remembered.
    """
    joined = "\n".join(p.read_text() for p in sorted(SQL.glob("*.sql")))
    assert "CREATE TABLE award_budget" in joined, (
        "award_budget is gone; nothing records which categories a contract "
        "funds, so the invoice format cannot be checked against anything")
    assert "v_invoice_budget_check" in joined
    assert "award_budget_needs_citation" in joined, (
        "a budget line with no citation is somebody's recollection of a "
        "schedule")


def test_an_award_with_no_budget_read_neither_passes_nor_fails():
    """Both sides of the comparison are empty on an award nobody has
    transcribed, and an empty set matches an empty set perfectly.

    Without the guard, every category on an unread award reads as "billed
    outside the budget" — a finding the data cannot support, because you
    cannot say a category is unbudgeted when nobody has read the budget.
    """
    body = _view("v_invoice_budget_check")
    assert "evaluable" in body, (
        "the budget check no longer says whether it could be evaluated")
    assert body.count("CASE WHEN EXISTS") >= 2, (
        "the billed_not_budgeted and budgeted_not_billed lists are no longer "
        "guarded on a budget existing, so an award nobody has read reports "
        "every category as a finding")


def _view(name: str) -> str:
    import re as _re
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        m = _re.search(
            rf"CREATE (?:OR REPLACE )?VIEW {name} AS(.*?);\s*(?:COMMENT|CREATE|--|$)",
            src, _re.S)
        if m:
            return m.group(1)
    raise AssertionError(f"{name} is not defined in any migration")
