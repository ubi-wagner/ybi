"""Controlled vocabularies from the FCS Foundation Architecture Specification.

These values are contractual. They appear in the canonical 2025 package, in the
FCS 1.4 Apps Script implementation, and in the review surfaces YBI staff already
use. Changing a member's string value breaks canonical package import, so treat
this module as a schema.

Spec references are to FOUNDATION_ARCHITECTURE_SPEC.md sections.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceClass(StrEnum):
    """Spec 3.4 -- how a cost record came to exist."""

    BOOKED_ACTUAL = "BOOKED ACTUAL"
    ALLOCATED_ACTUAL = "ALLOCATED ACTUAL"
    RECONSTRUCTED_ACTUAL = "RECONSTRUCTED ACTUAL"
    ECONOMIC_ONLY = "ECONOMIC ONLY"


class CostDisposition(StrEnum):
    """Spec 3.4 -- the analytical treatment of a cost record."""

    DIRECT = "DIRECT"
    FRINGE = "FRINGE"
    FACILITIES = "FACILITIES"
    GA = "G&A"
    RENTAL_DIRECT = "RENTAL-DIRECT"
    FUNDRAISING_BP = "FUNDRAISING/B&P"
    COST_SHARE = "COST SHARE"
    EXCLUDED_UNALLOWABLE = "EXCLUDED/UNALLOWABLE"
    REVIEW = "REVIEW"


class EvidenceQuality(StrEnum):
    """Spec 6 -- independent of allowability and of cost disposition."""

    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    MANAGEMENT_RECONSTRUCTION = "MANAGEMENT RECONSTRUCTION"
    TEST_ASSUMPTION = "TEST ASSUMPTION"
    UNSUPPORTED = "UNSUPPORTED"


class ReviewStatus(StrEnum):
    """Spec 6 -- workflow state of a record."""

    OPEN = "OPEN"
    SUPPORT_NEEDED = "SUPPORT NEEDED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    EXCLUDED = "EXCLUDED"


class Allowability(StrEnum):
    """2 CFR 200 Subpart E status of a cost."""

    NOT_APPLICABLE = "NOT APPLICABLE"
    PENDING = "PENDING"
    ALLOWABLE = "ALLOWABLE"
    PARTIALLY_ALLOWABLE = "PARTIALLY ALLOWABLE"
    UNALLOWABLE = "UNALLOWABLE"


class Recoverability(StrEnum):
    """Contractual recoverability, distinct from allowability."""

    NOT_APPLICABLE = "NOT APPLICABLE"
    PENDING = "PENDING"
    RECOVERABLE = "RECOVERABLE"
    PARTIALLY_RECOVERABLE = "PARTIALLY RECOVERABLE"
    UNRECOVERABLE = "UNRECOVERABLE"
    COST_SHARE = "COST SHARE"


class ObjectiveType(StrEnum):
    """Spec 3.2 -- final cost / revenue objectives are peers."""

    FEDERAL_AWARD = "FEDERAL AWARD"
    STATE_LOCAL_PROGRAM = "STATE/LOCAL PROGRAM"
    RENTAL = "RENTAL"
    MANUFACTURING_SERVICES = "MANUFACTURING/SERVICES"
    FUNDRAISING = "FUNDRAISING"
    ADMINISTRATION = "ADMINISTRATION"
    PROGRAM = "PROGRAM"


class Function(StrEnum):
    """Spec 3.1 -- broad operating functions."""

    FEDERAL = "FEDERAL"
    STATE_LOCAL = "STATE/LOCAL"
    RENTAL = "RENTAL"
    MANUFACTURING = "MANUFACTURING"
    FUNDRAISING = "FUNDRAISING"
    ADMINISTRATION = "ADMINISTRATION"
    FACILITIES = "FACILITIES"
    PROGRAM = "PROGRAM"


class PoolKind(StrEnum):
    """Indirect cost pools. Spec 4.3, 4.4, 4.7."""

    FRINGE = "FRINGE"
    FACILITIES = "FACILITIES"
    GA = "G&A"


class BaseKind(StrEnum):
    """Allocation bases."""

    SALARIES_AND_WAGES = "S&W"
    MODIFIED_TOTAL_DIRECT_COST = "MTDC"
    TOTAL_DIRECT_COST = "TDC"
    SQUARE_FOOTAGE = "SQFT"
    HEADCOUNT = "HEADCOUNT"


class RateType(StrEnum):
    """2 CFR 200 Appendix IV section C rate types.

    The distinction matters for retroactive adjustment: a period billed under a
    PROVISIONAL rate is trued up when a FINAL rate is established for that same
    period. A de minimis election is not a provisional rate.
    """

    PROVISIONAL = "PROVISIONAL"
    FINAL = "FINAL"
    PREDETERMINED = "PREDETERMINED"
    FIXED_WITH_CARRYFORWARD = "FIXED"
    DE_MINIMIS = "DE MINIMIS"


class ScenarioStatus(StrEnum):
    """Lifecycle of a rate scenario.

    Only NEGOTIATED and FINAL scenarios may back a restated invoice. A scenario
    carrying TEST ASSUMPTION inputs may never leave DRAFT -- spec invariant 8.
    """

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    NEGOTIATED = "NEGOTIATED"
    FINAL = "FINAL"
    SUPERSEDED = "SUPERSEDED"


#: Scenario statuses that may support a restated invoice or a posted disposition.
POSTABLE_SCENARIO_STATUSES = frozenset(
    {ScenarioStatus.NEGOTIATED, ScenarioStatus.FINAL}
)

#: Evidence qualities that may never appear in a locked foundation -- spec 6.
UNLOCKABLE_EVIDENCE_QUALITIES = frozenset(
    {EvidenceQuality.TEST_ASSUMPTION, EvidenceQuality.UNSUPPORTED}
)

#: Cost dispositions that are removed from indirect pools entirely.
POOL_EXCLUDED_DISPOSITIONS = frozenset(
    {
        CostDisposition.EXCLUDED_UNALLOWABLE,
        CostDisposition.FUNDRAISING_BP,
        CostDisposition.COST_SHARE,
    }
)

#: FCS 1.4 invariant 10 -- the only objectives the America Makes downstream
#: disposition updater will accept.
AMERICA_MAKES_OBJECTIVES = ("DRIVE-AM", "HYBRID-II", "LTM")
