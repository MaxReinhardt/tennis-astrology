"""M7: staking rules turn (probability, price, bankroll) into a stake. Flat ignores
probability, fixed-fraction scales with bankroll, and fractional Kelly sizes by edge
and never exceeds its cap."""

import pytest

from tennisdb.backtest.staking import (
    FixedFractionStake,
    FlatStake,
    FractionalKellyStake,
    WagerContext,
    build_staking,
    parse_stake_plan,
)

pytestmark = pytest.mark.m7


def test_flat_stake_ignores_probability_and_price():
    stake = FlatStake(amount=25.0)

    low_probability = stake.stake(WagerContext(probability=0.01, price=1.5, bankroll=1000.0))
    high_probability = stake.stake(WagerContext(probability=0.99, price=50.0, bankroll=1000.0))

    assert low_probability == high_probability == 25.0


def test_flat_stake_is_capped_at_the_remaining_bankroll():
    stake = FlatStake(amount=25.0)

    result = stake.stake(WagerContext(probability=0.5, price=2.0, bankroll=10.0))

    assert result == 10.0


def test_fixed_fraction_stake_scales_with_bankroll():
    stake = FixedFractionStake(fraction=0.1)

    result = stake.stake(WagerContext(probability=0.5, price=2.0, bankroll=200.0))

    assert result == pytest.approx(20.0)


def test_kelly_stake_sizes_with_edge():
    stake = FractionalKellyStake(multiplier=1.0, cap=1.0)
    # price 2.0, true probability 0.6 -> full Kelly = (0.6*1 - 0.4)/1 = 0.2
    result = stake.stake(WagerContext(probability=0.6, price=2.0, bankroll=1000.0))

    assert result == pytest.approx(200.0)


def test_kelly_stake_is_zero_at_zero_or_negative_edge():
    stake = FractionalKellyStake(multiplier=1.0, cap=1.0)
    # price 2.0 implies a break-even probability of 0.5; betting at 0.4 is -EV.
    result = stake.stake(WagerContext(probability=0.4, price=2.0, bankroll=1000.0))

    assert result == 0.0


def test_kelly_stake_never_exceeds_its_cap():
    stake = FractionalKellyStake(multiplier=1.0, cap=0.05)
    # Full Kelly here is 0.98 (near-certain win at long odds) -- the cap must bite.
    result = stake.stake(WagerContext(probability=0.99, price=100.0, bankroll=1000.0))

    assert result == pytest.approx(50.0)


def test_build_staking_resolves_defaults_for_missing_parameters():
    staking = build_staking("kelly", {})

    assert isinstance(staking, FractionalKellyStake)
    assert staking.multiplier == 0.25
    assert staking.cap == 0.05


def test_parse_stake_plan_handles_bare_name():
    assert parse_stake_plan("flat") == ("flat", {})


def test_parse_stake_plan_handles_name_and_value():
    assert parse_stake_plan("kelly:0.25") == ("kelly", {"multiplier": 0.25})


def test_parse_stake_plan_rejects_an_unknown_rule():
    with pytest.raises(ValueError, match="flat"):
        parse_stake_plan("double_or_nothing:1.0")


def test_parse_stake_plan_rejects_a_non_numeric_value():
    with pytest.raises(ValueError, match="number"):
        parse_stake_plan("flat:lots")
