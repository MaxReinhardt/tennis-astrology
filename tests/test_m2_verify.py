"""M2 Verify block from PLAN.md — runs against the real DuckDB warehouse.

Requires `uv run python scripts/build_db.py --stage` to have populated it first.
"""

import duckdb
import pytest

from tennisdb.config import DUCKDB_PATH
from tennisdb.ingest.manifest import MANIFEST_PATH, Manifest
from tennisdb.ingest.stage_tennisdata import ODDS_COLUMNS

pytestmark = pytest.mark.m2

STAGING_TABLES = (
    "staging.sackmann_matches",
    "staging.sackmann_players",
    "staging.sackmann_rankings",
    "staging.tennisdata_matches",
)

ROUND_COVERAGE_FLOOR = 0.999

# Documented waiver: these two tennisdata rows are genuinely blank in the source
# spreadsheet (Guangzhou 2010 final, Cincinnati 2012 final) — not a parse failure.
EXPECTED_NULL_DATES = 2


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.fail(
            "data/raw/manifest.json missing — run `uv run python scripts/ingest_all.py` first"
        )
    return Manifest.load(MANIFEST_PATH)


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py --stage` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()


def test_staging_row_counts_match_manifest(connection, manifest):
    manifest_counts = {entry.path: entry.row_count for entry in manifest.entries()}
    mismatches = []
    for table in STAGING_TABLES:
        query = f"SELECT source_file, count(*) FROM {table} GROUP BY 1"
        for source_file, staged_count in connection.execute(query).fetchall():
            expected = manifest_counts.get(source_file)
            if expected != staged_count:
                mismatches.append((table, source_file, expected, staged_count))
    assert mismatches == []


def test_every_manifest_raw_file_is_represented_in_staging(connection, manifest):
    staged_files = set()
    for table in STAGING_TABLES:
        query = f"SELECT DISTINCT source_file FROM {table}"
        for (source_file,) in connection.execute(query).fetchall():
            staged_files.add(source_file)

    expected_files = {
        entry.path
        for entry in manifest.entries()
        if entry.path.startswith("sackmann/") or entry.path.startswith("tennisdata/")
    }
    assert expected_files - staged_files == set()


def test_tennisdata_winner_and_loser_are_always_present(connection):
    count = connection.execute(
        "SELECT count(*) FROM staging.tennisdata_matches WHERE Winner IS NULL OR Loser IS NULL"
    ).fetchone()[0]
    assert count == 0


def test_tennisdata_date_nulls_match_documented_waiver(connection):
    count = connection.execute(
        'SELECT count(*) FROM staging.tennisdata_matches WHERE "Date" IS NULL'
    ).fetchone()[0]
    assert count == EXPECTED_NULL_DATES


def test_tennisdata_odds_are_within_valid_range(connection):
    failures = {}
    for column in ODDS_COLUMNS:
        out_of_range = connection.execute(
            f'SELECT count(*) FROM staging.tennisdata_matches '
            f'WHERE "{column}" IS NOT NULL AND ("{column}" < 1.001 OR "{column}" >= 1001)'
        ).fetchone()[0]
        if out_of_range:
            failures[column] = out_of_range
    assert failures == {}


@pytest.mark.parametrize(
    "table, date_column",
    [("staging.sackmann_matches", "tourney_date"), ("staging.tennisdata_matches", '"Date"')],
)
def test_hard_is_the_most_common_surface_post_2000(connection, table, date_column):
    top_surface = connection.execute(
        f"SELECT surface FROM {table} "
        f"WHERE {date_column} >= DATE '2001-01-01' AND surface IS NOT NULL "
        f"GROUP BY surface ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()[0]
    assert top_surface == "Hard"


@pytest.mark.parametrize("table", ["staging.sackmann_matches", "staging.tennisdata_matches"])
def test_round_canonical_coverage_meets_floor(connection, table):
    total = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    mapped_query = f"SELECT count(*) FROM {table} WHERE round IS NOT NULL"
    mapped = connection.execute(mapped_query).fetchone()[0]
    coverage = mapped / total
    if coverage < ROUND_COVERAGE_FLOOR:
        unmapped = connection.execute(
            f"SELECT round_raw, count(*) FROM {table} WHERE round IS NULL "
            f"GROUP BY round_raw ORDER BY 2 DESC"
        ).fetchall()
        pytest.fail(f"{table} round coverage {coverage:.4f} < {ROUND_COVERAGE_FLOOR}: {unmapped}")
