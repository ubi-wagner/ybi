"""The classification log proposes, and what it proposes has to be acceptable.

Two different guarantees, and the second is the one that bites.

A recommendation that the database would refuse is worse than no
recommendation: it is work offered to somebody that cannot be done, which is
the `FACILITY_UNPARTITIONED` defect in a new costume. `decision` carries two
CHECK constraints that a proposal can violate — `direct_needs_objective` and
`unallowable_not_allowable` — and every judgment this module emits is tested
against both, without a database, because the rule is knowable from the
schema and a test that needs Postgres to state it is one nobody runs on a
fresh clone.

The other guarantee is that it does not quietly fill the queue in. Blocked
has to stay blocked where the driver is genuinely missing, or the whole thing
becomes a way of defaulting unclassified cost into a pool with extra steps.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.chart import pool_for
from app.domain.classification_log import (
    ANALYSIS, BLOCKED, CROSSWALK_ONE_POOL, OBJECTIVE_BY_PATH, OCCUPANCY,
    RECORDED, Group, disagreements, judge, objective_for, parent_function,
    pick_branch, summarise, walk)
from app.domain.crosswalk import CROSSWALK

ROOT = Path(__file__).resolve().parent.parent


def g(account: str, payee: str = "Somebody", lines: int = 3,
      net: str = "1000.00", gross: str | None = None, month: str = "2025-01",
      credits: str = "0", judged: int = 0) -> Group:
    return Group(account=account, payee=payee, lines=lines,
                 net=Decimal(net), gross=Decimal(gross or net),
                 first_month=month, credits=Decimal(credits), judged=judged)


# Every account in the 2025 chart, so the sweep below has something real to
# run over and cannot silently check nothing.
ACCOUNTS = [
    "Grant Expenses:Drive AM", "Grant Expenses:LTM Grant",
    "Grant Expenses:AAMEN Grant", "Grant Expenses:Digital Engineering",
    "Grant Expenses:Rising Tides Expense", "Grant Expenses:DOE Hybrid",
    "Grant Expenses:DLA Grant", "Grant Expenses:ARC Arise",
    "Program Expenses:ESP:5221 ESP/EIR Consulting",
    "Program Expenses:ESP:5227 Portfolio consulting",
    "Program Expenses:5014 MBAC - ODSA - YBI",
    "Program Expenses:SBA Growth Accelerator",
    "5010 Depreciation Expense", "5129 Payroll Expenses:5130 Benefits",
    "5129 Payroll Expenses:5139 Wages:5140 Employee Wages",
    "5129 Payroll Expenses:5139 Wages:5142 Intern Wages",
    "Management & Administrative Expenses:5024 Facilities Expense:5035 Maintenance",
    "Management & Administrative Expenses:5024 Facilities Expense:5051 Utilities:5027 TTC Utilities",
    "Management & Administrative Expenses:5200 Real Estate Tax",
    "Management & Administrative Expenses:5075 Insurance",
    "Management & Administrative Expenses:5201 Professional Services:5202 Accounting",
    "Management & Administrative Expenses:5250 Meals & Entertainment",
    "5080 Fundraising:5085 Advertising", "5310 Interest Expense",
    "5107 Interest Income", "5108 Other Income",
    "Management & Administrative Expenses:5215 Dues and Subscriptions",
]


def test_there_are_accounts_to_check():
    """A sweep that checks nothing passes for ever."""
    assert len(ACCOUNTS) > 20
    assert any(not judge(g(a)).blocked for a in ACCOUNTS)
    assert any(judge(g(a)).blocked for a in ACCOUNTS)


@pytest.mark.parametrize("account", ACCOUNTS)
def test_no_recommendation_the_database_would_refuse(account):
    """`direct_needs_objective` and `unallowable_not_allowable`, in the one
    place that can break them.

    The first is an equality, not an implication — DIRECT requires an
    objective *and* every other pool requires none — so a proposal carrying
    OVERHEAD with an objective is refused exactly as hard as DIRECT without
    one. `classify.propose()` was violating it on 24 accounts of the live
    ledger, which is how this test came to exist.
    """
    j = judge(g(account))
    if j.blocked:
        return
    assert (j.pool == "DIRECT") == (j.objective_id is not None), (
        f"{account} proposes {j.pool} with objective {j.objective_id!r} — "
        f"direct_needs_objective refuses that.")
    if j.pool in ("FUNDRAISING", "UNALLOWABLE"):
        assert j.federal != "ALLOWABLE", (
            f"{account} proposes {j.pool} as federally allowable, which "
            f"unallowable_not_allowable refuses. A fundraising dollar is not "
            f"a federal dollar.")
    assert j.grade in ("MANAGEMENT_RECONSTRUCTION", "CORROBORATED")
    assert j.rationale.strip(), (
        "supported_needs_rationale refuses a graded decision with no "
        "rationale, and a recommendation with no reason is worth less than "
        "the machine's own list")


def test_a_split_within_one_pool_is_proposed():
    """The defect this module was written around.

    Five crosswalk entries divide by natural type — labour, subawards,
    materials, travel — and every branch is a 5xxx account, which is DIRECT.
    The split decides which 2026 account and the queue is asking which 2025
    pool, so refusing it is refusing on punctuation.
    """
    j = judge(g("Grant Expenses:Drive AM"))
    assert j.pool == "DIRECT" and j.objective_id == "DRIVE-AM"
    assert j.basis == CROSSWALK_ONE_POOL
    for leaf in ("Rising Tides Expense", "LTM Grant", "Drive AM",
                 "Digital Engineering", "AAMEN Grant"):
        target = CROSSWALK[leaf][0]
        pools = {pool_for(p.strip()) for p in target.split("/")}
        assert len(pools) == 1, (
            f"{leaf} no longer maps within one pool ({target}), so this "
            f"module must stop proposing it")


#: Crosswalk entries that genuinely divide across pools and reach the
#: crosswalk branch — no earlier rule in `judge()` names them. Derived from
#: the crosswalk rather than listed by hand, because the first version of the
#: test below listed three accounts by hand and every one of them was blocked
#: by a *named* rule several branches earlier. It therefore passed with the
#: cross-pool test deleted: a test that could not fail for the thing it named,
#: which is the defect this repository keeps finding in its own checks.
def _cross_pool_leaves() -> list[str]:
    out = []
    for leaf, (target, _) in CROSSWALK.items():
        pools = {pool_for(p.strip()) for p in target.split("/")}
        pools.discard(None)
        if len(pools) > 1:
            out.append(leaf)
    return out


#: Cross-pool splits that a *named rule* resolves before the crosswalk
#: branch is ever reached, so they resolve from the leaf alone with no parent
#: in the path. Each carries its reason: an allowlist entry with no reason is
#: the defect wearing a permission slip, and this list can only shrink by
#: somebody noticing.
#: The nine occupancy accounts share one reason, so it is written once and
#: they are read from the module rather than copied nine times — nine copies
#: of one sentence is a hand-kept map, and the day one of them stops being
#: occupancy the list would still claim it was.
DELIBERATE: dict[str, str] = {
    **{leaf: ("occupancy: 2025 has no rental pool, so it goes to OVERHEAD and "
              "the tenant share comes out as a 200.465 carve-out at rate time")
       for leaf in OCCUPANCY},
    "5027 TTC Utilities": "rebilled to Steelite International in full and "
                          "evidenced line for line, so it is EXCLUDED rather "
                          "than split at all",
    "5215 Dues and Subscriptions": "200.454 as it actually reads: (a) and (b) "
                                   "allow business and professional bodies "
                                   "and periodicals, (c) makes civic "
                                   "membership allowable with prior approval "
                                   "rather than unallowable, and only (d) — a "
                                   "country, social or dining club — is "
                                   "refused outright. No payee is a club.",
}


def test_the_deliberate_exceptions_are_still_needed():
    """An allowlist that outlives its entries is the defect wearing a
    permission slip. Every name here must still be a cross-pool split that
    `judge()` still resolves, and must still say why."""
    cross = set(_cross_pool_leaves())
    for leaf, reason in DELIBERATE.items():
        assert leaf in cross, (
            f"{leaf} is no longer a cross-pool split — drop it from "
            f"DELIBERATE rather than leaving a stale exemption")
        assert not judge(g(leaf)).blocked, (
            f"{leaf} is now blocked, so it does not need an exemption")
        assert len(reason) > 25, f"{leaf} is exempted with no real reason"


def test_a_split_across_pools_is_refused_when_nothing_names_the_function():
    """The guarantee, stated the way the code actually holds it.

    A bare leaf carries no parent, so there is no signal for *whose activity
    this is*. Without one, a cross-pool split proposes nothing — proposing a
    side would be inventing the driver, which is what the original refusal
    was right about.
    """
    leaves = [x for x in _cross_pool_leaves() if x not in DELIBERATE]
    assert len(leaves) > 5, "no cross-pool splits left to check"
    reached = 0
    for leaf in leaves:
        j = judge(g(leaf))
        assert j.blocked, (
            f"{leaf} divides across pools and nothing in a bare leaf says "
            f"which side it belongs on, yet {j.pool} was proposed")
        assert j.blocked_on, "a blocked group must say what it waits for"
        if j.blocked_on == "a documented driver":
            reached += 1
    assert reached > 3, (
        "every cross-pool split is caught by an earlier named rule, so this "
        "test never exercises the crosswalk branch it is written about")


def test_the_parent_of_the_account_settles_a_split_of_function():
    """And the signal that does exist, when the path carries it.

    2025 files every account under a parent that says what kind of activity
    it is, and where a split turns on *whose activity is this* the parent
    answers it. Travel under Management & Administrative Expenses is the
    bookkeeper saying the trip was administrative — weaker than a timesheet,
    and not nothing. Refusing it while using the same path for the objective
    would hold one signal to two standards.
    """
    admin = judge(g("Management & Administrative Expenses:5205 Travel:5206 Travel"))
    assert admin.pool == "G&A", (
        "travel filed under administration is not being read as "
        "administrative")
    assert "filed by the bookkeeper" in admin.rationale

    fund = judge(g("5080 Fundraising:5095 Workshops/Seminars"))
    assert fund.pool == "FUNDRAISING"

    bare = judge(g("5206 Travel"))
    assert bare.blocked, (
        "the same account with no parent in the path resolves anyway, so the "
        "rule is guessing rather than reading a signal")


def test_insurance_stays_blocked_on_its_own_named_rule():
    """Not the parent rule — insurance never reaches it.

    The first version of this test said insurance exercised the
    "more than one candidate" guard. It does not: a named rule several
    branches earlier catches it, so the test passed with that guard deleted.
    The same shape as the cross-pool test before it, found the same way.
    """
    j = judge(g("Management & Administrative Expenses:5075 Insurance"))
    assert j.blocked and j.blocked_on == "the policy schedule"
    assert "combined indirect rate" in j.rationale


def test_more_than_one_candidate_means_no_candidate():
    """The guard, tested where it can actually be reached.

    No cross-pool split in the live crosswalk divides two *indirect*
    branches, so nothing exercises this through `judge()` — which is exactly
    why it is tested on the function directly. The day somebody adds a split
    between OVERHEAD and G&A, the alternative to this guard is silently
    picking whichever came first.
    """
    assert pick_branch("INDIRECT", {"G&A": "8600", "DIRECT": "5500"}) == "G&A"
    assert pick_branch("INDIRECT", {"OVERHEAD": "7300", "G&A": "8300"}) is None
    assert pick_branch("DIRECT", {"DIRECT": "5500", "G&A": "8600"}) == "DIRECT"
    assert pick_branch("FUNDRAISING", {"FUNDRAISING": "9110", "G&A": "8500"}) \
        == "FUNDRAISING"
    assert pick_branch(None, {"DIRECT": "5500", "G&A": "8600"}) is None, (
        "an account whose path names no parent function gets a side picked "
        "for it anyway")


def test_a_blocked_group_says_what_would_unblock_it():
    """"Cannot be classified" on its own is a dead end — the defect this
    repository keeps finding. Every block names the thing to go and get."""
    for account in ACCOUNTS:
        j = judge(g(account))
        if not j.blocked:
            continue
        assert j.blocked_on and len(j.blocked_on) > 3
        assert len(j.rationale) > 60, (
            f"{account} is blocked with a reason too short to act on: "
            f"{j.rationale!r}")


def test_a_pass_through_is_not_cost():
    """$257,774 of gross movement and $0.00 net, because a tenant pays all of
    it. Putting that in OVERHEAD is two entries that cancel, inside a pool an
    indirect rate is taken over."""
    j = judge(g("Management & Administrative Expenses:5024 Facilities "
                "Expense:5051 Utilities:5027 TTC Utilities", net="0.00",
                gross="257774.24"))
    assert j.pool == "EXCLUDED" and j.basis == ANALYSIS
    assert "Steelite" in j.rationale


def test_occupancy_goes_to_overhead_and_warns_about_the_carve_out():
    """2025 has no rental pool: occupancy is OVERHEAD and the tenant share
    comes out at rate time. But a group already carrying tenant credits is
    part-netted before the carve-out ever runs, and carving on top of it
    removes the same money twice."""
    plain = judge(g("Management & Administrative Expenses:5200 Real Estate Tax"))
    assert plain.pool == "OVERHEAD"
    netted = judge(g("Management & Administrative Expenses:5200 Real Estate Tax",
                     credits="61469.77"))
    assert netted.pool == "OVERHEAD"
    assert "twice" in netted.rationale, (
        "a group already net of tenant recovery does not warn that carving a "
        "square-footage share on top would remove it twice")


def test_a_group_already_judged_is_not_re_proposed():
    """The log walks the whole ledger so it reads the same after its own
    recommendations are accepted. What it must not do is offer to re-judge
    what somebody has already decided."""
    j = judge(g("Grant Expenses:Drive AM", judged=4))
    assert j.basis == RECORDED and j.pool is None
    s = summarise(walk([g("Grant Expenses:Drive AM", judged=4),
                        g("Grant Expenses:LTM Grant")]))
    assert s["recorded"] == 1 and s["judged"] == 1 and s["blocked"] == 0


def test_the_walk_reaches_every_group_once_in_ledger_order():
    groups = [g("a", month="2025-03"), g("b", month="2025-01"),
              g("c", month="2025-01", gross="9"), g("d", month="2025-12")]
    walked = walk(groups)
    assert len(walked) == len(groups)
    assert [x[0].account for x in walked] == ["b", "c", "a", "d"]
    assert {x[0].account for x in walked} == {"a", "b", "c", "d"}


def test_every_objective_in_the_map_is_a_real_objective():
    """A DIRECT proposal naming an objective that does not exist is refused
    by a foreign key, which is the same defect as naming none."""
    sql = "\n".join(p.read_text() for p in sorted((ROOT / "app" / "sql").glob("*.sql")))
    for _, objective in OBJECTIVE_BY_PATH:
        assert re.search(rf"'{re.escape(objective)}'", sql), (
            f"{objective} is proposed for DIRECT cost and no migration "
            f"creates a cost_objective row for it")


def test_the_queue_no_longer_proposes_what_it_cannot_accept():
    """`classify.propose()`, the other half of the same rule.

    It offered DIRECT with `objective_id: None` on every crosswalk account
    mapping into the 5xxx range — 24 of them in the live ledger — so pressing
    Enter on the queue's own suggestion answered a constraint violation.
    """
    src = (ROOT / "app" / "routers" / "classify.py").read_text()
    body = src[src.index("def propose("):src.index("class MaterialityIn")]
    assert "objective_for(" in body, (
        "propose() no longer resolves an objective from the account path, so "
        "its DIRECT proposals carry none and the database refuses them")
    assert '"objective_id": None' not in body.split("if mapped:")[-1], (
        "the crosswalk branch is back to proposing DIRECT with no objective")
    assert '"/" not in mapped[0]' not in body, (
        "propose() is back to testing for a slash rather than for the pools, "
        "which refuses $1,382,737 of the queue on punctuation")


def test_the_walk_is_the_same_read_either_way():
    """December back to January must change the order and nothing else.

    `judge()` is a pure function of one group and holds no state between
    calls, so the same ledger has to produce the same judgments read in
    either direction. That is a claim, and a claim here is a thing to check:
    a log whose recommendations depended on the direction of the read would
    be one where the order of the books decided the rate, and nobody would
    find that by looking at either run on its own.

    Compared by group key, not by position — the positions are *supposed* to
    differ, and an elementwise comparison would report 757 differences on a
    correct run, which is a test arguing against working code.
    """
    # Three payees per account, because the live ledger is 757 groups over
    # 87 accounts and an account repeats across payees. A fixture of
    # distinct accounts cannot catch the order-dependence that matters —
    # a walk that remembered which accounts it had already seen passed this
    # test with one group per account and would have mangled the real
    # ledger. Found by breaking it on purpose and watching it not fail.
    groups = [g(a, payee=f"payee-{k}", month=f"2025-{i % 12 + 1:02d}",
                net=str(100 * (i + 1) + k))
              for i, a in enumerate(ACCOUNTS) for k in range(3)]
    assert len({x.account for x in groups}) < len(groups), (
        "the fixture has one group per account, so a walk that carried state "
        "between groups of the same account would pass this test")
    fed = frozenset({"DRIVE-AM", "LTM", "AAMEN", "DIG-ENG", "HYBRID-II", "DLA"})
    forward = walk(groups, federal_objectives=fed)
    backward = walk(groups, reverse=True, federal_objectives=fed)

    assert [x[0].key for x in forward] != [x[0].key for x in backward], (
        "reverse=True did not change the order, so this test cannot fail "
        "for the thing it names")
    assert not disagreements(forward, backward)

    # And it has to catch a real difference, not just agree with itself.
    poisoned = [(gg, jj) for gg, jj in backward]
    poisoned[0] = (poisoned[0][0],
                   judge(g("Grant Expenses:Drive AM"), frozenset({"DRIVE-AM"})))
    assert disagreements(forward, poisoned), (
        "disagreements() reports nothing when two walks genuinely differ")


def test_a_non_federal_objective_is_not_federally_allowable():
    """ALLOWABLE is an assertion about a federal award.

    The first version of this log wrote it for every DIRECT judgment, which
    put $986,592.77 of cost on non-federal objectives — Rising Tides, ESP,
    the Hub, MBAC — down as claimable against a federal award. Rising Tides
    is the one that matters: whether it is federally funded is an open
    question in the engagement, the objective master says it is not, and a
    log asserting ALLOWABLE would have taken a side on it in 33 places
    without saying so.
    """
    federal = judge(g("Grant Expenses:Drive AM"), frozenset({"DRIVE-AM"}))
    assert federal.pool == "DIRECT" and federal.federal == "ALLOWABLE"

    not_federal = judge(g("Grant Expenses:Rising Tides Expense"),
                        frozenset({"DRIVE-AM"}))
    assert not_federal.pool == "DIRECT"
    assert not_federal.federal == "NOT_APPLICABLE", (
        "cost on an objective the record does not call federal is being "
        "reported as federally allowable")
    assert "not a federal objective" in not_federal.rationale, (
        "the judgment says NOT_APPLICABLE and does not say why, so a reader "
        "cannot tell it from an oversight")


def test_the_safe_default_is_not_federal():
    """A caller that forgets to pass the federal set gets the conservative
    answer rather than the flattering one."""
    j = judge(g("Grant Expenses:Drive AM"))
    assert j.federal == "NOT_APPLICABLE"
