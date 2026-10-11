"""Standard backtest charts as plain data. Framework-free and plotting-library-free:
the matplotlib renderer (plots.py) draws these into the study PNGs and the web UI draws
the same series with Recharts, so a chart means the same thing everywhere. Drawdown is
measured on day-end bankrolls, so it understates intraday troughs."""

from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from tennisdb.backtest import metrics
from tennisdb.backtest.domain import SettledBet

INTERVAL_DRAWS = 1000
INTERVAL_SEED = 7
CLV_BIN_COUNT = 20
CALIBRATION_BIN_COUNT = 10
_SURFACE_ORDER = ("Hard", "Clay", "Grass", "Carpet")
_PRICE_EDGES = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0)

CHART_KEYS = (
    "equity_curve",
    "drawdown",
    "roi_by_price_bucket",
    "roi_by_surface",
    "roi_by_season",
    "clv_distribution",
    "calibration",
)


@dataclass(frozen=True)
class ChartPoint:
    x: float | str
    y: float
    low: float | None = None
    high: float | None = None
    count: int | None = None


@dataclass(frozen=True)
class ChartSeries:
    key: str
    title: str
    kind: str  # 'line' | 'bar' | 'histogram' | 'calibration'
    x_label: str
    y_label: str
    points: tuple[ChartPoint, ...]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "kind": self.kind,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "points": [
                {name: value for name, value in vars(point).items() if value is not None}
                for point in self.points
            ],
        }


def build_charts(bets: Sequence[SettledBet], starting_bankroll: float) -> tuple[ChartSeries, ...]:
    day_end = _day_end_bankrolls(bets)
    return (
        ChartSeries(
            "equity_curve", "Bankroll over time", "line", "Date", "Bankroll",
            tuple(ChartPoint(day.isoformat(), bankroll) for day, bankroll in day_end),
        ),
        ChartSeries(
            "drawdown", "Drawdown from peak", "line", "Date", "Drawdown",
            _drawdown_points(day_end, starting_bankroll),
        ),
        _roi_bars(
            "roi_by_price_bucket", "ROI by price taken", "Decimal price", bets, _price_label,
            _price_order,
        ),
        _roi_bars(
            "roi_by_surface", "ROI by surface", "Surface", bets,
            lambda bet: bet.surface or "Unknown", _surface_order,
        ),
        _roi_bars(
            "roi_by_season", "ROI by season", "Season", bets,
            lambda bet: str(bet.match_date.year), str,
        ),
        _clv_histogram(bets),
        _calibration(bets),
    )  # fmt: skip


def _day_end_bankrolls(bets: Sequence[SettledBet]) -> list[tuple[date, float]]:
    last_of_day: dict[date, float] = {}
    for bet in bets:
        last_of_day[bet.match_date] = bet.bankroll_after
    return sorted(last_of_day.items())


def _drawdown_points(
    day_end: list[tuple[date, float]], starting_bankroll: float
) -> tuple[ChartPoint, ...]:
    peak = starting_bankroll
    points = []
    for day, bankroll in day_end:
        peak = max(peak, bankroll)
        points.append(ChartPoint(day.isoformat(), bankroll / peak - 1.0))
    return tuple(points)


def _price_label(bet: SettledBet) -> str:
    for low, high in zip(_PRICE_EDGES, _PRICE_EDGES[1:], strict=False):
        if bet.price < high:
            return f"{low:.1f}–{high:.1f}"
    return f"{_PRICE_EDGES[-1]:.1f}+"


def _price_order(label: str) -> float:
    return float(label.rstrip("+").split("–")[0])


def _surface_order(label: str) -> int:
    return _SURFACE_ORDER.index(label) if label in _SURFACE_ORDER else len(_SURFACE_ORDER)


def _roi_bars(
    key: str,
    title: str,
    x_label: str,
    bets: Sequence[SettledBet],
    group_of: Callable[[SettledBet], Hashable],
    order_of: Callable,
) -> ChartSeries:
    groups: dict = defaultdict(list)
    for bet in bets:
        groups[group_of(bet)].append(bet)
    points = []
    for label in sorted(groups, key=order_of):
        members = groups[label]
        low, high = metrics.bootstrap_roi_interval(members, INTERVAL_DRAWS, INTERVAL_SEED)
        points.append(ChartPoint(label, metrics.roi(members), low, high, len(members)))
    return ChartSeries(key, title, "bar", x_label, "ROI", tuple(points))


def _clv_histogram(bets: Sequence[SettledBet]) -> ChartSeries:
    series = ("clv_distribution", "Closing line value per bet", "histogram", "CLV", "Share of bets")
    if not bets:
        return ChartSeries(*series, ())
    values = np.array([bet.fill_price / bet.consensus_price - 1.0 for bet in bets])
    counts, edges = np.histogram(values, bins=CLV_BIN_COUNT)
    centres = (edges[:-1] + edges[1:]) / 2.0
    points = tuple(
        ChartPoint(float(centre), float(count) / len(bets), count=int(count))
        for centre, count in zip(centres, counts, strict=True)
        if count
    )
    return ChartSeries(*series, points)


def _calibration(bets: Sequence[SettledBet]) -> ChartSeries:
    bins: dict[int, list[SettledBet]] = defaultdict(list)
    for bet in bets:
        bins[min(int(bet.probability * CALIBRATION_BIN_COUNT), CALIBRATION_BIN_COUNT - 1)].append(
            bet
        )
    points = tuple(
        ChartPoint(
            float(np.mean([bet.probability for bet in members])),
            sum(bet.won for bet in members) / len(members),
            count=len(members),
        )
        for _, members in sorted(bins.items())
    )
    return ChartSeries(
        "calibration", "Predicted vs realised win rate", "calibration",
        "Predicted probability", "Realised win rate", points,
    )  # fmt: skip
