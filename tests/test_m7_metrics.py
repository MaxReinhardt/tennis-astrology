"""M7: each metric checked against a hand-computed fixture, not against the engine —
so a regression in metrics.py shows up even if the engine's wiring stays correct."""

from datetime import date, timedelta
from math import log

import pytest

from tennisdb.backtest import metrics
from tennisdb.backtest.domain import SettledBet

pytestmark = pytest.mark.m7

_START = date(2020, 1, 1)


def _bet(index: int, bankroll_after: float, **overrides) -> SettledBet:
    fields = {
        "match_id": f"m{index}",
        "match_date": _START + timedelta(days=index),
        "side": "p1",
        "probability": 0.5,
        "price": 2.0,
        "fill_price": 2.0,
        "consensus_price": 2.0,
        "consensus_prob": 0.5,
        "stake": 10.0,
        "profit": 0.0,
        "won": True,
        "bankroll_after": bankroll_after,
    }
    fields.update(overrides)
    return SettledBet(**fields)


def test_roi_is_profit_over_turnover():
    bets = [_bet(0, 110.0, stake=10.0, profit=10.0), _bet(1, 100.0, stake=10.0, profit=-10.0)]

    assert metrics.roi(bets) == pytest.approx(0.0)


def test_roi_is_zero_for_no_bets():
    assert metrics.roi([]) == 0.0


def test_max_drawdown_tracks_the_worst_peak_to_trough_decline():
    bets = [_bet(0, 120.0), _bet(1, 90.0), _bet(2, 150.0), _bet(3, 60.0)]

    drawdown = metrics.max_drawdown(starting_bankroll=100.0, bets=bets)

    assert drawdown == pytest.approx(0.6)


def test_max_drawdown_is_zero_when_bankroll_only_grows():
    bets = [_bet(0, 110.0), _bet(1, 130.0), _bet(2, 150.0)]

    assert metrics.max_drawdown(starting_bankroll=100.0, bets=bets) == 0.0


def test_hit_rate_is_the_fraction_of_winning_bets():
    bets = [_bet(i, 100.0, won=won) for i, won in enumerate([True, True, True, False, False])]

    assert metrics.hit_rate(bets) == pytest.approx(0.6)


def test_brier_score_against_a_textbook_value():
    bets = [
        _bet(0, 100.0, probability=0.7, won=True),
        _bet(1, 100.0, probability=0.3, won=False),
    ]

    assert metrics.brier_score(bets) == pytest.approx(0.09)


def test_log_loss_against_a_textbook_value():
    bets = [
        _bet(0, 100.0, probability=0.7, won=True),
        _bet(1, 100.0, probability=0.3, won=False),
    ]

    assert metrics.log_loss(bets) == pytest.approx(-log(0.7))


def test_clv_is_zero_when_fill_book_equals_consensus_book_with_no_slippage():
    bets = [_bet(0, 100.0, fill_price=2.0, consensus_price=2.0)]

    assert metrics.clv(bets) == pytest.approx(0.0)


def test_clv_is_positive_when_the_fill_price_beats_the_consensus():
    bets = [_bet(0, 100.0, fill_price=2.2, consensus_price=2.0)]

    assert metrics.clv(bets) == pytest.approx(0.1)


def test_fair_value_edge_matches_the_overround_cost_for_a_fair_coin():
    # fill == consensus book, consensus no-vig prob 0.5 on both sides, overround 5%:
    # raw prob per side = 0.525, price = 1/0.525 ~= 1.9048.
    price = 1.0 / 0.525
    bets = [_bet(0, 100.0, fill_price=price, consensus_price=price, consensus_prob=0.5)]

    edge = metrics.fair_value_edge(bets)

    assert edge == pytest.approx(-0.05 / 1.05, abs=1e-6)


def _bets_with_known_edge(count: int, win_fraction: float) -> list[SettledBet]:
    win_count = int(count * win_fraction)
    return [
        _bet(i, 100.0, stake=10.0, profit=10.0 if i < win_count else -10.0, won=i < win_count)
        for i in range(count)
    ]


def test_bootstrap_roi_interval_brackets_the_point_estimate():
    bets = _bets_with_known_edge(200, 0.6)
    point_roi = metrics.roi(bets)

    low, high = metrics.bootstrap_roi_interval(bets, draws=2000, seed=7)

    assert low <= point_roi <= high


def test_bootstrap_roi_interval_is_reproducible_under_a_fixed_seed():
    bets = _bets_with_known_edge(200, 0.6)

    first = metrics.bootstrap_roi_interval(bets, draws=500, seed=42)
    second = metrics.bootstrap_roi_interval(bets, draws=500, seed=42)

    assert first == second


def test_ruin_probability_is_zero_when_bets_are_too_small_to_ever_ruin():
    bets = _bets_with_known_edge(100, 0.6)

    probability = metrics.ruin_probability(
        bets, starting_bankroll=1_000_000.0, draws=200, seed=1
    )

    assert probability == 0.0


def test_ruin_probability_is_high_when_a_single_loss_wipes_the_bankroll():
    bets = [_bet(i, 0.0, stake=100.0, profit=-100.0, won=False) for i in range(10)]

    probability = metrics.ruin_probability(bets, starting_bankroll=100.0, draws=200, seed=1)

    assert probability == pytest.approx(1.0)
