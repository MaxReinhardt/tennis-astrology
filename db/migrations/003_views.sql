-- matches_model: leak-free modeling view with deterministic pseudo-random p1/p2.
-- Winner is p1 iff the first hex digit of md5(match_id) is 0-7, so DuckDB,
-- Postgres, and Python hashlib all agree on the assignment.

CREATE OR REPLACE VIEW tennis.matches_model AS
WITH assigned AS (
  SELECT
    matches.*,
    substr(md5(matches.match_id), 1, 1)
      IN ('0', '1', '2', '3', '4', '5', '6', '7') AS winner_is_p1
  FROM tennis.matches AS matches
)
SELECT
  match_id,
  edition_id,
  round,
  best_of,
  match_date,
  CASE WHEN winner_is_p1 THEN winner_id ELSE loser_id END AS p1_id,
  CASE WHEN winner_is_p1 THEN loser_id ELSE winner_id END AS p2_id,
  winner_is_p1 AS p1_won,
  CASE WHEN winner_is_p1 THEN winner_rank ELSE loser_rank END AS p1_rank,
  CASE WHEN winner_is_p1 THEN loser_rank ELSE winner_rank END AS p2_rank,
  CASE WHEN winner_is_p1 THEN winner_rank_points ELSE loser_rank_points END AS p1_rank_points,
  CASE WHEN winner_is_p1 THEN loser_rank_points ELSE winner_rank_points END AS p2_rank_points,
  score,
  retirement,
  walkover,
  minutes
FROM assigned;

-- odds_implied: implied probabilities with proportional vig removal per bookmaker.

CREATE OR REPLACE VIEW tennis.odds_implied AS
SELECT
  match_id,
  bookmaker,
  is_closing,
  winner_odds,
  loser_odds,
  1.0 / winner_odds::float8 AS raw_winner_prob,
  1.0 / loser_odds::float8 AS raw_loser_prob,
  (1.0 / winner_odds::float8)
    / (1.0 / winner_odds::float8 + 1.0 / loser_odds::float8) AS p_winner_novig,
  (1.0 / loser_odds::float8)
    / (1.0 / winner_odds::float8 + 1.0 / loser_odds::float8) AS p_loser_novig,
  (1.0 / winner_odds::float8 + 1.0 / loser_odds::float8) - 1.0 AS overround
FROM tennis.odds
WHERE winner_odds IS NOT NULL AND loser_odds IS NOT NULL;
