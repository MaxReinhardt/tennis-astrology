"""DuckDB adapter for OpportunitySource — the only backtest module that imports
duckdb. Translates a validated BacktestRequest into one SQL query against the
warehouse, pushing every filter down to SQL so Python only ever iterates the matches
the request actually wants, in the same chronological order
features.ordering.in_match_order defines.
"""

from collections.abc import Iterator

import duckdb

from tennisdb.backtest.domain import MatchEvent, MatchOpportunity
from tennisdb.backtest.request import BacktestRequest
from tennisdb.features.elo import elo_probability
from tennisdb.features.ordering import DEFAULT_ROUND_ORDINAL, ROUND_ORDINAL

_ROUND_CASE = "CASE round {whens} ELSE {default} END".format(
    whens=" ".join(f"WHEN '{name}' THEN {ordinal}" for name, ordinal in ROUND_ORDINAL.items()),
    default=DEFAULT_ROUND_ORDINAL,
)

_QUERY_TEMPLATE = """
WITH fill AS (
  SELECT
    match_id,
    winner_odds::DOUBLE AS winner_price,
    loser_odds::DOUBLE AS loser_price,
    row_number() OVER (PARTITION BY match_id ORDER BY {fill_preference_case}) AS preference
  FROM tennis.odds
  WHERE bookmaker IN ({fill_book_placeholders})
    AND winner_odds IS NOT NULL AND loser_odds IS NOT NULL
)
SELECT
  model.match_id,
  coalesce(model.match_date, e.start_date) AS match_date,
  e.season,
  e.tour,
  e.surface,
  e.level,
  model.round,
  model.p1_won,
  CASE WHEN model.p1_won THEN fill.winner_price ELSE fill.loser_price END AS p1_price,
  CASE WHEN model.p1_won THEN fill.loser_price ELSE fill.winner_price END AS p2_price,
  CASE WHEN model.p1_won THEN consensus.winner_odds ELSE consensus.loser_odds END::DOUBLE
    AS p1_consensus_price,
  CASE WHEN model.p1_won THEN consensus.loser_odds ELSE consensus.winner_odds END::DOUBLE
    AS p2_consensus_price,
  mk.p1_market_prob AS p1_consensus_prob,
  elo.p1_elo_pre, elo.p2_elo_pre,
  elo.p1_surface_elo_pre, elo.p2_surface_elo_pre
FROM tennis.matches_model AS model
JOIN tennis.tournament_editions AS e USING (edition_id)
JOIN fill USING (match_id)
JOIN analytics.market AS mk USING (match_id)
JOIN analytics.elo_pre AS elo USING (match_id)
JOIN tennis.odds AS consensus
  ON consensus.match_id = model.match_id AND consensus.bookmaker = mk.bookmaker
WHERE fill.preference = 1
{filter_clause}
ORDER BY match_date, model.edition_id, {round_case}, model.match_id
"""


def _fill_preference_case(fill_preference: tuple[str, ...]) -> str:
    whens = " ".join(f"WHEN '{book}' THEN {rank}" for rank, book in enumerate(fill_preference))
    return f"CASE bookmaker {whens} ELSE {len(fill_preference)} END"


def _build_filters(request: BacktestRequest) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    filters = request.filters
    if filters.tour is not None:
        clauses.append("e.tour = ?")
        params.append(filters.tour)
    if filters.surfaces:
        clauses.append(f"e.surface IN ({', '.join('?' for _ in filters.surfaces)})")
        params.extend(filters.surfaces)
    if filters.levels:
        clauses.append(f"e.level IN ({', '.join('?' for _ in filters.levels)})")
        params.extend(filters.levels)
    if filters.rounds:
        clauses.append(f"model.round IN ({', '.join('?' for _ in filters.rounds)})")
        params.extend(filters.rounds)
    if filters.from_season is not None:
        clauses.append("e.season >= ?")
        params.append(filters.from_season)
    if filters.to_season is not None:
        clauses.append("e.season <= ?")
        params.append(filters.to_season)
    clause = "".join(f"  AND {sql}\n" for sql in clauses)
    return clause, params


class DuckDbOpportunitySource:
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    @classmethod
    def open(cls, connection: duckdb.DuckDBPyConnection) -> "DuckDbOpportunitySource":
        return cls(connection)

    def events(self, request: BacktestRequest) -> Iterator[MatchEvent]:
        filter_clause, filter_params = _build_filters(request)
        fill_books = request.fill_preference
        query = _QUERY_TEMPLATE.format(
            fill_preference_case=_fill_preference_case(fill_books),
            fill_book_placeholders=", ".join("?" for _ in fill_books),
            filter_clause=filter_clause,
            round_case=_ROUND_CASE,
        )
        params = [*fill_books, *filter_params]
        frame = self._connection.execute(query, params).fetch_df()
        frame["match_date"] = frame["match_date"].dt.date
        frame["p1_elo_prob"] = elo_probability(frame["p1_elo_pre"], frame["p2_elo_pre"])
        frame["p1_surface_elo_prob"] = elo_probability(
            frame["p1_surface_elo_pre"], frame["p2_surface_elo_pre"]
        )
        for row in frame.itertuples(index=False):
            opportunity = MatchOpportunity(
                match_id=row.match_id,
                match_date=row.match_date,
                season=row.season,
                tour=row.tour,
                surface=row.surface,
                level=row.level,
                round=row.round,
                p1_price=row.p1_price,
                p2_price=row.p2_price,
                p1_consensus_price=row.p1_consensus_price,
                p2_consensus_price=row.p2_consensus_price,
                p1_consensus_prob=row.p1_consensus_prob,
                p1_elo_prob=row.p1_elo_prob,
                p1_surface_elo_prob=row.p1_surface_elo_prob,
            )
            yield MatchEvent(opportunity=opportunity, p1_won=row.p1_won)
