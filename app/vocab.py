"""The words the database will accept, in one place.

Every one of these mirrors a Postgres enum. They are here so a bad value is
refused by the request model — a 422 naming the values that are allowed —
rather than reaching the database and coming back as a 500 that says
"invalid input value for enum" to a person who did nothing wrong.

Keeping them beside each other is also how the drift gets noticed:
``test_vocab.py`` reads the enums out of the database and fails if any of
these has fallen behind.
"""

from __future__ import annotations

from enum import StrEnum


class Pool(StrEnum):
    DIRECT = "DIRECT"
    FRINGE = "FRINGE"
    OVERHEAD = "OVERHEAD"
    GA = "G&A"
    RENTAL_DIRECT = "RENTAL_DIRECT"
    FUNDRAISING = "FUNDRAISING"
    UNALLOWABLE = "UNALLOWABLE"
    EXCLUDED = "EXCLUDED"


class Function990(StrEnum):
    PROGRAM = "PROGRAM"
    MANAGEMENT_AND_GENERAL = "MANAGEMENT_AND_GENERAL"
    FUNDRAISING = "FUNDRAISING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FederalTreatment(StrEnum):
    ALLOWABLE = "ALLOWABLE"
    UNALLOWABLE = "UNALLOWABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"


class EvidenceGrade(StrEnum):
    UNSUPPORTED = "UNSUPPORTED"
    TEST_ASSUMPTION = "TEST_ASSUMPTION"
    MANAGEMENT_RECONSTRUCTION = "MANAGEMENT_RECONSTRUCTION"
    CORROBORATED = "CORROBORATED"
    VERIFIED = "VERIFIED"


class TimeBasis(StrEnum):
    AS_WORKED = "AS_WORKED"
    CALENDAR = "CALENDAR"
    PROJECT_RECORD = "PROJECT_RECORD"
    DELIVERABLE = "DELIVERABLE"
    RECALL = "RECALL"
    #: Written only by POST /api/timesheet/adopt. Deliberately absent from
    #: the basis picker: a person typing a day cannot assert that the
    #: organisation reconstructed it for them.
    ADOPTED = "ADOPTED"


class EmploymentStatus(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    TEMPORARY = "TEMPORARY"
    INTERN = "INTERN"
    CONTRACT = "CONTRACT"


class SpaceUse(StrEnum):
    TENANT = "TENANT"
    PROGRAM = "PROGRAM"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    SHARED_LAB = "SHARED_LAB"
    COMMON = "COMMON"
    VACANT = "VACANT"
    COMMITTED = "COMMITTED"


class OccupancyStatus(StrEnum):
    OCCUPIED = "OCCUPIED"
    VACANT = "VACANT"
    INTERNAL = "INTERNAL"
    COMMITTED = "COMMITTED"
    COMMON = "COMMON"


class AccessPolicy(StrEnum):
    FREE = "FREE"
    SUBSIDIZED = "SUBSIDIZED"
    CHARGED = "CHARGED"
    INTERNAL = "INTERNAL"


class InKindKind(StrEnum):
    THIRD_PARTY_SPACE = "THIRD_PARTY_SPACE"
    THIRD_PARTY_EQUIPMENT = "THIRD_PARTY_EQUIPMENT"
    THIRD_PARTY_SERVICES = "THIRD_PARTY_SERVICES"
    OWN_SPACE_SUBSIDY = "OWN_SPACE_SUBSIDY"
    OWN_EQUIPMENT_SUBSIDY = "OWN_EQUIPMENT_SUBSIDY"
    UNRECOVERED_INDIRECT = "UNRECOVERED_INDIRECT"


class LaneKind(StrEnum):
    BASELINE = "BASELINE"
    CANDIDATE = "CANDIDATE"
    SANDBOX = "SANDBOX"


class OrgRole(StrEnum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    CONTROLLER = "CONTROLLER"
    EMPLOYEE = "EMPLOYEE"
    AUDITOR = "AUDITOR"


class PortfolioVocab(StrEnum):
    CONTROLLER = "CONTROLLER"
    INVENTORY = "INVENTORY"
    PROJECT = "PROJECT"
    FACILITIES = "FACILITIES"
    OFFICE = "OFFICE"


class ReconcilingKind(StrEnum):
    RECLASS_AFTER_EXPORT = "RECLASS_AFTER_EXPORT"
    TIMING = "TIMING"
    PRESENTATION = "PRESENTATION"
    ROUNDING = "ROUNDING"
    SOURCE_DEFECT = "SOURCE_DEFECT"


#: enum name in Postgres -> the class that mirrors it. The drift test walks
#: this, so adding one here is what puts it under test.
MIRRORS = {
    "pool_type": Pool,
    "function_990": Function990,
    "federal_treatment": FederalTreatment,
    "evidence_grade": EvidenceGrade,
    "time_basis": TimeBasis,
    "employment_status": EmploymentStatus,
    "lane_kind": LaneKind,
    "space_use": SpaceUse,
    "occupancy_status": OccupancyStatus,
    "access_policy": AccessPolicy,
    "in_kind_kind": InKindKind,
    "reconciling_kind": ReconcilingKind,
    "org_role": OrgRole,
    "portfolio": PortfolioVocab,
}
