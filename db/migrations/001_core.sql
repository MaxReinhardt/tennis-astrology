-- Canonical tennis schema: players, tournament editions, matches, stats, rankings.
-- Written in the DuckDB/Postgres common SQL subset and applied to both targets by
-- scripts/migrate.py; tracked in tennis.schema_migrations — never edit after it
-- has been applied, add a new numbered migration instead.
-- Tables carry foreign keys: loaders must INSERT in dependency order
-- (players/tournament_editions -> matches -> match_stats/rankings/odds).

CREATE SCHEMA IF NOT EXISTS tennis;

CREATE TABLE IF NOT EXISTS tennis.players (
  player_id    INTEGER PRIMARY KEY,  -- Sackmann ID; WTA ids offset by +10,000,000
  tour         TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
  full_name    TEXT NOT NULL,
  hand         TEXT CHECK (hand IN ('R', 'L', 'U', 'A')),
  dob          DATE,
  country_ioc  TEXT,
  height_cm    INTEGER CHECK (height_cm BETWEEN 120 AND 230),
  wikidata_id  TEXT
);

CREATE TABLE IF NOT EXISTS tennis.tournament_editions (
  edition_id  TEXT PRIMARY KEY,  -- Sackmann tourney_id, e.g. '2019-540'
  tour        TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
  name        TEXT NOT NULL,
  surface     TEXT CHECK (surface IN ('Hard', 'Clay', 'Grass', 'Carpet')),
  level       TEXT,
  draw_size   INTEGER CHECK (draw_size > 1),
  start_date  DATE,
  season      INTEGER CHECK (season BETWEEN 1968 AND 2100)
);

CREATE TABLE IF NOT EXISTS tennis.matches (
  match_id            TEXT PRIMARY KEY,  -- '<edition_id>-<match_num>'
  edition_id          TEXT NOT NULL REFERENCES tennis.tournament_editions (edition_id),
  round               TEXT NOT NULL CHECK (round IN
    ('F', 'SF', 'QF', 'R16', 'R32', 'R64', 'R128', 'RR', 'Q1', 'Q2', 'Q3', 'BR')),
  best_of             INTEGER CHECK (best_of IN (3, 5)),
  match_date          DATE,
  winner_id           INTEGER NOT NULL REFERENCES tennis.players (player_id),
  loser_id            INTEGER NOT NULL REFERENCES tennis.players (player_id),
  score               TEXT,
  retirement          BOOLEAN NOT NULL DEFAULT false,
  walkover            BOOLEAN NOT NULL DEFAULT false,
  minutes             INTEGER CHECK (minutes > 0),
  winner_rank         INTEGER CHECK (winner_rank > 0),
  winner_rank_points  INTEGER CHECK (winner_rank_points >= 0),
  loser_rank          INTEGER CHECK (loser_rank > 0),
  loser_rank_points   INTEGER CHECK (loser_rank_points >= 0),
  CHECK (winner_id <> loser_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_edition ON tennis.matches (edition_id);
CREATE INDEX IF NOT EXISTS idx_matches_date ON tennis.matches (match_date);

CREATE TABLE IF NOT EXISTS tennis.match_stats (
  match_id   TEXT PRIMARY KEY REFERENCES tennis.matches (match_id),
  w_ace      INTEGER,
  w_df       INTEGER,
  w_svpt     INTEGER,
  w_1stin    INTEGER,
  w_1stwon   INTEGER,
  w_2ndwon   INTEGER,
  w_svgms    INTEGER,
  w_bpsaved  INTEGER,
  w_bpfaced  INTEGER,
  l_ace      INTEGER,
  l_df       INTEGER,
  l_svpt     INTEGER,
  l_1stin    INTEGER,
  l_1stwon   INTEGER,
  l_2ndwon   INTEGER,
  l_svgms    INTEGER,
  l_bpsaved  INTEGER,
  l_bpfaced  INTEGER
);

CREATE TABLE IF NOT EXISTS tennis.rankings (
  ranking_date  DATE NOT NULL,
  tour          TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
  player_id     INTEGER NOT NULL REFERENCES tennis.players (player_id),
  rank          INTEGER NOT NULL CHECK (rank > 0),
  points        INTEGER CHECK (points >= 0),
  PRIMARY KEY (ranking_date, player_id)
);

CREATE INDEX IF NOT EXISTS idx_rankings_player ON tennis.rankings (player_id);
