"""Helpers shared by the studies: how a study states a backtest request, and how it
turns a result into a table row with its bootstrap intervals."""

from collections.abc import Mapping

from tennisdb.backtest import metrics
from tennisdb.backtest.charts import ChartPoint
from tennisdb.backtest.report import BacktestResult
from tennisdb.backtest.request import BacktestRequest

FLAT_STAKE = 10.0
# Large enough that a flat stake can never exhaust it: a study measures the strategy,
# not how long a small bankroll survives it.
STUDY_BANKROLL = 10_000_000.0
IN_SAMPLE_LAST_SEASON = 2018
OUT_OF_SAMPLE_FIRST_SEASON = 2019
MIN_BETS_FOR_A_CLAIM = 100


def flat_request(
    strategy: str,
    strategy_parameters: Mapping[str, float] | None = None,
    **filters: object,
) -> BacktestRequest:
    return BacktestRequest.from_dict(
        {
            "strategy": strategy,
            "strategy_parameters": dict(strategy_parameters or {}),
            "filters": filters,
            "stake_rule": "flat",
            "stake_parameters": {"amount": FLAT_STAKE},
            "starting_bankroll": STUDY_BANKROLL,
        }
    )


def roi_interval(result: BacktestResult) -> tuple[float, float]:
    return result.metrics.roi_ci_low, result.metrics.roi_ci_high


def clv_interval(result: BacktestResult) -> tuple[float, float]:
    request = result.request
    return metrics.bootstrap_clv_interval(result.bets, request.bootstrap_draws, request.random_seed)


def roi_point(label: str, result: BacktestResult) -> ChartPoint:
    low, high = roi_interval(result)
    return ChartPoint(label, result.metrics.roi, low, high, result.metrics.bet_count)


def percent(value: float) -> str:
    return f"{value:+.2%}"
