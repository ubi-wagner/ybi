"""A reasoned classification for every open group, and a reason where there
is none.

This is not a second classification queue and it does not decide anything.
*Proposals are never decisions* — what it produces is a recommendation with a
citation and a rationale, for the controller to accept, amend or refuse. The
value is that the reasoning is written down once, in one place, against the
whole ledger, rather than reconstructed group by group at the screen.

Three things it does that `classify.propose()` does not, and each one was
found by walking the 2025 ledger end to end:

**A split that lands in one pool is not a split, for this question.** The
crosswalk maps twenty-four 2025 accounts to more than one 2026 account, and
`propose()` refuses all twenty-four — correctly for most, because a split
needs a documented driver and proposing one side would be inventing it. But
five of them (Rising Tides, LTM, Drive AM, Digital Engineering, AAMEN) split
by *natural type* — labour to 5100, subawards to 5200, materials to 5300,
travel to 5500 — and **every one of those numbers is in the DIRECT range**.
The split decides which 2026 account, not which 2025 pool, and the queue is
asking about the pool. That is $1,382,737 of the queue refused on a slash.

**A pass-through is not cost.** Several accounts carry paired entries where
YBI fronts a cost and somebody else repays it. `5027 TTC Utilities` is
$257,774 of gross movement and **$0.00 net**: Ohio Edison bills 255 W.
Federal, and Steelite International — a tenant — reimburses the identical
amount, line for line, twenty-four lines, twelve pairs. `ARC Arise` is
$21,000 in and $21,000 straight back out. Coverage counts *absolute* dollars
so a group counts by what it moved, which is right; but it puts these at the
top of a worst-first queue while they represent no cost at all.

**An account can be something other than its name.** `5227 Portfolio
consulting` reads as consulting expense. Its entries are *"50% of <vendor>
Invoice #N"* booked back against a portfolio company — a fifty-fifty cost
share, where YBI pays a service provider and the company repays half. It
carries $943,283.72 of credits against $1,531,822.61 of debits, and among
them a **$392,447.09 pair on 31 December with no payee and no description,
posted in and straight back out on the same day**. That single wash is
$784,894 of the account's $2,475,106 gross and nothing of its net.

Pure: no database, no HTTP. `scripts/classification_log.py` reads the live
rows and hands them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .chart import pool_for
from .core import money
from .crosswalk import CROSSWALK

#: How a judgment was arrived at. The log prints this beside every line,
#: because "the reviewed crosswalk says so" and "I read the payees" are
#: different strengths of claim and a reader must not have to guess which.
CROSSWALK_DIRECT = "crosswalk one-to-one"
CROSSWALK_ONE_POOL = "crosswalk split, single pool"
ANALYSIS = "analysis of the lines"
BLOCKED = "blocked"

#: 2025 buries program identity in the account name — that is the structural
#: defect the 2026 chart fixes by moving it to Customer:Job. Until then the
#: account path *is* the objective signal, and it is a good one: these are
#: the names the bookkeeper chose to separate the awards.
#:
#: `customer_job_hint` is empty on all 4,038 cost lines, so this is the only
#: signal there is. Without it no DIRECT proposal can be made at all —
#: `direct_needs_objective` refuses a DIRECT decision with no objective.
OBJECTIVE_BY_PATH: list[tuple[str, str]] = [
    ("Drive AM", "DRIVE-AM"),
    ("LTM Grant", "LTM"),
    ("AAMEN Grant", "AAMEN"),
    ("Digital Engineering", "DIG-ENG"),
    ("DOE Hybrid", "HYBRID-II"),
    ("DLA Grant", "DLA"),
    ("Rising Tides", "RISING-TIDES"),
    ("IH-Other", "HUB"),
    ("IH-EIR", "HUB"),
    ("Innovation Hub", "HUB"),
    ("Youth Entrepreneurship", "YOUTH"),
    ("MBAC", "MBAC"),
    ("VGV", "VGV"),
    ("Additive Manufacturing", "XJET"),
    ("ESP", "ESP"),
]

#: Accounts that net to nothing because a third party repaid them in full.
#: Each is evidenced by paired lines, not inferred from the total: the
#: reimbursing payee is named on the offsetting line.
PASS_THROUGH: dict[str, tuple[str, str]] = {
    "5027 TTC Utilities": (
        "Steelite International",
        "Ohio Edison bills 255 W. Federal and Steelite International — a "
        "tenant — reimburses the identical amount, line for line, across "
        "twelve pairs. $257,774.24 of gross movement and $0.00 net. This "
        "needs no square-footage measurement: the tenant pays 100% of it.",
    ),
    "ARC Arise": (
        "GBA ARC ARISE Planning Program",
        "One pair: Fourth Economy invoice #5644756 at $21,000.00 paid on "
        "30 May and repaid in full by the GBA ARC ARISE Planning Program on "
        "31 May. YBI fronted a partner's cost and was made whole.",
    ),
}

#: Facilities accounts whose 2026 mapping splits OVERHEAD from RENTAL_DIRECT
#: on square footage.
#:
#: **These are not blocked, and getting that right is the difference between
#: a usable answer and a wrong one.** The 2026 chart books tenant cost
#: straight to the 93xx rental pool, so there the split is a classification
#: question. 2025 has no such account: the model classifies occupancy cost to
#: OVERHEAD and removes the tenant and vacant share at rate time, as a 2 CFR
#: 200.465 carve-out off `v_facility_occupancy`. So for the 2025 record the
#: pool is OVERHEAD and the square footage is the *carve-out's* problem, not
#: the classification's.
#:
#: What they carry instead is a warning, because two things about that
#: carve-out are open and both move the rate.
OCCUPANCY = {
    "5035 Maintenance", "5043 Boardman Street Electric", "5055 Electric",
    "5041 Semple Electric", "5060 Heating/Cooling", "5044 Boardman St. Gas",
    "5042 Semple Gas", "5070 Water", "5200 Real Estate Tax",
}


@dataclass(frozen=True)
class Group:
    """One account-and-payee group, as the queue deals them."""
    account: str
    payee: str
    lines: int
    net: Decimal
    gross: Decimal
    first_month: str
    debits: Decimal = Decimal(0)
    credits: Decimal = Decimal(0)
    #: Lines already carrying a live decision. The log walks the *whole*
    #: ledger, not just what is open, so that it reads the same before and
    #: after its own recommendations are accepted — a log that empties itself
    #: when acted on cannot be checked against the books afterwards, which is
    #: the one time somebody will want to.
    judged: int = 0

    @property
    def leaf(self) -> str:
        return self.account.rsplit(":", 1)[-1].strip()

    @property
    def key(self) -> str:
        return f"{self.account}\x1f{self.payee}"


@dataclass(frozen=True)
class Judgment:
    """What is recommended, why, and how strong the claim is.

    `pool is None` means blocked — and blocked carries `blocked_on`, which is
    the whole point of it. *A control that cannot be evaluated has not
    passed*, and a group that cannot be judged is not judged: it stays in the
    queue saying what it is waiting for, rather than being defaulted into a
    pool to make a percentage look better.
    """
    pool: str | None
    function_990: str | None
    federal: str | None
    objective_id: str | None
    grade: str
    citation: str
    rationale: str
    basis: str
    blocked_on: str | None = None

    @property
    def blocked(self) -> bool:
        return self.pool is None


def objective_for(account: str) -> str | None:
    for fragment, objective in OBJECTIVE_BY_PATH:
        if fragment.lower() in account.lower():
            return objective
    return None


def _block(on: str, why: str) -> Judgment:
    return Judgment(None, None, None, None, "UNSUPPORTED", "", why,
                    BLOCKED, blocked_on=on)


#: A group the controller has already judged. Not re-proposed and not
#: counted as this log's work: recommending what is already on the record
#: would let the log take credit for somebody else's judgment.
RECORDED = "already recorded"


def judge(g: Group) -> Judgment:
    """The recommended treatment for one group, or the reason there is none.

    Ordered by strength of signal, the way `propose()` is: what the lines
    themselves show beats what the account is called, and what the account is
    called beats a general rule.
    """
    if g.judged:
        return Judgment(None, None, None, None, "UNSUPPORTED", "",
                        f"{g.judged} line(s) already carry a live decision.",
                        RECORDED, blocked_on=None)
    leaf, account = g.leaf, g.account

    # ---- 1. The lines themselves -------------------------------------
    #
    # A pass-through is not cost, whatever the account is called, and the
    # evidence is on the face of the ledger: an offsetting line naming the
    # payer. EXCLUDED rather than a pool, because putting $128,887 of
    # gross movement into OVERHEAD and $128,887 of credit beside it is two
    # entries that cancel, in a pool an indirect rate is taken over.
    if leaf in PASS_THROUGH:
        payer, why = PASS_THROUGH[leaf]
        return Judgment(
            "EXCLUDED", "NOT_APPLICABLE", "NOT_APPLICABLE", None,
            "CORROBORATED", "2 CFR 200.406(a)",
            f"Reimbursed in full by {payer}. {why}",
            ANALYSIS)

    # `5227 Portfolio consulting` — the largest single open judgment in the
    # ledger and not what its name says. See the module docstring.
    if leaf == "5227 Portfolio consulting":
        if g.lines <= 6 and g.payee == "" and g.net == 0:
            return Judgment(
                "EXCLUDED", "NOT_APPLICABLE", "NOT_APPLICABLE", None,
                "CORROBORATED", "2 CFR 200.403(g)",
                "A wash. $392,447.09 posted and reversed on 31 December with "
                "no payee and no description, plus two smaller reversals. "
                "Nothing was spent; it is $784,894 of the account's gross "
                "and none of its net, and it sits at the top of a worst-"
                "first queue measured in absolute dollars.",
                ANALYSIS)
        return _block(
            "what portfolio consulting serves",
            "Not a consulting expense account. Its entries are `50% of "
            "<vendor> Invoice #N` booked back against a portfolio company — "
            "a fifty-fifty cost share where YBI pays the service provider "
            "and the company repays half — so the net is YBI's own half. "
            "$1,531,822.61 of debits against $943,283.72 of credits across "
            "442 lines and 72 payees. The pool turns on a question the "
            "ledger cannot answer: whether supporting portfolio companies "
            "is programme delivery against a cost objective (DIRECT), or "
            "YBI's own business development (G&A). No Customer:Job was "
            "ever recorded. The account path puts it under `Program Expenses:ESP`, which is a real signal for ESP and the one the crosswalk's own note points at — but the path is also where 2025 buries every programme, and a $588,538.89 judgment should not rest on account nesting alone.")

    # ---- 2. What the account is called -------------------------------
    #
    # Depreciation is the one occupancy account that does not go to OVERHEAD
    # on the strength of being occupancy cost, because it carries a second
    # split the carve-out cannot reach: 200.436(b) makes depreciation on a
    # federally funded asset unallowable, and no allocation of square footage
    # answers that. The asset register has no funding-source column — which
    # 200.313(d)(1) requires and which is a finding of its own — so the basis
    # is unknown for all 263 assets.
    if leaf == "5010 Depreciation Expense":
        return _block(
            "the asset register's funding source",
            "$850,382.89 across twelve monthly entries, and two splits, not "
            "one. The occupancy share is the carve-out's to make. The other "
            "is 200.436(b): depreciation on an asset bought with federal "
            "money is unallowable, and the fixed-asset schedule has no "
            "funding-source column at all — 2 CFR 200.313(d)(1) requires "
            "one. Sending the whole account to OVERHEAD would claim "
            "depreciation YBI may not be entitled to; sending it anywhere "
            "else would invent a basis. It is the largest single figure in "
            "this log that no amount of reading the ledger can settle.")

    if leaf in OCCUPANCY:
        warn = ("The 200.465 carve-out then removes the tenant and vacant "
                "share, and two things about it are open: square footage is "
                "recorded for one building only (SPACE_UNMEASURED)")
        if g.credits > 0:
            warn += (f", and this group already carries ${g.credits:,.2f} of "
                     "credits, so part of the tenant share is booked rather "
                     "than estimated — carving a square-footage share on top "
                     "of a figure already net of recovery removes it twice")
        return _dress(g, "OVERHEAD", ANALYSIS, CROSSWALK[leaf][0], warn)

    if leaf == "5075 Insurance":
        return _block(
            "the policy schedule",
            "Splits property cover (OVERHEAD) from general liability (G&A) "
            "and the declarations page has not been read. Both halves are "
            "indirect, so this moves the split between the two pools and "
            "**not the combined indirect rate**.")

    if leaf == "5140 Employee Wages":
        return _block(
            "the effort distribution",
            "Split across direct, administrative and fundraising by the "
            "timesheet. This is the one split with its driver already on the "
            "record — `v_labor_effective` — and it is judged from there "
            "rather than from this log.")

    if leaf == "5142 Intern Wages":
        return _block(
            "FOR_TOM_TO_VERIFY 0",
            "Carries the $45,053.24 donor credit that sat in an intern wage "
            "account for a year and made the fringe rate read 22.45% instead "
            "of 21.90%. Named as a reconciling item and not yet reposted in "
            "QuickBooks; classifying the account before the repost would "
            "bake the error into a pool.")

    # The crosswalk, for the sixty-one accounts it maps one-to-one. A
    # mapping somebody already built and reviewed is a stronger claim than
    # anything this module could reason out, so it is preferred wherever it
    # speaks.
    mapped = CROSSWALK.get(leaf)
    if mapped:
        target, note = mapped
        parts = [p.strip() for p in target.split("/")]
        pools = {pool_for(p) for p in parts}
        pools.discard(None)
        if len(pools) == 1:
            pool = pools.pop().value
            basis = CROSSWALK_DIRECT if len(parts) == 1 else CROSSWALK_ONE_POOL
            return _dress(g, pool, basis, target, note)
        # A split that genuinely crosses pools, and not one of the named
        # cases above. Blocked, with both readings stated.
        return _block(
            "a documented driver",
            f"Splits across pools in the 2026 chart ({target}"
            + (f": {note}" if note else "")
            + "). A split needs a driver with a person's name on it, and "
              "proposing one side would be inventing it.")

    # ---- 3. A general rule -------------------------------------------
    if "interest income" in account.lower():
        return Judgment(
            "EXCLUDED", "NOT_APPLICABLE", "NOT_APPLICABLE", None,
            "CORROBORATED", "2 CFR 200.305(b)(9)",
            "Interest earned, not cost incurred, and not an applicable "
            "credit against any cost pool. Interest earned on federal "
            "advances above the de minimis is remitted annually rather than "
            "offset, so it must not reduce a pool.",
            ANALYSIS)

    if "other income" in account.lower():
        return _block(
            "FOR_TOM_TO_VERIFY — new",
            "Applicable credits under 200.406, which reduce cost rather than "
            "being revenue, so they stay in scope. $105,865.41 of this is a "
            "Q1 **2020** Employee Retention Tax Credit received from "
            "Staffmark in May 2025. A credit relating to a period in which "
            "federal awards bore the wage cost is due back to the awards "
            "under 200.406(b) — as a cost reduction or a cash refund — and "
            "which 2020 awards bore those wages is not on this record.")

    return _block(
        "no signal",
        "No crosswalk entry, no account-name pattern and no objective in the "
        "account path. Left in the queue: unclassified cost is never "
        "defaulted into a pool.")


def _dress(g: Group, pool: str, basis: str, target: str, note: str) -> Judgment:
    """Fill in the function, the federal treatment and the objective.

    The pool comes off the crosswalk. These three do not, because an account
    number knows none of them — so they are set here, from the rules that
    govern each pool, and DIRECT is refused outright where the account path
    names no objective rather than being given a plausible one.
    """
    citation, rationale = _why(pool, note)

    if pool == "DIRECT":
        objective = objective_for(g.account)
        if objective is None:
            return _block(
                "a cost objective",
                f"Direct cost by its 2026 mapping ({target}) and the account "
                "path names no objective, so there is nothing to charge it "
                "to. `direct_needs_objective` refuses a DIRECT decision with "
                "no objective, and that is the right refusal: cost charged "
                "to an objective nobody chose is worse than cost nobody has "
                "judged.")
        return Judgment(pool, "PROGRAM", "ALLOWABLE", objective,
                        "MANAGEMENT_RECONSTRUCTION", citation, rationale, basis)

    function = {
        "FRINGE": "NOT_APPLICABLE",
        "OVERHEAD": "PROGRAM",
        "G&A": "MANAGEMENT_AND_GENERAL",
        "RENTAL_DIRECT": "NOT_APPLICABLE",
        "FUNDRAISING": "FUNDRAISING",
        "UNALLOWABLE": "MANAGEMENT_AND_GENERAL",
        "EXCLUDED": "NOT_APPLICABLE",
    }[pool]
    # `unallowable_not_allowable` refuses ALLOWABLE on either of these two,
    # and the schema is right: a fundraising dollar is not a federal dollar.
    federal = ("UNALLOWABLE" if pool in ("FUNDRAISING", "UNALLOWABLE")
               else "NOT_APPLICABLE" if pool in ("RENTAL_DIRECT", "EXCLUDED")
               else "ALLOWABLE")
    return Judgment(pool, function, federal, None,
                    "MANAGEMENT_RECONSTRUCTION", citation, rationale, basis)


def _why(pool: str, note: str) -> tuple[str, str]:
    base = {
        "DIRECT": ("2 CFR 200.413(a)",
                   "Identified specifically with one final cost objective"),
        "FRINGE": ("2 CFR 200.431",
                   "Employee benefit cost, pooled and applied on a wage base"),
        "OVERHEAD": ("2 CFR 200 Appendix IV B.3",
                     "Facilities and related occupancy cost, benefiting work "
                     "in common"),
        "G&A": ("2 CFR 200.414(a)",
                "General administration benefiting the organisation as a "
                "whole and not assignable to one objective"),
        "RENTAL_DIRECT": ("2 CFR 200.465",
                          "Tenant and rental activity, carved out of the "
                          "federal pool"),
        "FUNDRAISING": ("2 CFR 200.442",
                        "Fundraising and bid & proposal activity, "
                        "unallowable federally and reportable on Form 990"),
        "UNALLOWABLE": ("2 CFR 200.420-475",
                        "Expressly unallowable federally; still bears "
                        "indirect and is still reported on Form 990"),
        "EXCLUDED": ("2 CFR 200.403(g)", "Not cost of the period"),
    }[pool]
    return base[0], base[1] + (f". {note}" if note else "")


def walk(groups: list[Group]) -> list[tuple[Group, Judgment]]:
    """Every group in ledger order — by the month it first appears, then by
    what it moved. A walk that jumped about would be impossible to check
    against the books a month at a time, which is how a controller reads
    them.
    """
    ordered = sorted(groups, key=lambda g: (g.first_month, -g.gross, g.account))
    return [(g, judge(g)) for g in ordered]


def summarise(walked: list[tuple[Group, Judgment]]) -> dict:
    """What the walk decided, in the shapes the log reports."""
    out: dict = {"groups": len(walked), "judged": 0, "blocked": 0,
                 "recorded": 0, "recorded_gross": money(0),
                 "judged_gross": money(0), "blocked_gross": money(0),
                 "by_pool": {}, "by_block": {}, "by_month": {}}
    for g, j in walked:
        m = out["by_month"].setdefault(
            g.first_month, {"groups": 0, "judged": 0, "blocked": 0,
                            "recorded": 0, "recorded_gross": money(0),
                            "judged_gross": money(0), "blocked_gross": money(0)})
        m["groups"] += 1
        if j.basis == RECORDED:
            out["recorded"] += 1
            out["recorded_gross"] = money(out["recorded_gross"] + g.gross)
            m["recorded"] += 1
            m["recorded_gross"] = money(m["recorded_gross"] + g.gross)
        elif j.blocked:
            out["blocked"] += 1
            out["blocked_gross"] = money(out["blocked_gross"] + g.gross)
            m["blocked"] += 1
            m["blocked_gross"] = money(m["blocked_gross"] + g.gross)
            b = out["by_block"].setdefault(
                j.blocked_on, {"groups": 0, "gross": money(0), "net": money(0)})
            b["groups"] += 1
            b["gross"] = money(b["gross"] + g.gross)
            b["net"] = money(b["net"] + g.net)
        else:
            out["judged"] += 1
            out["judged_gross"] = money(out["judged_gross"] + g.gross)
            m["judged"] += 1
            m["judged_gross"] = money(m["judged_gross"] + g.gross)
            p = out["by_pool"].setdefault(
                j.pool, {"groups": 0, "gross": money(0), "net": money(0)})
            p["groups"] += 1
            p["gross"] = money(p["gross"] + g.gross)
            p["net"] = money(p["net"] + g.net)
    return out
