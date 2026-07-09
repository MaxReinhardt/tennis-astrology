-- Odds attached to canonical matches, alias tables for entity resolution (M4),
-- and the ingest audit log. Common-subset SQL: a sequence instead of bigserial,
-- JSON instead of jsonb (DuckDB has no jsonb).
-- bookmaker is deliberately unconstrained: M4 publishes B365/PS/Max/Avg, but older
-- seasons carry extra books; the M5 quality suite validates the distribution.

CREATE TABLE IF NOT EXISTS tennis.odds (
  match_id     TEXT NOT NULL REFERENCES tennis.matches (match_id),
  bookmaker    TEXT NOT NULL,  -- 'B365', 'PS', 'Max', 'Avg'
  winner_odds  NUMERIC(7, 3) CHECK (winner_odds > 1.0 AND winner_odds < 1001),
  loser_odds   NUMERIC(7, 3) CHECK (loser_odds > 1.0 AND loser_odds < 1001),
  is_closing   BOOLEAN NOT NULL DEFAULT true,  -- tennis-data odds are (approx.) closing
  source       TEXT,
  source_row   TEXT,
  PRIMARY KEY (match_id, bookmaker)
);

CREATE TABLE IF NOT EXISTS tennis.player_aliases (
  alias      TEXT NOT NULL,
  tour       TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
  player_id  INTEGER NOT NULL REFERENCES tennis.players (player_id),
  PRIMARY KEY (alias, tour)
);

CREATE TABLE IF NOT EXISTS tennis.edition_aliases (
  alias       TEXT NOT NULL,
  season      INTEGER NOT NULL,
  tour        TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
  edition_id  TEXT NOT NULL REFERENCES tennis.tournament_editions (edition_id),
  PRIMARY KEY (alias, season, tour)
);

CREATE SEQUENCE IF NOT EXISTS tennis.ingest_log_id_seq;

CREATE TABLE IF NOT EXISTS tennis.ingest_log (
  id      BIGINT PRIMARY KEY DEFAULT nextval('tennis.ingest_log_id_seq'),
  run_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  step    TEXT NOT NULL,
  stats   JSON
);
