"""The settlement memorandum says what the record says.

`docs/SETTLEMENT_2025.md` is the paper that goes to NCDMM, and every figure on
it is read off the cost record rather than recalled. This repository has paid
for the alternative twice already — `PROJECT_CONTEXT.md` carried 22.45% in its
recommendation table while its own §8.6 said 21.90%, and four published
figures were computed against a three-invoice sample of a sixty-one invoice
register. *Figures in a document for somebody else get read from the record,
not recalled*, and a document nothing checks is a document that recalls.

Two figures on the first draft of this memorandum were exactly that: the
controller's retainer priced at 0.69 points, which was arithmetic on the
34.82% rate from before the carve-outs existed, and Drive AM's non-labour gap
at $90,613.08, which compared the restated non-labour against the ODC category
alone instead of against all the non-labour billed. Both were found by running
this check, not by reading.

The other half is the rule the whole restatement rests on: **the register never
nets an over-collection against an under-recovery.** The memorandum is allowed
to state an aggregate — the user asked for one and a single credit is the
commercial mechanism — but only *after* both directions are on the page in
full, and never as a substitute for them.
"""

from __future__ import annotations

import os
import pathlib
import re
from decimal import Decimal as D

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")

MEMO = pathlib.Path(__file__).resolve().parent.parent / "docs" / "SETTLEMENT_2025.md"
PERIOD = "2025"


def _cur(con):
    import psycopg.rows
    return con.cursor(row_factory=psycopg.rows.dict_row)


@pytest.fixture()
def cur():
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        with _cur(con) as c:
            yield c
        con.rollback()


@pytest.fixture()
def memo():
    if not MEMO.exists():
        pytest.skip("the settlement memorandum has not been written")
    return MEMO.read_text()


def money(x) -> str:
    return f"{D(str(x)):,.2f}"


def _live_rates(cur):
    cur.execute("SELECT kind, rate, pool_amount, base_amount "
                "FROM rate WHERE period = %s AND status <> 'SUPERSEDED'",
                (PERIOD,))
    return {r["kind"]: r for r in cur.fetchall()}


def _positions(cur):
    cur.execute("SELECT objective_id, under_recovered, over_collected, "
                "       billed_total, invoices "
                "FROM v_restatement "
                "WHERE period = %s AND status <> 'SUPERSEDED'", (PERIOD,))
    return {r["objective_id"]: r for r in cur.fetchall()}


# ── The rate structure on the paper is the rate on the record ────────

def _rate_table(memo: str) -> str:
    """The §3 table that states the structure, and nothing else.

    Scoped deliberately. Asserting a rate merely *appears somewhere* in a
    nine-page memorandum is satisfied by any one of several mentions, so a
    wrong figure in the table passes as long as the right one survives in a
    footnote — which is how a paper comes to carry two readings of one rate.
    `PROJECT_CONTEXT.md` did exactly that with 22.45% and 21.90%.
    """
    start = memo.find("## 3.")
    assert start > 0, "the memorandum has no §3 rate structure"
    end = memo.find("\n## ", start + 1)
    body = memo[start:end if end > 0 else len(memo)]
    return "\n".join(l for l in body.splitlines() if l.startswith("|"))


def test_every_live_rate_is_stated(cur, memo):
    rates = _live_rates(cur)
    assert rates, "no rate stands on the record"
    missing = [f"{k} {D(str(r['rate'])) * 100:.2f}%"
               for k, r in rates.items()
               if f"{D(str(r['rate'])) * 100:.2f}%" not in memo]
    assert not missing, f"the memorandum does not state: {missing}"


def test_the_rate_table_carries_no_rate_the_record_does_not_hold(cur, memo):
    """Every percentage in the structure table is one of the four on file."""
    recorded = {f"{D(str(r['rate'])) * 100:.2f}%" for r in _live_rates(cur).values()}
    printed = set(re.findall(r"\d+\.\d\d%", _rate_table(memo)))
    assert printed, "the §3 table states no rate at all"
    assert not printed - recorded, (
        f"the rate structure table states {sorted(printed - recorded)}, "
        f"which the record does not hold; it holds {sorted(recorded)}")


def test_every_pool_and_both_bases_are_stated(cur, memo):
    rates = _live_rates(cur)
    missing = [f"{k} pool {money(r['pool_amount'])}"
               for k, r in rates.items() if money(r["pool_amount"]) not in memo]
    for kind in ("INDIRECT_COMBINED", "FRINGE"):
        if kind in rates and money(rates[kind]["base_amount"]) not in memo:
            missing.append(f"{kind} base {money(rates[kind]['base_amount'])}")
    assert not missing, f"the memorandum does not state: {missing}"


