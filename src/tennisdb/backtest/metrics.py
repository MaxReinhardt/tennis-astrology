"""Pure metric functions over a sequence of SettledBet. Every metric is reproducible
given the same bets and random_seed — the whole point of a backtest is a number you
can trust twice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import log

import numpy as np

from tennisdb.backtest.domain import SettledBet

_YEAR_DAYS = 365.25


@dataclass(frozen=True)
class BacktestMetrics:
    bet_count: int
    roi: float
    annualized_return: float
    max_drawdown: float
    hit_rate: float
    average_price_taken: float
    clv: float
    fair_value_edge: float
    brier_score: float
    log_loss: float
    roi_ci_low: float
    roi_ci_high: float
    ruin_probability: float


def roi(bets: Sequence[SettledBet]) -> float:
    """Profit over turnover — the headline return-on-investment figure."""
    if not bets:
        return 0.0
    turnover = sum(bet.stake for bet in bets)
    profit = sum(bet.profit for bet in bets)
    return profit / turnover if turnover else 0.0


def annualized_return(starting_bankroll: float, bets: Sequence[SettledBet]) -> float:
    if not bets or starting_bankroll <= 0:
        return 0.0
    span_days = (bets[-1].match_date - bets[0].match_date).days
    if span_days <= 0:
        return 0.0
    growth = bets[-1].bankroll_after / starting_bankroll
    if growth <= 0:
        return -1.0
    return growth ** (_YEAR_DAYS / span_days) - 1.0


def max_drawdown(starting_bankroll: float, bets: Sequence[SettledBet]) -> float:
    """Largest peak-to-trough decline in the realized equity curve, as a fraction of
    the peak (0.0 when the curve never falls below its running high)."""
    peak = starting_bankroll
    worst = 0.0
    for bet in bets:
        peak = max(peak, bet.bankroll_after)
        if peak > 0:
            worst = max(worst, (peak - bet.bankroll_after) / peak)
    return worst


def hit_rate(bets: Sequence[SettledBet]) -> float:
    if not bets:
        return 0.0
    return sum(1 for bet in bets if bet.won) / len(bets)


def average_price_taken(bets: Sequence[SettledBet]) -> float:
    if not bets:
        return 0.0
    return sum(bet.price for bet in bets) / len(bets)


def clv(bets: Sequence[SettledBet]) -> float:
    """Mean (fill price / consensus price) − 1. Zero when the fill book is the
    consensus book and there is no slippage; positive when the fill book offers a
    better price than the consensus (e.g. filling at Max against an Avg consensus)."""
    if not bets:
        return 0.0
    return sum(bet.fill_price / bet.consensus_price - 1.0 for bet in bets) / len(bets)


def fair_value_edge(bets: Sequence[SettledBet]) -> float:
    """Mean (fill price × consensus no-vig probability) − 1: the expected value per
    unit staked, judged against the vig-free consensus. For a side-selector with no
    real edge, filling at the consensus book with no slippage, this is
    −overround / (1 + overround) ≈ −overround for a typical single-digit-percent
    overround — the cost of playing at all."""
    if not bets:
        return 0.0
    return sum(bet.fill_price * bet.consensus_prob - 1.0 for bet in bets) / len(bets)


def brier_score(bets: Sequence[SettledBet]) -> float:
    if not bets:
        return 0.0
    return sum((bet.probability - float(bet.won)) ** 2 for bet in bets) / len(bets)


def log_loss(bets: Sequence[SettledBet], epsilon: float = 1e-9) -> float:
    if not bets:
        return 0.0
    total = 0.0
    for bet in bets:
        probability = min(max(bet.probability, epsilon), 1.0 - epsilon)
        total += -log(probability) if bet.won else -log(1.0 - probability)
    return total / len(bets)


def bootstrap_ratio_interval(
    numerators: Sequence[float],
    denominators: Sequence[float],
    draws: int,
    seed: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap CI on sum(numerators)/sum(denominators): resample pairs with
    replacement `draws` times and take the (1-confidence)/2 and 1-(1-confidence)/2
    percentiles. ROI is profit/stake; a per-bet mean such as CLV is value/1. Each draw is
    one vectorised numpy pass, so this stays fast at tens of thousands of bets."""
    if len(numerators) < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    top = np.asarray(numerators, dtype=float)
    bottom = np.asarray(denominators, dtype=float)
    count = len(top)
    resampled = np.empty(draws)
    for i in range(draws):
        sample = rng.integers(0, count, size=count)
        total = bottom[sample].sum()
        resampled[i] = top[sample].sum() / total if total else 0.0
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(resampled, [tail, 1.0 - tail])
    return float(low), float(high)


def bootstrap_roi_interval(
    bets: Sequence[SettledBet], draws: int, seed: int, confidence: float = 0.95
) -> tuple[float, float]:
    return bootstrap_ratio_interval(
        [bet.profit for bet in bets], [bet.stake for bet in bets], draws, seed, confidence
    )


def bootstrap_clv_interval(
    bets: Sequence[SettledBet], draws: int, seed: int, confidence: float = 0.95
) -> tuple[float, float]:
    return bootstrap_ratio_interval(
        [bet.fill_price / bet.consensus_price - 1.0 for bet in bets],
        [1.0] * len(bets),
        draws,
        seed,
        confidence,
    )


def ruin_probability(
    bets: Sequence[SettledBet],
    starting_bankroll: float,
    draws: int,
    seed: int,
    ruin_fraction: float = 0.1,
) -> float:
    """Monte-Carlo estimate of the probability that compounding the observed per-bet
    returns, in a resampled order, drives the bankroll below `ruin_fraction` of its
    start. Each draw replays one resampled sequence as a vectorised cumulative
    product — no inner Python loop over bets."""
    if not bets or starting_bankroll <= 0:
        return 0.0
    rng = np.random.default_rng(seed)
    per_bet_return = np.array(
        [bet.profit / bet.stake if bet.stake else 0.0 for bet in bets]
    )
    stake_fraction = np.array([bet.stake / starting_bankroll for bet in bets])
    count = len(bets)
    ruined = 0
    for _ in range(draws):
        order = rng.integers(0, count, size=count)
        equity_curve = np.cumprod(1.0 + stake_fraction[order] * per_bet_return[order])
        if np.any(equity_curve <= ruin_fraction):
            ruined += 1
    return ruined / draws
