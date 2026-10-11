"""Research entities, framework-free: a pre-registered Hypothesis, the tables a study
finds, and the Verdict it reaches. StudyResult follows the stats()/summary_lines()/
to_dict() convention of the repo's other reports (quality, features, publish)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from tennisdb.backtest.charts import ChartSeries
from tennisdb.research.context import StudyContext


class Verdict(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Hypothesis:
    """Fixed before any result is looked at. `metric` and `threshold` are the
    pre-registered decision rule; in/out-of-sample say which seasons may be used to tune
    and which are held out for the verdict."""

    statement: str
    rationale: str
    metric: str
    threshold: str
    in_sample: str
    out_of_sample: str


@dataclass(frozen=True)
class PlainSummary:
    """Everyday-language framing shown next to a study. It sits beside the pre-registered
    Hypothesis and never replaces it, so wording the protocol fixed stays untouched."""

    title: str
    summary: str


@dataclass(frozen=True)
class FindingTable:
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]

    def to_dict(self) -> dict:
        return {"title": self.title, "columns": list(self.columns),
                "rows": [list(row) for row in self.rows]}  # fmt: skip


@dataclass(frozen=True)
class StudyResult:
    study_id: str
    title: str
    hypothesis: Hypothesis
    plain: PlainSummary
    tables: tuple[FindingTable, ...]
    charts: tuple[ChartSeries, ...]
    verdict: Verdict
    conclusion: str

    def stats(self) -> dict:
        return {"study_id": self.study_id, "verdict": self.verdict.value}

    def summary_lines(self) -> list[str]:
        return [f"{self.study_id}: {self.verdict.value}", f"  {self.conclusion}"]

    def to_dict(self) -> dict:
        return {
            "study_id": self.study_id,
            "title": self.title,
            "hypothesis": vars(self.hypothesis),
            "plain_title": self.plain.title,
            "plain_summary": self.plain.summary,
            "tables": [table.to_dict() for table in self.tables],
            "charts": [chart.to_dict() for chart in self.charts],
            "verdict": self.verdict.value,
            "conclusion": self.conclusion,
        }


class Study(Protocol):
    study_id: str
    title: str
    hypothesis: Hypothesis
    plain: PlainSummary

    def run(self, context: StudyContext) -> StudyResult: ...
