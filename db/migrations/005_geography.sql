-- Tournament host geography (M8 S4): which country hosts each edition, derived from
-- the M4 edition_aliases host-city token (the "<tournament> @ <city>" alias format).
-- Written in the DuckDB/Postgres common SQL subset and applied to both targets by
-- scripts/migrate.py; tracked in tennis.schema_migrations — never edit after it has
-- been applied, add a new numbered migration instead.
-- Derived (rebuildable by `build_db.py --features`) and deliberately carries no foreign
-- keys, matching the other analytics.* tables in 004_features.sql.

CREATE TABLE IF NOT EXISTS analytics.edition_geo (
  edition_id        TEXT PRIMARY KEY,
  host_city         TEXT NOT NULL,
  host_country_ioc  TEXT
);
