"""M2: tennis-data.co.uk season files → one wide staging frame (synthetic fixtures)."""

from datetime import date

import pandas as pd
import pytest

from tennisdb.ingest.stage_tennisdata import (
    ODDS_COLUMNS,
    TENNISDATA_COLUMNS,
    read_season_file,
    stage_matches,
)

pytestmark = pytest.mark.m2

BASE_ROW = {
    "Location": "Melbourne",
    "Tournament": "Australian Open",
    "Date": pd.Timestamp("2023-01-16"),
    "Court": "Outdoor",
    "Surface": "Hard",
    "Round": "1st Round",
    "Best of": 3,
    "Winner": "Djokovic N.",
    "Loser": "Federer R.",
    "WRank": 1,
    "LRank": 2,
}


def season_frame(rows):
    return pd.DataFrame([{**BASE_ROW, **row} for row in rows])


def test_stage_matches_unions_columns_in_declared_order(manifest, record_file):
    atp = season_frame([{"ATP": 1, "Series": "Grand Slam", "CBW": 1.5, "CBL": 2.5}])
    wta = season_frame([{"WTA": 1, "Tier": "Tier I", "MaxW": 1.8, "MaxL": 2.0}])
    record_file("tennisdata/atp/2005.xlsx", atp)
    record_file("tennisdata/wta/2007.xlsx", wta)

    staged = stage_matches(manifest)

    assert list(staged.columns) == list(TENNISDATA_COLUMNS)
    atp_row = staged[staged["tour"] == "atp"].iloc[0]
    wta_row = staged[staged["tour"] == "wta"].iloc[0]
    assert pd.isna(atp_row["Tier"]) and atp_row["Series"] == "Grand Slam"
    assert pd.isna(wta_row["CBW"]) and wta_row["MaxW"] == 1.8
    assert atp_row["season"] == 2005
    assert wta_row["source_file"] == "tennisdata/wta/2007.xlsx"


def test_stage_matches_source_row_points_at_spreadsheet_rows(manifest, record_file):
    record_file("tennisdata/atp/2010.xlsx", season_frame([{}, {}, {}]))
    record_file("tennisdata/wta/2010.xlsx", season_frame([{}]))

    staged = stage_matches(manifest)

    atp_rows = staged[staged["tour"] == "atp"]["source_row"]
    assert list(atp_rows) == [2, 3, 4]
    assert list(staged[staged["tour"] == "wta"]["source_row"]) == [2]


def test_stage_matches_infers_numbered_rounds_from_event_depth(manifest, record_file):
    slam = [
        {"Round": "1st Round"},
        {"Round": "2nd Round"},
        {"Round": "3rd Round"},
        {"Round": "4th Round"},
        {"Round": "Quarterfinals"},
    ]
    small_draw = [
        {"Tournament": "Forest Hills", "Round": "1st Round"},
        {"Tournament": "Forest Hills", "Round": "Quarterfinals"},
    ]
    record_file("tennisdata/atp/2019.xlsx", season_frame(slam + small_draw))

    staged = stage_matches(manifest)

    slam_rounds = staged[staged["Tournament"] == "Australian Open"]
    assert list(slam_rounds["round"]) == ["R128", "R64", "R32", "R16", "QF"]
    small_rounds = staged[staged["Tournament"] == "Forest Hills"]
    assert list(small_rounds["round"]) == ["R16", "QF"]
    assert list(small_rounds["round_raw"]) == ["1st Round", "Quarterfinals"]


def test_stage_matches_maps_fixed_round_labels(manifest, record_file):
    rows = [{"Round": "The Final"}, {"Round": "Third Place"}, {"Round": "Round Robin"}]
    record_file("tennisdata/atp/2019.xlsx", season_frame(rows))

    staged = stage_matches(manifest)

    assert list(staged["round"]) == ["F", "BR", "RR"]


def test_stage_matches_normalizes_every_odds_column(manifest, record_file):
    row = {"B365W": "2,25", "B365L": 1.5, "CBW": 0.5, "MaxL": 42136.0, "PSW": 3.75}
    record_file("tennisdata/atp/2015.xlsx", season_frame([row]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "B365W"] == 2.25
    assert staged.loc[0, "B365L"] == 1.5
    assert pd.isna(staged.loc[0, "CBW"])
    assert pd.isna(staged.loc[0, "MaxL"])
    assert staged.loc[0, "PSW"] == 3.75
    assert set(ODDS_COLUMNS) < set(staged.columns)


def test_stage_matches_coerces_rank_garbage_to_null(manifest, record_file):
    record_file("tennisdata/atp/2004.xlsx", season_frame([{"LRank": "NR", "W1": "\t"}]))

    staged = stage_matches(manifest)

    assert pd.isna(staged.loc[0, "LRank"])
    assert pd.isna(staged.loc[0, "W1"])
    assert staged.loc[0, "WRank"] == 1


def test_stage_matches_keeps_fractional_ranking_points(manifest, record_file):
    record_file("tennisdata/wta/2007.xlsx", season_frame([{"WPts": 332.25, "LPts": 90.5}]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "WPts"] == 332.25
    assert staged.loc[0, "LPts"] == 90.5


def test_stage_matches_types_excel_date_as_date(manifest, record_file):
    record_file("tennisdata/atp/2023.xlsx", season_frame([{}]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "Date"] == date(2023, 1, 16)


def test_stage_matches_parses_csv_season_with_dayfirst_dates(manifest, record_file):
    frame = season_frame([{}])
    frame["Date"] = "16/01/2004"
    record_file("tennisdata/atp/2004.csv", frame)

    staged = stage_matches(manifest)

    assert staged.loc[0, "Date"] == date(2004, 1, 16)


def test_stage_matches_keeps_surface_and_comment_verbatim(manifest, record_file):
    record_file(
        "tennisdata/atp/2011.xlsx",
        season_frame([{"Surface": "Greenset", "Comment": "Walkoer"}]),
    )

    staged = stage_matches(manifest)

    assert staged.loc[0, "surface"] == "Hard"
    assert staged.loc[0, "surface_raw"] == "Greenset"
    assert staged.loc[0, "Comment"] == "Walkoer"


def test_read_season_file_rejects_unknown_format(tmp_path):
    file = tmp_path / "2010.parquet"
    file.touch()

    with pytest.raises(ValueError, match="2010.parquet"):
        read_season_file(file)


def test_stage_matches_raises_when_listed_file_missing(manifest, record_file):
    file = record_file("tennisdata/atp/2015.xlsx", season_frame([{}]))
    file.unlink()

    with pytest.raises(FileNotFoundError, match="2015.xlsx"):
        stage_matches(manifest)
