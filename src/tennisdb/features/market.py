"""Per-match market features from the closing novig odds, oriented to p1/p2.

The closing bookmaker is the aggregate `Avg` where present, else Pinnacle (`PS`). The
Max/Avg dispersion — the gap between the best-price and average-price novig probability —
is a book-disagreement / liquidity proxy. Only matches carrying the chosen book appear.
"""

import duckdb

_CLOSING_PREFERENCE = "CASE bookmaker WHEN 'Avg' THEN 0 WHEN 'PS' THEN 1 ELSE 2 END"

_BUILD = f"""
INSERT INTO analytics.market
WITH closing AS (
  SELECT
    match_id, bookmaker, p_winner_novig, p_loser_novig, overround,
    row_number() OVER (PARTITION BY match_id ORDER BY {_CLOSING_PREFERENCE}) AS preference
  FROM tennis.odds_implied
  WHERE bookmaker IN ('Avg', 'PS')
),
best_price AS (
  SELECT match_id, p_winner_novig AS max_winner_prob
  FROM tennis.odds_implied
  WHERE bookmaker = 'Max'
)
SELECT
  closing.match_id,
  closing.bookmaker,
  CASE WHEN model.p1_won THEN closing.p_winner_novig ELSE closing.p_loser_novig END,
  CASE WHEN model.p1_won THEN closing.p_loser_novig ELSE closing.p_winner_novig END,
  closing.overround,
  abs(best_price.max_winner_prob - closing.p_winner_novig)
FROM closing
JOIN tennis.matches_model AS model USING (match_id)
LEFT JOIN best_price USING (match_id)
WHERE closing.preference = 1
"""


def build_market(connection: duckdb.DuckDBPyConnection) -> int:
    connection.execute("DELETE FROM analytics.market")
    return connection.execute(_BUILD).fetchone()[0]
