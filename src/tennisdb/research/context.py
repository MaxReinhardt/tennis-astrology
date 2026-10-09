"""What a study may depend on: a way to run backtests and a market-relative cross
section of outcomes. Both are Protocols defined here (inner layer); the DuckDB-backed
implementations live outside, so no study imports a database."""

from dataclasses import dataclass
from typing import Protocol

from tennisdb.backtest.engine import OpportunitySource, run_backtest
from tennisdb.backtest.report import BacktestResult
from tennisdb.backtest.request import BacktestRequest


@dataclass(frozen=True)
class GroupOutcome:
    """One cohort's results against its own market expectation: every observation is a
    player in a match, a success is that player winning, and the expectation is the sum
    of the player's no-vig market win probabilities."""

    group: str
    trials: int
    successes: int
    expected_successes: float


class BacktestRunner(Protocol):
    def run(self, request: BacktestRequest) -> BacktestResult: ...


class MatchCrossSection(Protocol):
    def outcomes(self, dimension: str) -> list[GroupOutcome]: ...


class EngineBacktestRunner:
    def __init__(self, source: OpportunitySource):
        self._source = source

    def run(self, request: BacktestRequest) -> BacktestResult:
        return run_backtest(request, self._source)


@dataclass(frozen=True)
class StudyContext:
    backtests: BacktestRunner
    cross_section: MatchCrossSection
