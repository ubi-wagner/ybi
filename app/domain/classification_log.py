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
    ("SBA Growth Accelerator", "SBA-ACCEL"),
]

#: The 2025 chart files every account under a parent that says what kind of
#: activity it is, and that is a judgment somebody already made and wrote
#: down. Where the crosswalk's split crosses pools because the question is
#: *whose activity is this* — direct programme work, administration, or
#: fundraising — the parent answers it.
#:
#: It is weaker evidence than a timesheet and it is not nothing: travel filed
#: under `Management & Administrative Expenses` is the bookkeeper saying this
#: trip was administrative. Using the path for the objective and refusing it
#: for the function would be holding one signal to two standards.
#:
#: **It only decides a split whose branches differ in function.** Insurance
#: divides 8300 from 7300 and both are indirect, so the parent cannot
#: discriminate and its own named rule keeps it blocked; depreciation divides
#: on an attribute of the asset, not on whose activity it is. Both stay out
#: of this by being caught earlier.
PARENT_FUNCTION: list[tuple[str, str]] = [
    ("5080 Fundraising", "FUNDRAISING"),
    ("Management & Administrative Expenses", "INDIRECT"),
    ("Grant Expenses", "DIRECT"),
    ("Program Expenses", "DIRECT"),
]


def pick_branch(function: str | None, branches: dict[str, str]) -> str | None:
    """Which side of a cross-pool split the parent's function points at.

    Pulled out of `judge()` so it can be tested on branch sets the live
    crosswalk does not currently contain — and it does not contain one, which
    is the point. Every cross-pool split that reaches this today has exactly
    one indirect branch, so the *more than one candidate means no candidate*
    guard below never actually bites on live data. It is kept, and tested
    here directly, because the day somebody adds a split dividing OVERHEAD
    from G&A the alternative is silently picking whichever came first.
    """
    if function == "FUNDRAISING" and "FUNDRAISING" in branches:
        return "FUNDRAISING"
    if function == "DIRECT" and "DIRECT" in branches:
        return "DIRECT"
    if function == "INDIRECT":
        indirect = sorted(b for b in branches
                          if b in ("OVERHEAD", "G&A", "UNALLOWABLE"))
        if len(indirect) == 1:
            return indirect[0]
    return None


def parent_function(account: str) -> str | None:
    """What the account's own parent says this activity is."""
    head = account.split(":", 1)[0].strip()
    for prefix, function in PARENT_FUNCTION:
        if head == prefix:
            return function
    return None


#: Objectives the account names and the register has never had a row for.
#: Opening one is transcription, not judgment — the account already says the
#: programme exists and money was spent on it — so `--apply` opens them
#: through `POST /api/contracts/charge-codes` as the controller, with an
#: audit row, before recording anything against them. Non-federal until
#: somebody shows an award: a federal code needs a CFDA number, and the
#: Single Audit scope is decided by what reaches the SEFA.
OBJECTIVES_TO_OPEN: dict[str, str] = {
    "SBA-ACCEL": "SBA Growth Accelerator",
}

#: Accounts the 2026 crosswalk moves *into* the direct pool, which in 2025
#: are filed under Management & Administrative Expenses and have no objective
#: in their path. The crosswalk describes where these should go next year —
#: `5226 Manuf. support` carries the note "reclassified from G&A" in so many
#: words — and this log is classifying the year that was actually worked, in
#: which they sat in administration. Three of them, each named with the pool
#: the 2026 chart would use for that nature of cost, because a rule clever
#: enough to infer it from three examples would be guessing.
STAYED_INDIRECT: dict[str, tuple[str, str]] = {
    "5226 Manuf. support - factory manage": (
        "G&A",
        "Twelve monthly payments to one contractor, filed under "
        "administration all year. The crosswalk's own note says "
        "'reclassified from G&A' — that is a change for 2026, and 2025 is "
        "the year where it had not happened yet."),
    "5015 Equipment Expenses": (
        "OVERHEAD",
        "Equipment filed under administration rather than against an award: "
        "used in common, so it belongs with the occupancy pool the way "
        "7400 takes equipment in the 2026 chart."),
    "5016 Equipment Purchases": (
        "OVERHEAD",
        "As above, and below the capitalisation threshold — a purchase over "
        "it would be an asset, not a 2025 cost."),
}

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


