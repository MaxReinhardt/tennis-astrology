"""S4 (behavioural): home-nation players. Do players from the tournament's host country
beat or lag their market price — and can either side of that be traded? No parameter is
tuned, so the strategies run on the whole sample and again on the 2019+ holdout."""

from tennisdb.backtest.charts import ChartSeries
from tennisdb.research.context import StudyContext
from tennisdb.research.protocol import FindingTable, Hypothesis, PlainSummary, StudyResult, Verdict
from tennisdb.research.significance import two_sided_binomial_p_value
from tennisdb.research.studies.common import (
    MIN_BETS_FOR_A_CLAIM,
    OUT_OF_SAMPLE_FIRST_SEASON,
    clv_interval,
    flat_request,
    percent,
    roi_point,
)

SIGNIFICANCE_LEVEL = 0.05
STRATEGIES = ("back_home_nation", "fade_home_nation")
_CHART_SAMPLES = {
    "all seasons": "all",
    f"{OUT_OF_SAMPLE_FIRST_SEASON}+ holdout": f"{OUT_OF_SAMPLE_FIRST_SEASON}+",
}
_SAMPLES = (
    ("all seasons", {}),
    (f"{OUT_OF_SAMPLE_FIRST_SEASON}+ holdout", {"from_season": OUT_OF_SAMPLE_FIRST_SEASON}),
)


class HostNationStudy:
    study_id = "s4_host_nation"
    title = "S4 · Does backing or fading home-nation players make money?"
    plain = PlainSummary(
        title="Do players win more at home than the odds expect?",
        summary=(
            "We check whether players from the country hosting a tournament win more or less "
            "often than the bookmakers' odds imply, and whether betting on them (or against "
            "them) would have made money."
        ),
    )
    hypothesis = Hypothesis(
        statement=(
            "Players from the tournament's host country win at a rate different from their "
            "no-vig market price, and backing or fading them earns a positive ROI."
        ),
        rationale=(
            "Home crowds, local-media attention and bettors backing their compatriots could "
            "push home players' prices below fair — or crowd support could genuinely help "
            "them and the market under-price it. Either direction is testable."
        ),
        metric="home-player win rate vs market-implied (z-test); ROI and CLV bootstrap 95% "
        "CIs of back_home_nation and fade_home_nation",
        threshold=(
            f"Supported iff the cohort p < {SIGNIFICANCE_LEVEL} and a strategy's 2019+ ROI CI "
            f"lies entirely above 0 with >= {MIN_BETS_FOR_A_CLAIM} bets."
        ),
        in_sample="none — nothing is tuned",
        out_of_sample=(
            f"seasons >= {OUT_OF_SAMPLE_FIRST_SEASON}, reported alongside the full sample"
        ),
    )

    def run(self, context: StudyContext) -> StudyResult:
        home = next(o for o in context.cross_section.outcomes("host_nation") if o.group == "home")
        p_value = two_sided_binomial_p_value(home.successes, home.trials, home.expected_successes)
        cross_section_table = FindingTable(
            "Home player vs market (matches with exactly one home player)",
            ("Observations", "Win rate", "Market-implied", "Gap", "p"),
            ((
                home.trials, f"{home.successes / home.trials:.2%}",
                f"{home.expected_successes / home.trials:.2%}",
                percent((home.successes - home.expected_successes) / home.trials),
                f"{p_value:.3f}",
            ),),
        )  # fmt: skip
        rows, points, profitable = [], [], []
        for strategy in STRATEGIES:
            for label, filters in _SAMPLES:
                result = context.backtests.run(flat_request(strategy, **filters))
                point = roi_point(f"{strategy.split('_')[0]} · {_CHART_SAMPLES[label]}", result)
                clv_low, clv_high = clv_interval(result)
                points.append(point)
                rows.append((
                    strategy, label, point.count, percent(point.y),
                    f"{percent(point.low)} … {percent(point.high)}",
                    f"{percent(result.metrics.clv)} ({percent(clv_low)} … {percent(clv_high)})",
                ))  # fmt: skip
                if "holdout" in label and point.count >= MIN_BETS_FOR_A_CLAIM and point.low > 0:
                    profitable.append(strategy)
        control = context.backtests.run(flat_request("random_bet"))
        rows.append((
            "random_bet (control)", "all seasons", control.metrics.bet_count,
            percent(control.metrics.roi), "", percent(control.metrics.clv),
        ))  # fmt: skip
        strategy_table = FindingTable(
            "Trading the home-nation effect (flat stake; CLV is only meaningful relative to "
            "the control — fills at Pinnacle vs an Avg close give every bet positive CLV)",
            ("Strategy", "Sample", "Bets", "ROI", "ROI 95% CI", "CLV (95% CI)"),
            tuple(rows),
        )
        chart = ChartSeries(
            "roi_by_strategy", "ROI of host-nation strategies", "bar", "Strategy · sample", "ROI",
            tuple(points),
        )  # fmt: skip
        if p_value < SIGNIFICANCE_LEVEL and profitable:
            verdict = Verdict.SUPPORTED
            conclusion = f"A reliable mispricing, tradeable via {', '.join(profitable)}."
        elif p_value >= SIGNIFICANCE_LEVEL and not profitable:
            verdict = Verdict.NOT_SUPPORTED
            conclusion = (
                f"Home players' win rate is indistinguishable from their market price "
                f"(p = {p_value:.3f}) and neither strategy beats the margin on the holdout."
            )
        else:
            verdict = Verdict.INCONCLUSIVE
            conclusion = (
                f"Mixed evidence: cohort p = {p_value:.3f}; profitable on holdout: "
                f"{', '.join(profitable) or 'neither strategy'}."
            )
        return StudyResult(
            self.study_id, self.title, self.hypothesis, self.plain,
            (cross_section_table, strategy_table), (chart,), verdict, conclusion,
        )  # fmt: skip
