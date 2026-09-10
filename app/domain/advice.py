"""What to think about before classifying this group.

Advice, not decisions. The rule in this codebase is that anything the system
infers is a suggestion a person confirms, and this is the weakest kind of
inference there is — a pattern in an account name, a shape in the lines. What
it is good for is the thing a controller forgets at four in the afternoon on
the six hundredth group: that meals are two different things under 200.438,
that a group spanning four Customer:Job values is probably four judgments,
that this account was called something else last time.

Every advisory carries the citation it rests on, because "split this" without
"and here is the rule that says so" is an opinion.

Pure: no database, no imports from app.db. Tested without Postgres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class Advisory:
    kind: str          # SPLIT | MERGE | POOL | EVIDENCE | CONSISTENCY | UNALLOWABLE
    headline: str
    detail: str
    citation: str = ""
    weight: int = 1    # 3 shows first; 1 is a nudge


@dataclass
class GroupFacts:
    """Everything the advisor is allowed to look at."""
    account: str
    payee: str = ""
    amount: Decimal = Decimal(0)
    line_count: int = 0
    objective_hints: list[str] = field(default_factory=list)
    memos: list[str] = field(default_factory=list)
    evidence_count: int = 0
    note_count: int = 0
    #: how the same account was classified elsewhere in this period
    prior_pools: list[str] = field(default_factory=list)
    #: how it was classified in the previous period, if known
    last_year_pool: str = ""
    federal_share_of_period: Decimal = Decimal(0)


#: Account-name patterns worth stopping on, with the rule behind each. The
#: wording is what a person reads, so it says what to do rather than naming a
#: category.
PATTERNS: list[tuple[str, Advisory]] = [
    (r"meals?|entertain|catering",
     Advisory("SPLIT", "Meals and entertainment are two different things",
              "A business meal with a documented purpose and attendees is "
              "allowable; entertainment is not, whatever it was booked as. "
              "If this account holds both, split it rather than choosing.",
              "2 CFR 200.438, 200.474", 3)),
    (r"travel|airfare|lodging|hotel|mileage",
     Advisory("EVIDENCE", "Travel needs the purpose, not just the receipt",
              "Allowable travel is travel on the award's business. Cite the "
              "trip report or the agenda, not the hotel bill — the bill "
              "proves the spend, not the reason.",
              "2 CFR 200.475", 2)),
    (r"lobby|government relations|advocacy|political",
     Advisory("UNALLOWABLE", "Lobbying is unallowable and reportable",
              "Unallowable under 200.450 and separately reportable on Form "
              "990 Schedule C. It still belongs in the base as an "
              "unallowable direct cost; excluding it entirely understates "
              "the denominator.",
              "2 CFR 200.450", 3)),
    (r"contribution|donation|charitable",
     Advisory("UNALLOWABLE", "Contributions made are unallowable",
              "Contributions and donations made by the organisation are "
              "unallowable regardless of recipient.",
              "2 CFR 200.434", 3)),
    (r"bad debt|write.?off|uncollect",
     Advisory("UNALLOWABLE", "Bad debts are unallowable",
              "Including related collection and legal costs.",
              "2 CFR 200.426", 3)),
    (r"interest|finance charge",
     Advisory("POOL", "Interest is unallowable but still a 990 expense",
              "Unallowable under 200.449 except for the narrow building "
              "acquisition case. It is reportable on Form 990 Part IX, which "
              "is why the two dimensions are recorded separately.",
              "2 CFR 200.449", 2)),
    (r"fine|penalt|settlement|litigation",
     Advisory("UNALLOWABLE", "Fines, penalties and most settlements",
              "Unallowable unless incurred as a result of compliance with "
              "the award's terms and with prior written approval.",
              "2 CFR 200.441", 2)),
    (r"alcohol",
     Advisory("UNALLOWABLE", "Alcohol is unallowable, full stop",
              "No purpose makes it allowable.", "2 CFR 200.423", 3)),
    (r"depreciat|amorti",
     Advisory("EVIDENCE", "Depreciation turns on how the asset was funded",
              "Depreciation on an asset bought with federal funds is "
              "unallowable. Until the asset register names a funding source "
              "this cannot be graded above a test assumption.",
              "2 CFR 200.436(b)", 3)),
    (r"rent|lease|facilit|janitor|utilit|maintenance",
     Advisory("SPLIT", "Facility cost usually serves tenants and programmes",
              "YBI lets space and runs programmes in the same building. A "
              "facility cost that is not carved out between them puts tenant "
              "cost into the indirect pool, which is the carve-out an auditor "
              "looks for first.",
              "2 CFR 200.414, Appendix IV", 3)),
    (r"consult|professional service|contractor",
     Advisory("SPLIT", "Consulting is often several objectives at once",
              "If the statements of work name different programmes, the "
              "driver is the statements of work rather than one pool.",
              "2 CFR 200.413(a)", 2)),
    (r"salar|wage|payroll|fringe|benefit",
     Advisory("EVIDENCE", "Labour needs a certification behind it",
              "Charges to federal awards for salaries must be supported by "
              "records of actual work, certified by the person who did it. "
              "The timesheet screen is where that comes from.",
              "2 CFR 200.430(i)", 3)),
    (r"advertis|marketing|promotion",
     Advisory("POOL", "Most advertising is unallowable; recruitment is not",
              "Advertising for staff recruitment, procurement or disposal of "
              "surplus is allowable. Promotion of the organisation generally "
              "is not, and often belongs to fundraising.",
              "2 CFR 200.421", 2)),
    (r"membership|subscription|dues",
     Advisory("POOL", "Memberships are allowable, civic clubs are not",
              "Business, technical and professional organisation memberships "
              "are allowable. Country, social and dining clubs are not.",
              "2 CFR 200.454", 1)),
    (r"training|conference|seminar",
     Advisory("POOL", "Training is allowable; the meals inside it may not be",
              "Conference costs are allowable, but check whether the invoice "
              "carries entertainment or alcohol that has to come out.",
              "2 CFR 200.432", 1)),
]


def advise(g: GroupFacts) -> list[Advisory]:
    """What is worth thinking about before this group is classified."""
    out: list[Advisory] = []

    # The account name only. Matching a vendor's company name against expense
    # categories reads "S-Gen Marketing LLC" as advertising, which is a
    # confident answer to a question nobody asked — the vendor's trading name
    # says nothing about what the cost was for.
    name = g.account.lower()

    for pattern, advisory in PATTERNS:
        if re.search(pattern, name):
            out.append(advisory)

    # ── shape of the group itself ────────────────────────────────────
    hints = [h for h in g.objective_hints if h]
    if len(set(hints)) > 1:
        out.append(Advisory(
            "SPLIT", f"These lines carry {len(set(hints))} different objectives",
            "The Customer:Job field already says these are different pieces of "
            "work: " + ", ".join(sorted(set(hints))[:5]) +
            ". One decision would put them all in the same place.",
            "2 CFR 200.405(a)", 3))

    if g.line_count >= 100:
        out.append(Advisory(
            "SPLIT", f"{g.line_count} lines under one judgment",
            "A group this large rarely holds one kind of cost. It is worth "
            "reading a sample of the memos before deciding for all of it.",
            "", 2))

    if len(set(g.prior_pools)) > 1:
        out.append(Advisory(
            "CONSISTENCY", "This account has been classified two ways already",
            "Elsewhere in this period the same account sits in " +
            " and ".join(sorted(set(g.prior_pools))) + ". Like costs have to "
            "be treated alike, or the rate cannot be defended.",
            "2 CFR 200.403(d)", 3))
    elif g.prior_pools:
        out.append(Advisory(
            "MERGE", f"Classified as {g.prior_pools[0]} elsewhere this period",
            "Same account, same period. Unless something distinguishes these "
            "lines, the consistent answer is the same one.",
            "2 CFR 200.403(d)", 1))

    if g.last_year_pool and g.last_year_pool not in g.prior_pools:
        out.append(Advisory(
            "CONSISTENCY", f"Last year this was {g.last_year_pool}",
            "Changing treatment between periods is allowed and has to be "
            "deliberate — a rate that moves because the treatment moved is a "
            "question an auditor will ask.",
            "2 CFR 200.403(d)", 2))

    if abs(g.amount) >= 100_000 and g.evidence_count == 0:
        out.append(Advisory(
            "EVIDENCE", "Six figures with nothing attached",
            f"${abs(g.amount):,.0f} carried on a judgment with no document "
            f"cited. It can be graded, but not as verified.",
            "2 CFR 200.403(g)", 2))

    if g.amount < 0:
        out.append(Advisory(
            "POOL", "This group is a credit",
            "A refund, rebate or correction reduces the cost it relates to. "
            "It belongs in the same pool as the cost it reverses, not in a "
            "pool of its own.",
            "2 CFR 200.406", 2))

    # Strongest first, and never the same headline twice.
    seen, ordered = set(), []
    for a in sorted(out, key=lambda a: -a.weight):
        if a.headline not in seen:
            seen.add(a.headline)
            ordered.append(a)
    return ordered
