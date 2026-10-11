"""M8 S4: the host-nation strategies and the is_home view of a match."""

from datetime import date

import pytest

from tennisdb.backtest.domain import MatchOpportunity
from tennisdb.backtest.strategies import STRATEGIES, build_strategy

pytestmark = pytest.mark.m8


def _opportunity(p1_is_home: bool, p2_is_home: bool, p1_price=1.5, p2_price=2.8):
    return MatchOpportunity(
        match_id="m",
        match_date=date(2019, 1, 1),
        season=2019,
        tour="atp",
        surface="Hard",
        level="A",
        round="R32",
        p1_price=p1_price,
        p2_price=p2_price,
        p1_consensus_price=p1_price,
        p2_consensus_price=p2_price,
        p1_consensus_prob=0.65,
        p1_elo_prob=0.5,
        p1_surface_elo_prob=0.5,
        p1_is_home=p1_is_home,
        p2_is_home=p2_is_home,
    )


def test_back_home_nation_one_home_player_backs_that_player():
    strategy = build_strategy("back_home_nation", {})

    bet = strategy.evaluate(_opportunity(p1_is_home=False, p2_is_home=True))

    assert bet.side == "p2"


def test_fade_home_nation_one_home_player_backs_the_visitor():
    strategy = build_strategy("fade_home_nation", {})

    bet = strategy.evaluate(_opportunity(p1_is_home=False, p2_is_home=True))

    assert bet.side == "p1"


@pytest.mark.parametrize("name", ["back_home_nation", "fade_home_nation"])
@pytest.mark.parametrize("flags", [(False, False), (True, True)])
def test_host_nation_strategies_no_home_asymmetry_place_no_bet(name, flags):
    strategy = build_strategy(name, {})

    assert strategy.evaluate(_opportunity(*flags)) is None


def test_back_home_nation_price_outside_band_places_no_bet():
    strategy = build_strategy("back_home_nation", {"max_price": 2.0})

    assert strategy.evaluate(_opportunity(p1_is_home=False, p2_is_home=True)) is None


def test_host_nation_strategies_are_registered_with_price_band_parameters():
    for name in ("back_home_nation", "fade_home_nation"):
        assert {spec.name for spec in STRATEGIES[name].parameters} == {"min_price", "max_price"}


def test_opportunity_is_home_unknown_defaults_to_not_home():
    opportunity = _opportunity(False, False)

    assert not opportunity.is_home("p1") and not opportunity.is_home("p2")
