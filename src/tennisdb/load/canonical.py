"""Rebuild the canonical tennis.* tables from the staging schema (DuckDB).

Sackmann ATP and WTA ids collide, so both id spaces are namespaced here and only
here: WTA player ids get +10,000,000, WTA edition ids the 'wta-' prefix. Rows that
cannot satisfy a primary key or NOT NULL constraint are dropped; values that would
violate a CHECK constraint are nulled. Every drop and null is counted in the
LoadReport and logged to tennis.ingest_log.
"""

import json
from dataclasses import dataclass, field

import duckdb

from tennisdb.ids import WTA_EDITION_PREFIX, WTA_PLAYER_ID_OFFSET

_DELETE_ORDER = (
    "odds",
    "match_stats",
    "rankings",
    "player_aliases",
    "edition_aliases",
    "matches",
    "tournament_editions",
    "players",
)

_EDITION_ID = (
    f"CASE WHEN tour = 'wta' THEN '{WTA_EDITION_PREFIX}' || tourney_id ELSE tourney_id END"
)
_MATCH_ID = f"{_EDITION_ID} || '-' || match_num"
_VALID_HANDS = "('R', 'L', 'U', 'A')"

_RANKED_MATCHES = """WITH ranked AS (
    SELECT *, row_number() OVER (
        PARTITION BY tour, tourney_id, match_num ORDER BY source_file
    ) AS duplicate_rank
    FROM staging.sackmann_matches
    WHERE tourney_id IS NOT NULL AND match_num IS NOT NULL
)"""

_ELIGIBLE_MATCH = (
    "duplicate_rank = 1 AND round IS NOT NULL AND winner_id IS NOT NULL "
    "AND loser_id IS NOT NULL AND winner_id <> loser_id"
)

_STAT_COLUMNS = (
    'w_ace, w_df, w_svpt, "w_1stIn", "w_1stWon", "w_2ndWon", "w_SvGms", "w_bpSaved", '
    '"w_bpFaced", l_ace, l_df, l_svpt, "l_1stIn", "l_1stWon", "l_2ndWon", "l_SvGms", '
    '"l_bpSaved", "l_bpFaced"'
)


def _offset_player_id(column: str) -> str:
    return f"CASE WHEN tour = 'wta' THEN {column} + {WTA_PLAYER_ID_OFFSET} ELSE {column} END"


_KNOWN_PLAYERS = (
    f"{_offset_player_id('winner_id')} IN (SELECT player_id FROM tennis.players) "
    f"AND {_offset_player_id('loser_id')} IN (SELECT player_id FROM tennis.players)"
)


@dataclass
class LoadReport:
    table_rows: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, dict[str, int]] = field(default_factory=dict)
    nulled: dict[str, dict[str, int]] = field(default_factory=dict)

    def stats(self) -> dict:
        return {"table_rows": self.table_rows, "dropped": self.dropped, "nulled": self.nulled}

    def summary_lines(self) -> list[str]:
        lines = [f"tennis.{table}: {count} rows" for table, count in self.table_rows.items()]
        for table, reasons in self.dropped.items():
            lines.extend(
                f"  {table}: dropped {count} rows ({reason})"
                for reason, count in reasons.items()
                if count
            )
        for table, columns in self.nulled.items():
            lines.extend(
                f"  {table}: nulled {count} values ({column})"
                for column, count in columns.items()
                if count
            )
        return lines


def load_canonical(connection: duckdb.DuckDBPyConnection) -> LoadReport:
    """Statements autocommit individually: DuckDB's ART index rejects deleting and
    reinserting the same key inside one transaction, so a failed run leaves a partial
    canonical layer — re-running repairs it."""
    report = LoadReport()
    for table in _DELETE_ORDER:
        connection.execute(f"DELETE FROM tennis.{table}")
    _load_players(connection, report)
    _load_tournament_editions(connection, report)
    _load_matches(connection, report)
    _load_match_stats(connection, report)
    _load_rankings(connection, report)
    connection.execute(
        "INSERT INTO tennis.ingest_log (step, stats) VALUES ('load:canonical', CAST(? AS JSON))",
        [json.dumps(report.stats())],
    )
    return report


