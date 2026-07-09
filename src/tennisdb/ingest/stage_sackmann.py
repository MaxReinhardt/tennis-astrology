"""Sackmann raw CSVs → staging DataFrames with lossless typing and canonical surface/round."""

import re

import pandas as pd

from tennisdb.ingest.manifest import Manifest, ManifestEntry
from tennisdb.ingest.normalize import (
    normalize_sackmann_round,
    normalize_series,
    normalize_surface,
    parse_yyyymmdd,
)

MATCH_SOURCE_COLUMNS = (
    "tourney_id",
    "tourney_name",
    "surface",
    "draw_size",
    "tourney_level",
    "tourney_date",
    "match_num",
    "winner_id",
    "winner_seed",
    "winner_entry",
    "winner_name",
    "winner_hand",
    "winner_ht",
    "winner_ioc",
    "winner_age",
    "loser_id",
    "loser_seed",
    "loser_entry",
    "loser_name",
    "loser_hand",
    "loser_ht",
    "loser_ioc",
    "loser_age",
    "score",
    "best_of",
    "round",
    "minutes",
    "w_ace",
    "w_df",
    "w_svpt",
    "w_1stIn",
    "w_1stWon",
    "w_2ndWon",
    "w_SvGms",
    "w_bpSaved",
    "w_bpFaced",
    "l_ace",
    "l_df",
    "l_svpt",
    "l_1stIn",
    "l_1stWon",
    "l_2ndWon",
    "l_SvGms",
    "l_bpSaved",
    "l_bpFaced",
    "winner_rank",
    "winner_rank_points",
    "loser_rank",
    "loser_rank_points",
)

PLAYER_SOURCE_COLUMNS = (
    "player_id",
    "name_first",
    "name_last",
    "hand",
    "dob",
    "ioc",
    "height",
    "wikidata_id",
)

RANKING_SOURCE_COLUMNS = ("ranking_date", "rank", "player", "points", "tours")

MATCH_INTEGER_COLUMNS = (
    "draw_size",
    "match_num",
    "winner_id",
    "winner_seed",
    "winner_ht",
    "loser_id",
    "loser_seed",
    "loser_ht",
    "best_of",
    "minutes",
    "w_ace",
    "w_df",
    "w_svpt",
    "w_1stIn",
    "w_1stWon",
    "w_2ndWon",
    "w_SvGms",
    "w_bpSaved",
    "w_bpFaced",
    "l_ace",
    "l_df",
    "l_svpt",
    "l_1stIn",
    "l_1stWon",
    "l_2ndWon",
    "l_SvGms",
    "l_bpSaved",
    "l_bpFaced",
    "winner_rank",
    "winner_rank_points",
    "loser_rank",
    "loser_rank_points",
)

MATCH_DOUBLE_COLUMNS = ("winner_age", "loser_age")

_MATCHES_FILE = re.compile(r"^sackmann/(atp|wta)/\1_matches_\d{4}\.csv$")
_PLAYERS_FILE = re.compile(r"^sackmann/(atp|wta)/\1_players\.csv$")
_RANKINGS_FILE = re.compile(r"^sackmann/(atp|wta)/\1_rankings_\w+\.csv$")


def stage_matches(manifest: Manifest) -> pd.DataFrame:
    combined = _read_all(manifest, _MATCHES_FILE)
    combined = _split_raw_and_canonical(combined)
    combined["tourney_date"] = normalize_series(combined["tourney_date"], parse_yyyymmdd)
    _coerce_integers(combined, MATCH_INTEGER_COLUMNS)
    _coerce_doubles(combined, MATCH_DOUBLE_COLUMNS)
    return combined[_with_raw_pairs(MATCH_SOURCE_COLUMNS, {"surface", "round"})]


def stage_players(manifest: Manifest) -> pd.DataFrame:
    combined = _read_all(manifest, _PLAYERS_FILE)
    combined["dob_raw"] = combined["dob"]
    combined["dob"] = normalize_series(combined["dob_raw"], parse_yyyymmdd)
    _coerce_integers(combined, ("player_id", "height"))
    return combined[_with_raw_pairs(PLAYER_SOURCE_COLUMNS, {"dob"})]


def stage_rankings(manifest: Manifest) -> pd.DataFrame:
    combined = _read_all(manifest, _RANKINGS_FILE)
    combined["ranking_date"] = normalize_series(combined["ranking_date"], parse_yyyymmdd)
    _coerce_integers(combined, ("rank", "player", "points", "tours"))
    return combined[["tour", "source_file", *RANKING_SOURCE_COLUMNS]]


def _read_all(manifest: Manifest, file_pattern: re.Pattern) -> pd.DataFrame:
    matching = (
        entry for entry in manifest.find_with_prefix("sackmann/") if file_pattern.match(entry.path)
    )
    entries = sorted(matching, key=lambda entry: entry.path)
    frames = [_read_file(manifest, entry) for entry in entries]
    return pd.concat(frames, ignore_index=True)


def _read_file(manifest: Manifest, entry: ManifestEntry) -> pd.DataFrame:
    file = manifest.raw_dir / entry.path
    if not file.exists():
        raise FileNotFoundError(
            f"manifest lists {entry.path} but the file is missing — re-run scripts/ingest_all.py"
        )
    frame = pd.read_csv(file, dtype=str)
    frame.insert(0, "tour", entry.path.split("/")[1])
    frame.insert(1, "source_file", entry.path)
    return frame


def _split_raw_and_canonical(combined: pd.DataFrame) -> pd.DataFrame:
    combined["surface_raw"] = combined["surface"]
    combined["surface"] = normalize_series(combined["surface_raw"], normalize_surface)
    combined["round_raw"] = combined["round"]
    combined["round"] = normalize_series(combined["round_raw"], normalize_sackmann_round)
    return combined


def _coerce_integers(combined: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        if column in combined.columns:
            combined[column] = pd.to_numeric(combined[column], errors="coerce").astype("Int64")
        else:
            combined[column] = pd.array([None] * len(combined), dtype="Int64")


def _coerce_doubles(combined: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        combined[column] = pd.to_numeric(combined[column], errors="coerce")


def _with_raw_pairs(source_columns: tuple[str, ...], paired: set[str]) -> list[str]:
    ordered = ["tour", "source_file"]
    for column in source_columns:
        ordered.append(column)
        if column in paired:
            ordered.append(f"{column}_raw")
    return ordered
