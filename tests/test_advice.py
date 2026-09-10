"""The advisor's job is to be useful without being confident about things it
cannot know."""

from decimal import Decimal

from app.domain.advice import GroupFacts, advise


def kinds(g):
    return {a.kind for a in advise(g)}


def headlines(g):
    return [a.headline for a in advise(g)]


def test_a_vendors_trading_name_is_not_a_cost_category():
    """"S-Gen Marketing LLC" is who was paid, not what for."""
    g = GroupFacts(account="Program Expenses:ESP:5227 Portfolio consulting",
                   payee="S-Gen Marketing LLC", amount=Decimal("100000"),
                   line_count=8)
    assert not any("advertising" in h.lower() for h in headlines(g))


def test_meals_are_flagged_for_splitting():
    g = GroupFacts(account="5210 Meals and Entertainment", line_count=3)
    assert "SPLIT" in kinds(g)
    assert any("200.438" in a.citation for a in advise(g))


def test_two_objectives_in_one_group_suggests_a_split():
    g = GroupFacts(account="5227 Consulting", line_count=12,
                   objective_hints=["Drive AM", "Hub", "Drive AM"])
    assert any("2 different objectives" in h for h in headlines(g))


def test_the_same_account_classified_two_ways_is_a_consistency_flag():
    g = GroupFacts(account="5300 Supplies", line_count=4,
                   prior_pools=["G&A", "DIRECT"])
    assert "CONSISTENCY" in kinds(g)
    assert any("200.403(d)" in a.citation for a in advise(g))


def test_one_prior_pool_is_a_merge_nudge_not_a_conflict():
    g = GroupFacts(account="5300 Supplies", line_count=4, prior_pools=["G&A"])
    assert "MERGE" in kinds(g)
    assert "CONSISTENCY" not in kinds(g)


def test_a_credit_is_called_out():
    g = GroupFacts(account="5300 Supplies", amount=Decimal("-2500"), line_count=2)
    assert any("credit" in h.lower() for h in headlines(g))


def test_advice_is_ordered_strongest_first_and_never_repeats():
    g = GroupFacts(account="5210 Meals and Travel", line_count=200,
                   objective_hints=["A", "B"], prior_pools=["G&A", "DIRECT"])
    got = advise(g)
    assert [a.weight for a in got] == sorted((a.weight for a in got), reverse=True)
    assert len({a.headline for a in got}) == len(got)


def test_nothing_to_say_is_an_empty_list_not_a_guess():
    g = GroupFacts(account="4010 Program Fees", line_count=1,
                   amount=Decimal("500"))
    assert advise(g) == []
