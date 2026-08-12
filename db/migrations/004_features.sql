-- Feature layer (M6): pre-match ratings, form, market, and player-astro tables.
-- Written in the DuckDB/Postgres common SQL subset and applied to both targets by
-- scripts/migrate.py; tracked in tennis.schema_migrations — never edit after it has
-- been applied, add a new numbered migration instead.
-- These tables are derived (rebuildable by `build_db.py --features`) and deliberately
-- carry no foreign keys: the builders DELETE + INSERT wholesale, and publish truncates
-- them independently of the tennis.* foreign-key ordering.

CREATE SCHEMA IF NOT EXISTS analytics;

-- Pre-match Elo: both players' overall and surface-specific rating *before* each match,
-- oriented to the leak-free p1/p2 of tennis.matches_model.
CREATE TABLE IF NOT EXISTS analytics.elo_pre (
  match_id            TEXT PRIMARY KEY,
  p1_elo_pre          DOUBLE PRECISION NOT NULL,
  p2_elo_pre          DOUBLE PRECISION NOT NULL,
  p1_surface_elo_pre  DOUBLE PRECISION NOT NULL,
  p2_surface_elo_pre  DOUBLE PRECISION NOT NULL,
  surface             TEXT
);

-- Rolling pre-match form, oriented to p1/p2. NULLs where a player has no prior history.
CREATE TABLE IF NOT EXISTS analytics.form (
  match_id        TEXT PRIMARY KEY,
  p1_win_pct_10   DOUBLE PRECISION,
  p1_win_pct_25   DOUBLE PRECISION,
  p2_win_pct_10   DOUBLE PRECISION,
  p2_win_pct_25   DOUBLE PRECISION,
  p1_rest_days    INTEGER,
  p2_rest_days    INTEGER,
  p1_matches_14d  INTEGER,
  p2_matches_14d  INTEGER,
  h2h_p1_wins     INTEGER,
  h2h_total       INTEGER,
  p1_age_years    DOUBLE PRECISION,
  p2_age_years    DOUBLE PRECISION
);

-- Market features from the closing novig odds, oriented to p1/p2. Only matches that
-- carry the chosen bookmaker appear here.
CREATE TABLE IF NOT EXISTS analytics.market (
  match_id            TEXT PRIMARY KEY,
  bookmaker           TEXT NOT NULL,
  p1_market_prob      DOUBLE PRECISION NOT NULL,
  p2_market_prob      DOUBLE PRECISION NOT NULL,
  overround           DOUBLE PRECISION,
  max_avg_dispersion  DOUBLE PRECISION
);

-- Static zodiac features per player (the M8 null-hypothesis demonstrator).
CREATE TABLE IF NOT EXISTS analytics.player_astro (
  player_id    INTEGER PRIMARY KEY,
  zodiac_sign  TEXT,
  element      TEXT,
  birth_month  INTEGER
);
