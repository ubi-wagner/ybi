"""
YBI Cost Allocation Engine — core domain model.

Design rule that drives everything here: the ledger is immutable and every
derived number must reconcile back to it. Classification, pooling, rate
computation and allocation are overlays. Nothing in this package writes to
source data.

"Without prejudice" is enforced structurally, not by convention:
classification decisions are recorded in a DecisionSet that is hashed and
sealed before any rate is computed. The rate carries the hash of the decision
set it came from, so the question "did you tune the classifications to hit a
number?" has a documentary answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Iterable

CENT = Decimal("0.01")


def money(x) -> Decimal:
    """Everything monetary is Decimal, rounded half-up to the cent."""
    if isinstance(x, Decimal):
        d = x
    elif x is None or x == "":
        d = Decimal(0)
    else:
        d = Decimal(str(x).replace(",", "").replace("$", "").strip() or 0)
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Vocabulary — 2 CFR 200 concepts kept orthogonal on purpose.
#
# One enum cannot serve both Form 990 Part IX and 2 CFR 200 Subpart E. A cost
# that is federally unallowable (fundraising, interest, bad debt) is still a
# reportable 990 expense, and lobbying is unallowable AND triggers Schedule C.
# So each ledger line carries four independent dimensions.
# ---------------------------------------------------------------------------

class PoolType(str, Enum):
    DIRECT = "DIRECT"                    # assigned to a final cost objective
    FRINGE = "FRINGE"                    # 200.431
    OVERHEAD = "OVERHEAD"                # facilities & related, Appendix IV
    GA = "G&A"                           # general & administrative
    RENTAL_DIRECT = "RENTAL_DIRECT"      # tenant space — not allocable to awards
    FUNDRAISING = "FUNDRAISING"          # 200.442 — unallowable, bears indirect
    UNALLOWABLE = "UNALLOWABLE"          # 200.420-475 — bears indirect, never recovered
    EXCLUDED = "EXCLUDED"                # outside the cost model entirely


class Function990(str, Enum):
    PROGRAM = "PROGRAM"
    MGMT_GENERAL = "MANAGEMENT_AND_GENERAL"
    FUNDRAISING = "FUNDRAISING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FederalTreatment(str, Enum):
    ALLOWABLE = "ALLOWABLE"
    UNALLOWABLE = "UNALLOWABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"


class EvidenceGrade(str, Enum):
    """Ordered weakest to strongest. Default is UNSUPPORTED — quality is earned.

    A blanket grade applied to every row asserts a conclusion nobody reached,
    which is worse in an audit than an honest blank.
    """
    UNSUPPORTED = "UNSUPPORTED"
    TEST_ASSUMPTION = "TEST_ASSUMPTION"
    MANAGEMENT_RECONSTRUCTION = "MANAGEMENT_RECONSTRUCTION"
    CORROBORATED = "CORROBORATED"
    VERIFIED = "VERIFIED"

    @property
    def rank(self) -> int:
        return list(EvidenceGrade).index(self)

    @property
    def federally_supportable(self) -> bool:
        return self.rank >= EvidenceGrade.MANAGEMENT_RECONSTRUCTION.rank


class AllocationBase(str, Enum):
    MTDC = "MTDC"                        # 200.1 modified total direct cost
    TOTAL_DIRECT = "TOTAL_DIRECT"
    SALARIES_WAGES = "SALARIES_WAGES"
    SALARIES_FRINGE = "SALARIES_FRINGE"
    SQUARE_FEET = "SQUARE_FEET"
    TOTAL_COST_INPUT = "TOTAL_COST_INPUT"


# ---------------------------------------------------------------------------
# Control totals — the ledger boundary every derived figure must respect.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlTotal:
    control_id: str
    description: str
    expected: Decimal
    source: str
    mandatory: bool = True
    tolerance: Decimal = CENT


@dataclass
class TieOut:
    control_id: str
    description: str
    expected: Decimal
    actual: Decimal
    mandatory: bool
    tolerance: Decimal

    @property
    def variance(self) -> Decimal:
        return money(self.actual - self.expected)

    @property
    def passed(self) -> bool:
        return abs(self.variance) <= self.tolerance

    def __str__(self) -> str:
        flag = "PASS" if self.passed else ("FAIL" if self.mandatory else "WARN")
        return (f"[{flag}] {self.control_id:<22} expected {self.expected:>15,.2f}  "
                f"actual {self.actual:>15,.2f}  variance {self.variance:>13,.2f}")


class ControlRegister:
    """The bound. Nothing leaves the engine without passing through here."""

    def __init__(self, controls: Iterable[ControlTotal] = ()):
        self._controls: dict[str, ControlTotal] = {c.control_id: c for c in controls}

    def add(self, control: ControlTotal) -> None:
        self._controls[control.control_id] = control

    def test(self, control_id: str, actual) -> TieOut:
        c = self._controls[control_id]
        return TieOut(c.control_id, c.description, c.expected, money(actual),
                      c.mandatory, c.tolerance)

    def test_all(self, actuals: dict[str, object]) -> list[TieOut]:
        return [self.test(cid, actuals[cid]) for cid in self._controls if cid in actuals]

    @property
    def ids(self) -> list[str]:
        return list(self._controls)


# ---------------------------------------------------------------------------
# Classification decisions — append-only, evidence-bearing, reversible.
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """One classification judgment, applied to a group of ledger lines.

    Tom works at group grain (account × vendor); the decision fans out to rows.
    Rationale and evidence are required before a decision can be marked
    supported, which is what makes the resulting pool defensible.
    """
    decision_id: str
    scope: str                       # e.g. "account=5227 Portfolio consulting"
    line_ids: tuple[str, ...]
    pool: PoolType
    function_990: Function990
    federal: FederalTreatment
    objective_id: str | None
    evidence: EvidenceGrade
    rationale: str
    evidence_refs: tuple[str, ...] = ()
    decided_by: str = ""
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supersedes: str | None = None
    citation: str | None = None      # 2 CFR reference where one applies

    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.line_ids:
            errs.append(f"{self.decision_id}: decision affects no ledger lines")
        if self.pool is PoolType.DIRECT and not self.objective_id:
            errs.append(f"{self.decision_id}: direct cost requires a final cost objective")
        if self.pool is not PoolType.DIRECT and self.objective_id:
            errs.append(f"{self.decision_id}: pooled cost must not carry an objective")
        if self.evidence.federally_supportable and not self.rationale.strip():
            errs.append(f"{self.decision_id}: supported grades require a written rationale")
        if (self.evidence is EvidenceGrade.VERIFIED and not self.evidence_refs):
            errs.append(f"{self.decision_id}: VERIFIED requires at least one evidence reference")
        if (self.federal is FederalTreatment.ALLOWABLE
                and self.pool in (PoolType.FUNDRAISING, PoolType.UNALLOWABLE)):
            errs.append(f"{self.decision_id}: fundraising/unallowable cannot be federally allowable")
        return errs

    def fingerprint(self) -> str:
        payload = {
            "scope": self.scope,
            "lines": sorted(self.line_ids),
            "pool": self.pool.value,
            "function_990": self.function_990.value,
            "federal": self.federal.value,
            "objective_id": self.objective_id,
            "evidence": self.evidence.value,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class DecisionSet:
    """A sealed body of classification judgments.

    Seal before computing a rate. The seal hash travels with the rate, so a
    reviewer can prove the classifications were not adjusted afterwards to
    produce a more favourable number.
    """

    def __init__(self, period: str):
        self.period = period
        self._decisions: dict[str, Decision] = {}
        self._sealed_hash: str | None = None
        self._sealed_at: str | None = None

    def record(self, decision: Decision) -> None:
        if self._sealed_hash:
            raise RuntimeError(
                "Decision set is sealed. Unseal and re-record to change a "
                "classification; the rate must then be recomputed and the "
                "prior rate marked superseded."
            )
        errs = decision.validate()
        if errs:
            raise ValueError("; ".join(errs))
        if decision.supersedes:
            self._decisions.pop(decision.supersedes, None)
        self._decisions[decision.decision_id] = decision

    def unseal(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Unsealing requires a reason for the audit trail.")
        self._sealed_hash = None
        self._sealed_at = None

    def seal(self) -> str:
        fps = sorted(d.fingerprint() for d in self._decisions.values())
        self._sealed_hash = hashlib.sha256("".join(fps).encode()).hexdigest()
        self._sealed_at = datetime.now(timezone.utc).isoformat()
        return self._sealed_hash

    @property
    def sealed(self) -> bool:
        return self._sealed_hash is not None

    @property
    def seal_hash(self) -> str | None:
        return self._sealed_hash

    @property
    def sealed_at(self) -> str | None:
        return self._sealed_at

    def __iter__(self):
        return iter(self._decisions.values())

    def __len__(self) -> int:
        return len(self._decisions)

    def coverage(self, all_line_ids: set[str]) -> tuple[set[str], set[str]]:
        decided = set()
        for d in self._decisions.values():
            decided.update(d.line_ids)
        return decided & all_line_ids, all_line_ids - decided

    def to_records(self) -> list[dict]:
        out = []
        for d in self._decisions.values():
            r = asdict(d)
            r["pool"] = d.pool.value
            r["function_990"] = d.function_990.value
            r["federal"] = d.federal.value
            r["evidence"] = d.evidence.value
            r["line_count"] = len(d.line_ids)
            r["line_ids"] = ""
            r["evidence_refs"] = "; ".join(d.evidence_refs)
            out.append(r)
        return out