def judge(g: Group, federal_objectives: frozenset[str] = frozenset()
          ) -> Judgment:
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
    fed = frozenset(federal_objectives)

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
        # **A consultant pass-through is contractor cost, and it belongs in
        # the base.** YBI pays a service provider and books half back against
        # the portfolio company — 442 lines of `50% of <vendor> Invoice #N`,
        # $1,531,822.61 of debits against $943,283.72 of credits, so the net
        # is YBI's own half.
        #
        # 200.331 decides which it is. A subrecipient carries out part of a
        # federal programme in its own right and its subaward counts in MTDC
        # only to the first $25,000; a *contractor* provides services inside
        # the recipient's own programme and counts in full. These consultants
        # deliver into YBI's incubation programme against YBI's scope, so
        # they are contractors and the whole amount sits in the base.
        #
        # Which is the point of putting it there. **The oversight is the
        # recovery.** YBI selects the consultant, scopes the engagement,
        # administers the payment and carries the other half — real
        # administrative effort, and the G&A pool is what that effort is
        # paid out of. Cost in the base is cost the rate applies to; moving
        # it out of the base because it "passes through" would forgo
        # recovery on the very activity the administration exists for.
        objective = objective_for(g.account)
        return _dress(
            g, "DIRECT", ANALYSIS, "5110",
            "Consultant pass-through: YBI engages a service provider for a "
            "portfolio company and books half back to the company, so the "
            "net is YBI's own share. A contractor under 200.331 rather than "
            "a subrecipient — services inside YBI's own programme — so it "
            "carries no $25,000 MTDC cap and sits in the base at full value, "
            "which is what the G&A pool is applied against for YBI's "
            "oversight and management of those engagements. The account path "
            "puts it under ESP", fed) if objective else _block(
            "a cost objective for portfolio consulting",
            "Consultant pass-through, direct by nature, and the account path "
            "names no objective to charge it to.")

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
        # Occupancy cost, so the pool is not in doubt — OVERHEAD, like every
        # other thing that keeps the buildings running. What *is* in doubt is
        # 200.436(b): depreciation on an asset bought with federal money is
        # unallowable, and the fixed-asset schedule has no funding-source
        # column at all, which 200.313(d)(1) requires.
        #
        # `PENDING` is the schema's own word for that and this log had been
        # ignoring it. Refusing to classify $850,382.89 leaves it out of the
        # pool entirely, which understates OVERHEAD by more than any other
        # single figure; classifying it ALLOWABLE would claim depreciation
        # YBI may not be entitled to. PENDING puts the cost where it belongs
        # and leaves the claim open, which is what is actually true.
        return Judgment(
            "OVERHEAD", "PROGRAM", "PENDING", None,
            "MANAGEMENT_RECONSTRUCTION", "2 CFR 200.436",
            "$850,382.89 across twelve monthly entries. Occupancy cost, so "
            "OVERHEAD — but the federal treatment stays PENDING because "
            "200.436(b) makes depreciation on a federally funded asset "
            "unallowable and the fixed-asset schedule has no funding-source "
            "column, which 200.313(d)(1) requires. The unallowable share is "
            "an adjustment against this pool the day the register arrives, "
            "and until then nothing here claims it is recoverable",
            ANALYSIS)

    if False:
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
        return _dress(g, "OVERHEAD", ANALYSIS, CROSSWALK[leaf][0], warn, fed)

    if leaf == "5215 Dues and Subscriptions":
        # The crosswalk's note — "civic and community memberships are
        # unallowable" — overstates the rule, and the rule is worth reading
        # rather than recalling. 200.454(a) allows membership of business,
        # technical and professional organisations; (b) allows subscriptions
        # to business, professional and technical periodicals; (c) makes
        # civic and community membership allowable *with prior approval*,
        # which is a condition rather than a prohibition; and only (d) — a
        # country, social or dining club — is unallowable outright.
        #
        # Sixty payees and not one of them is a club. They are software
        # subscriptions (Mailchimp, LinkedIn, Zoom, Adobe, Hubspot, Dropbox,
        # Calendly), chambers of commerce and professional bodies (Ohio
        # Chamber, Pittsburgh Technology Council, American Foundry Society,
        # the Better Business Bureau, the Center for Nonprofit Leadership)
        # and one business periodical. Every one is allowable, so the split
        # this account was blocked on does not arise on these facts.
        return _dress(
            g, "G&A", ANALYSIS, "8230",
            "Every payee in this account is a software subscription, a "
            "business or professional organisation, or a business "
            "periodical — 200.454(a) and (b). None is a country, social or "
            "dining club, which is the only category 200.454(d) makes "
            "unallowable outright; the crosswalk's note that civic "
            "membership is unallowable overstates (c), which makes it "
            "allowable with prior approval. The one thing worth a look is "
            "$961 to the Association of Fundraising Professionals, which "
            "supports fundraising rather than administration", fed)

    if leaf == "5001 Cost of Goods Sold":
        return Judgment(
            "DIRECT", "PROGRAM", "NOT_APPLICABLE", "XJET",
            "MANAGEMENT_RECONSTRUCTION", "2 CFR 200.413(a)",
            "Two entries, 31 October and 31 December, both 'Used Inventory "
            "(See JE for breakdown)'. Cost of goods sold belongs to the "
            "activity that sold them, and Xjet / Manufacturing Services is "
            "the only goods-and-manufacturing objective on the register — "
            "the PayPal selling fees in the same COGS section point the same "
            "way. This rests on that inference and not on the journal entry, "
            "which exists, names what was consumed and for whom, and nobody "
            "has read: the cheapest $37,261.00 on this list to settle and "
            "the one to check first",
            ANALYSIS)

    if leaf == "5075 Insurance":
        return _dress(
            g, "OVERHEAD", ANALYSIS, "7300",
            "Splits property cover (7300, OVERHEAD) from general liability "
            "(8300, G&A) and the declarations page has not been read. YBI "
            "owns and operates its buildings, so the larger share is "
            "property, and the whole of it sits in OVERHEAD until the policy "
            "says otherwise. **It does not move the combined indirect rate** "
            "— both halves are indirect — but it is not neutral either: "
            "OVERHEAD is carved for tenant and vacant space under 200.465 "
            "and G&A is not, so the share that is really general liability "
            "is being carved when it should not be", fed)

    # **The wage accounts are already in the model, and putting them in a
    # pool as well counts the same labour twice.**
    #
    # `POST /api/rates/compute` feeds `v_labor_effective.distributed_wages`
    # into `PoolModel.add_labor()`, which sets `ObjectiveCost.direct_labor`
    # per objective — $1,835,047.17, the payroll register to the cent, split
    # ESP $561,145, MBAC $278,466, YBI-GA $264,445, the Hub $172,214 and so
    # on down to DLA at $401. `build()` separately puts every DIRECT decision
    # into `direct_nonlabor`. **Both feed MTDC.** So a DIRECT judgment on
    # `5140 Employee Wages` would add $1,678,157.27 of labour to a base that
    # already carries it, and every indirect rate taken over that base would
    # read low by the width of the payroll.
    #
    # EXCLUDED is not "this is not cost". It is the pool enum's word for cost
    # the pools must not carry, and the reason is on the judgment. The labour
    # is in the record, in the base, from the record that distributes it —
    # which is the whole of the eleventh control's point: *the fringe base
    # comes from the effort distribution, not from the ledger's wage
    # accounts*.
    if leaf in ("5140 Employee Wages", "5142 Intern Wages"):
        extra = ""
        if leaf == "5142 Intern Wages":
            extra = (" It also carries the $45,053.23 donor credit that sat "
                     "here for a year and made the fringe rate read 22.45% "
                     "instead of 21.90% — named as a reconciling item and "
                     "not yet reposted in QuickBooks, so a pool must not "
                     "take it either.")
        return Judgment(
            "EXCLUDED", "NOT_APPLICABLE", "NOT_APPLICABLE", None,
            "CORROBORATED", "2 CFR 200.430(i)",
            "Wages reach the rate model through the effort distribution, not "
            "through this account: `v_labor_effective` distributes "
            "$1,835,047.17 across the objectives and the computation reads it "
            "straight into the direct base. A pool judgment here would put "
            "the same labour in twice and every indirect rate over that base "
            "would read low by the width of the payroll." + extra,
            ANALYSIS)

    # The crosswalk, for the sixty-one accounts it maps one-to-one. A
    # mapping somebody already built and reviewed is a stronger claim than
    # anything this module could reason out, so it is preferred wherever it
    # speaks.
    if leaf in STAYED_INDIRECT:
        pool, why = STAYED_INDIRECT[leaf]
        return _dress(g, pool, ANALYSIS, CROSSWALK.get(leaf, ("", ""))[0],
                      why, fed)

    mapped = CROSSWALK.get(leaf)
    if mapped:
        target, note = mapped
        parts = [p.strip() for p in target.split("/")]
        pools = {pool_for(p) for p in parts}
        pools.discard(None)
        if len(pools) == 1:
            pool = pools.pop().value
            basis = CROSSWALK_DIRECT if len(parts) == 1 else CROSSWALK_ONE_POOL
            return _dress(g, pool, basis, target, note, fed)

        # A split that crosses pools. Before refusing it, ask what the
        # account's own parent says — the bookkeeper filed it somewhere, and
        # where they filed it is a driver already on the record.
        function = parent_function(account)
        branches = {pool_for(x).value: x for x in parts if pool_for(x)}
        pick = pick_branch(function, branches)
        if pick:
            return _dress(
                g, pick, ANALYSIS, branches[pick],
                f"filed by the bookkeeper under "
                f"{account.split(':', 1)[0].strip()}, which is the driver "
                f"for a split between {' and '.join(sorted(branches))} — "
                f"whose activity this is, answered by where it was booked"
                + (f". The 2026 note reads: {note}" if note else ""), fed)

        return _block(
            "a documented driver",
            f"Splits across pools in the 2026 chart ({target}"
            + (f": {note}" if note else "")
            + f"), and the account's parent does not settle it: "
            + (f"{', '.join(sorted(branches))} are not told apart by where "
               f"it was filed" if function else
               "the path names no parent function")
            + ". A split needs a driver with a person's name on it, and "
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
        return Judgment(
            "EXCLUDED", "NOT_APPLICABLE", "PENDING", None,
            "MANAGEMENT_RECONSTRUCTION", "2 CFR 200.406(b)",
            "Applicable credits, which reduce cost rather than being revenue "
            "— but not 2025's cost. $105,865.41 of this is a Q1 **2020** "
            "Employee Retention Tax Credit received from Staffmark in May "
            "2025, and a credit relating to a period in which federal awards "
            "bore the wage cost is due back to those awards under 200.406(b), "
            "as a cost reduction or a cash refund. Netting it against a 2025 "
            "pool would reduce this year's rate by a credit that belongs to "
            "2020's, so it is excluded from the pools and the federal "
            "treatment stays PENDING until somebody establishes which 2020 "
            "awards bore those wages. That is a liability, not income",
            ANALYSIS)

    return _block(
        "no signal",
        "No crosswalk entry, no account-name pattern and no objective in the "
        "account path. Left in the queue: unclassified cost is never "
        "defaulted into a pool.")


def _dress(g: Group, pool: str, basis: str, target: str, note: str,
           federal_objectives: frozenset[str] = frozenset()) -> Judgment:
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
            # The account names a programme the objective register has never
            # heard of. That is not the same as having no signal: the work is
            # identified, there is simply no row to charge it to, and opening
            # one is a short act by a person rather than a document to go and
            # find. So the block names the objective to open rather than
            # reporting a gap.
            suggested = g.account.rsplit(":", 1)[-1].strip()
            return _block(
                f"a cost objective for {suggested}",
                f"Direct cost by its 2026 mapping ({target}) and the account "
                f"names {suggested}, which has no row in the objective "
                f"register — so there is nothing to charge it to. "
                f"`direct_needs_objective` refuses a DIRECT decision with no "
                f"objective, and that is the right refusal: cost charged to "
                f"an objective nobody chose is worse than cost nobody has "
                f"judged. Open the objective and this classifies itself.")
        # **The federal treatment follows the objective, not the pool.**
        # This read ALLOWABLE for every DIRECT judgment in the first version
        # of this log, which put $986,592.77 of cost on non-federal
        # objectives — Rising Tides, ESP, the Hub, MBAC — down as claimable
        # against a federal award. ALLOWABLE is an assertion about a federal
        # award and there is no award behind a non-federal objective to make
        # it about. Rising Tides is the one that matters: whether it is
        # federally funded is an open question in the engagement, the
        # objective master says it is not, and a log that wrote ALLOWABLE
        # would have taken a side on it in 33 places without saying so.
        federal = ("ALLOWABLE" if objective in federal_objectives
                   else "NOT_APPLICABLE")
        if objective not in federal_objectives:
            rationale += (f". {objective} is not a federal objective on the "
                          f"record, so the federal treatment is not "
                          f"applicable rather than allowable")
        return Judgment(pool, "PROGRAM", federal, objective,
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


def walk(groups: list[Group], *, reverse: bool = False,
         federal_objectives: frozenset[str] = frozenset()
         ) -> list[tuple[Group, Judgment]]:
    """Every group in ledger order — by the month it first appears, then by
    what it moved. A walk that jumped about would be impossible to check
    against the books a month at a time, which is how a controller reads
    them.

    `reverse=True` runs December back to January. **It must change the order
    and nothing else.** `judge()` is a pure function of one group and holds no
    state between calls, so the same ledger has to produce the same set of
    judgments read either way — and that is a claim, which in this repository
    is a thing to check rather than assert. A log whose recommendations
    depended on the direction of the read would be one where the order of the
    books decided the rate, and nobody would find that by looking at either
    run on its own.

    `tests/test_classification_log.py::test_the_walk_is_the_same_read_either_way`
    holds it, and `scripts/classification_log.py --reverse` runs it against
    the live ledger.
    """
    ordered = sorted(groups, key=lambda g: (g.first_month, -g.gross, g.account),
                     reverse=reverse)
    return [(g, judge(g, federal_objectives)) for g in ordered]


def disagreements(forward: list[tuple[Group, Judgment]],
                  backward: list[tuple[Group, Judgment]]) -> list[str]:
    """Where two walks of the same ledger judged the same group differently.

    Compared on the group key rather than on position, because the positions
    are *supposed* to differ — comparing the lists elementwise would report
    757 differences on a correct run, which is the "test that argues against
    correct code" this file warns about.
    """
    def by_key(w):
        return {g.key: j for g, j in w}
    a, b = by_key(forward), by_key(backward)
    out = []
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            out.append(f"{key.replace(chr(31), ' / ')}: in one walk only")
            continue
        x, y = a[key], b[key]
        if (x.pool, x.function_990, x.federal, x.objective_id,
                x.grade, x.basis, x.blocked_on) != (
                y.pool, y.function_990, y.federal, y.objective_id,
                y.grade, y.basis, y.blocked_on):
            out.append(f"{key.replace(chr(31), ' / ')}: "
                       f"{x.pool or x.blocked_on} forward, "
                       f"{y.pool or y.blocked_on} backward")
    return out


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