def test_every_carve_out_is_stated_with_its_citation(cur, memo):
    cur.execute("SELECT citation, amount FROM carve_out WHERE period = %s",
                (PERIOD,))
    rows = cur.fetchall()
    if not rows:
        pytest.skip("no carve-out has been recorded")
    missing = [f"{r['citation']} {money(r['amount'])}"
               for r in rows if money(r["amount"]) not in memo]
    assert not missing, f"carve-outs not on the paper: {missing}"
    total = sum(D(str(r["amount"])) for r in rows)
    assert money(total) in memo, f"the carve-out total {money(total)} is not stated"
    for citation in {r["citation"] for r in rows}:
        assert citation.replace("2 CFR ", "") in memo, \
            f"{citation} is carved out of the pool and not cited on the paper"


# ── Each award's offset, in the direction it runs ────────────────────

def test_every_award_position_is_stated(cur, memo):
    positions = _positions(cur)
    assert positions, "no restatement stands on the record"
    missing = []
    for obj, r in sorted(positions.items()):
        for field in ("under_recovered", "over_collected"):
            amount = D(str(r[field]))
            if amount > 0 and money(amount) not in memo:
                missing.append(f"{obj} {field} {money(amount)}")
        if money(r["billed_total"]) not in memo:
            missing.append(f"{obj} billed {money(r['billed_total'])}")
    assert not missing, f"the memorandum does not state: {missing}"


def test_the_aggregate_is_arithmetic_on_the_recorded_positions(cur, memo):
    """The aggregate is allowed, and it has to be the sum of what is recorded.

    A settlement figure that is not the arithmetic of the positions is a
    number somebody chose.
    """
    positions = _positions(cur)
    claim = sum(D(str(r["under_recovered"])) for r in positions.values())
    give = sum(D(str(r["over_collected"])) for r in positions.values())
    assert money(claim) in memo, f"the total to claim {money(claim)} is not stated"
    assert money(give) in memo, f"the total to return {money(give)} is not stated"
    assert money(give - claim) in memo or money(claim - give) in memo, \
        f"the aggregate {money(give - claim)} is not stated"


# ── And it never nets in place of saying both ────────────────────────

def test_both_directions_appear_before_any_aggregate(cur, memo):
    """The aggregate may not be the first thing a reader meets.

    `v_restatement` carried `under_recovered - over_collected AS net_movement`
    once and migration 061 removed it, because $120,000 to ask for and
    $120,000 to give back is not a quiet year. A memorandum that opened on the
    net would do the same thing to a reader that the column did to a screen.
    """
    positions = _positions(cur)
    claim = sum(D(str(r["under_recovered"])) for r in positions.values())
    give = sum(D(str(r["over_collected"])) for r in positions.values())
    net = money(give - claim)
    first_net = memo.find(net)
    if first_net < 0:
        pytest.skip("the memorandum states no aggregate")
    for label, amount in (("to claim", claim), ("to return", give)):
        where = memo.find(money(amount))
        assert 0 <= where < first_net, (
            f"the aggregate {net} appears before the total {label} "
            f"{money(amount)}; both directions come first")


def test_the_memorandum_says_the_two_directions_are_not_added(memo):
    """Stated as a rule on the paper, not merely implied by the layout."""
    assert re.search(r"not added together|never added together", memo), \
        ("the memorandum has to say that money to ask for and money to give "
         "back are not added together")


# ── The band, and what it does not claim ─────────────────────────────

def test_the_paper_says_whether_the_rate_is_certified(cur, memo):
    cur.execute("SELECT certified, certified_by FROM v_rate_certified "
                "WHERE period = %s", (PERIOD,))
    row = cur.fetchone()
    if row is None:
        pytest.skip("no certification row for the period")
    if row["certified"]:
        assert "CERTIFIED" in memo, "the rate is certified and the paper is silent"
        assert row["certified_by"] in memo, \
            f"the paper does not name {row['certified_by']} as the signatory"
    else:
        assert "NOT CERTIFIED" in memo, \
            "nobody has signed the rate and the paper does not say so"


def test_nothing_on_the_paper_is_a_claim_until_the_sponsor_accepts(cur, memo):
    cur.execute("SELECT DISTINCT status FROM restatement WHERE period = %s",
                (PERIOD,))
    assert "PROPOSED" in memo or "accepts it in writing" in memo, \
        "a position put to a sponsor is a proposal until they answer in writing"
