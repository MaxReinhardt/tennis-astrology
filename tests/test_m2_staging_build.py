"""M2: orchestrator that builds every staging table from raw files + manifest."""

import duckdb
import pandas as pd
import pytest

from tennisdb.ingest.stage_sackmann import MATCH_SOURCE_COLUMNS, PLAYER_SOURCE_COLUMNS
from tennisdb.ingest.staging import STAGING_SCHEMA, build_staging
from tennisdb.warehouse import Warehouse

pytestmark = pytest.mark.m2

TENNISDATA_BASE_ROW = {
    "Location": "Melbourne",
    "Tournament": "Australian Open",
    "Date": pd.Timestamp("2023-01-16"),
    "Court": "Outdoor",
    "Surface": "Hard",
    "Round": "The Final",
    "Best of": 3,
    "Winner": "Djokovic N.",
    "Loser": "Federer R.",
    "WRank": 1,
    "LRank": 2,
}


@pytest.fixture
def warehouse():
    connection = duckdb.connect(":memory:")
    yield Warehouse(connection)
    connection.close()


def sackmann_match_frame(round_value: str) -> pd.DataFrame:
    row = {column: "" for column in MATCH_SOURCE_COLUMNS}
    row["round"] = round_value
    return pd.DataFrame([row], columns=list(MATCH_SOURCE_COLUMNS))


def sackmann_player_frame() -> pd.DataFrame:
    row = {column: "" for column in PLAYER_SOURCE_COLUMNS}
    row["player_id"] = "100001"
    return pd.DataFrame([row], columns=list(PLAYER_SOURCE_COLUMNS))


def sackmann_ranking_frame() -> pd.DataFrame:
    row = {"ranking_date": "20230102", "rank": "1", "player": "100001", "points": "100"}
    return pd.DataFrame([row])


def seed_minimal_raw_files(record_file, round_value="F"):
    record_file("sackmann/atp/atp_matches_2023.csv", sackmann_match_frame(round_value))
    record_file("sackmann/atp/atp_players.csv", sackmann_player_frame())
    record_file("sackmann/atp/atp_rankings_20s.csv", sackmann_ranking_frame())
    record_file("tennisdata/atp/2023.xlsx", pd.DataFrame([TENNISDATA_BASE_ROW]))


def test_build_staging_creates_all_four_tables_with_row_counts(manifest, record_file, warehouse):
    seed_minimal_raw_files(record_file)

    report = build_staging(manifest, warehouse)

    assert report.table_rows == {
        "sackmann_matches": 1,
        "sackmann_players": 1,
        "sackmann_rankings": 1,
        "tennisdata_matches": 1,
    }
    assert set(warehouse.table_names(STAGING_SCHEMA)) == set(report.table_rows)


def test_build_staging_is_idempotent(manifest, record_file, warehouse):
    seed_minimal_raw_files(record_file)

    first = build_staging(manifest, warehouse)
    second = build_staging(manifest, warehouse)

    assert first.table_rows == second.table_rows
    count = warehouse._connection.execute(
        "SELECT count(*) FROM staging.sackmann_matches"
    ).fetchone()[0]
    assert count == 1


def test_build_staging_reports_unmapped_rounds(manifest, record_file, warehouse):
    seed_minimal_raw_files(record_file, round_value="ER")

    report = build_staging(manifest, warehouse)

    assert any("ER" in message for message in report.warnings)


def test_build_staging_reports_no_warnings_when_everything_maps(manifest, record_file, warehouse):
    seed_minimal_raw_files(record_file, round_value="F")

    report = build_staging(manifest, warehouse)

    assert report.warnings == []
