"""M7: BacktestRequest.from_dict is the single validation gate — every rejection names
the allowed values, so a caller can self-correct from the error text alone."""

import pytest

from tennisdb.backtest.request import BacktestRequest, InvalidBacktestRequest, MatchFilter

pytestmark = pytest.mark.m7


def test_from_dict_applies_defaults_for_a_minimal_request():
    request = BacktestRequest.from_dict({"strategy": "random_bet"})

    assert request.strategy == "random_bet"
    assert request.stake_rule == "flat"
    assert request.strategy_parameters == {"seed": 7}
    assert request.filters == MatchFilter()


def test_from_dict_round_trips_through_to_dict():
    payload = {
        "strategy": "elo_value",
        "strategy_parameters": {"theta": 0.1, "use_surface_elo": 1},
        "filters": {
            "tour": "atp",
            "surfaces": ["Clay"],
            "levels": [],
            "rounds": [],
            "from_season": 2015,
            "to_season": 2018,
        },
        "stake_rule": "kelly",
        "stake_parameters": {"multiplier": 0.5, "cap": 0.1},
        "fill_preference": ["Avg"],
        "slippage": 0.0,
        "starting_bankroll": 500.0,
        "bootstrap_draws": 500,
        "random_seed": 1,
    }

    request = BacktestRequest.from_dict(payload)

    assert request.to_dict() == payload


def test_from_dict_rejects_an_unknown_top_level_field():
    with pytest.raises(InvalidBacktestRequest, match="unknown field"):
        BacktestRequest.from_dict({"strategy": "random_bet", "nonsense": 1})


def test_from_dict_rejects_an_unknown_strategy_naming_the_valid_ones():
    with pytest.raises(InvalidBacktestRequest, match="elo_value"):
        BacktestRequest.from_dict({"strategy": "zodiac_edge"})


def test_from_dict_rejects_an_unknown_strategy_parameter():
    with pytest.raises(InvalidBacktestRequest, match="unknown parameter"):
        BacktestRequest.from_dict(
            {"strategy": "elo_value", "strategy_parameters": {"not_a_real_param": 1}}
        )


def test_from_dict_rejects_an_out_of_band_parameter_value():
    with pytest.raises(InvalidBacktestRequest, match="maximum"):
        BacktestRequest.from_dict(
            {"strategy": "elo_value", "strategy_parameters": {"theta": 10.0}}
        )


def test_from_dict_rejects_an_inverted_season_window():
    with pytest.raises(InvalidBacktestRequest, match="from_season"):
        BacktestRequest.from_dict(
            {"strategy": "random_bet", "filters": {"from_season": 2020, "to_season": 2010}}
        )


def test_from_dict_rejects_an_empty_fill_preference():
    with pytest.raises(InvalidBacktestRequest, match="fill_preference"):
        BacktestRequest.from_dict({"strategy": "random_bet", "fill_preference": []})


def test_from_dict_rejects_an_unknown_stake_rule():
    with pytest.raises(InvalidBacktestRequest, match="flat"):
        BacktestRequest.from_dict({"strategy": "random_bet", "stake_rule": "double_or_nothing"})
