"""Fully burdened cost buildup (spec 4 and 5).

Spec invariant 3: fully burdened actual cost is built upstream, before any
recovery analysis. Nothing in this module knows what was billed.

The buildup is::

    Direct Labor
  + Fringe
  + Direct Nonlabor
  + Facilities
  + G&A
  = Fully Burdened Actual Cost

Django is not imported here. The buildup is pure arithmetic over Decimals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from fcs.money import ZERO, money, quantize_money, rate as to_rate, safe_divide

__all__ = [
    "SubawardCost",
    "MTDCBase",
    "RateSet",
    "BurdenBuildup",
    "build_mtdc_base",
    "apply_burden",
    "MTDC_SUBAWARD_CAP_PRE_2024",
    "MTDC_SUBAWARD_CAP_POST_2024",
    "UNIFORM_GUIDANCE_2024_EFFECTIVE",
    "subaward_cap_for",
]

#: 2 CFR 200.1 "Modified Total Direct Cost" -- the per-subaward amount included
#: in the base. Raised by the 2024 Uniform Guidance revisions (89 FR 30046).
MTDC_SUBAWARD_CAP_PRE_2024 = Decimal("25000")
MTDC_SUBAWARD_CAP_POST_2024 = Decimal("50000")

#: The 2024 revisions apply to awards issued on or after this date.
UNIFORM_GUIDANCE_2024_EFFECTIVE = date(2024, 10, 1)


def subaward_cap_for(award_date: date | None) -> Decimal:
    """Return the MTDC per-subaward cap applicable to an award issued on a date.

    Both America Makes agreements in hand predate the 2024 revisions -- Hybrid
    Phase 2 (2023-09-08) and Project 88 / LTM (2024-09-24) -- so both carry the
    $25,000 cap, not $50,000.
    """
    if award_date is None or award_date < UNIFORM_GUIDANCE_2024_EFFECTIVE:
        return MTDC_SUBAWARD_CAP_PRE_2024
    return MTDC_SUBAWARD_CAP_POST_2024


@dataclass(frozen=True)
class SubawardCost:
    """One subaward, for MTDC base purposes.

    ``is_subrecipient`` records the 2 CFR 200.331 determination. A *contractor*
    (vendor) is included in MTDC in full as "services"; a *subrecipient* is
    included only up to the cap. Getting this wrong in either direction misstates
    the base, so the determination is carried on the record rather than assumed.
    """

    identifier: str
    amount: Decimal
    is_subrecipient: bool
    determination_note: str = ""

    def base_included(self, cap: Decimal) -> Decimal:
        if not self.is_subrecipient:
            return self.amount
        return min(self.amount, cap)

    def base_excluded(self, cap: Decimal) -> Decimal:
        return quantize_money(self.amount - self.base_included(cap))


@dataclass(frozen=True)
class MTDCBase:
    """A modified total direct cost base with its exclusions itemized.

    Every exclusion carries its authority so the base can print itself as a
    workpaper.
    """

    direct_labor: Decimal = ZERO
    fringe: Decimal = ZERO
    materials_and_supplies: Decimal = ZERO
    services: Decimal = ZERO
    travel: Decimal = ZERO
    other_direct: Decimal = ZERO
    subawards_included: Decimal = ZERO

    # Excluded from MTDC by 2 CFR 200.1.
    equipment: Decimal = ZERO
    capital_expenditures: Decimal = ZERO
    participant_support: Decimal = ZERO
    rental_costs: Decimal = ZERO
    tuition_and_scholarships: Decimal = ZERO
    subawards_excluded: Decimal = ZERO

    @property
    def base(self) -> Decimal:
        """The MTDC base -- what an indirect rate is applied to."""
        return quantize_money(
            self.direct_labor
            + self.fringe
            + self.materials_and_supplies
            + self.services
            + self.travel
            + self.other_direct
            + self.subawards_included
        )

    @property
    def total_excluded(self) -> Decimal:
        return quantize_money(
            self.equipment
            + self.capital_expenditures
            + self.participant_support
            + self.rental_costs
            + self.tuition_and_scholarships
            + self.subawards_excluded
        )

    @property
    def total_direct_cost(self) -> Decimal:
        """Total direct cost -- the base plus everything excluded from it."""
        return quantize_money(self.base + self.total_excluded)

    def exclusion_schedule(self) -> list[tuple[str, Decimal, str]]:
        """Itemized exclusions with their authority, for the workpaper."""
        rows = [
            ("Equipment", self.equipment, "2 CFR 200.1 (MTDC)"),
            ("Capital expenditures", self.capital_expenditures, "2 CFR 200.1 (MTDC)"),
            ("Participant support costs", self.participant_support, "2 CFR 200.1 (MTDC)"),
            ("Rental costs", self.rental_costs, "2 CFR 200.1 (MTDC)"),
            (
                "Tuition remission and scholarships",
                self.tuition_and_scholarships,
                "2 CFR 200.1 (MTDC)",
            ),
            (
                "Subaward amounts above the per-subaward cap",
                self.subawards_excluded,
                "2 CFR 200.1 (MTDC)",
            ),
        ]
        return [r for r in rows if r[1] != ZERO]


def build_mtdc_base(
    *,
    direct_labor=ZERO,
    fringe=ZERO,
    materials_and_supplies=ZERO,
    services=ZERO,
    travel=ZERO,
    other_direct=ZERO,
    equipment=ZERO,
    capital_expenditures=ZERO,
    participant_support=ZERO,
    rental_costs=ZERO,
    tuition_and_scholarships=ZERO,
    subawards: Iterable[SubawardCost] = (),
    award_date: date | None = None,
) -> MTDCBase:
    """Assemble an :class:`MTDCBase`, applying the per-subaward cap."""
    cap = subaward_cap_for(award_date)
    included = ZERO
    excluded = ZERO
    for sub in subawards:
        included += sub.base_included(cap)
        excluded += sub.base_excluded(cap)

    return MTDCBase(
        direct_labor=money(direct_labor, field="direct_labor"),
        fringe=money(fringe, field="fringe"),
        materials_and_supplies=money(
            materials_and_supplies, field="materials_and_supplies"
        ),
        services=money(services, field="services"),
        travel=money(travel, field="travel"),
        other_direct=money(other_direct, field="other_direct"),
        subawards_included=quantize_money(included),
        equipment=money(equipment, field="equipment"),
        capital_expenditures=money(capital_expenditures, field="capital_expenditures"),
        participant_support=money(participant_support, field="participant_support"),
        rental_costs=money(rental_costs, field="rental_costs"),
        tuition_and_scholarships=money(
            tuition_and_scholarships, field="tuition_and_scholarships"
        ),
        subawards_excluded=quantize_money(excluded),
    )


@dataclass(frozen=True)
class RateSet:
    """The rates in force for a period under one scenario.

    ``facilities_rate`` is optional. Under the two-tier structure recommended for
    YBI, facilities is folded into a single indirect pool and this stays zero.
    """

    fringe_rate: Decimal = ZERO
    facilities_rate: Decimal = ZERO
    ga_rate: Decimal = ZERO
    scenario: str = ""
    period: str = ""

    @classmethod
    def of(
        cls,
        *,
        fringe_rate=ZERO,
        facilities_rate=ZERO,
        ga_rate=ZERO,
        scenario: str = "",
        period: str = "",
    ) -> "RateSet":
        return cls(
            fringe_rate=to_rate(fringe_rate, field="fringe_rate"),
            facilities_rate=to_rate(facilities_rate, field="facilities_rate"),
            ga_rate=to_rate(ga_rate, field="ga_rate"),
            scenario=scenario,
            period=period,
        )


@dataclass(frozen=True)
class BurdenBuildup:
    """Fully burdened actual cost for one objective-period (spec 5)."""

    objective_id: str
    period: str
    direct_labor: Decimal = ZERO
    fringe: Decimal = ZERO
    direct_nonlabor: Decimal = ZERO
    facilities: Decimal = ZERO
    ga: Decimal = ZERO
    other_excluded: Decimal = ZERO
    mtdc_base: Decimal = ZERO
    rate_set: RateSet | None = None

    @property
    def fully_burdened(self) -> Decimal:
        """Spec 5. ``other_excluded`` is carried but not burdened."""
        return quantize_money(
            self.direct_labor
            + self.fringe
            + self.direct_nonlabor
            + self.facilities
            + self.ga
        )

    @property
    def total_indirect(self) -> Decimal:
        return quantize_money(self.facilities + self.ga)

    @property
    def effective_indirect_rate(self) -> Decimal:
        """Indirect recovered divided by the MTDC base actually used."""
        return safe_divide(self.total_indirect, self.mtdc_base)

    def as_rows(self) -> Sequence[tuple[str, Decimal]]:
        """Ordered buildup lines, for display and for the workpaper."""
        return (
            ("Direct labor", self.direct_labor),
            ("Fringe", self.fringe),
            ("Direct nonlabor", self.direct_nonlabor),
            ("Facilities", self.facilities),
            ("G&A", self.ga),
            ("Fully burdened actual cost", self.fully_burdened),
        )


def apply_burden(
    *,
    objective_id: str,
    period: str,
    direct_labor,
    base: MTDCBase,
    rates: RateSet,
    other_excluded=ZERO,
) -> BurdenBuildup:
    """Apply a :class:`RateSet` to a direct cost population.

    Fringe follows labor to its destination (spec 4.3), so it is computed on
    direct labor rather than on the whole base. Facilities and G&A are applied
    to MTDC.

    The ``base`` passed in should already carry the fringe amount, since fringe
    is part of MTDC. This function recomputes fringe from ``direct_labor`` and
    the fringe rate and does not second-guess the base it was handed -- if the
    two disagree, the control framework surfaces it rather than this function
    silently reconciling them.
    """
    labor = money(direct_labor, field="direct_labor")
    fringe = quantize_money(labor * rates.fringe_rate)
    mtdc = base.base

    facilities = quantize_money(mtdc * rates.facilities_rate)
    ga = quantize_money(mtdc * rates.ga_rate)

    direct_nonlabor = quantize_money(mtdc - labor - base.fringe)

    return BurdenBuildup(
        objective_id=objective_id,
        period=period,
        direct_labor=labor,
        fringe=fringe,
        direct_nonlabor=direct_nonlabor,
        facilities=facilities,
        ga=ga,
        other_excluded=money(other_excluded, field="other_excluded"),
        mtdc_base=mtdc,
        rate_set=rates,
    )
