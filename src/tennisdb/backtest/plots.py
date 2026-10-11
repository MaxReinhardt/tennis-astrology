"""Render ChartSeries to PNG with matplotlib (the study markdown's figures). Draws the
same data the web UI draws; kept out of the API's import path. One blue series on a
quiet grid, with a gray zero/ideal reference and the bootstrap interval as whiskers."""

from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from tennisdb.backtest.charts import ChartSeries  # noqa: E402

_SERIES = "#2a78d6"
_REFERENCE = "#8a8984"
_GRID = "#e6e5e1"
_INK = "#0b0b0b"
_FIGURE_SIZE = (7.0, 3.6)
_PERCENT_AXES = {"ROI", "Drawdown", "CLV", "Realised win rate", "Share of bets"}


def render_charts(charts: tuple[ChartSeries, ...], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return [_render(chart, directory) for chart in charts if chart.points]


def _render(chart: ChartSeries, directory: Path) -> Path:
    figure, axes = plt.subplots(figsize=_FIGURE_SIZE)
    _DRAWERS[chart.kind](axes, chart)
    axes.set_title(chart.title, loc="left", color=_INK, fontsize=11)
    axes.set_xlabel(chart.x_label, color=_INK)
    axes.set_ylabel(chart.y_label, color=_INK)
    axes.grid(axis="y", color=_GRID, linewidth=0.8)
    axes.set_axisbelow(True)
    for edge in ("top", "right"):
        axes.spines[edge].set_visible(False)
    if chart.y_label in _PERCENT_AXES:
        axes.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    path = directory / f"{chart.key}.png"
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def _draw_line(axes, chart: ChartSeries) -> None:
    axes.plot([p.x for p in chart.points], [p.y for p in chart.points], color=_SERIES, linewidth=2)
    axes.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6))
    if chart.key == "drawdown":
        axes.axhline(0, color=_REFERENCE, linewidth=1)


def _draw_bars(axes, chart: ChartSeries) -> None:
    positions = range(len(chart.points))
    values = [p.y for p in chart.points]
    axes.bar(positions, values, color=_SERIES, width=0.6)
    errors = [
        [p.y - p.low for p in chart.points],
        [p.high - p.y for p in chart.points],
    ]
    axes.errorbar(positions, values, yerr=errors, fmt="none", ecolor=_INK, capsize=3, linewidth=1)
    axes.axhline(0, color=_REFERENCE, linewidth=1)
    axes.set_xticks(positions, [f"{p.x}\nn={p.count:,}" for p in chart.points])


def _draw_histogram(axes, chart: ChartSeries) -> None:
    width = (chart.points[-1].x - chart.points[0].x) / max(len(chart.points) - 1, 1) * 0.9
    axes.bar([p.x for p in chart.points], [p.y for p in chart.points], width=width, color=_SERIES)
    axes.axvline(0, color=_REFERENCE, linewidth=1)
    axes.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))


def _draw_calibration(axes, chart: ChartSeries) -> None:
    axes.plot([0, 1], [0, 1], color=_REFERENCE, linewidth=1, linestyle="--")
    axes.plot([p.x for p in chart.points], [p.y for p in chart.points],
              color=_SERIES, linewidth=2, marker="o", markersize=6)  # fmt: skip
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)
    axes.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))


_DRAWERS = {
    "line": _draw_line,
    "bar": _draw_bars,
    "histogram": _draw_histogram,
    "calibration": _draw_calibration,
}
