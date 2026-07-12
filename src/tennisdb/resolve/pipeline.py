"""Compose the resolve steps: aliases → editions → matches → odds, persist the
alias tables, write the unmatched-rows CSV, and log stats to tennis.ingest_log."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from tennisdb import config
from tennisdb.resolve.matches import MatchResolution, OddsSourceRow, resolve_matches
from tennisdb.resolve.odds import emit_odds
from tennisdb.resolve.players import resolve_player_aliases
from tennisdb.resolve.tournaments import resolve_editions

UNMATCHED_FILE = "unmatched_odds.csv"

_UNMATCHED_HEADER = (
    "reason", "tour", "season", "tournament", "location", "date", "round",
    "winner", "loser", "wrank", "lrank", "source_file", "source_row",
)


@dataclass
class ResolutionReport:
    total_rows: int
    resolved_rows: int
    odds_rows: int
    player_alias_rows: int
    edition_alias_rows: int
    reason_counts: dict[str, int]
    season_tour_counts: dict[tuple[int, str], tuple[int, int]]
    unmatched_path: Path

    def match_rate(self) -> float:
        return self.resolved_rows / self.total_rows if self.total_rows else 0.0

    def summary_lines(self) -> list[str]:
        lines = [
            f"resolved {self.resolved_rows}/{self.total_rows} tennis-data rows "
            f"({self.match_rate():.2%})",
            f"tennis.odds: {self.odds_rows} rows",
            f"tennis.player_aliases: {self.player_alias_rows} rows",
            f"tennis.edition_aliases: {self.edition_alias_rows} rows",
        ]
        lines.extend(
            f"  unmatched ({reason}): {count}"
            for reason, count in sorted(self.reason_counts.items(), key=lambda item: -item[1])
        )
        lines.extend(self._season_lines())
        lines.append(f"unmatched rows written to {self.unmatched_path}")
        return lines

    def _season_lines(self) -> list[str]:
        by_season: dict[int, list[str]] = {}
        for (season, tour), (matched, total) in sorted(self.season_tour_counts.items()):
            by_season.setdefault(season, []).append(f"{tour} {matched / total:.1%}")
        return [
            f"  {season}: " + ", ".join(rates) for season, rates in sorted(by_season.items())
        ]

    def stats(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "resolved_rows": self.resolved_rows,
            "odds_rows": self.odds_rows,
            "player_alias_rows": self.player_alias_rows,
            "edition_alias_rows": self.edition_alias_rows,
            "reasons": self.reason_counts,
            "season_tour": {
                f"{season}/{tour}": [matched, total]
                for (season, tour), (matched, total) in sorted(self.season_tour_counts.items())
            },
        }


def run_resolution(connection: duckdb.DuckDBPyConnection) -> ResolutionReport:
    players = resolve_player_aliases(connection)
    editions = resolve_editions(connection)
    resolution = resolve_matches(connection, players, editions)

    connection.execute("DELETE FROM tennis.odds")
    connection.execute("DELETE FROM tennis.player_aliases")
    connection.execute("DELETE FROM tennis.edition_aliases")
    player_alias_rows = _insert_rows(
        connection, "tennis.player_aliases", players.single_id_rows()
    )
    edition_alias_rows = _insert_rows(
        connection, "tennis.edition_aliases", editions.alias_rows()
    )
    odds_rows = emit_odds(connection, resolution.resolved)
    unmatched_path = _write_unmatched_csv(resolution)

    report = ResolutionReport(
        total_rows=len(resolution.resolved) + len(resolution.unmatched),
        resolved_rows=len(resolution.resolved),
        odds_rows=odds_rows,
        player_alias_rows=player_alias_rows,
        edition_alias_rows=edition_alias_rows,
        reason_counts=resolution.reason_counts(),
        season_tour_counts=resolution.season_tour_counts(),
        unmatched_path=unmatched_path,
    )
    connection.execute(
        "INSERT INTO tennis.ingest_log (step, stats) VALUES ('resolve:matches', CAST(? AS JSON))",
        [json.dumps(report.stats())],
    )
    return report


def _insert_rows(connection: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in rows[0])
    connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    return len(rows)


def _write_unmatched_csv(resolution: MatchResolution) -> Path:
    config.QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    path = config.QUALITY_DIR / UNMATCHED_FILE
    ordered = sorted(
        resolution.unmatched, key=lambda pair: (pair[0].source_file, pair[0].source_row)
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_UNMATCHED_HEADER)
        writer.writerows(_unmatched_record(row, reason) for row, reason in ordered)
    return path


def _unmatched_record(row: OddsSourceRow, reason: str) -> tuple:
    return (
        reason, row.tour, row.season, row.tournament, row.location, row.match_date,
        row.round, row.winner, row.loser, row.winner_rank, row.loser_rank,
        row.source_file, row.source_row,
    )
