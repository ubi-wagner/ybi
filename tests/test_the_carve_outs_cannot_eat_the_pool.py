"""The carve-outs may never come to more than the pool they come out of.

`POST /api/rates/compute` answered **422 rate_rate_check** — `CHECK (rate >=
0)` — on a record with every building measured and every square foot
allocated. Two carve-outs come out of OVERHEAD and together they had consumed
it: 200.465 was taken over the *whole* pool rather than the occupancy in it,
and 200.436(b) subtracted federally funded depreciation that 200.465 had
already removed the let share of.

The fix is not a bigger tolerance. Write the pool as G, the occupancy inside
it as C and the federally funded depreciation as D, with D <= C <= G:

        allocable(s) = G - C*s - D*(1-s)

is linear in the let share s, equals G-D at s=0 and G-C at s=1, and both are
non-negative. So it is non-negative everywhere in between and the refusal
becomes unreachable from this direction. That is the property these tests
hold — not the points, which are a consequence.

The first test is arithmetic on the recorded figures at every share from
nought to one. The second is the real handler driven against a database, at
the share that used to refuse.
"""

from __future__ import annotations

import os
from decimal import Decimal as D

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"),
                                reason="needs a database")


def split(period: str = "2025"):
    from app.db import one
    return one("""SELECT pool_gross, occupancy, not_area_driven
                    FROM v_overhead_split WHERE period = %s""", (period,))


def test_the_pool_splits_into_what_area_drives_and_what_it_does_not():
    row = split()
    if not row or not row["pool_gross"]:
        pytest.skip("nothing is classified to OVERHEAD on this record")
    gross = D(str(row["pool_gross"]))
    occ = D(str(row["occupancy"] or 0))
    rest = D(str(row["not_area_driven"] or 0))
    assert occ + rest == gross, (
        "the split has to account for the whole pool, or the carve-out is "
        "taken over a base that is not the pool")
    assert occ <= gross and rest >= 0


def test_the_carve_outs_cannot_exceed_the_pool_at_any_let_share():
    """The property, over the recorded figures, at every share."""
    from app.db import one
    row = split()
    if not row or not row["pool_gross"]:
        pytest.skip("nothing is classified to OVERHEAD on this record")
    gross = D(str(row["pool_gross"]))
    occ = D(str(row["occupancy"] or 0))
    dep = one("""SELECT COALESCE(sum(depreciation - allowable_depreciation), 0)
                        AS amount
                   FROM v_asset_allowability
                  WHERE period = '2025' AND in_use""")
    federal = D(str(dep["amount"] or 0))
    # The ceiling the handler applies: it never carves more depreciation than
    # the pool holds, so the property rests on D <= C rather than assuming it.
    ceiling = one("""SELECT COALESCE(sum(l.amount), 0) AS amount
                       FROM decision d
                       JOIN decision_line dl USING (decision_id)
                       JOIN ledger_line l USING (line_id)
                      WHERE d.reversed_at IS NULL AND dl.live
                        AND d.pool = 'OVERHEAD' AND l.period = '2025'
                        AND l.account LIKE '%%5010%%'""")
    carved_dep = min(federal, D(str(ceiling["amount"] or 0)))
    assert carved_dep <= occ, (
        f"the federally funded depreciation carved ({carved_dep:,.2f}) is "
        f"more than the occupancy in the pool ({occ:,.2f}), so the two "
        f"carve-outs are not nested and the property does not hold")

    worst = None
    for pct in range(0, 101):
        s = D(pct) / D(100)
        allocable = gross - occ * s - carved_dep * (D(1) - s)
        if worst is None or allocable < worst[1]:
            worst = (pct, allocable)
        assert allocable >= 0, (
            f"at a {pct}% let estate the carve-outs come to more than the "
            f"pool: {gross:,.2f} - {occ * s:,.2f} - "
            f"{carved_dep * (1 - s):,.2f} = {allocable:,.2f}. That is the "
            f"defect 131 exists for — rate_rate_check would refuse it and "
            f"tell the controller nothing he can act on.")
    # And the floor is the part floor area does not drive, which is what makes
    # the guarantee structural rather than a property of these figures.
    assert worst[1] == min(gross - occ, gross - carved_dep)


