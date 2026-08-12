"""Pre-match Elo ratings computed chronologically over tennis.matches.

Elo is inherently sequential — a rating depends on every prior result — so this is a
single chronological pass in Python. For each match we snapshot both players' overall
and surface-specific rating *before* applying the outcome, so analytics.elo_pre carries
no lookahead. New players enter at 1500; K decays with a player's match count.
"""

import duckdb
import pandas as pd

from tennisdb.features.ordering import in_match_order

_BASE_RATING = 1500.0
_K_NUMERATOR = 250.0
_K_OFFSET = 5.0
_K_DECAY = 0.4

_MATCHES_QUERY = """
SELECT
  m.match_id,
  m.edition_id,
  m.winner_id,
  m.loser_id,
  e.surface,
  coalesce(m.match_date, e.start_date) AS order_date,
  m.round
FROM tennis.matches AS m
JOIN tennis.tournament_editions AS e USING (edition_id)
"""

_ORIENT_AND_INSERT = """
INSERT INTO analytics.elo_pre
SELECT
  ratings.match_id,
  CASE WHEN model.p1_won THEN ratings.w_elo_pre ELSE ratings.l_elo_pre END,
  CASE WHEN model.p1_won THEN ratings.l_elo_pre ELSE ratings.w_elo_pre END,
  CASE WHEN model.p1_won THEN ratings.w_surface_elo_pre ELSE ratings.l_surface_elo_pre END,
  CASE WHEN model.p1_won THEN ratings.l_surface_elo_pre ELSE ratings.w_surface_elo_pre END,
  ratings.surface
FROM _elo_ratings AS ratings
JOIN tennis.matches_model AS model USING (match_id)
"""


def _expected(rating: float, opponent_rating: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / 400.0))


def _k_factor(match_count: int) -> float:
    return _K_NUMERATOR / (match_count + _K_OFFSET) ** _K_DECAY


def compute_elo_pre(matches: pd.DataFrame) -> pd.DataFrame:
    """Pure core: winner/loser-oriented pre-match ratings. Depends only on the
    chronological sort, never on the input row order — the as-of guarantee."""
    ordered = in_match_order(matches)
    overall: dict[int, float] = {}
    surface: dict[tuple[str, int], float] = {}
    overall_played: dict[int, int] = {}
    surface_played: dict[tuple[str, int], int] = {}
    records = []
    for match in ordered.itertuples(index=False):
        winner, loser, court = match.winner_id, match.loser_id, match.surface
        w_overall = overall.get(winner, _BASE_RATING)
        l_overall = overall.get(loser, _BASE_RATING)
        w_surface = surface.get((court, winner), _BASE_RATING)
        l_surface = surface.get((court, loser), _BASE_RATING)
        records.append((match.match_id, w_overall, l_overall, w_surface, l_surface, court))
        _apply_result(overall, overall_played, winner, loser, w_overall, l_overall)
        _apply_result(
            surface, surface_played, (court, winner), (court, loser), w_surface, l_surface
        )
    return pd.DataFrame(
        records,
        columns=[
            "match_id", "w_elo_pre", "l_elo_pre",
            "w_surface_elo_pre", "l_surface_elo_pre", "surface",
        ],  # fmt: skip
    )


def _apply_result(ratings, played, winner_key, loser_key, winner_rating, loser_rating) -> None:
    winner_expected = _expected(winner_rating, loser_rating)
    ratings[winner_key] = winner_rating + _k_factor(played.get(winner_key, 0)) * (
        1.0 - winner_expected
    )
    ratings[loser_key] = loser_rating + _k_factor(played.get(loser_key, 0)) * (
        winner_expected - 1.0
    )
    played[winner_key] = played.get(winner_key, 0) + 1
    played[loser_key] = played.get(loser_key, 0) + 1


def read_matches(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return connection.execute(_MATCHES_QUERY).fetch_df()


def build_elo(connection: duckdb.DuckDBPyConnection) -> int:
    matches = read_matches(connection)
    ratings = compute_elo_pre(matches)
    connection.execute("DELETE FROM analytics.elo_pre")
    connection.register("_elo_ratings", ratings)
    try:
        return connection.execute(_ORIENT_AND_INSERT).fetchone()[0]
    finally:
        connection.unregister("_elo_ratings")
