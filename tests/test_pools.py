"""The rate engine.

This is the arithmetic the whole system exists to produce, and until now it
had no tests at all. The properties that matter are not "does it divide" but
the ones an auditor tests: that the pool ties to the ledger, that every
allocable dollar lands on exactly one objective, that a rate cannot come out
of an unsealed set, and that the base is the base the regulation defines.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.core import (AllocationBase, Decision, DecisionSet,
                             EvidenceGrade, FederalTreatment, Function990,
                             PoolType, money)
from app.domain.ingest import Ledger, LedgerLine
from app.domain.pools import CarveOut, ObjectiveCost, PoolModel


def line(line_id: str, amount: str, account: str = "5000 Cost") -> LedgerLine:
    return LedgerLine(line_id=line_id, period="2025", date="2025-06-30",
                      account=account, payee="", description="",
                      amount=Decimal(amount), pl_scope="P&L",
                      pl_section="Expense", source_key=line_id)


def decision(did: str, pool: PoolType, line_ids, objective=None,
             grade=EvidenceGrade.CORROBORATED) -> Decision:
    return Decision(
        decision_id=did, scope=f"test={did}", line_ids=tuple(line_ids),
        pool=pool,
        function_990=(Function990.PROGRAM if pool is PoolType.DIRECT
                      else Function990.MGMT_GENERAL),
        federal=FederalTreatment.PENDING, objective_id=objective,
        evidence=grade, rationale="test", decided_by="test")


def model(pairs, extra_lines=()) -> PoolModel:
    """pairs: (decision_id, pool, [(line_id, amount)], objective)"""
    lines, decisions = list(extra_lines), []
    for did, pool, rows, objective in pairs:
        for lid, amt in rows:
            lines.append(line(lid, amt))
        decisions.append(decision(did, pool, [lid for lid, _ in rows], objective))
    ledger = Ledger("2025", lines)
    ds = DecisionSet("2025")
    for d in decisions:
        ds.record(d)
    m = PoolModel(ledger, ds)
    m.build()
    return m


# ── the pool has to tie to the ledger ────────────────────────────────

def test_classified_plus_unclassified_equals_the_ledger():
    m = model([("d1", PoolType.DIRECT, [("l1", "1000")], "DRIVE-AM"),
               ("d2", PoolType.OVERHEAD, [("l2", "400")], None)],
              extra_lines=[line("l3", "250")])          # never classified
    r = m.reconciliation(Decimal("1650"))
    assert r["variance"] == Decimal("0.00")
    assert r["unclassified"] == Decimal("250.00")


def test_an_unclassified_dollar_is_never_quietly_pooled():
    m = model([("d1", PoolType.DIRECT, [("l1", "1000")], "DRIVE-AM")],
              extra_lines=[line("l9", "9999")])
    assert m.unclassified == Decimal("9999.00")
    assert sum(p.gross for p in m.pools.values()) == Decimal("1000.00")


# ── carve-outs ───────────────────────────────────────────────────────

def test_a_carve_out_reduces_the_allocable_pool_and_keeps_its_reason():
    m = model([("d1", PoolType.OVERHEAD, [("l1", "10000")], None)])
    m.add_carve_out(PoolType.OVERHEAD, CarveOut(
        name="Tenant share of facilities", citation="2 CFR 200.465",
        amount=Decimal("4000"), driver="square footage"))
    pool = m.pools[PoolType.OVERHEAD]
    assert pool.gross == Decimal("10000.00")
    assert pool.removed == Decimal("4000.00")
    assert pool.allocable == Decimal("6000.00")
    assert "200.465" in str(pool.carve_outs[0])


# ── the base is the one the regulation defines ───────────────────────

def test_mtdc_excludes_equipment_and_the_subaward_tail():
    o = ObjectiveCost(objective_id="X", direct_labor=Decimal("100000"),
                      fringe=Decimal("22450"), direct_nonlabor=Decimal("80000"),
                      equipment=Decimal("30000"),
                      subaward_excess=Decimal("15000"))
    assert o.total_direct == Decimal("202450.00")
    assert o.mtdc == Decimal("157450.00")       # 202,450 - 30,000 - 15,000


def test_base_amount_answers_differently_per_base_type():
    m = model([("d1", PoolType.DIRECT, [("l1", "50000")], "DRIVE-AM")])
    m.add_labor({"Drive AM": {"wages": Decimal("100000"),
                              "backed": Decimal("100000")}},
                fringe_rate=Decimal("0.2245"),
                objective_map={"Drive AM": "DRIVE-AM"}, federal={"DRIVE-AM"})
    wages = m.base_amount(AllocationBase.SALARIES_WAGES)
    with_fringe = m.base_amount(AllocationBase.SALARIES_FRINGE)
    total = m.base_amount(AllocationBase.TOTAL_DIRECT)
    assert wages == Decimal("100000.00")
    assert with_fringe == Decimal("122450.00")
    assert total == Decimal("172450.00")        # wages + fringe + 50,000


# ── the seal gate ────────────────────────────────────────────────────

def test_a_rate_cannot_be_computed_from_an_unsealed_set():
    m = model([("d1", PoolType.OVERHEAD, [("l1", "1000")], None)])
    assert not m.decisions.sealed
    with pytest.raises(RuntimeError, match="unsealed"):
        m.compute_rates(fringe_base=Decimal("1000"))


def test_every_rate_carries_the_seal_it_came_from():
    m = model([("d1", PoolType.OVERHEAD, [("l1", "1000")], None),
               ("d2", PoolType.DIRECT, [("l2", "4000")], "DRIVE-AM")])
    seal = m.decisions.seal()
    m.compute_rates(fringe_base=Decimal("1000"))
    assert set(m.rate_provenance.values()) == {seal}
    assert len(seal) == 64


def test_unsealing_puts_the_gate_back():
    m = model([("d1", PoolType.OVERHEAD, [("l1", "1000")], None)])
    m.decisions.seal()
    m.decisions.unseal("found an error")
    with pytest.raises(RuntimeError):
        m.compute_rates(fringe_base=Decimal("1000"))


# ── the rates themselves ─────────────────────────────────────────────

def test_the_indirect_rate_is_the_pool_over_the_base():
    m = model([("oh", PoolType.OVERHEAD, [("l1", "30000")], None),
               ("ga", PoolType.GA, [("l2", "20000")], None),
               ("dir", PoolType.DIRECT, [("l3", "200000")], "DRIVE-AM")])
    m.decisions.seal()
    rates = m.compute_rates(fringe_base=Decimal("100000"))
    # base is MTDC = the 200,000 of direct non-labour on DRIVE-AM
    assert rates["OVERHEAD"] == Decimal("0.1500")
    assert rates["G&A"] == Decimal("0.1000")
    assert rates["INDIRECT_COMBINED"] == Decimal("0.2500")


def test_a_zero_base_gives_a_zero_rate_rather_than_an_exception():
    m = model([("oh", PoolType.OVERHEAD, [("l1", "30000")], None)])
    m.decisions.seal()
    rates = m.compute_rates(fringe_base=Decimal("0"))
    assert rates["FRINGE"] == Decimal("0")
    assert rates["INDIRECT_COMBINED"] == Decimal("0")


# ── allocation ties, to the cent ─────────────────────────────────────

def test_every_allocable_dollar_lands_on_exactly_one_objective():
    m = model([("oh", PoolType.OVERHEAD, [("l1", "33333.33")], None),
               ("ga", PoolType.GA, [("l2", "16666.67")], None),
               ("a", PoolType.DIRECT, [("l3", "111111.11")], "DRIVE-AM"),
               ("b", PoolType.DIRECT, [("l4", "77777.77")], "HUB"),
               ("c", PoolType.DIRECT, [("l5", "55555.55")], "LTM")])
    m.decisions.seal()
    m.compute_rates(fringe_base=Decimal("100000"))
    m.allocate()
    proof = m.allocation_proof()
    assert proof["variance"] == Decimal("0.00"), proof


def test_the_rounding_residual_is_disclosed_not_hidden():
    m = model([("oh", PoolType.OVERHEAD, [("l1", "10000.01")], None),
               ("a", PoolType.DIRECT, [("l2", "33333.33")], "A"),
               ("b", PoolType.DIRECT, [("l3", "33333.33")], "B"),
               ("c", PoolType.DIRECT, [("l4", "33333.34")], "C")])
    m.decisions.seal()
    m.compute_rates(fringe_base=Decimal("1"))
    m.allocate()
    assert m.allocation_proof()["variance"] == Decimal("0.00")
    # Whatever the residual was, it is a stated number rather than a gap.
    assert isinstance(m.rounding_residual, Decimal)


def test_fundraising_takes_an_allocation_even_though_nothing_is_recovered():
    """2 CFR 200.413 and Appendix IV B.3.d: a benefiting activity bears its
    share, which is what stops the federal objectives absorbing it."""
    m = model([("oh", PoolType.OVERHEAD, [("l1", "10000")], None),
               ("fr", PoolType.FUNDRAISING, [("l2", "40000")], None),
               ("dir", PoolType.DIRECT, [("l3", "60000")], "DRIVE-AM")])
    m.decisions.seal()
    m.compute_rates(fringe_base=Decimal("1000"))
    m.allocate()
    fundraising = m.objectives["FUNDRAISING"]
    assert fundraising.mtdc == Decimal("40000.00")
    assert fundraising.indirect > 0
    assert m.allocation_proof()["variance"] == Decimal("0.00")


def test_allocating_before_computing_is_refused():
    m = model([("oh", PoolType.OVERHEAD, [("l1", "1000")], None)])
    with pytest.raises(RuntimeError, match="Compute rates"):
        m.allocate()


# ── the evidence ratio behind a labour charge ────────────────────────

def test_evidence_ratio_reports_how_much_labour_is_timesheet_backed():
    m = model([("dir", PoolType.DIRECT, [("l1", "1000")], "DRIVE-AM")])
    m.add_labor({"Drive AM": {"wages": Decimal("100000"),
                              "backed": Decimal("25000")}},
                fringe_rate=Decimal("0.2245"),
                objective_map={"Drive AM": "DRIVE-AM"}, federal={"DRIVE-AM"})
    assert m.objectives["DRIVE-AM"].evidence_ratio == Decimal("0.2500")


def test_evidence_ratio_is_none_rather_than_zero_when_there_is_no_labour():
    assert ObjectiveCost(objective_id="X").evidence_ratio is None


# ── administrative labour: in the base, or in the G&A pool ───────────
#
# Migration 068. `YBI-GA` carries $264,444.90 of wages and the model has
# always treated it as a cost objective, so it takes an allocation of
# indirect rather than forming part of it. Appendix IV B puts the director's
# office, accounting and personnel administration *in* the G&A pool.
#
# It is a judgment rather than arithmetic, so the engine offers both and the
# rate records which was used. What these hold is that the move is exactly
# the move described and nothing else travels with it.

def admin_model() -> PoolModel:
    """One administrative objective and one programme objective."""
    m = model([("dir", PoolType.DIRECT, [("l1", "500000")], "DRIVE-AM"),
               ("ga", PoolType.GA, [("l2", "100000")], None),
               ("oh", PoolType.OVERHEAD, [("l3", "200000")], None),
               # A real fringe pool, because a model without one computes a
               # fringe rate of 0.00 either side of any change and every
               # assertion about it compares nothing to nothing.
               ("fr", PoolType.FRINGE, [("l4", "80000")], None)])
    m.add_labor({"Drive AM": {"wages": Decimal("300000"),
                              "backed": Decimal("0")},
                 "YBI G&A": {"wages": Decimal("100000"),
                             "backed": Decimal("0")}},
                fringe_rate=Decimal("0.2000"),
                objective_map={"Drive AM": "DRIVE-AM", "YBI G&A": "YBI-GA"},
                federal={"DRIVE-AM"})
    return m


def test_administration_moves_its_whole_cost_into_the_pool():
    m = admin_model()
    before_mtdc = m.base_amount(AllocationBase.MTDC)
    moved = m.administration_into_the_pool("YBI-GA")

    # wages 100,000 + fringe at 20% + no direct non-labour on it
    assert moved == Decimal("120000.00")
    assert m.pools[PoolType.GA].gross == Decimal("220000.00")
    assert m.base_amount(AllocationBase.MTDC) == before_mtdc - moved
    # Removed, not zeroed: an objective carrying nothing still prints a row
    # and still takes an allocation of zero, which reads as "administration
    # bore no indirect" rather than "it stopped being an objective".
    assert "YBI-GA" not in m.objectives


def test_the_wage_base_is_the_payroll_register_either_way():
    """The bug the anchors caught, held as a property.

    Administrative staff draw benefits like everybody else, so their wages
    belong in the fringe denominator whether or not their salary sits in the
    G&A pool. The first draft answered both questions at once: deleting the
    objective took its wages out of the *fringe* base too and the rate went
    21.90% to 25.58% on the live record — which is the payroll register
    disagreeing with itself.
    """
    m = admin_model()
    payroll = dict(fringe_denominator=True)
    wages_before = m.base_amount(AllocationBase.SALARIES_WAGES, **payroll)
    fringed_before = m.base_amount(AllocationBase.SALARIES_FRINGE, **payroll)
    assert wages_before == Decimal("400000.00")
    assert fringed_before == Decimal("480000.00")

    m.administration_into_the_pool("YBI-GA")

    assert m.base_amount(AllocationBase.SALARIES_WAGES, **payroll) == wages_before
    assert m.base_amount(AllocationBase.SALARIES_FRINGE, **payroll) == fringed_before
    # And it is genuinely out of the *allocation* base, or nothing happened.
    assert m.base_amount(AllocationBase.SALARIES_WAGES) == Decimal("300000.00")
    assert m.base_amount(AllocationBase.MTDC) < Decimal("920000.00")


def test_the_fringe_rate_does_not_move_when_administration_is_pooled():
    """The whole point of the previous test, stated as the figure that
    reaches a workpaper."""
    a, b = admin_model(), admin_model()
    b.administration_into_the_pool("YBI-GA")
    assert (a.apply_fringe(AllocationBase.SALARIES_WAGES)
            == b.apply_fringe(AllocationBase.SALARIES_WAGES))
    # The same holds on a salaries-and-fringe denominator, which the first
    # version of `base_amount` got wrong by exactly the administrative
    # fringe: it added the wages back and not the benefits on them.
    c, d = admin_model(), admin_model()
    d.administration_into_the_pool("YBI-GA")
    assert (c.apply_fringe(AllocationBase.SALARIES_FRINGE)
            == d.apply_fringe(AllocationBase.SALARIES_FRINGE))


def test_pooling_administration_raises_the_indirect_rate_and_ties():
    """Both halves: the rate moves in the direction the decision claims, and
    the allocation still proves out over the objectives that remain."""
    plain, pooled = admin_model(), admin_model()
    for m in (plain, pooled):
        m.apply_fringe(AllocationBase.SALARIES_WAGES)
    pooled.administration_into_the_pool("YBI-GA")
    for m in (plain, pooled):
        m.decisions.seal()
        m.compute_rates(fringe_base=m.base_amount(
            AllocationBase.SALARIES_WAGES, fringe_denominator=True))
        m.allocate()

    assert pooled.rates["G&A"] > plain.rates["G&A"]
    assert pooled.rates["INDIRECT_COMBINED"] > plain.rates["INDIRECT_COMBINED"]
    assert pooled.allocation_proof()["variance"] == Decimal("0.00")


def test_a_rate_over_named_objectives_does_not_get_the_moved_wages_back():
    """`include` is a filter over objectives and moved administration is no
    longer one, so a rate over a named subset is asking a different question
    and must not have the whole payroll added to its denominator."""
    m = admin_model()
    m.administration_into_the_pool("YBI-GA")
    subset = m.base_amount(AllocationBase.SALARIES_WAGES, include={"DRIVE-AM"},
                           fringe_denominator=True)
    assert subset == Decimal("300000.00")


def test_fundraising_is_not_swept_along_with_administration():
    """200.413 and Appendix IV B.3.d make fundraising bear indirect while
    recovering nothing, so it *is* a benefiting objective. General
    administration is the opposite case, and a change to one must not be a
    change to the other."""
    m = admin_model()
    m.pools[PoolType.FUNDRAISING].gross = Decimal("40000.00")
    m.objectives.setdefault("FUNDRAISING",
                            ObjectiveCost(objective_id="FUNDRAISING"))
    m.administration_into_the_pool("YBI-GA")
    assert "FUNDRAISING" in m.objectives


def test_moving_an_objective_that_is_not_there_changes_nothing():
    """A period with no administrative distribution is a real state, and it
    is not a reason to refuse a computation."""
    m = admin_model()
    ga_before = m.pools[PoolType.GA].gross
    assert m.administration_into_the_pool("NOT-A-THING") == Decimal(0)
    assert m.pools[PoolType.GA].gross == ga_before
