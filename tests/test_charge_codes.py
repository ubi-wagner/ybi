"""Charge codes, and the rules that make them worth having.

The cost side of this system reads a year already spent. This is the half
that has to exist before the year is worked, and each rule below is one
somebody would otherwise have to remember.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
ROUTER = (ROOT / "app" / "routers" / "contracts.py").read_text()
TIMESHEET = (ROOT / "app" / "routers" / "timesheet.py").read_text()


def _sql(name: str) -> str:
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        m = re.search(rf"CREATE (?:OR REPLACE )?(?:VIEW|TABLE) {name}[ (]"
                      rf"(.*?);\s*(?:COMMENT|CREATE|ALTER|--|$)", src, re.S)
        if m:
            return re.sub(r"--[^\n]*", "", m.group(1))
    raise AssertionError(f"{name} is not defined in any migration")


def test_the_charge_code_is_the_cost_objective():
    """No second register of codes.

    An hour and a dollar spent on the same work have to land in the same
    place. Two lists of "the thing you charge to" is how they stop doing
    that, and reconciling them afterwards is a job nobody should have.
    """
    assert "REFERENCES cost_objective" in _sql("charge_authority"), (
        "charge_authority does not reference cost_objective — a charge code "
        "has been invented alongside the objective rather than being one.")
    for bad in ("CREATE TABLE charge_code", "CREATE TABLE chargecode"):
        assert not any(bad in p.read_text() for p in SQL.glob("*.sql")), (
            f"{bad}: the objective is the charge code.")


def test_one_live_grant_per_person_per_code():
    """An amendment supersedes; it does not sit beside the thing it amends."""
    idx = next((p.read_text() for p in SQL.glob("*.sql")
                if "one_live_authority" in p.read_text()), "")
    assert "UNIQUE INDEX one_live_authority" in idx
    assert "WHERE revoked_at IS NULL" in idx, (
        "the uniqueness is not partial on live grants, so a revoked grant "
        "blocks a re-assignment for ever.")


def test_a_revocation_says_why():
    body = _sql("charge_authority")
    assert "(revoked_at IS NULL) = (revoked_reason IS NULL)" in body, (
        "a grant can be revoked with no reason. Taking somebody off a federal "
        "charge code is a decision, and a decision with no reason on it is "
        "one nobody can review.")


def test_nobody_authorises_themselves():
    assert "actor.employee_key == body.employee_key" in ROUTER, (
        "the authorise handler does not refuse self-assignment. It is the "
        "rule the portfolios follow and it holds here for the same reason.")


def test_a_federal_code_carries_its_cfda():
    assert "is_federal and not body.cfda" in ROUTER, (
        "a federal charge code can be opened without a CFDA number. Without "
        "it the award cannot reach the SEFA, and the Single Audit scope is "
        "decided by what is on the SEFA.")


def test_time_entry_asks_the_same_view_the_screen_asks():
    """One place answers "may this person charge this code"."""
    assert "v_charge_authorised" in TIMESHEET, (
        "the timesheet handler does not consult v_charge_authorised, so the "
        "screen and the handler can hold different opinions about who may "
        "charge what.")


def test_the_gate_only_bites_on_a_managed_code():
    """2025 was worked before any of this existed.

    Gating every code would make reconstructing the year impossible. A code
    with an assignment list is a code being managed; one with an empty list
    predates the mechanism and stays open.
    """
    assert "if managed:" in TIMESHEET, (
        "the charge gate is unconditional. Every 2025 hour was booked to a "
        "code nobody was assigned to, so this refuses the whole year.")


def test_a_milestone_state_that_claims_a_date_carries_one():
    body = _sql("milestone")
    assert "state <> 'DELIVERED' OR delivered_on IS NOT NULL" in body
    assert "state <> 'ACCEPTED'  OR accepted_on IS NOT NULL" in body, (
        "a milestone can be ACCEPTED with no acceptance date — a status "
        "somebody set rather than a thing that happened.")


def test_a_receipt_may_be_negative():
    """A refund and a clawback are money moving the other way."""
    assert "amount <> 0" in _sql("receipt"), (
        "receipt.amount is constrained positive, so a refund cannot be "
        "recorded and the money in will overstate for ever.")


def test_the_employee_view_says_whether_anybody_authorised_the_charge():
    body = _sql("v_employee_charging")
    assert "authorised" in body and "charge_authority" in body, (
        "v_employee_charging does not report whether a grant existed. The "
        "auditor's first question about an hour is who said it could be "
        "charged, and an answer of silence reads as yes.")


# ── the 2026 crosswalk as a proposal source ───────────────────────────


def test_the_crosswalk_proposes_but_never_decides():
    """A mapping somebody already built and reviewed is a real signal.

    Sixty-one of the eighty-five 2025 accounts map one-to-one to a 2026
    account number, and pool_for() reads the pool off that number. That took
    proposal coverage from 36% of dollars to 65%. It is still a proposal: the
    grade, the citation and the source are on it and a human confirms.
    """
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    assert '"source": "crosswalk"' in src, (
        "the 2026 crosswalk is not offered as a proposal source, so 275 "
        "groups sit in the queue with no suggestion against a mapping that "
        "already exists.")
    assert '"citation": "2026 chart crosswalk"' in src, (
        "a crosswalk proposal carries no citation, so somebody accepting it "
        "cannot say where the suggestion came from.")


def test_the_crosswalk_refuses_to_guess_a_split():
    """Twenty-four accounts divide and need a documented driver.

    Depreciation splits by square footage, wages by timesheet. Proposing one
    side of a split would be inventing the driver, which is the judgment the
    split exists to force somebody to make.
    """
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    assert '"/" not in mapped[0]' in src, (
        "a split account is being proposed as if it mapped one-to-one.")


def test_a_crosswalk_proposal_leaves_the_990_function_and_federal_open():
    """An account number does not know either.

    Proposing a function would put cost in a column of the return nobody
    chose; proposing ALLOWABLE would assert a federal treatment off a chart.
    """
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    block = src[src.index('"source": "crosswalk"') - 1400:
                src.index('"source": "crosswalk"')]
    assert '"federal": "PENDING"' in block, (
        "a crosswalk proposal asserts a federal treatment that the account "
        "number cannot know.")
