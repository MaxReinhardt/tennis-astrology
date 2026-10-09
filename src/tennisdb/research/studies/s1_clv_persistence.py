"""S1 (market microstructure): does EloValue earn closing-line value beyond what its
fills alone would, even when its ROI is too noisy to call? θ is tuned on seasons <= 2018
only; the verdict is read off the untouched 2019+ seasons.

Raw CLV here is contaminated: fills are Pinnacle prices but the closing benchmark is the
Avg book, and Pinnacle's lower margin gives *every* bet positive CLV. A random_bet
control with identical fills measures that artefact; edge is CLV in excess of it."""

from tennisdb.research.context import StudyContext
from tennisdb.research.protocol import FindingTable, Hypothesis, StudyResult, Verdict
from tennisdb.research.studies.common import (
    IN_SAMPLE_LAST_SEASON,
    OUT_OF_SAMPLE_FIRST_SEASON,
    clv_interval,
    flat_request,
    percent,
    roi_interval,
)

THETA_GRID = (0.02, 0.04, 0.06, 0.08, 0.10)
MIN_TUNING_BETS = 300


class ClvPersistenceStudy:
    study_id = "s1_clv_persistence"
    title = "S1 · Does EloValue show positive CLV when ROI is noisy?"
    hypothesis = Hypothesis(
        statement=(
            "Bets placed when Elo disagrees with the closing market by at least θ beat the "
            "closing price by more than a random-bet control with the same fills, even "
            "though the ROI over the same bets cannot be distinguished from zero."
        ),
        rationale=(
            "Closing prices are the sharpest estimate of true probability, so beating them "
            "is the cleanest evidence of edge; ROI over a few thousand bets at long odds "
            "has a confidence interval too wide to show it."
        ),
        metric="CLV bootstrap 95% CI, random_bet control CLV, and ROI bootstrap 95% CI "
        "on the 2019+ holdout",
        threshold=(
            "Supported iff the CLV CI lies entirely above the control's CLV and the ROI CI "
            "contains 0."
        ),
        in_sample=f"seasons <= {IN_SAMPLE_LAST_SEASON}: pick θ from {THETA_GRID} with the "
        f"highest CLV in excess of the control among grids with >= {MIN_TUNING_BETS} bets",
        out_of_sample=f"seasons >= {OUT_OF_SAMPLE_FIRST_SEASON}, touched once, with the chosen θ",
    )

    def run(self, context: StudyContext) -> StudyResult:
        control_in_sample = context.backtests.run(
            flat_request("random_bet", to_season=IN_SAMPLE_LAST_SEASON)
        )
        tuning = {
            theta: context.backtests.run(
                flat_request("elo_value", {"theta": theta}, to_season=IN_SAMPLE_LAST_SEASON)
            )
            for theta in THETA_GRID
        }
        eligible = {
            theta: result
            for theta, result in tuning.items()
            if result.metrics.bet_count >= MIN_TUNING_BETS
        }
        tuning_table = FindingTable(
            "In-sample tuning grid",
            ("θ", "Bets", "ROI", "CLV"),
            tuple(
                (theta, r.metrics.bet_count, percent(r.metrics.roi), percent(r.metrics.clv))
                for theta, r in tuning.items()
            ),
        )
        if not eligible:
            return StudyResult(
                self.study_id, self.title, self.hypothesis, (tuning_table,), (),
                Verdict.INCONCLUSIVE, "No θ placed enough in-sample bets to tune on.",
            )  # fmt: skip
        chosen = max(
            eligible,
            key=lambda theta: eligible[theta].metrics.clv - control_in_sample.metrics.clv,
        )
        holdout = context.backtests.run(
            flat_request("elo_value", {"theta": chosen}, from_season=OUT_OF_SAMPLE_FIRST_SEASON)
        )
        control = context.backtests.run(
            flat_request("random_bet", from_season=OUT_OF_SAMPLE_FIRST_SEASON)
        )
        roi_low, roi_high = roi_interval(holdout)
        clv_low, clv_high = clv_interval(holdout)
        holdout_table = FindingTable(
            f"Holdout {OUT_OF_SAMPLE_FIRST_SEASON}+ (θ = {chosen})",
            ("Bets", "ROI", "ROI 95% CI", "CLV", "CLV 95% CI", "Control CLV (random_bet)"),
            ((
                holdout.metrics.bet_count,
                percent(holdout.metrics.roi),
                f"{percent(roi_low)} … {percent(roi_high)}",
                percent(holdout.metrics.clv),
                f"{percent(clv_low)} … {percent(clv_high)}",
                percent(control.metrics.clv),
            ),),
        )  # fmt: skip
        verdict, conclusion = _verdict(clv_low, control.metrics.clv, roi_low, roi_high)
        return StudyResult(
            self.study_id, self.title, self.hypothesis, (tuning_table, holdout_table),
            holdout.charts(), verdict, conclusion,
        )  # fmt: skip


def _verdict(
    clv_low: float, control_clv: float, roi_low: float, roi_high: float
) -> tuple[Verdict, str]:
    if clv_low <= control_clv:
        return (
            Verdict.NOT_SUPPORTED,
            "EloValue's CLV does not exceed a random-bet control with the same fills: the "
            "positive raw CLV comes from the fill book's tighter prices, not from edge.",
        )
    if roi_low <= 0 <= roi_high:
        return Verdict.SUPPORTED, "CLV beats the control while the ROI interval spans zero."
    return (
        Verdict.INCONCLUSIVE,
        "CLV beats the control but ROI is decisively away from zero, so the divergence the "
        "hypothesis predicts is absent.",
    )
