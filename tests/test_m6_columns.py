"""M6: the feature COPY column lists must match the live analytics.* schema exactly,
or a publish would send values into the wrong columns. Runs against the real warehouse.
"""

import duckdb
import pytest

from tennisdb.config import DUCKDB_PATH
from tennisdb.load.publish import FEATURE_TABLES

pytestmark = pytest.mark.m6


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--all --features` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()


@pytest.mark.parametrize("table", FEATURE_TABLES, ids=lambda table: table.name)
def test_copy_columns_match_warehouse_schema(connection, table):
    actual = [
        name
        for (name,) in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [table.schema, table.name],
        ).fetchall()
    ]

    assert list(table.columns) == actual
