"""Attributing a difference between two source documents to specific lines.

A reconciliation with two outcomes — zero, or broken — gets forced to zero.
The third outcome is a difference that is *named*: this much, these lines,
this reason. That is what a reconciling item is in a workpaper.

Naming one by hand means finding which lines in an account add up to the
difference, which is a subset-sum problem and exactly the kind of arithmetic
nobody should do at eleven at night before a deadline. This module does it,
and refuses to guess: if more than one set of lines adds to the difference,
it says so and proposes nothing, because an attribution that could equally
have been a different set of lines is not evidence.

Pure. No database, no opinion about what the difference means — that
judgment stays with the controller, and the proposal is only ever a
proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations

from .core import money

#: Beyond this, "these four lines happen to add up" stops being evidence and
#: starts being numerology. A difference that needs five or more lines to
#: explain is better described in prose by whoever knows what happened.
MAX_LINES = 4


@dataclass(frozen=True)
class Candidate:
    """One ledger line that could be part of the explanation."""
    line_id: str
    amount: Decimal
    date: str = ""
    payee: str = ""
    memo: str = ""


@dataclass
class Attribution:
    """A difference, and the lines that account for it — or why not."""
    target: Decimal
    lines: list[Candidate] = field(default_factory=list)
    #: Distinct sets of lines reaching the target at the smallest size that
    #: reaches it, counted up to two — one is a proposal, more than one is a
    #: coincidence and proposes nothing, and the exact count of coincidences
    #: is not worth the search.
    solutions: int = 0
    searched: int = 0

    @property
    def unique(self) -> bool:
        return self.solutions == 1

    @property
    def total(self) -> Decimal:
        return money(sum((c.amount for c in self.lines), Decimal(0)))

    def why_not(self) -> str:
        if self.unique:
            return ""
        if self.solutions == 0:
            return (f"No combination of up to {MAX_LINES} lines in this "
                    f"account adds to {self.target}. The difference is not a "
                    f"whole number of lines moving, and needs an explanation "
                    f"in words.")
        return (f"More than one combination of lines adds to {self.target}. "
                f"Any one of them would be a guess, so none is proposed.")


def _cents(d: Decimal) -> int:
    return int(money(d) * 100)


def attribute(target: Decimal, candidates: list[Candidate],
              max_lines: int = MAX_LINES) -> Attribution:
    """Find the lines that add to `target`, if exactly one set does.

    Only lines running the same way as the target and no larger than it can
    be part of it — a difference of $280.40 cannot contain a $30,000 line —
    which is what keeps the search small enough to be exact rather than
    heuristic. Sizes are tried smallest first: two lines that add up is a
    better explanation than four that do, and stopping at the first size
    that produces an answer avoids proposing an elaborate story when a
    simple one fits.
    """
    t = _cents(target)
    if t == 0:
        return Attribution(target=money(target), solutions=0, searched=0)
    sign = 1 if t > 0 else -1
    pool = [(c, _cents(c.amount)) for c in candidates
            if _cents(c.amount) != 0
            and (_cents(c.amount) > 0) == (sign > 0)
            and abs(_cents(c.amount)) <= abs(t)]
    n = len(pool)

    def found(idxs: tuple[int, ...]) -> list[Candidate]:
        return [pool[i][0] for i in idxs]

    for size in range(1, max_lines + 1):
        hits: list[tuple[int, ...]] = []
        if size <= 2:
            for combo in combinations(range(n), size):
                if sum(pool[i][1] for i in combo) == t:
                    hits.append(combo)
                    if len(hits) > 1:
                        break
        else:
            # Meet in the middle. Sums of every pair, then look for the
            # complement — the alternative is C(n, 4), which for a
            # hundred-odd lines is several million tuples per difference.
            half = size // 2          # 1 for size 3, 2 for size 4
            rest = size - half
            index: dict[int, list[tuple[int, ...]]] = {}
            for combo in combinations(range(n), half):
                index.setdefault(sum(pool[i][1] for i in combo), []).append(combo)
            seen: set[frozenset[int]] = set()
            for combo in combinations(range(n), rest):
                want = t - sum(pool[i][1] for i in combo)
                for other in index.get(want, ()):
                    if set(other) & set(combo):
                        continue      # a line cannot be used twice
                    key = frozenset(other + combo)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(tuple(sorted(other + combo)))
                    if len(hits) > 1:
                        break
                if len(hits) > 1:
                    break
        if hits:
            return Attribution(target=money(target),
                               lines=found(hits[0]) if len(hits) == 1 else [],
                               solutions=len(hits), searched=n)
    return Attribution(target=money(target), solutions=0, searched=n)
