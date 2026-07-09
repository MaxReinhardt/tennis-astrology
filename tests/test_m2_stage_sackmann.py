"""M2: Sackmann raw CSVs → staging frames (synthetic fixtures)."""

from datetime import date

import pandas as pd
import pytest

from tennisdb.ingest.stage_sackmann import (
    MATCH_SOURCE_COLUMNS,
    PLAYER_SOURCE_COLUMNS,
    stage_matches,
    stage_players,
    stage_rankings,
)

pytestmark = pytest.mark.m2


def match_frame(rows):
    filled = [{column: row.get(column, "") for column in MATCH_SOURCE_COLUMNS} for row in rows]
    return pd.DataFrame(filled, columns=list(MATCH_SOURCE_COLUMNS))


def player_frame(rows):
    filled = [{column: row.get(column, "") for column in PLAYER_SOURCE_COLUMNS} for row in rows]
    return pd.DataFrame(filled, columns=list(PLAYER_SOURCE_COLUMNS))


def test_stage_matches_stamps_tour_and_source_file(manifest, record_file):
    record_file("sackmann/atp/atp_matches_2023.csv", match_frame([{"round": "F"}]))
    record_file("sackmann/wta/wta_matches_2023.csv", match_frame([{"round": "SF"}]))

    staged = stage_matches(manifest)

    assert list(staged.columns[:2]) == ["tour", "source_file"]
    assert sorted(staged["tour"]) == ["atp", "wta"]
    assert set(staged["source_file"]) == {
        "sackmann/atp/atp_matches_2023.csv",
        "sackmann/wta/wta_matches_2023.csv",
    }


def test_stage_matches_folds_surface_case_and_keeps_raw(manifest, record_file):
    record_file("sackmann/atp/atp_matches_2023.csv", match_frame([{"surface": "clay"}]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "surface"] == "Clay"
    assert staged.loc[0, "surface_raw"] == "clay"


def test_stage_matches_nulls_unmapped_round_and_keeps_raw(manifest, record_file):
    record_file("sackmann/atp/atp_matches_1974.csv", match_frame([{"round": "ER"}]))

    staged = stage_matches(manifest)

    assert pd.isna(staged.loc[0, "round"])
    assert staged.loc[0, "round_raw"] == "ER"


def test_stage_matches_parses_tourney_date(manifest, record_file):
    record_file("sackmann/atp/atp_matches_2023.csv", match_frame([{"tourney_date": "20230115"}]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "tourney_date"] == date(2023, 1, 15)


def test_stage_matches_coerces_numeric_columns(manifest, record_file):
    row = {"winner_rank": "3", "minutes": "", "winner_age": "22.3", "w_ace": "11"}
    record_file("sackmann/atp/atp_matches_2023.csv", match_frame([row]))

    staged = stage_matches(manifest)

    assert staged.loc[0, "winner_rank"] == 3
    assert pd.isna(staged.loc[0, "minutes"])
    assert staged.loc[0, "winner_age"] == 22.3
    assert staged.loc[0, "w_ace"] == 11


def test_stage_matches_ignores_players_and_rankings_files(manifest, record_file):
    record_file("sackmann/atp/atp_matches_2023.csv", match_frame([{"round": "F"}]))
    record_file("sackmann/atp/atp_players.csv", player_frame([{"player_id": "1"}]))

    staged = stage_matches(manifest)

    assert len(staged) == 1


def test_stage_matches_raises_when_listed_file_missing(manifest, record_file):
    file = record_file("sackmann/atp/atp_matches_2023.csv", match_frame([{"round": "F"}]))
    file.unlink()

    with pytest.raises(FileNotFoundError, match="atp_matches_2023.csv"):
        stage_matches(manifest)


def test_stage_players_parses_dob_and_keeps_raw(manifest, record_file):
    rows = [
        {"player_id": "100001", "dob": "19870822"},
        {"player_id": "100002", "dob": "19750000"},
    ]
    record_file("sackmann/atp/atp_players.csv", player_frame(rows))

    staged = stage_players(manifest)

    assert staged.loc[0, "dob"] == date(1987, 8, 22)
    assert pd.isna(staged.loc[1, "dob"])
    assert staged.loc[1, "dob_raw"] == "19750000"
    assert staged.loc[0, "player_id"] == 100001


def test_stage_rankings_unions_wta_only_tours_column(manifest, record_file):
    atp = pd.DataFrame(
        [{"ranking_date": "20230102", "rank": "1", "player": "104925", "points": "7070"}]
    )
    wta = pd.DataFrame(
        [
            {
                "ranking_date": "20230102",
                "rank": "1",
                "player": "201594",
                "points": "5000",
                "tours": "21",
            }
        ]
    )
    record_file("sackmann/atp/atp_rankings_20s.csv", atp)
    record_file("sackmann/wta/wta_rankings_20s.csv", wta)

    staged = stage_rankings(manifest)

    atp_row = staged[staged["tour"] == "atp"].iloc[0]
    wta_row = staged[staged["tour"] == "wta"].iloc[0]
    assert pd.isna(atp_row["tours"])
    assert wta_row["tours"] == 21
    assert atp_row["ranking_date"] == date(2023, 1, 2)
    assert atp_row["rank"] == 1
