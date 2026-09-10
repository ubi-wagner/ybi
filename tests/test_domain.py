"""Sealing, validation and pool arithmetic. No database required."""

import pytest

from app.domain.core import (Decision, DecisionSet, EvidenceGrade,
                             FederalTreatment, Function990, PoolType, money)


def _d(**kw):
    base = dict(decision_id="D-1", scope="account=X", line_ids=("L1",),
                pool=PoolType.GA, function_990=Function990.MGMT_GENERAL,
                federal=FederalTreatment.ALLOWABLE, objective_id=None,
                evidence=EvidenceGrade.CORROBORATED, rationale="because")
    base.update(kw)
    return Decision(**base)


def test_money_is_exact():
    assert money("1,234.565") == money("1234.57")
    assert money(None) == 0


def test_direct_requires_objective():
    assert "final cost objective" in " ".join(_d(pool=PoolType.DIRECT).validate())


def test_pooled_must_not_carry_objective():
    assert "must not carry" in " ".join(_d(objective_id="DRIVE-AM").validate())


def test_supported_grade_requires_rationale():
    assert "rationale" in " ".join(_d(rationale="  ").validate())


def test_unallowable_cannot_be_federally_allowable():
    errs = " ".join(_d(pool=PoolType.UNALLOWABLE, federal=FederalTreatment.ALLOWABLE).validate())
    assert "cannot be federally allowable" in errs


def test_seal_is_stable_and_content_addressed():
    a, b = DecisionSet("2025"), DecisionSet("2025")
    a.record(_d()); b.record(_d())
    assert a.seal() == b.seal()


def test_seal_changes_when_a_classification_changes():
    a, b = DecisionSet("2025"), DecisionSet("2025")
    a.record(_d(pool=PoolType.GA))
    b.record(_d(pool=PoolType.OVERHEAD))
    assert a.seal() != b.seal()


def test_sealed_set_rejects_new_decisions():
    ds = DecisionSet("2025")
    ds.record(_d())
    ds.seal()
    with pytest.raises(RuntimeError, match="sealed"):
        ds.record(_d(decision_id="D-2"))


def test_unseal_requires_a_reason():
    ds = DecisionSet("2025")
    ds.record(_d()); ds.seal()
    with pytest.raises(ValueError):
        ds.unseal("   ")
    ds.unseal("controller corrected the facilities mapping")
    assert not ds.sealed


def test_coverage_reports_undecided_lines():
    ds = DecisionSet("2025")
    ds.record(_d(line_ids=("L1", "L2")))
    decided, undecided = ds.coverage({"L1", "L2", "L3"})
    assert decided == {"L1", "L2"} and undecided == {"L3"}


# --- chart of accounts -----------------------------------------------------

from app.domain.chart import CHART, pool_for, chart_csv, classes_csv, customers_csv
from app.domain.crosswalk import CROSSWALK, build


def test_account_number_determines_pool():
    assert pool_for("5100").value == "DIRECT"
    assert pool_for("6100").value == "FRINGE"
    assert pool_for("7200").value == "OVERHEAD"
    assert pool_for("8100").value == "G&A"
    assert pool_for("9110").value == "FUNDRAISING"
    assert pool_for("9220").value == "UNALLOWABLE"
    assert pool_for("9310").value == "RENTAL_DIRECT"
    assert pool_for("1010") is None      # balance sheet carries no pool


def test_no_duplicate_account_numbers():
    numbers = [a.number for a in CHART]
    assert len(numbers) == len(set(numbers))


def test_unallowable_accounts_are_never_federally_allowable():
    for a in CHART:
        if a.pool and a.pool.value in ("UNALLOWABLE", "FUNDRAISING"):
            assert a.federal.value != "ALLOWABLE", a.name


def test_exports_are_valid_csv_with_qbo_headers():
    import csv as _csv, io as _io
    head = next(_csv.reader(_io.StringIO(chart_csv())))
    assert head[:2] == ["Account Number", "Account Name"]
    assert next(_csv.reader(_io.StringIO(classes_csv())))[0] == "Class Name"
    assert next(_csv.reader(_io.StringIO(customers_csv())))[1] == "Sub-customer of"


def test_crosswalk_carries_every_dollar():
    src = [{"Source Account": a, "Booked Amount": "1000", "Cost Disposition": ""}
           for a in CROSSWALK]
    rows, tie = build(src, {})
    assert tie["unmapped"] == 0
    assert tie["variance"] == 0
    assert all(r["account_2026"] for r in rows)
