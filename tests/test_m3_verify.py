"""M3 Verify: migrate.py is idempotent against the real warehouse and Supabase."""

import subprocess
import sys

import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import PostgresMigrationTarget

pytestmark = pytest.mark.m3

EXPECTED_TENNIS_OBJECT_COUNT = 12


def _run_migrate_cli(target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/migrate.py", "--target", target],
        cwd=config.PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_migrate_duckdb_second_run_reports_zero_changes():
    first = _run_migrate_cli("duckdb")
    assert first.returncode == 0, first.stderr

    second = _run_migrate_cli("duckdb")

    assert second.returncode == 0, second.stderr
    assert "duckdb: 0 changes" in second.stdout


def test_cli_migrate_supabase_without_credentials_explains_and_fails():
    if config.SUPABASE_DB_URL:
        pytest.skip("Supabase is configured — the unconfigured-path message cannot occur")

    result = _run_migrate_cli("supabase")

    assert result.returncode == 1
    assert "SUPABASE_DB_URL not set" in result.stdout


@pytest.mark.skipif(
    config.SUPABASE_DB_URL is None,
    reason="Supabase not configured — set SUPABASE_DB_URL in .env",
)
def test_supabase_migrations_idempotent_and_schema_complete():
    scripts = load_migration_scripts(config.MIGRATIONS_DIR)
    first_target = PostgresMigrationTarget.open()
    try:
        run_migrations(scripts, first_target)
    finally:
        first_target.close()

    second_target = PostgresMigrationTarget.open()
    try:
        report = run_migrations(scripts, second_target)
        object_count = second_target._connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tennis'"
        ).fetchone()[0]
    finally:
        second_target.close()

    assert report.applied == []
    assert object_count == EXPECTED_TENNIS_OBJECT_COUNT
