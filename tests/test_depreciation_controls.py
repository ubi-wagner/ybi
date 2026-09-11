"""Depreciation is read from expense accounts, and an absent register says so.

Both of these were found by cross-tying the 2025 baseline, and both are the
same shape of mistake: a figure that looked plausible and was not checkable
against anything.
"""

from __future__ import annotations

import re
from pathlib import Path

SQL = Path(__file__).resolve().parent.parent / "app" / "sql"


def _latest(view: str) -> str:
    """The definition that actually runs — the last migration to define it."""
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        m = re.search(rf"CREATE (?:OR REPLACE )?VIEW {view} AS(.*?);\s*(?:COMMENT|CREATE|--|$)",
                      src, re.S)
        if m:
            return m.group(1)
    raise AssertionError(f"{view} is not defined in any migration")


def test_depreciation_expense_is_scoped_to_expense_accounts():
    """Six accounts carry 'depreciation' in their name; one is expense.

    The other five are contra-assets, and the one the old pattern caught was
    caught only because it spells the word out where the others say 'Accum.
    Depr.'. It reported 1,289,255.94 against a ledger that expensed
    850,382.89 — the TBB5 credit added back as if it were more expense.
    """
    clause = _latest("v_depreciation_basis")
    assert "pl_account" in clause, (
        "depreciation_expensed does not scope to pl_account. An unscoped "
        "name match picks up the accumulated-depreciation contra-assets on "
        "the balance sheet and counts them as expense.")
    assert "abs(" not in clause.lower(), (
        "depreciation_expensed uses abs(). A credit to depreciation expense "
        "is a reduction of it; abs() turns the contra-asset's credit into an "
        "addition, which is how the figure came to overstate by 51.6%.")


def test_the_asset_control_says_no_data_rather_than_a_variance():
    """A control that cannot be evaluated has not passed — including this one."""
    body = _latest("v_asset_control")
    assert "evaluable" in body, (
        "v_asset_control has no evaluable test, so with no register loaded it "
        "reports the whole of the ledger's depreciation as a variance — a "
        "disagreement where the truth is a missing document.")
    assert "NO DATA" in body, "v_asset_control never reports NO DATA"
    assert "needs" in body, (
        "v_asset_control does not say what it needs. 'No data' on its own "
        "sends somebody looking for which document was forgotten.")


def test_the_audit_package_carries_the_control_state():
    """The distinction has to survive into the workpaper, or it is decorative.

    v_statement_reconciliation and v_asset_control both compute `state`, but
    the Controls sheet emitted only the variance and a boolean. With no
    register on file ASSET_REGISTER printed -850,382.89 and Ties=False, which
    a reviewer reads as "the register disagrees with the ledger by the whole
    of its depreciation" rather than "there is no register" — the exact
    misreading migration 029 exists to prevent, in the one artefact that
    leaves the building.
    """
    src = (Path(__file__).resolve().parent.parent
           / "app" / "domain" / "audit_package.py").read_text()
    controls = src[src.index('_sheet(wb, "Controls"'):
                   src.index('_sheet(wb, "A-1 Reconciliation"')]
    assert '"state"' in controls, (
        "the Controls sheet does not emit `state`, so a control that could "
        "not be evaluated is indistinguishable from one that disagrees.")
    a1 = src[src.index('_sheet(wb, "A-1 Reconciliation"'):]
    assert '"state"' in a1[:1200], "schedule A-1 does not emit `state` either"
