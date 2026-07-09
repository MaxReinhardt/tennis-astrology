"""M3: DuckDB migration target — ledger bootstrap, transactional apply, rollback."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.scripts import MigrationScript
from tennisdb.migrate.targets import (
    DuckDbMigrationTarget,
    PostgresMigrationTarget,
    SupabaseNotConfiguredError,
)

pytestmark = pytest.mark.m3


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def target(connection):
    return DuckDbMigrationTarget(connection)


def test_applied_checksums_on_fresh_database_bootstraps_ledger_and_returns_empty(
    target, connection
):
    assert target.applied_checksums() == {}
    ledger_rows = connection.execute("SELECT count(*) FROM tennis.schema_migrations").fetchone()
    assert ledger_rows == (0,)


def test_apply_executes_script_and_records_ledger_row(target, connection):
    target.applied_checksums()
    script = MigrationScript(
        name="001_example.sql",
        checksum="deadbeef",
        sql="CREATE TABLE tennis.example (id INTEGER PRIMARY KEY);",
    )

    target.apply(script)

    assert connection.execute("SELECT count(*) FROM tennis.example").fetchone() == (0,)
    assert target.applied_checksums() == {"001_example.sql": "deadbeef"}


def test_apply_failing_script_rolls_back_and_records_nothing(target, connection):
    target.applied_checksums()
    script = MigrationScript(
        name="001_broken.sql",
        checksum="deadbeef",
        sql="CREATE TABLE tennis.example (id INTEGER PRIMARY KEY); THIS IS NOT SQL;",
    )

    with pytest.raises(duckdb.Error):
        target.apply(script)

    tables = connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'tennis'"
    ).fetchall()
    assert ("example",) not in tables
    assert target.applied_checksums() == {}


def test_postgres_target_without_supabase_url_raises(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_DB_URL", None)

    with pytest.raises(SupabaseNotConfiguredError):
        PostgresMigrationTarget.open()
