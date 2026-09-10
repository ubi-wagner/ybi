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


class EmploymentStatus(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    TEMPORARY = "TEMPORARY"
    INTERN = "INTERN"
    CONTRACT = "CONTRACT"


class LaneKind(StrEnum):
    BASELINE = "BASELINE"
    CANDIDATE = "CANDIDATE"
    SANDBOX = "SANDBOX"


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
}
