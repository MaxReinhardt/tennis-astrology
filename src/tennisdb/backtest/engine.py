"""Event-driven walk-forward backtest loop: iterate pre-match opportunities in strict
chronological order (enforced by the OpportunitySource, see opportunities.py), let the
strategy bet on what it can see, size and fill the bet, and settle it against the
known outcome. One pass produces one BacktestResult.
"""

from collections.abc import Iterator
from typing import Protocol

from tennisdb.backtest import report
from tennisdb.backtest.domain import Bet, MatchEvent, SettledBet
from tennisdb.backtest.report import BacktestResult
from tennisdb.backtest.request import BacktestRequest
from tennisdb.backtest.staking import StakingStrategy, WagerContext, build_staking
from tennisdb.backtest.strategies import build_strategy


class OpportunitySource(Protocol):
    def events(self, request: BacktestRequest) -> Iterator[MatchEvent]: ...


def run_backtest(request: BacktestRequest, source: OpportunitySource) -> BacktestResult:
    strategy = build_strategy(request.strategy, request.strategy_parameters)
    staking = build_staking(request.stake_rule, request.stake_parameters)

    bankroll = request.starting_bankroll
    settled_bets: list[SettledBet] = []
    matches_seen = 0

    for event in source.events(request):
        matches_seen += 1
        bet = strategy.evaluate(event.opportunity)
        if bet is None:
            continue
        settled = _settle(event, bet, staking, bankroll, request.slippage)
        if settled is None:
            continue
        settled_bets.append(settled)
        bankroll = settled.bankroll_after

    return report.build_result(request, matches_seen, settled_bets)


def _settle(
    event: MatchEvent, bet: Bet, staking: StakingStrategy, bankroll: float, slippage: float
) -> SettledBet | None:
    opportunity = event.opportunity
    price = opportunity.price(bet.side)
    wager = WagerContext(probability=bet.probability, price=price, bankroll=bankroll)
    stake = min(max(staking.stake(wager), 0.0), bankroll)
    if stake <= 0:
        return None
    fill_price = price * (1.0 - slippage)
    won = event.won(bet.side)
    profit = stake * (fill_price - 1.0) if won else -stake
    return SettledBet(
        match_id=opportunity.match_id,
        match_date=opportunity.match_date,
        side=bet.side,
        probability=bet.probability,
        price=price,
        fill_price=fill_price,
        consensus_price=opportunity.consensus_price(bet.side),
        consensus_prob=opportunity.consensus_prob(bet.side),
        stake=stake,
        profit=profit,
        won=won,
        bankroll_after=bankroll + profit,
        surface=opportunity.surface,
    )