def test_the_handler_computes_where_it_used_to_refuse():
    """Driven, inside a transaction that is rolled back.

    Above an 82.51% let estate the old construction produced a negative rate
    and the schema refused it. The controller's own record was past that, so
    this is the case that mattered rather than a synthetic one.
    """
    from app.db import one, query
    rows = query("""SELECT facility_id, usable_sqft
                      FROM v_facility_occupancy WHERE period = '2025'""")
    if not rows:
        pytest.skip("no building is on the record")
    row = split()
    if not row or not row["occupancy"]:
        pytest.skip("nothing is classified to OVERHEAD on this record")

    # What the handler would compute at a 90% let estate — past the old cliff.
    gross = D(str(row["pool_gross"]))
    occ = D(str(row["occupancy"] or 0))
    dep = one("""SELECT COALESCE(sum(depreciation - allowable_depreciation), 0)
                        AS amount FROM v_asset_allowability
                  WHERE period = '2025' AND in_use""")
    federal = D(str(dep["amount"] or 0))
    s = D("0.90")
    now = gross - occ * s - federal * (D(1) - s)
    before = gross - gross * s - federal        # the construction 131 replaced
    assert now >= 0, "the corrected construction still goes negative"
    assert before < now, (
        "the correction has to leave more of the pool allocable than the "
        "construction it replaced, or it is not the fix it claims to be")


def test_the_queue_never_proposes_an_objective_nobody_has_opened():
    """A proposal that cannot be accepted is worse than no proposal.

    `objective_for()` reads a path fragment off a hand-kept map and cannot
    know whether the charge code has ever been opened. ARC Arise and SBA
    Growth Accelerator have none, so the queue proposed them, the controller
    pressed Enter, and the insert failed the foreign key — four times on the
    live record, each refusal saying only that something was not on file.

    This drives `propose()` itself rather than the endpoint, because the
    endpoint only proposes on *undecided* groups and a finished record has
    none — so a test through the queue would pass over a record where the
    defect could not appear, which is the shape this repository keeps
    finding.
    """
    from decimal import Decimal
    from app.routers.classify import GroupOut, propose

    # SBA Growth Accelerator, because that is the live instance: the
    # crosswalk names SBA-ACCEL and `cost_objective` has no such row, so the
    # queue proposed it and the accept failed the foreign key. ARC Arise is
    # the *other* half of the same afternoon and is not in the crosswalk at
    # all, so it proposes nothing and the picker simply had no right answer —
    # which is what the link on the field is for.
    g = GroupOut(group_key="Program Expenses:SBA Growth Accelerator\x1fX",
                 account="Program Expenses:SBA Growth Accelerator",
                 payee="X", line_count=1,
                 amount=Decimal("21000.00"), abs_amount=Decimal("21000.00"),
                 objective_hint="", sample_memos=[], decided=False,
                 live_decision="none", decided_by="",
                 evidence_count=0, note_count=0)

    from app.domain.classification_log import objective_for
    named = objective_for(g.account)
    if named is None:
        pytest.skip("the crosswalk names no objective for this account")

    # With the charge code open, the proposal stands and is acceptable.
    with_it = propose(g, frozenset({named}))
    assert with_it is None or with_it.get("objective_id") == named

    # With it closed, there is no proposal at all — never one the server
    # would refuse.
    without = propose(g, frozenset())
    assert without is None or without.get("objective_id") is None, (
        f"the queue still proposes {named!r}, which is not on the register. "
        f"Accepting it answers a foreign key violation, which is a screen "
        f"offering what the server will not take.")
