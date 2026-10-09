"""Formats a finished backtest into a CLI table and a JSON/CSV artifact bundle.

`BacktestResult.to_dict()` is the contract a future LLM wrapper quotes from: every
metric carries a pre-formatted, labelled, unit-tagged string, so the presenting model
never recomputes or reformats a number — the same discipline `quality.checks` already
applies to data-quality reports.
"""

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tennisdb import config
from tennisdb.backtest import metrics as metric_functions
from tennisdb.backtest.charts import ChartSeries, build_charts
from tennisdb.backtest.domain import EquityPoint, SettledBet
from tennisdb.backtest.metrics import BacktestMetrics
from tennisdb.backtest.request import BacktestRequest


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str  # 'percent' | 'ratio' | 'count' | 'odds'
    precision: int


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("bet_count", "Bets placed", "count", 0),
    MetricSpec("roi", "Return on investment", "percent", 2),
    MetricSpec("annualized_return", "Annualized return", "percent", 2),
    MetricSpec("max_drawdown", "Maximum drawdown", "percent", 2),
    MetricSpec("hit_rate", "Hit rate", "percent", 1),
    MetricSpec("average_price_taken", "Average price taken", "odds", 2),
    MetricSpec("clv", "Closing line value", "percent", 2),
    MetricSpec("fair_value_edge", "Fair-value edge", "percent", 2),
    MetricSpec("brier_score", "Brier score", "ratio", 4),
    MetricSpec("log_loss", "Log loss", "ratio", 4),
    MetricSpec("roi_ci_low", "ROI 95% CI low", "percent", 2),
    MetricSpec("roi_ci_high", "ROI 95% CI high", "percent", 2),
    MetricSpec("ruin_probability", "Probability of ruin", "percent", 2),
)


def _format(value: float, unit: str, precision: int) -> str:
    if unit == "percent":
        return f"{value * 100:.{precision}f}%"
    if unit == "count":
        return f"{value:,.0f}"
    return f"{value:.{precision}f}"


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    request: BacktestRequest
    matches_seen: int
    ruined: bool
    equity_curve: tuple[EquityPoint, ...]
    bets: tuple[SettledBet, ...]
    metrics: BacktestMetrics

    def charts(self) -> tuple[ChartSeries, ...]:
        return build_charts(self.bets, self.request.starting_bankroll)

    def summary_lines(self) -> list[str]:
        headline = (
            f"backtest {self.run_id}: {self.request.strategy} on {self.matches_seen} "
            f"matches, {self.metrics.bet_count} bets" + (" (RUINED)" if self.ruined else "")
        )
        return [headline] + [
            f"  {spec.label}: {_format(getattr(self.metrics, spec.key), spec.unit, spec.precision)}"
            for spec in METRIC_SPECS
        ]

    def stats(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy": self.request.strategy,
            "bet_count": self.metrics.bet_count,
            "roi": self.metrics.roi,
            "ruined": self.ruined,
        }

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "request": self.request.to_dict(),
            "universe": {
                "matches_seen": self.matches_seen,
                "bets_placed": self.metrics.bet_count,
            },
            "ruined": self.ruined,
            "metrics": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "unit": spec.unit,
                    "value": getattr(self.metrics, spec.key),
                    "formatted": _format(
                        getattr(self.metrics, spec.key), spec.unit, spec.precision
                    ),
                }
                for spec in METRIC_SPECS
            ],
            "equity_curve": [
                {"match_date": point.match_date.isoformat(), "bankroll": point.bankroll}
                for point in self.equity_curve
            ],
            "charts": [chart.to_dict() for chart in self.charts()],
        }


def _generate_run_id(request: BacktestRequest) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{request.strategy}"


def build_result(
    request: BacktestRequest, matches_seen: int, bets: list[SettledBet]
) -> BacktestResult:
    roi_low, roi_high = metric_functions.bootstrap_roi_interval(
        bets, request.bootstrap_draws, request.random_seed
    )
    ruin = metric_functions.ruin_probability(
        bets, request.starting_bankroll, request.bootstrap_draws, request.random_seed + 1
    )
    computed_metrics = BacktestMetrics(
        bet_count=len(bets),
        roi=metric_functions.roi(bets),
        annualized_return=metric_functions.annualized_return(request.starting_bankroll, bets),
        max_drawdown=metric_functions.max_drawdown(request.starting_bankroll, bets),
        hit_rate=metric_functions.hit_rate(bets),
        average_price_taken=metric_functions.average_price_taken(bets),
        clv=metric_functions.clv(bets),
        fair_value_edge=metric_functions.fair_value_edge(bets),
        brier_score=metric_functions.brier_score(bets),
        log_loss=metric_functions.log_loss(bets),
        roi_ci_low=roi_low,
        roi_ci_high=roi_high,
        ruin_probability=ruin,
    )
    equity_curve = tuple(EquityPoint(bet.match_date, bet.bankroll_after) for bet in bets)
    ruined = bool(bets) and bets[-1].bankroll_after <= 0
    return BacktestResult(
        run_id=_generate_run_id(request),
        request=request,
        matches_seen=matches_seen,
        ruined=ruined,
        equity_curve=equity_curve,
        bets=tuple(bets),
        metrics=computed_metrics,
    )


def _write_csv(path: Path, header: tuple[str, ...], rows: Iterable[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def write_artifacts(result: BacktestResult, directory: Path = config.BACKTESTS_DIR) -> Path:
    run_directory = directory / result.run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / "result.json").write_text(
        json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (run_directory / "charts.json").write_text(
        json.dumps([chart.to_dict() for chart in result.charts()]), encoding="utf-8"
    )
    _write_csv(
        run_directory / "equity_curve.csv",
        ("match_date", "bankroll"),
        ((point.match_date, point.bankroll) for point in result.equity_curve),
    )
    _write_csv(
        run_directory / "bets.csv",
        (
            "match_id", "match_date", "side", "probability", "price", "fill_price",
            "consensus_price", "consensus_prob", "stake", "profit", "won", "bankroll_after",
        ),  # fmt: skip
        (
            (
                bet.match_id, bet.match_date, bet.side, bet.probability, bet.price,
                bet.fill_price, bet.consensus_price, bet.consensus_prob, bet.stake,
                bet.profit, bet.won, bet.bankroll_after,
            )  # fmt: skip
            for bet in result.bets
        ),
    )
    return run_directory
