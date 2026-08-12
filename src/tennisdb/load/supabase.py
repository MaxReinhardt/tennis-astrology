"""Concrete DuckDB -> Supabase adapters for the publish use case.

The sink runs the whole publish in one psycopg transaction (autocommit off): the
caller commits on success and rolls back on any failure, so a partial COPY never
reaches the served schema. COPY streams straight from the DuckDB cursor in batches,
so a 360k-row table never fully materialises in memory.
"""

from collections.abc import Iterable, Iterator, Sequence

import duckdb
import psycopg
from psycopg.types.json import Json

from tennisdb import config, warehouse

_FETCH_BATCH = 10_000


class SupabaseNotConfiguredError(RuntimeError):
    pass


class DuckDbCanonicalSource:
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    @classmethod
    def open(cls) -> "DuckDbCanonicalSource":
        return cls(warehouse.connect())

    def count(self, table: str) -> int:
        return self._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def rows(self, table: str, columns: Sequence[str]) -> Iterator[tuple]:
        projection = ", ".join(columns)
        cursor = self._connection.execute(f"SELECT {projection} FROM {table}")
        while True:
            batch = cursor.fetchmany(_FETCH_BATCH)
            if not batch:
                return
            yield from batch

    def close(self) -> None:
        self._connection.close()


class SupabasePublishSink:
    name = "supabase"

    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    @classmethod
    def open(cls) -> "SupabasePublishSink":
        if not config.SUPABASE_DB_URL:
            raise SupabaseNotConfiguredError(
                "SUPABASE_DB_URL is not set — create a Supabase project and copy "
                ".env.example to .env with its direct connection string (port 5432)"
            )
        return cls(psycopg.connect(config.SUPABASE_DB_URL))

    def truncate(self, tables: Sequence[str]) -> None:
        self._connection.execute(f"TRUNCATE {', '.join(tables)}")

    def copy(self, table: str, columns: Sequence[str], rows: Iterable[tuple]) -> int:
        statement = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
        copied = 0
        with self._connection.cursor() as cursor, cursor.copy(statement) as copy:
            for row in rows:
                copy.write_row(row)
                copied += 1
        return copied

    def count(self, table: str) -> int:
        return self._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def record_log(self, step: str, stats: dict) -> None:
        self._connection.execute(
            "INSERT INTO tennis.ingest_log (step, stats) VALUES (%s, %s)",
            (step, Json(stats)),
        )

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()