def _scalar(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    return connection.execute(sql).fetchone()[0]


def _load_players(connection: duckdb.DuckDBPyConnection, report: LoadReport) -> None:
    report.nulled["players"] = {
        "hand": _scalar(
            connection,
            "SELECT count(*) FROM staging.sackmann_players "
            f"WHERE hand IS NOT NULL AND hand NOT IN {_VALID_HANDS}",
        ),
        "height_cm": _scalar(
            connection,
            "SELECT count(*) FROM staging.sackmann_players "
            "WHERE height IS NOT NULL AND height NOT BETWEEN 120 AND 230",
        ),
    }
    report.table_rows["players"] = connection.execute(
        f"""
        INSERT INTO tennis.players
        SELECT {_offset_player_id("player_id")}, tour,
               trim(coalesce(name_first, '') || ' ' || coalesce(name_last, '')),
               CASE WHEN hand IN {_VALID_HANDS} THEN hand END,
               dob, ioc,
               CASE WHEN height BETWEEN 120 AND 230 THEN height END,
               wikidata_id
        FROM staging.sackmann_players
        WHERE player_id IS NOT NULL
        """
    ).fetchone()[0]


def _load_tournament_editions(connection: duckdb.DuckDBPyConnection, report: LoadReport) -> None:
    report.table_rows["tournament_editions"] = connection.execute(
        f"""
        INSERT INTO tennis.tournament_editions
        WITH editions AS (
            SELECT tour, tourney_id,
                   any_value(tourney_name) AS name,
                   any_value(surface) AS surface,
                   any_value(tourney_level) AS level,
                   any_value(draw_size) AS draw_size,
                   any_value(tourney_date) AS start_date,
                   coalesce(
                       try_cast(substr(tourney_id, 1, 4) AS INTEGER),
                       year(any_value(tourney_date))
                   ) AS season_candidate
            FROM staging.sackmann_matches
            WHERE tourney_id IS NOT NULL
            GROUP BY tour, tourney_id
        )
        SELECT {_EDITION_ID}, tour, name, surface, level,
               CASE WHEN draw_size > 1 THEN draw_size END,
               start_date,
               CASE WHEN season_candidate BETWEEN 1968 AND 2100 THEN season_candidate END
        FROM editions
        """
    ).fetchone()[0]


def _load_matches(connection: duckdb.DuckDBPyConnection, report: LoadReport) -> None:
    report.dropped["matches"] = {
        "duplicate": _scalar(
            connection, f"{_RANKED_MATCHES} SELECT count(*) FROM ranked WHERE duplicate_rank > 1"
        ),
        "null_round": _scalar(
            connection,
            f"{_RANKED_MATCHES} SELECT count(*) FROM ranked "
            "WHERE duplicate_rank = 1 AND round IS NULL",
        ),
        "same_player": _scalar(
            connection,
            f"{_RANKED_MATCHES} SELECT count(*) FROM ranked "
            "WHERE duplicate_rank = 1 AND round IS NOT NULL "
            "AND (winner_id IS NULL OR loser_id IS NULL OR winner_id = loser_id)",
        ),
        "unknown_player": _scalar(
            connection,
            f"{_RANKED_MATCHES} SELECT count(*) FROM ranked "
            f"WHERE {_ELIGIBLE_MATCH} AND NOT ({_KNOWN_PLAYERS})",
        ),
    }
    best_of, minutes, ranks = connection.execute(
        f"""
        {_RANKED_MATCHES}
        SELECT count(*) FILTER (WHERE best_of IS NOT NULL AND best_of NOT IN (3, 5)),
               count(*) FILTER (WHERE minutes IS NOT NULL AND minutes <= 0),
               count(*) FILTER (WHERE winner_rank IS NOT NULL AND winner_rank <= 0)
               + count(*) FILTER (WHERE loser_rank IS NOT NULL AND loser_rank <= 0)
               + count(*) FILTER (
                   WHERE winner_rank_points IS NOT NULL AND winner_rank_points < 0)
               + count(*) FILTER (WHERE loser_rank_points IS NOT NULL AND loser_rank_points < 0)
        FROM ranked WHERE {_ELIGIBLE_MATCH} AND {_KNOWN_PLAYERS}
        """
    ).fetchone()
    report.nulled["matches"] = {"best_of": best_of, "minutes": minutes, "ranks": ranks}
    report.table_rows["matches"] = connection.execute(
        f"""
        INSERT INTO tennis.matches
        {_RANKED_MATCHES}
        SELECT {_MATCH_ID}, {_EDITION_ID}, round,
               CASE WHEN best_of IN (3, 5) THEN best_of END,
               tourney_date,
               {_offset_player_id("winner_id")}, {_offset_player_id("loser_id")}, score,
               coalesce(score ILIKE '%RET%', false),
               coalesce(score ILIKE '%W/O%', false),
               CASE WHEN minutes > 0 THEN minutes END,
               CASE WHEN winner_rank > 0 THEN winner_rank END,
               CASE WHEN winner_rank_points >= 0 THEN winner_rank_points END,
               CASE WHEN loser_rank > 0 THEN loser_rank END,
               CASE WHEN loser_rank_points >= 0 THEN loser_rank_points END
        FROM ranked
        WHERE {_ELIGIBLE_MATCH} AND {_KNOWN_PLAYERS}
        """
    ).fetchone()[0]


def _load_match_stats(connection: duckdb.DuckDBPyConnection, report: LoadReport) -> None:
    report.table_rows["match_stats"] = connection.execute(
        f"""
        INSERT INTO tennis.match_stats
        {_RANKED_MATCHES}
        SELECT {_MATCH_ID}, {_STAT_COLUMNS}
        FROM ranked
        WHERE {_ELIGIBLE_MATCH} AND {_KNOWN_PLAYERS}
          AND coalesce({_STAT_COLUMNS}) IS NOT NULL
        """
    ).fetchone()[0]


def _load_rankings(connection: duckdb.DuckDBPyConnection, report: LoadReport) -> None:
    deduped = f"""WITH deduped AS (
        SELECT ranking_date, tour,
               {_offset_player_id("player")} AS player_id,
               rank, points,
               row_number() OVER (
                   PARTITION BY tour, ranking_date, player
                   ORDER BY rank, points DESC NULLS LAST
               ) AS duplicate_rank
        FROM staging.sackmann_rankings
        WHERE ranking_date IS NOT NULL AND player IS NOT NULL AND rank > 0
    )"""
    report.dropped["rankings"] = {
        "duplicate": _scalar(
            connection, f"{deduped} SELECT count(*) FROM deduped WHERE duplicate_rank > 1"
        ),
        "unknown_player": _scalar(
            connection,
            f"{deduped} SELECT count(*) FROM deduped WHERE duplicate_rank = 1 "
            "AND player_id NOT IN (SELECT player_id FROM tennis.players)",
        ),
    }
    report.table_rows["rankings"] = connection.execute(
        f"""
        INSERT INTO tennis.rankings
        {deduped}
        SELECT ranking_date, tour, player_id, rank,
               CASE WHEN points >= 0 THEN points END
        FROM deduped
        WHERE duplicate_rank = 1
          AND player_id IN (SELECT player_id FROM tennis.players)
        """
    ).fetchone()[0]
