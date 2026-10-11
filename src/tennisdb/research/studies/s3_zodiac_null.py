"""S3 (astrology, and a deliberate multiple-testing lesson): do zodiac sign, element or
birth month predict beating the market? 28 cohort tests are run at once, so one raw
p < 0.05 is expected by chance alone; the verdict reads only the corrected p-values."""

from math import sqrt

from tennisdb.backtest.charts import ChartPoint, ChartSeries
from tennisdb.research.context import GroupOutcome, StudyContext
from tennisdb.research.protocol import FindingTable, Hypothesis, PlainSummary, StudyResult, Verdict
from tennisdb.research.significance import (
    benjamini_hochberg,
    bonferroni,
    two_sided_binomial_p_value,
)

DIMENSIONS = ("zodiac_sign", "zodiac_element", "birth_month")
SIGNIFICANCE_LEVEL = 0.05
_Z_95 = 1.96


class ZodiacNullStudy:
    study_id = "s3_zodiac_null"
    title = "S3 · Does a player's zodiac sign beat the market?"
    plain = PlainSummary(
        title="Do star signs predict who wins?",
        summary=(
            "We check whether players born under a given star sign, element or month win more "
            "often than the odds predict. There is no reason this should work, so it shows "
            "how often pure chance looks like a pattern when many groups are tested."
        ),
    )
    hypothesis = Hypothesis(
        statement=(
            "At least one zodiac sign, element or birth month wins more often than its "
            "no-vig market price implies."
        ),
        rationale=(
            "None: the claim has no causal mechanism. It is the harness's null "
            "demonstrator — the expected verdict is that the correction rejects it."
        ),
        metric="two-sided z-test of wins vs market-implied wins per cohort; Bonferroni "
        "and Benjamini–Hochberg corrected over all cohorts",
        threshold=f"Supported iff any Bonferroni-corrected p < {SIGNIFICANCE_LEVEL}.",
        in_sample="none — nothing is fit",
        out_of_sample="none — the whole odds-era sample",
    )

    def run(self, context: StudyContext) -> StudyResult:
        cohorts = [
            (dimension, outcome)
            for dimension in DIMENSIONS
            for outcome in context.cross_section.outcomes(dimension)
        ]
        raw = [
            two_sided_binomial_p_value(o.successes, o.trials, o.expected_successes)
            for _, o in cohorts
        ]
        bonferroni_p, fdr_p = bonferroni(raw), benjamini_hochberg(raw)
        rows = tuple(
            (
                dimension, o.group, o.trials, f"{o.successes / o.trials:.2%}",
                f"{o.expected_successes / o.trials:.2%}", f"{raw[i]:.3f}",
                f"{bonferroni_p[i]:.3f}", f"{fdr_p[i]:.3f}",
            )
            for i, (dimension, o) in enumerate(cohorts)
        )  # fmt: skip
        table = FindingTable(
            f"{len(cohorts)} cohort tests against the market",
            ("Dimension", "Cohort", "Observations", "Win rate", "Market-implied", "p", "p (Bonf.)",
             "q (BH)"),
            rows,
        )  # fmt: skip
        chart = _gap_chart(
            [(o, raw[i]) for i, (dimension, o) in enumerate(cohorts) if dimension == "zodiac_sign"]
        )
        smallest = min(bonferroni_p, default=1.0)
        chance_hits = sum(p < SIGNIFICANCE_LEVEL for p in raw)
        if smallest < SIGNIFICANCE_LEVEL:
            verdict = Verdict.SUPPORTED
            conclusion = f"A cohort survives Bonferroni correction (p = {smallest:.3f})."
        else:
            verdict = Verdict.NOT_SUPPORTED
            conclusion = (
                f"{chance_hits} of {len(cohorts)} cohorts have raw p < {SIGNIFICANCE_LEVEL} "
                f"(about {len(cohorts) * SIGNIFICANCE_LEVEL:.1f} expected by chance); none "
                f"survives correction (smallest Bonferroni p = {smallest:.3f})."
            )
        return StudyResult(
            self.study_id,
            self.title,
            self.hypothesis,
            self.plain,
            (table,),
            (chart,),
            verdict,
            conclusion,
        )


def _gap_chart(signs: list[tuple[GroupOutcome, float]]) -> ChartSeries:
    points = []
    for outcome, _ in signs:
        gap = (outcome.successes - outcome.expected_successes) / outcome.trials
        probability = outcome.expected_successes / outcome.trials
        margin = _Z_95 * sqrt(probability * (1 - probability) / outcome.trials)
        points.append(ChartPoint(outcome.group, gap, gap - margin, gap + margin, outcome.trials))
    return ChartSeries(
        "zodiac_gap", "Win rate minus market-implied, by sign", "bar", "Sign", "Win-rate gap",
        tuple(points),
    )  # fmt: skip
