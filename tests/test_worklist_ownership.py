"""Every outstanding thing has somebody who can do it, and somewhere to do it.

v_worklist has always known what is undone and never whose job it is, so
every screen showed everybody the same list. That is a dashboard, not a
morning: Heidi should open the application and see that the buildings have no
square footage against them, not read past four items belonging to somebody
else to find hers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "app" / "sql"
DASH = (ROOT / "app" / "routers" / "dashboard.py").read_text()

PORTFOLIOS = {"CONTROLLER", "INVENTORY", "PROJECT", "FACILITIES", "OFFICE"}


def _view(name: str) -> str:
    """The definition that actually runs — the last migration to define it."""
    for path in sorted(SQL.glob("*.sql"), reverse=True):
        src = path.read_text()
        i = src.find(f"CREATE OR REPLACE VIEW {name} AS")
        if i == -1:
            i = src.find(f"CREATE VIEW {name} AS")
        if i == -1:
            continue
        # To the next CREATE or COMMENT at column zero, so a semicolon inside
        # a comment does not truncate the body.
        j = len(src)
        for marker in ("\nCOMMENT ON", "\nCREATE "):
            k = src.find(marker, i + 10)
            if k != -1:
                j = min(j, k)
        return src[i:j]
    raise AssertionError(f"{name} is not defined in any migration")


OWNED = _view("v_worklist_owned")

#: Every kind v_worklist and v_worklist_extra can emit, read out of them.
#:
#: This was a list kept by hand, and the hand-kept list was missing
#: STALE_CERTIFICATION and DONATION_RATE_MISSING — which is exactly how both
#: came to be unrouted, landing on the ELSE with the controller as owner and
#: `/` as destination. A test whose subject is "no kind falls off the end"
#: cannot keep its own list of the kinds; it has the same defect it is
#: looking for. The review script learned this when a hand-kept map of what
#: each screen calls reported four correct responses as faults.
KINDS = sorted({
    kind
    for view in ("v_worklist", "v_worklist_extra")
    for kind in re.findall(r"SELECT\s+'([A-Z_]{4,})'", _view(view))
})


def test_the_kinds_were_actually_found():
    """If the derivation breaks, every test below passes over an empty list."""
    assert len(KINDS) >= 14, (
        f"only {len(KINDS)} kinds read out of the worklist views: {KINDS}. "
        f"The parametrised tests below would pass over whatever is missing.")


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_an_owner(kind):
    assert f"'{kind}'" in OWNED, (
        f"{kind} is not routed to a portfolio, so it falls to the ELSE and "
        f"lands on the controller by accident rather than by decision.")


#: The two CASE expressions, cut apart. A window taken as a fixed number of
#: characters back from "AS goes_to" overlapped the owner CASE, so the
#: destination test was passing on the owner routing — it could not fail for
#: the thing it names, and did not when two kinds had no destination.
OWNERS = OWNED[:OWNED.index("AS owner_portfolio")]
DESTINATIONS = OWNED[OWNED.index("AS owner_portfolio"):OWNED.index("AS goes_to")]


def test_the_two_case_expressions_were_actually_separated():
    assert "/classify" not in OWNERS and "'CONTROLLER'" not in DESTINATIONS, (
        "the owner and destination CASE expressions overlap, so each test "
        "below can pass on the other one's routing.")


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_says_where_to_go(kind):
    """A list that says what is wrong and not where to fix it is a list
    somebody hunts through the nav for."""
    assert f"'{kind}'" in DESTINATIONS, f"{kind} has no destination"


def test_the_owner_is_a_real_portfolio():
    #: `THEN 'X'` followed by a newline matched nothing at all once the view
    #: was lifted out of pg_get_viewdef, which writes `THEN 'X'::text`. The
    #: set was empty and the test passed over it.
    routed = set(re.findall(r"THEN '([A-Z_]+)'(?:::text)?\s*$", OWNERS, re.M))
    assert routed, "no portfolio routing found at all; the regex matches nothing"
    unknown = {r for r in routed if r not in PORTFOLIOS}
    assert not unknown, (
        f"routed to something that is not a portfolio: {sorted(unknown)}. "
        f"Nobody can hold it, so nobody can act on it.")


def test_the_controller_sees_everything():
    """It is what the portfolio means, not a special case."""
    assert "Portfolio.CONTROLLER in actor.portfolios" in DASH, (
        "the worklist endpoint does not give the controller everything, so "
        "an item whose portfolio nobody holds falls off the end.")


def test_a_manager_cannot_sign_a_certification_for_somebody():
    """2 CFR 200.430(i) wants the person whose effort it was.

    The chase list is who to go and ask. If it ever grows an action that
    signs on their behalf, the signature stops being worth having.
    """
    chase = _view("v_certification_chase")
    assert "certified" in chase and "assigned_by" in chase
    for banned in ("INSERT INTO labor_certification", "UPDATE labor_certification"):
        assert banned not in DASH, (
            f"the worklist endpoint {banned} — a manager cannot sign for "
            f"somebody else.")


def test_an_award_with_no_ceiling_is_on_somebody_list():
    """Last Tactical Mile carried a ceiling of zero for the whole engagement.

    The citation said "Ceiling not yet transcribed from the agreement" — an
    honest placeholder that went quiet. The executed agreement had been on
    file since September and §4.3, $899,500 federal and $513,065 cost share,
    had never been read into the record. It surfaced because somebody looked
    at a screen and asked, which is not a control.

    A ceiling is what a restatement is capped against. An award without one
    cannot be tested against anything, so it belongs on a list.
    """
    extra = _view("v_worklist_extra")
    assert "AWARD_NO_CEILING" in extra, (
        "nothing asks about an award with no ceiling, so a placeholder can "
        "sit there for a whole engagement.")
    assert "a.ceiling_federal = 0" in extra
