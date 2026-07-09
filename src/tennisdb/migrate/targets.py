"""Strategy targets implementing runner.MigrationTarget per database engine.

Each target encapsulates one engine's transaction and placeholder semantics so the
runner stays engine-agnostic. Scripts must not bind parameters: both DuckDB and
psycopg reject multi-statement execute with parameters, so the ledger INSERT is
issued as its own statement inside the same transaction.
"""

import duckdb
import psycopg

from tennisdb import config, warehouse
from tennisdb.migrate.scripts import MigrationScript

_ENSURE_LEDGER = """
CREATE SCHEMA IF NOT EXISTS tennis;
CREATE TABLE IF NOT EXISTS tennis.schema_migrations (
  filename    TEXT PRIMARY KEY,
  checksum    TEXT NOT NULL,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
_SELECT_APPLIED = "SELECT filename, checksum FROM tennis.schema_migrations"
_RECORD_APPLIED = "INSERT INTO tennis.schema_migrations (filename, checksum) VALUES ({}, {})"


class SupabaseNotConfiguredError(RuntimeError):
    pass


class DuckDbMigrationTarget:
    name = "duckdb"

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    @classmethod
    def open(cls) -> "DuckDbMigrationTarget":
        return cls(warehouse.connect())

    def applied_checksums(self) -> dict[str, str]:
        self._connection.execute(_ENSURE_LEDGER)
        rows = self._connection.execute(_SELECT_APPLIED).fetchall()
        return dict(rows)

    def apply(self, script: MigrationScript) -> None:
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._connection.execute(script.sql)
            self._connection.execute(
                _RECORD_APPLIED.format("?", "?"), [script.name, script.checksum]
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._connection.close()


class PostgresMigrationTarget:
    name = "supabase"

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    @classmethod
    def open(cls) -> "PostgresMigrationTarget":
        if not config.SUPABASE_DB_URL:
            raise SupabaseNotConfiguredError(
                "SUPABASE_DB_URL is not set — create a Supabase project and copy "
                ".env.example to .env with its direct connection string (port 5432)"
            )
        return cls(psycopg.connect(config.SUPABASE_DB_URL))

    def applied_checksums(self) -> dict[str, str]:
        with self._connection.transaction():
            self._connection.execute(_ENSURE_LEDGER)
            rows = self._connection.execute(_SELECT_APPLIED).fetchall()
        return dict(rows)

    def apply(self, script: MigrationScript) -> None:
        with self._connection.transaction():
            self._connection.execute(script.sql)
            self._connection.execute(
                _RECORD_APPLIED.format("%s", "%s"), (script.name, script.checksum)
            )

    def close(self) -> None:
        self._connection.close()
