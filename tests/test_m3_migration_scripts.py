"""M3: loading migration SQL files into ordered, checksummed value objects."""

import hashlib

import pytest

from tennisdb.migrate.scripts import load_migration_scripts

pytestmark = pytest.mark.m3


def test_load_migration_scripts_sorts_by_filename(tmp_path):
    (tmp_path / "002_odds.sql").write_text("CREATE TABLE two (id INT);")
    (tmp_path / "001_core.sql").write_text("CREATE TABLE one (id INT);")
    (tmp_path / "003_views.sql").write_text("CREATE VIEW three AS SELECT 1;")

    scripts = load_migration_scripts(tmp_path)

    assert [script.name for script in scripts] == [
        "001_core.sql",
        "002_odds.sql",
        "003_views.sql",
    ]


def test_load_migration_scripts_checksum_is_sha256_of_file_bytes(tmp_path):
    sql = "CREATE TABLE example (id INT);"
    (tmp_path / "001_core.sql").write_text(sql)

    scripts = load_migration_scripts(tmp_path)

    assert scripts[0].checksum == hashlib.sha256(sql.encode()).hexdigest()
    assert scripts[0].sql == sql


def test_load_migration_scripts_ignores_non_sql_files(tmp_path):
    (tmp_path / "001_core.sql").write_text("CREATE TABLE one (id INT);")
    (tmp_path / "README.md").write_text("not a migration")
    (tmp_path / "notes.txt").write_text("also not a migration")

    scripts = load_migration_scripts(tmp_path)

    assert [script.name for script in scripts] == ["001_core.sql"]


def test_load_migration_scripts_empty_directory_returns_empty_list(tmp_path):
    assert load_migration_scripts(tmp_path) == []


def test_load_migration_scripts_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_migration_scripts(tmp_path / "does_not_exist")
