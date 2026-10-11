"""M7: the walk-forward engine's accounting, proven against a closed-form expectation
built from known probabilities and prices — the synthetic-truth test PLAN.md's M7
Verify block calls for. No database is involved: a hand-built OpportunitySource
replaces the warehouse entirely.
"""

import dataclasses
from datetime import date, timedelta

import pytest

from tennisdb.backtest.domain import MatchEvent, MatchOpportunity
from tennisdb.backtest.engine import run_backtest
from tennisdb.backtest.request import BacktestRequest

pytestmark = pytest.mark.m7


def _opportunity(
    match_id: str, match_date: date, p1_price: float, p2_price: float
) -> MatchOpportunity:
    raw_p1, raw_p2 = 1.0 / p1_price, 1.0 / p2_price
    return MatchOpportunity(
        match_id=match_id,
        match_date=match_date,
        season=match_date.year,
        tour="atp",
        surface="Hard",
        level="A",
        round="R32",
        p1_price=p1_price,
        p2_price=p2_price,
        p1_consensus_price=p1_price,
        p2_consensus_price=p2_price,
        p1_consensus_prob=raw_p1 / (raw_p1 + raw_p2),
        p1_elo_prob=0.5,
        p1_surface_elo_prob=0.5,
    )


class _FixedSource:
    """An OpportunitySource with a known, exact win sequence — no database, no
    randomness, so the resulting ROI can be checked against a closed-form value."""

    def __init__(self, win_flags: list[bool], price: float = 2.0, other_price: float = 3.0):
        self._win_flags = win_flags
        self._price = price
        self._other_price = other_price

    def events(self, request):
        start = date(2020, 1, 1)
        for index, won in enumerate(self._win_flags):
            opportunity = _opportunity(
                f"m{index}", start + timedelta(days=index), self._price, self._other_price
            )
            yield MatchEvent(opportunity=opportunity, p1_won=won)


def test_engine_roi_matches_the_closed_form_expectation():
    probability, price = 0.6, 2.0
    win_count = 600
    win_flags = [True] * win_count + [False] * (1000 - win_count)
    request = BacktestRequest.from_dict(
        {
            "strategy": "back_favorites",
            "stake_parameters": {"amount": 10.0},
            "slippage": 0.0,
            "starting_bankroll": 1_000_000.0,
        }
    )

    result = run_backtest(request, _FixedSource(win_flags, price=price))

    expected_roi = probability * (price - 1.0) - (1.0 - probability)
    assert result.metrics.roi == pytest.approx(expected_roi, abs=0.005)
    assert result.metrics.bet_count == 1000


def test_bankroll_never_goes_negative_even_when_a_strategy_overbets():
    request = BacktestRequest.from_dict(
        {
            "strategy": "back_favorites",
            "starting_bankroll": 100.0,
            "stake_parameters": {"amount": 1000.0},
        }
    )
    all_losses = [False] * 50

    result = run_backtest(request, _FixedSource(all_losses))

    assert all(bet.bankroll_after >= 0 for bet in result.bets)
    assert result.ruined


def test_match_opportunity_carries_no_outcome_field():
    field_names = {field.name for field in dataclasses.fields(MatchOpportunity)}

    assert "p1_won" not in field_names
    assert "won" not in field_names


def test_a_strategy_returning_none_books_no_bet():
    # theta 0.5 is unreachable given the fixed 0.5 Elo probabilities in _opportunity,
    # so elo_value never finds an edge and places zero bets despite seeing every match.
    request = BacktestRequest.from_dict(
        {"strategy": "elo_value", "strategy_parameters": {"theta": 0.5}}
    )
    win_flags = [True, False, True]

    result = run_backtest(request, _FixedSource(win_flags))

    assert result.metrics.bet_count == 0
    assert result.matches_seen == 3
