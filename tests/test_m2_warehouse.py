"""M2: DuckDB connection helper and thin write wrapper."""

import duckdb
import pandas as pd
import pytest

from tennisdb import config
from tennisdb.warehouse import Warehouse, connect

pytestmark = pytest.mark.m2


@pytest.fixture
def warehouse():
    connection = duckdb.connect(":memory:")
    yield Warehouse(connection)
    connection.close()


def test_connect_creates_parent_directory_and_opens_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DUCKDB_PATH", tmp_path / "nested" / "warehouse.duckdb")

    connection = connect()

    assert (tmp_path / "nested" / "warehouse.duckdb").exists()
    connection.close()


def test_ensure_schema_is_idempotent(warehouse):
    warehouse.ensure_schema("staging")
    warehouse.ensure_schema("staging")

    assert "staging" in _schema_names(warehouse)


def test_replace_table_writes_frame_contents(warehouse):
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    warehouse.ensure_schema("staging")

    warehouse.replace_table("staging.example", frame)

    rows = warehouse._connection.execute("SELECT a, b FROM staging.example ORDER BY a").fetchall()
    assert rows == [(1, "x"), (2, "y")]


def test_replace_table_overwrites_previous_contents(warehouse):
    warehouse.ensure_schema("staging")
    warehouse.replace_table("staging.example", pd.DataFrame({"a": [1, 2, 3]}))

    warehouse.replace_table("staging.example", pd.DataFrame({"a": [9]}))

    count = warehouse._connection.execute("SELECT count(*) FROM staging.example").fetchone()[0]
    assert count == 1


def test_table_names_lists_tables_in_schema(warehouse):
    warehouse.ensure_schema("staging")
    warehouse.replace_table("staging.one", pd.DataFrame({"a": [1]}))
    warehouse.replace_table("staging.two", pd.DataFrame({"a": [1]}))

    assert set(warehouse.table_names("staging")) == {"one", "two"}


def _schema_names(warehouse):
    rows = warehouse._connection.execute(
        "SELECT schema_name FROM information_schema.schemata"
    ).fetchall()
    return {row[0] for row in rows}
