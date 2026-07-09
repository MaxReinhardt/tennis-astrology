"""DuckDB connection factory and a thin write wrapper shared across milestones."""

import duckdb
import pandas as pd

from tennisdb import config


def connect() -> duckdb.DuckDBPyConnection:
    config.DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.DUCKDB_PATH))


class Warehouse:
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    def ensure_schema(self, name: str) -> None:
        self._connection.execute(f"CREATE SCHEMA IF NOT EXISTS {name}")

    def replace_table(self, qualified_name: str, frame: pd.DataFrame) -> None:
        self._connection.register("_staged_frame", frame)
        self._connection.execute(
            f"CREATE OR REPLACE TABLE {qualified_name} AS SELECT * FROM _staged_frame"
        )
        self._connection.unregister("_staged_frame")

    def table_names(self, schema: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?", [schema]
        ).fetchall()
        return [row[0] for row in rows]
