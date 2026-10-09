"""M8: standard backtest charts — shared by the study markdown (PNG) and the web UI."""

from datetime import date

import pytest

from tennisdb.backtest.charts import CHART_KEYS, build_charts
from tennisdb.backtest.domain import SettledBet

pytestmark = pytest.mark.m8


def _bet(match_date, price=2.0, won=True, surface="Hard", stake=10.0, bankroll_after=1000.0):
    fill = price * 0.99
    return SettledBet(
        match_id=f"m-{match_date}-{price}-{won}-{surface}",
        match_date=match_date,
        side="p1",
        probability=0.5,
        price=price,
        fill_price=fill,
        consensus_price=price,
        consensus_prob=1 / price,
        stake=stake,
        profit=stake * (fill - 1) if won else -stake,
        won=won,
        bankroll_after=bankroll_after,
        surface=surface,
    )


def _by_key(charts):
    return {chart.key: chart for chart in charts}


def test_build_charts_no_bets_returns_every_chart_empty():
    charts = _by_key(build_charts((), starting_bankroll=1000.0))

    assert set(charts) == set(CHART_KEYS)
    assert all(chart.points == () for chart in charts.values())


def test_equity_curve_several_bets_one_day_keeps_only_the_day_end_bankroll():
    day = date(2019, 1, 1)
    bets = (_bet(day, bankroll_after=1010.0), _bet(day, bankroll_after=1020.0))

    points = _by_key(build_charts(bets, 1000.0))["equity_curve"].points

    assert [(point.x, point.y) for point in points] == [("2019-01-01", 1020.0)]


def test_drawdown_after_a_peak_is_negative_fraction_below_the_peak():
    bets = (
        _bet(date(2019, 1, 1), bankroll_after=1200.0),
        _bet(date(2019, 1, 2), bankroll_after=900.0),
    )

    points = _by_key(build_charts(bets, 1000.0))["drawdown"].points

    assert [point.y for point in points] == [0.0, pytest.approx(-0.25)]


def test_roi_by_surface_splits_bets_by_surface_with_ordered_interval():
    bets = tuple(_bet(date(2019, 1, d), surface="Clay", won=d % 2 == 0) for d in range(1, 21))
    bets += tuple(_bet(date(2019, 2, d), surface="Hard") for d in range(1, 11))

    points = _by_key(build_charts(bets, 1000.0))["roi_by_surface"].points

    assert {point.x: point.count for point in points} == {"Clay": 20, "Hard": 10}
    assert all(point.low <= point.y <= point.high for point in points)


def test_roi_by_price_bucket_places_each_bet_in_its_price_band():
    bets = (_bet(date(2019, 1, 1), price=1.3), _bet(date(2019, 1, 2), price=4.0))

    points = _by_key(build_charts(bets, 1000.0))["roi_by_price_bucket"].points

    assert [(point.x, point.count) for point in points] == [("1.0–1.5", 1), ("3.0–5.0", 1)]


def test_calibration_points_report_realised_rate_against_mean_probability():
    bets = tuple(_bet(date(2019, 1, 1), won=index < 3) for index in range(4))

    points = _by_key(build_charts(bets, 1000.0))["calibration"].points

    assert [(point.x, point.y, point.count) for point in points] == [(0.5, 0.75, 4)]


def test_clv_distribution_bin_counts_sum_to_the_bet_count():
    bets = tuple(_bet(date(2019, 1, 1), price=2.0 + index / 10) for index in range(7))

    points = _by_key(build_charts(bets, 1000.0))["clv_distribution"].points

    assert sum(point.count for point in points) == 7
