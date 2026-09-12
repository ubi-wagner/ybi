"""
Awards: contract terms, invoice reconstruction, and the constraint tests that
decide whether a restated invoice is issuable.

A true-up is only issuable if every hard constraint passes. Where one fails,
the engine emits an acknowledged deficiency instead of an invoice — Eric's
"reissue or acknowledge" fork, made explicit so neither outcome is silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from .core import EvidenceGrade, money


class RateMethod(str, Enum):
    DE_MINIMIS_10 = "DE_MINIMIS_10"     # 200.414(f), awards before 10/1/2024
    DE_MINIMIS_15 = "DE_MINIMIS_15"     # 200.414(f) as revised 2024
    NEGOTIATED = "NEGOTIATED"           # NICRA or pass-through negotiated (200.332)


class Disposition(str, Enum):
    INVOICE_ADDITIONAL = "INVOICE_ADDITIONAL"
    CREDIT_DUE = "CREDIT_DUE"
    FORGONE_BY_ELECTION = "FORGONE_BY_ELECTION"
    DEFICIENCY_ACKNOWLEDGED = "DEFICIENCY_ACKNOWLEDGED"
    NO_ACTION = "NO_ACTION"


@dataclass
class Award:
    award_id: str
    objective_id: str
    sponsor: str
    prime: str
    instrument: str                      # e.g. "Cost reimbursement, no fee"
    ceiling_federal: Decimal
    cost_share_required: Decimal
    period_start: date
    period_end: date
    rate_method: RateMethod
    budget_lines: dict[str, Decimal] = field(default_factory=dict)
    billed_to_date: Decimal = Decimal(0)
    billed_after_term: Decimal = Decimal(0)
    cost_share_tracked: Decimal = Decimal(0)
    citation: str = ""


@dataclass
class Constraint:
    """One contract test, and whether it could be run at all.

    `evaluable` is the three-state this repository already uses everywhere a
    control meets missing data — `v_award_budget_check`'s unread award,
    `v_award_citation_check`'s NO TEXT LAYER, the register's NO DATA. **A
    control that cannot be evaluated has not passed**, and the alternative is
    the defect this engine was found in: an award reporting INVOICE_ISSUABLE
    because nobody had tested anything.
    """
    code: str
    citation: str
    description: str
    passed: bool
    detail: str
    blocking: bool = True
    evaluable: bool = True


@dataclass
class TrueUp:
    award: Award
    direct: Decimal
    indirect: Decimal
    rate_applied: Decimal
    rate_seal: str
    constraints: list[Constraint] = field(default_factory=list)

    @property
    def claimable_uncapped(self) -> Decimal:
        return money(self.direct + self.indirect)

    @property
    def claimable(self) -> Decimal:
        return money(min(self.claimable_uncapped, self.award.ceiling_federal))

    @property
    def ceiling_bite(self) -> Decimal:
        return money(self.claimable_uncapped - self.claimable)

    @property
    def delta(self) -> Decimal:
        return money(self.claimable - self.award.billed_to_date)

    @property
    def blocked(self) -> bool:
        return any(c.blocking and not c.passed for c in self.constraints)

    def disposition(self, forgo_upside: bool) -> Disposition:
        if self.delta < 0:
            return Disposition.CREDIT_DUE
        if self.delta == 0:
            return Disposition.NO_ACTION
        if self.blocked:
            return Disposition.DEFICIENCY_ACKNOWLEDGED
        return (Disposition.FORGONE_BY_ELECTION if forgo_upside
                else Disposition.INVOICE_ADDITIONAL)


def test_constraints(award: Award, direct: Decimal, indirect: Decimal,
                     rate: Decimal, evidence: EvidenceGrade | None,
                     rate_method: RateMethod) -> list[Constraint]:
    """Every constraint, each carrying whether it could be run.

    `evidence` is optional because it genuinely can be absent: an award with
    no cost classified to its objective has no evidence grade to test, and
    saying so is the honest answer. Everything else here is read off the
    agreement and the invoices, which are on the record or the award has not
    been set up.
    """
    claim = money(direct + indirect)
    cs: list[Constraint] = []

    cs.append(Constraint(
        "CEILING", "Agreement §4.2",
        "Claims may not exceed the obligated federal amount",
        claim <= award.ceiling_federal,
        f"claim {claim:,.2f} vs ceiling {award.ceiling_federal:,.2f}"))

    cs.append(Constraint(
        "TERM", "Agreement §10.1",
        "Costs must be incurred within the period of performance",
        award.billed_after_term == 0,
        f"{award.billed_after_term:,.2f} invoiced after {award.period_end:%d %b %Y}"))

    cs.append(Constraint(
        "COST_SHARE", "2 CFR 200.306",
        "Committed cost share must be met and documented",
        award.cost_share_tracked >= award.cost_share_required,
        f"tracked {award.cost_share_tracked:,.2f} of {award.cost_share_required:,.2f} required"))

    cs.append(Constraint(
        "RATE_METHOD", "2 CFR 200.414(f)",
        "One rate method applied consistently across all federal awards",
        award.rate_method is rate_method,
        f"award set to {award.rate_method.value}, model applying {rate_method.value}"))

    cs.append(Constraint(
        "EVIDENCE", "2 CFR 200.403(g)",
        "Charged costs must be adequately documented",
        bool(evidence and evidence.federally_supportable),
        (f"supporting evidence graded {evidence.value}" if evidence else
         "no cost is classified to this objective yet, so there is no "
         "evidence grade to test — unevaluable, which is not a pass"),
        evaluable=evidence is not None))

    budget_labor = award.budget_lines.get("LABOR")
    if budget_labor is not None:
        cs.append(Constraint(
            "BUDGET_LINE", "Agreement Schedule B",
            "Claims by line should track the approved budget",
            direct <= budget_labor * Decimal("1.10"),
            f"direct {direct:,.2f} vs approved labor line {budget_labor:,.2f}",
            blocking=False))

    return cs
