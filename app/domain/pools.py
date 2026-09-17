"""
Pool construction, rate computation, and allocation.

Method: multiple allocation base (2 CFR 200 Appendix IV, section B.3). YBI has
materially different functions — federal R&D, state programs, a rental
operation, fundraising — so a single simplified rate would mis-assign cost
between them.

Sequence is fixed and one-directional:
    decisions (sealed)  ->  pools  ->  rates  ->  allocation  ->  award true-up
A rate cannot be computed from an unsealed decision set. That is the
"without prejudice" guarantee, enforced in code rather than promised in a memo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .core import (AllocationBase, Decision, DecisionSet, EvidenceGrade,
                   FederalTreatment, PoolType, money)
from .ingest import Ledger

#: 2 CFR 200.1. MTDC takes the first $25,000 of each **subaward** and no more;
#: a contract for services goes in whole. Defined here, where `mtdc` is, so the
#: handler that records a 200.331 determination and the engine that applies it
#: cannot hold two opinions about where the line is.
SUBAWARD_CAP = Decimal("25000")


@dataclass
class CarveOut:
    """A documented reduction to a pool. Each one needs a citation and a driver
    so the workpaper explains itself without a covering note."""
    name: str
    citation: str
    amount: Decimal
    driver: str
    evidence: EvidenceGrade = EvidenceGrade.UNSUPPORTED

    def __str__(self) -> str:
        return f"{self.name} ({self.citation}): {self.amount:,.2f} — {self.driver}"


@dataclass
class Pool:
    pool_type: PoolType
    gross: Decimal = Decimal(0)          # from account-level classification
    labor_addition: Decimal = Decimal(0)  # redistributed from the wage pool
    carve_outs: list[CarveOut] = field(default_factory=list)
    base_type: AllocationBase = AllocationBase.MTDC

    @property
    def removed(self) -> Decimal:
        return money(sum(c.amount for c in self.carve_outs))

    @property
    def allocable(self) -> Decimal:
        return money(self.gross + self.labor_addition - self.removed)


@dataclass
class ObjectiveCost:
    objective_id: str
    label: str = ""
    is_federal: bool = False
    direct_labor: Decimal = Decimal(0)
    direct_nonlabor: Decimal = Decimal(0)
    fringe: Decimal = Decimal(0)
    timesheet_backed_labor: Decimal = Decimal(0)
    subaward_excess: Decimal = Decimal(0)   # subaward $ above 25k — out of MTDC
    equipment: Decimal = Decimal(0)          # out of MTDC
    allocated: dict[str, Decimal] = field(default_factory=dict)

    @property
    def total_direct(self) -> Decimal:
        return money(self.direct_labor + self.fringe + self.direct_nonlabor)

    @property
    def mtdc(self) -> Decimal:
        """2 CFR 200.1: excludes equipment, capital expenditure, and the portion
        of each subaward above $25,000."""
        return money(self.total_direct - self.subaward_excess - self.equipment)

    @property
    def indirect(self) -> Decimal:
        return money(sum(self.allocated.values()))

    @property
    def fully_burdened(self) -> Decimal:
        return money(self.total_direct + self.indirect)

    @property
    def evidence_ratio(self) -> Decimal | None:
        if not self.direct_labor:
            return None
        return (self.timesheet_backed_labor / self.direct_labor).quantize(Decimal("0.0001"))


class PoolModel:
    """Builds pools from a sealed decision set and allocates them out."""

    def __init__(self, ledger: Ledger, decisions: DecisionSet, period: str = "2025"):
        self.ledger = ledger
        self.decisions = decisions
        self.period = period
        self.pools: dict[PoolType, Pool] = {}
        self.objectives: dict[str, ObjectiveCost] = {}
        self.rates: dict[str, Decimal] = {}
        self.rate_provenance: dict[str, str] = {}
        self.unclassified: Decimal = Decimal(0)
        self.rounding_residual: Decimal = Decimal(0)
        #: Administrative wages moved into the G&A pool, kept because the
        #: *wage* base is not the *allocation* base and moving one must not
        #: move the other. See `administration_into_the_pool`.
        self.pooled_admin_labor: Decimal = Decimal(0)
        self.pooled_admin_fringe: Decimal = Decimal(0)

    # -- build -------------------------------------------------------------

    def build(self) -> None:
        totals: dict[PoolType, Decimal] = defaultdict(Decimal)
        by_objective: dict[str, Decimal] = defaultdict(Decimal)

        for d in self.decisions:
            amt = money(sum(self.ledger.get(lid).amount for lid in d.line_ids))
            totals[d.pool] += amt
            if d.pool is PoolType.DIRECT and d.objective_id:
                by_objective[d.objective_id] += amt

        _, undecided = self.decisions.coverage(self.ledger.line_ids)
        self.unclassified = money(sum(self.ledger.get(lid).amount for lid in undecided))

        for pt, gross in totals.items():
            self.pools.setdefault(pt, Pool(pool_type=pt)).gross = money(gross)
        for pt in PoolType:
            self.pools.setdefault(pt, Pool(pool_type=pt))

        for oid, amt in by_objective.items():
            o = self.objectives.setdefault(oid, ObjectiveCost(objective_id=oid))
            o.direct_nonlabor = money(o.direct_nonlabor + amt)

        # Fundraising and unallowable activities are benefiting activities: they
        # take an allocation of indirect even though nothing is recovered on
        # them (2 CFR 200.413, Appendix IV B.3.d). Modelling them as objectives
        # is what makes the allocation proof tie.
        for pt, oid in ((PoolType.FUNDRAISING, "FUNDRAISING"),
                        (PoolType.UNALLOWABLE, "UNALLOWABLE-ACTIVITY")):
            o = self.objectives.setdefault(oid, ObjectiveCost(objective_id=oid, label=oid))
            o.direct_nonlabor = money(o.direct_nonlabor + self.pools[pt].gross)

    def add_labor(self, distribution: dict[str, dict], fringe_rate: Decimal,
                  objective_map: dict[str, str], federal: set[str]) -> None:
        for raw_obj, vals in distribution.items():
            oid = objective_map.get(raw_obj, raw_obj)
            o = self.objectives.setdefault(oid, ObjectiveCost(objective_id=oid))
            o.label = oid
            o.is_federal = oid in federal
            o.direct_labor = money(o.direct_labor + vals["wages"])
            o.timesheet_backed_labor = money(o.timesheet_backed_labor + vals["backed"])
            o.fringe = money(o.direct_labor * fringe_rate)

    def apply_fringe(self, base_type: AllocationBase) -> Decimal:
        """Put fringe into the base, at this model's own fringe rate.

        2 CFR 200.1 includes applicable fringe in MTDC, so every objective's
        base has to carry it. `add_labor` used to take the rate from
        *whatever FRINGE rate was already on file* — which on the first
        computation after a seal is none, because the FRINGE rate is
        computed by this same call a few lines later.

        So the first compute built its base with **no fringe at all** and
        every subsequent one built it with fringe, and the same sealed set
        answered 37.82% then 34.82% — a rate that depended on how many times
        somebody pressed the button, converging silently on the right answer
        after one wasted press. Nothing caught it: the pools tie to
        themselves either way, and MTDC is deliberately not anchored because
        a second derivation of it in SQL would be one figure computed twice.

        The rate is a property of this model — the FRINGE pool over the wage
        base, both already built — so it is taken from here rather than from
        the rate table, and the computation stops depending on its own
        history.
        """
        base = self.base_amount(base_type, fringe_denominator=True)
        pool = self.pools[PoolType.FRINGE].allocable
        rate = ((pool / base).quantize(Decimal("0.0001"))
                if base else Decimal(0))
        for o in self.objectives.values():
            o.fringe = money(o.direct_labor * rate)
        return rate

    def administration_into_the_pool(self, objective_id: str) -> Decimal:
        """Move general-administration labour out of the base and into G&A.

        2 CFR 200 Appendix IV B puts the director's office, accounting and
        personnel administration *in* the indirect pool. Left as a cost
        objective it takes an allocation of indirect instead of forming part
        of it — the pool allocated to its own administration, recovering from
        nobody.

        Deliberately not applied to FUNDRAISING or UNALLOWABLE-ACTIVITY, and
        that is not an oversight: 200.413 and Appendix IV B.3.d make those
        bear indirect while recovering nothing, so they *are* benefiting
        objectives. General administration is the opposite case.

        Returns what moved, so the caller can say so rather than assert it.
        """
        o = self.objectives.get(objective_id)
        if o is None:
            return Decimal(0)
        moved = money(o.direct_labor + o.fringe + o.direct_nonlabor)
        if moved <= 0:
            return Decimal(0)
        # **The wage base is the payroll register and stays the payroll
        # register.** Administrative staff draw benefits like everybody else,
        # so their wages belong in the fringe denominator whether or not
        # their salary sits in the G&A pool — those are two different
        # questions and the first draft of this answered both at once.
        # Removing the objective took $264,444.90 out of the fringe base as
        # well and the rate went 21.90% to 25.58%, which
        # `WAGE_BASE_IS_THE_REGISTER` and `FRINGE_RATE_ON_THE_REGISTER` both
        # reported OPEN the moment it ran. That is exactly what migrations
        # 066 and 067 were built to catch, and they caught it.
        self.pooled_admin_labor = money(self.pooled_admin_labor + o.direct_labor)
        self.pooled_admin_fringe = money(self.pooled_admin_fringe + o.fringe)
        self.pools[PoolType.GA].gross = money(
            self.pools[PoolType.GA].gross + moved)
        # Removed from the base entirely rather than zeroed in place: an
        # objective carrying nothing would still take an allocation of zero
        # and print as a row, which reads as "administration bore no
        # indirect" when what happened is that it stopped being an objective.
        del self.objectives[objective_id]
        return moved

    def add_carve_out(self, pool_type: PoolType, carve: CarveOut) -> None:
        self.pools[pool_type].carve_outs.append(carve)

    # -- rates -------------------------------------------------------------

    def base_amount(self, base_type: AllocationBase,
                    include: set[str] | None = None, *,
                    fringe_denominator: bool = False) -> Decimal:
        """What a rate is taken over.

        `fringe_denominator` says which of two questions is being asked,
        because the base *type* cannot: `SALARIES_WAGES` is legitimately
        either the payroll the fringe pool is spread over or the base an
        indirect pool is allocated on, and a model that guesses from the
        type is answering two questions with one signal.

        It only matters once administration has moved into the G&A pool.
        There, the same wages are **out of the allocation base** — they are
        no longer a benefiting objective — and **still on the payroll**,
        because administrative staff draw benefits like everybody else. The
        first draft of this inferred it from the base type, which silently
        returned wages-without-fringe for `SALARIES_FRINGE` and would have
        under-stated a fringe rate taken over that base.
        """
        total = Decimal(0)
        for o in self.objectives.values():
            if include is not None and o.objective_id not in include:
                continue
            if base_type is AllocationBase.MTDC:
                total += o.mtdc
            elif base_type is AllocationBase.TOTAL_DIRECT:
                total += o.total_direct
            elif base_type is AllocationBase.SALARIES_WAGES:
                total += o.direct_labor
            elif base_type is AllocationBase.SALARIES_FRINGE:
                total += o.direct_labor + o.fringe
        # `include` is a filter over objectives, and moved administration is
        # no longer one, so it comes back only on the unfiltered ask — a rate
        # over a named subset of objectives is asking a different question.
        if fringe_denominator and include is None:
            if base_type is AllocationBase.SALARIES_WAGES:
                total += self.pooled_admin_labor
            elif base_type is AllocationBase.SALARIES_FRINGE:
                total += self.pooled_admin_labor + self.pooled_admin_fringe
        return money(total)

    def compute_rates(self, fringe_base: Decimal) -> dict[str, Decimal]:
        if not self.decisions.sealed:
            raise RuntimeError(
                "Cannot compute a rate from an unsealed decision set. "
                "Seal the classifications first — the rate must be a "
                "consequence of the judgments, not an input to them."
            )
        seal = self.decisions.seal_hash

        fringe_pool = self.pools[PoolType.FRINGE].allocable
        self.rates["FRINGE"] = (fringe_pool / fringe_base).quantize(Decimal("0.0001")) \
            if fringe_base else Decimal(0)

        oh_base = self.base_amount(self.pools[PoolType.OVERHEAD].base_type)
        ga_base = self.base_amount(self.pools[PoolType.GA].base_type)

        self.rates["OVERHEAD"] = (self.pools[PoolType.OVERHEAD].allocable / oh_base
                                  ).quantize(Decimal("0.0001")) if oh_base else Decimal(0)
        self.rates["G&A"] = (self.pools[PoolType.GA].allocable / ga_base
                             ).quantize(Decimal("0.0001")) if ga_base else Decimal(0)
        combined_pool = self.pools[PoolType.OVERHEAD].allocable + self.pools[PoolType.GA].allocable
        self.rates["INDIRECT_COMBINED"] = (combined_pool / ga_base
                                           ).quantize(Decimal("0.0001")) if ga_base else Decimal(0)

        for k in self.rates:
            self.rate_provenance[k] = seal
        return dict(self.rates)

    # -- allocation --------------------------------------------------------

    def allocate(self, use_combined: bool = True) -> None:
        if not self.rates:
            raise RuntimeError("Compute rates before allocating.")
        for o in self.objectives.values():
            o.allocated.clear()
            if use_combined:
                o.allocated["INDIRECT"] = money(o.mtdc * self.rates["INDIRECT_COMBINED"])
            else:
                o.allocated["OVERHEAD"] = money(o.mtdc * self.rates["OVERHEAD"])
                o.allocated["G&A"] = money(o.mtdc * self.rates["G&A"])

        # Per-objective rounding leaves a residual of a few dollars against the
        # pool. Assign it to the largest objective so the allocation ties to the
        # cent, and disclose it — an allocation that does not tie is a finding.
        available = money(self.pools[PoolType.OVERHEAD].allocable
                          + self.pools[PoolType.GA].allocable)
        distributed = money(sum(o.indirect for o in self.objectives.values()))
        residual = money(available - distributed)
        if residual and self.objectives:
            largest = max(self.objectives.values(), key=lambda o: o.mtdc)
            key = "INDIRECT" if use_combined else "G&A"
            largest.allocated[key] = money(largest.allocated.get(key, Decimal(0)) + residual)
            self.rounding_residual = residual

    # -- proofs ------------------------------------------------------------

    def reconciliation(self, ledger_total: Decimal) -> dict[str, Decimal]:
        pooled = money(sum(p.gross for p in self.pools.values()))  # account-level only
        return {
            "ledger_total": money(ledger_total),
            "classified": pooled,
            "unclassified": self.unclassified,
            "variance": money(pooled + self.unclassified - ledger_total),
        }

    def allocation_proof(self) -> dict[str, Decimal]:
        """Every allocable indirect dollar must land on exactly one objective."""
        available = money(self.pools[PoolType.OVERHEAD].allocable
                          + self.pools[PoolType.GA].allocable)
        distributed = money(sum(o.indirect for o in self.objectives.values()))
        return {
            "allocable": available,
            "distributed": distributed,
            "variance": money(distributed - available),
        }
