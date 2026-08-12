"""M5: the COPY column lists must match the live tennis.* schema exactly, else a
publish would send values into the wrong columns. Runs against the real warehouse.
"""

import duckdb
import pytest

from tennisdb.config import DUCKDB_PATH
from tennisdb.load.publish import ALL_TABLES

pytestmark = pytest.mark.m5


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--stage --load --resolve` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda table: table.name)
def test_copy_columns_match_warehouse_schema(connection, table):
    actual = [
        name
        for (name,) in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'tennis' AND table_name = ? ORDER BY ordinal_position",
            [table.name],
        ).fetchall()
    ]

    assert list(table.columns) == actual
