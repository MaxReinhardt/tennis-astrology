"""S2 (behavioural): the favourite–longshot bias. Where, by surface and price bucket, is
the vig-adjusted expected value least negative? Descriptive and untuned — nothing is fit,
so the whole sample is the sample."""

from tennisdb.backtest.charts import ChartSeries
from tennisdb.research.context import StudyContext
from tennisdb.research.protocol import FindingTable, Hypothesis, StudyResult, Verdict
from tennisdb.research.studies.common import MIN_BETS_FOR_A_CLAIM, percent, roi_point

SURFACES = ("Hard", "Clay", "Grass")
# (label, strategy, min_price, max_price); max prices sit just under the next edge.
BUCKETS = (
    ("1.0–1.5", "back_favorites", 1.01, 1.499),
    ("1.5–2.0", "back_favorites", 1.5, 1.999),
    ("2.0–3.0", "back_underdogs", 2.0, 2.999),
    ("3.0–5.0", "back_underdogs", 3.0, 4.999),
    ("5.0–10.0", "back_underdogs", 5.0, 9.999),
    ("10.0+", "back_underdogs", 10.0, 1000.0),
)


class FavouriteLongshotStudy:
    study_id = "s2_favourite_longshot"
    title = "S2 · Favourite–longshot bias by surface and price"
    hypothesis = Hypothesis(
        statement=(
            "Expected value declines as the price lengthens: on every surface the shortest "
            "bucket has a higher ROI than the longest, and no bucket's ROI interval lies "
            "entirely above zero."
        ),
        rationale=(
            "Bettors overpay for longshots, so books can shade them harder; favourites are "
            "closer to fairly priced, though still net of the margin."
        ),
        metric="ROI per surface x price bucket, with bootstrap 95% CI (flat stake)",
        threshold=(
            f"Supported iff shortest-bucket ROI > longest-bucket ROI on all {len(SURFACES)} "
            f"surfaces and no bucket with >= {MIN_BETS_FOR_A_CLAIM} bets has ROI CI low > 0."
        ),
        in_sample="none — descriptive, nothing is tuned",
        out_of_sample="none — the whole odds-era sample",
    )

    def run(self, context: StudyContext) -> StudyResult:
        rows, charts = [], []
        bias_by_surface, exploitable = {}, []
        for surface in SURFACES:
            points = []
            for label, strategy, minimum, maximum in BUCKETS:
                result = context.backtests.run(
                    _request(strategy, minimum, maximum, surface)
                )
                point = roi_point(label, result)
                points.append(point)
                rows.append((
                    surface, label, point.count, percent(point.y),
                    f"{percent(point.low)} … {percent(point.high)}",
                ))  # fmt: skip
                if point.count >= MIN_BETS_FOR_A_CLAIM and point.low > 0:
                    exploitable.append(f"{surface} {label}")
            bias_by_surface[surface] = points[0].y > points[-1].y
            charts.append(ChartSeries(
                f"roi_by_bucket_{surface.lower()}", f"ROI by price bucket — {surface}",
                "bar", "Decimal price", "ROI", tuple(points),
            ))  # fmt: skip
        verdict, conclusion = _verdict(bias_by_surface, exploitable)
        table = FindingTable(
            "ROI by surface and price bucket",
            ("Surface", "Price", "Bets", "ROI", "ROI 95% CI"),
            tuple(rows),
        )
        return StudyResult(
            self.study_id, self.title, self.hypothesis, (table,), tuple(charts),
            verdict, conclusion,
        )  # fmt: skip


def _request(strategy: str, minimum: float, maximum: float, surface: str):
    from tennisdb.research.studies.common import flat_request

    return flat_request(
        strategy, {"min_price": minimum, "max_price": maximum}, surfaces=[surface]
    )


def _verdict(bias_by_surface: dict[str, bool], exploitable: list[str]) -> tuple[Verdict, str]:
    if exploitable:
        return Verdict.NOT_SUPPORTED, f"A bucket beat the margin: {', '.join(exploitable)}."
    if all(bias_by_surface.values()):
        return (
            Verdict.SUPPORTED,
            "Longshots lose more than favourites on every surface and no bucket is profitable.",
        )
    held = [surface for surface, present in bias_by_surface.items() if present]
    return (
        Verdict.INCONCLUSIVE,
        f"No bucket is profitable, but the bias appears only on: {', '.join(held) or 'none'}.",
    )
