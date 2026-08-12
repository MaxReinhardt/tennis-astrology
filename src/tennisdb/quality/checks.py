"""Declarative data-quality suite over the canonical tennis.* warehouse.

Each check is one small Strategy object that turns a SQL question into a CheckResult;
CHECKS is the reviewed registry and run_quality_suite evaluates them all into one
QualityReport. Two shapes cover every check: a ViolationCheck fails when too large a
fraction of rows offend an invariant, a MetricCheck fails when an aggregate lands
outside an expected band. Known, reviewed exceptions live in waivers.yaml — a waived
failure is reported, not counted against the suite (PLAN.md M5).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import duckdb
import yaml

from tennisdb import config

WAIVERS_PATH = Path(__file__).with_name("waivers.yaml")
REPORT_PATH = config.QUALITY_DIR / "quality_report.json"


@dataclass(frozen=True)
class CheckResult:
    name: str
    scope: str
    passed: bool
    detail: str
    sample: tuple[tuple, ...] = ()


class Check(Protocol):
    name: str
    scope: str

    def evaluate(self, connection: duckdb.DuckDBPyConnection) -> CheckResult: ...


@dataclass(frozen=True)
class ViolationCheck:
    """Fails when offending rows exceed max_fraction of the population (0 = none allowed)."""

    name: str
    scope: str
    offenders: str
    population: str
    max_fraction: float = 0.0
    sample_size: int = 5

    def evaluate(self, connection: duckdb.DuckDBPyConnection) -> CheckResult:
        offending = connection.execute(f"SELECT count(*) FROM ({self.offenders})").fetchone()[0]
        total = connection.execute(self.population).fetchone()[0]
        fraction = offending / total if total else 0.0
        detail = (
            f"{offending}/{total} = {fraction:.4%} offending "
            f"(max {self.max_fraction:.4%})"
        )
        return CheckResult(
            name=self.name,
            scope=self.scope,
            passed=fraction <= self.max_fraction,
            detail=detail,
            sample=self._sample(connection, offending),
        )

    def _sample(self, connection: duckdb.DuckDBPyConnection, offending: int) -> tuple[tuple, ...]:
        if not offending:
            return ()
        rows = connection.execute(
            f"SELECT * FROM ({self.offenders}) LIMIT {self.sample_size}"
        ).fetchall()
        return tuple(rows)


@dataclass(frozen=True)
class MetricCheck:
    """Fails when a scalar aggregate falls outside [low, high] (either bound may be open)."""

    name: str
    scope: str
    metric: str
    low: float | None = None
    high: float | None = None

    def evaluate(self, connection: duckdb.DuckDBPyConnection) -> CheckResult:
        value = connection.execute(self.metric).fetchone()[0]
        within = (self.low is None or value >= self.low) and (
            self.high is None or value <= self.high
        )
        detail = f"{value:.4f} within [{self.low}, {self.high}]"
        return CheckResult(self.name, self.scope, within, detail)


@dataclass
class QualityReport:
    results: tuple[CheckResult, ...]
    waivers: dict[str, str] = field(default_factory=dict)

    def failing(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.name not in self.waivers]

    def waived(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.name in self.waivers]

    def passed(self) -> bool:
        return not self.failing()

    def summary_lines(self) -> list[str]:
        headline = (
            f"quality: {'PASS' if self.passed() else 'FAIL'} "
            f"({len(self.results)} checks, {len(self.waived())} waived)"
        )
        return [headline] + [
            f"  [{self._status(result)}] {result.name}: {result.detail}" for result in self.results
        ]

    def _status(self, result: CheckResult) -> str:
        if result.passed:
            return "pass"
        return "WAIVED" if result.name in self.waivers else "FAIL"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed(),
            "checks": [
                {
                    "name": r.name,
                    "scope": r.scope,
                    "passed": r.passed,
                    "waived": r.name in self.waivers,
                    "detail": r.detail,
                    "sample": [list(row) for row in r.sample],
                }
                for r in self.results
            ],
        }


def load_waivers(path: Path = WAIVERS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {name: entry["reason"] for name, entry in document.items()}


def run_quality_suite(
    connection: duckdb.DuckDBPyConnection,
    checks: tuple[Check, ...] | None = None,
    waivers: dict[str, str] | None = None,
) -> QualityReport:
    resolved_checks = CHECKS if checks is None else checks
    resolved_waivers = load_waivers() if waivers is None else waivers
    results = tuple(check.evaluate(connection) for check in resolved_checks)
    return QualityReport(results=results, waivers=resolved_waivers)


def write_report(report: QualityReport, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


_REAL_BOOKS = "('B365', 'PS', 'Avg')"  # 'Max' is a best-line aggregate, not a market

CHECKS: tuple[Check, ...] = (
    ViolationCheck(
        name="matches_no_self_play",
        scope="matches",
        offenders="SELECT match_id FROM tennis.matches WHERE winner_id = loser_id",
        population="SELECT count(*) FROM tennis.matches",
    ),
    ViolationCheck(
        name="matches_players_exist",
        scope="matches",
        offenders=(
            "SELECT match_id FROM tennis.matches m WHERE "
            "NOT EXISTS (SELECT 1 FROM tennis.players p WHERE p.player_id = m.winner_id) "
            "OR NOT EXISTS (SELECT 1 FROM tennis.players p WHERE p.player_id = m.loser_id)"
        ),
        population="SELECT count(*) FROM tennis.matches",
    ),
    ViolationCheck(
        name="matches_best_of_valid",
        scope="matches",
        offenders=(
            "SELECT match_id FROM tennis.matches "
            "WHERE best_of IS NOT NULL AND best_of NOT IN (3, 5)"
        ),
        population="SELECT count(*) FROM tennis.matches",
    ),
    ViolationCheck(
        name="matches_scores_accounted",
        scope="matches",
        offenders=(
            "SELECT match_id FROM tennis.matches "
            "WHERE (score IS NULL OR score = '') AND NOT retirement AND NOT walkover"
        ),
        population="SELECT count(*) FROM tennis.matches",
        max_fraction=0.0005,
    ),
    ViolationCheck(
        name="matches_dates_within_edition",
        scope="matches",
        offenders=(
            "SELECT m.match_id FROM tennis.matches m "
            "JOIN tennis.tournament_editions te USING (edition_id) "
            "WHERE m.match_date IS NOT NULL AND te.start_date IS NOT NULL "
            "AND (m.match_date < te.start_date "
            "OR m.match_date > te.start_date + INTERVAL 27 DAY)"
        ),
        population=(
            "SELECT count(*) FROM tennis.matches m "
            "JOIN tennis.tournament_editions te USING (edition_id) "
            "WHERE m.match_date IS NOT NULL AND te.start_date IS NOT NULL"
        ),
        max_fraction=0.01,
    ),
    ViolationCheck(
        name="matches_no_duplicate_odds_pairings",
        scope="matches",
        offenders=(
            "SELECT edition_id, round, winner_id, loser_id FROM tennis.matches "
            "WHERE match_id IN (SELECT match_id FROM tennis.odds) "
            "GROUP BY 1, 2, 3, 4 HAVING count(*) > 1"
        ),
        population="SELECT count(DISTINCT match_id) FROM tennis.odds",
    ),
    ViolationCheck(
        name="matches_no_duplicate_pairings",
        scope="matches",
        offenders=(
            "SELECT edition_id, round, winner_id, loser_id, score, match_date "
            "FROM tennis.matches GROUP BY 1, 2, 3, 4, 5, 6 HAVING count(*) > 1"
        ),
        population="SELECT count(*) FROM tennis.matches",
    ),
    ViolationCheck(
        name="odds_reference_matches",
        scope="odds",
        offenders=(
            "SELECT o.match_id, o.bookmaker FROM tennis.odds o "
            "WHERE NOT EXISTS (SELECT 1 FROM tennis.matches m WHERE m.match_id = o.match_id)"
        ),
        population="SELECT count(*) FROM tennis.odds",
    ),
    ViolationCheck(
        name="odds_overround_within_band",
        scope="odds",
        offenders=(
            "SELECT match_id, bookmaker, overround FROM tennis.odds_implied "
            f"WHERE bookmaker IN {_REAL_BOOKS} "
            "AND NOT (overround > 0 AND overround < 0.15)"
        ),
        population=f"SELECT count(*) FROM tennis.odds_implied WHERE bookmaker IN {_REAL_BOOKS}",
        max_fraction=0.01,
    ),
    ViolationCheck(
        name="odds_max_ge_avg",
        scope="odds",
        offenders=(
            "SELECT mx.match_id FROM tennis.odds mx JOIN tennis.odds av USING (match_id) "
            "WHERE mx.bookmaker = 'Max' AND av.bookmaker = 'Avg' "
            "AND (mx.winner_odds < av.winner_odds OR mx.loser_odds < av.loser_odds)"
        ),
        population=(
            "SELECT count(*) FROM tennis.odds mx JOIN tennis.odds av USING (match_id) "
            "WHERE mx.bookmaker = 'Max' AND av.bookmaker = 'Avg'"
        ),
        max_fraction=0.01,
    ),
    MetricCheck(
        name="odds_favorite_win_rate",
        scope="odds",
        metric=(
            "SELECT avg((winner_odds < loser_odds)::int) FROM tennis.odds "
            "WHERE bookmaker = 'Avg' AND winner_odds <> loser_odds"
        ),
        low=0.62,
        high=0.70,
    ),
    MetricCheck(
        name="odds_pinnacle_margin_below_bet365",
        scope="odds",
        metric=(
            "SELECT (SELECT avg(overround) FROM tennis.odds_implied WHERE bookmaker = 'PS') "
            "- (SELECT avg(overround) FROM tennis.odds_implied WHERE bookmaker = 'B365')"
        ),
        high=0.0,
    ),
)
