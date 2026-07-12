"""Emit long-format tennis.odds rows (one per match × bookmaker) for resolved rows."""

import duckdb
import pandas as pd

from tennisdb.resolve.matches import OddsSourceRow

ODDS_SOURCE = "tennisdata"

_ODDS_COLUMNS = (
    "match_id",
    "bookmaker",
    "winner_odds",
    "loser_odds",
    "is_closing",
    "source",
    "source_row",
)


def emit_odds(
    connection: duckdb.DuckDBPyConnection,
    resolved: list[tuple[OddsSourceRow, str]],
) -> int:
    records = [
        (match_id, bookmaker, winner_odds, loser_odds, True, ODDS_SOURCE,
         f"{row.source_file}:{row.source_row}")
        for row, match_id in resolved
        for bookmaker, (winner_odds, loser_odds) in row.bookmaker_odds.items()
        if winner_odds is not None and loser_odds is not None
    ]
    if not records:
        return 0
    frame = pd.DataFrame(records, columns=_ODDS_COLUMNS)
    connection.register("_odds_rows", frame)
    try:
        return connection.execute("INSERT INTO tennis.odds SELECT * FROM _odds_rows").fetchone()[0]
    finally:
        connection.unregister("_odds_rows")
