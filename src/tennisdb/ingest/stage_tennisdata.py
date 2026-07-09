"""tennis-data.co.uk season files → one wide staging frame with per-year column drift
unioned into NULLs, and numbered rounds inferred from each event's observed depth."""

import re
from pathlib import Path

import pandas as pd

from tennisdb.ingest.manifest import Manifest, ManifestEntry
from tennisdb.ingest.normalize import (
    TENNISDATA_FIXED_ROUNDS,
    normalize_odds,
    normalize_series,
    normalize_surface,
    numbered_round_codes,
)

PROVENANCE_COLUMNS = ("tour", "season", "source_file", "source_row")

EVENT_COLUMNS = ("ATP", "WTA", "Location", "Tournament", "Date", "Series", "Tier", "Court")

SCORE_COLUMNS = (
    "Best of",
    "Winner",
    "Loser",
    "WRank",
    "LRank",
    "WPts",
    "LPts",
    "W1",
    "L1",
    "W2",
    "L2",
    "W3",
    "L3",
    "W4",
    "L4",
    "W5",
    "L5",
    "Wsets",
    "Lsets",
    "Comment",
)

ODDS_COLUMNS = (
    "CBW",
    "CBL",
    "GBW",
    "GBL",
    "IWW",
    "IWL",
    "SBW",
    "SBL",
    "B365W",
    "B365L",
    "B&WW",
    "B&WL",
    "EXW",
    "EXL",
    "PSW",
    "PSL",
    "UBW",
    "UBL",
    "LBW",
    "LBL",
    "SJW",
    "SJL",
    "MaxW",
    "MaxL",
    "AvgW",
    "AvgL",
    "BFEW",
    "BFEL",
)

TENNISDATA_COLUMNS = (
    *PROVENANCE_COLUMNS,
    *EVENT_COLUMNS,
    "surface_raw",
    "surface",
    "round_raw",
    "round",
    *SCORE_COLUMNS,
    *ODDS_COLUMNS,
)

_INTEGER_COLUMNS = (
    "ATP",
    "WTA",
    "Best of",
    "WRank",
    "LRank",
    "W1",
    "L1",
    "W2",
    "L2",
    "W3",
    "L3",
    "W4",
    "L4",
    "W5",
    "L5",
    "Wsets",
    "Lsets",
)

# WTA 2007 carries fractional ranking points (shared points from co-sanctioned
# events), so WPts/LPts cannot be a lossless INTEGER column.
_DOUBLE_COLUMNS = ("WPts", "LPts")

_EXCEL_SUFFIXES = {".xls", ".xlsx"}
_NUMBERED_ROUND = re.compile(r"^(\d+)(?:st|nd|rd|th) Round$")


def stage_matches(manifest: Manifest) -> pd.DataFrame:
    entries = sorted(manifest.find_with_prefix("tennisdata/"), key=lambda entry: entry.path)
    frames = [_stage_season(manifest, entry) for entry in entries]
    combined = pd.concat(frames, ignore_index=True)
    return combined.reindex(columns=list(TENNISDATA_COLUMNS))


def read_season_file(file: Path) -> pd.DataFrame:
    if file.suffix in _EXCEL_SUFFIXES:
        frame = pd.read_excel(file, dtype=str)
        dayfirst = False  # openpyxl datetimes arrive as unambiguous "YYYY-MM-DD ..." strings
    elif file.suffix == ".csv":
        frame = pd.read_csv(file, dtype=str)
        dayfirst = True  # tennis-data.co.uk CSV seasons write dates as DD/MM/YYYY
    else:
        raise ValueError(f"unsupported tennis-data file format: {file.name}")
    frame.columns = [str(column).strip() for column in frame.columns]
    frame.insert(0, "source_row", frame.index + 2)
    frame["Date"] = pd.to_datetime(frame["Date"], dayfirst=dayfirst, errors="coerce").dt.date
    return frame


def infer_rounds(season_frame: pd.DataFrame) -> pd.Series:
    canonical = pd.Series(index=season_frame.index, dtype=object)
    for _, event in season_frame.groupby(["Location", "Tournament"], sort=False):
        codes = _round_codes_for_event(event["Round"])
        canonical.loc[event.index] = event["Round"].map(codes)
    return canonical


def _round_codes_for_event(round_values: pd.Series) -> dict[str, str]:
    numbered_depths = [
        int(match.group(1))
        for value in round_values.dropna()
        if (match := _NUMBERED_ROUND.match(str(value).strip()))
    ]
    codes = dict(TENNISDATA_FIXED_ROUNDS)
    if numbered_depths:
        codes.update(numbered_round_codes(max(numbered_depths)))
    return codes


def _stage_season(manifest: Manifest, entry: ManifestEntry) -> pd.DataFrame:
    file = manifest.raw_dir / entry.path
    if not file.exists():
        raise FileNotFoundError(
            f"manifest lists {entry.path} but the file is missing — re-run scripts/ingest_all.py"
        )
    frame = read_season_file(file)
    frame["tour"] = entry.path.split("/")[1]
    frame["season"] = int(file.stem)
    frame["source_file"] = entry.path
    frame["surface_raw"] = frame["Surface"]
    frame["surface"] = normalize_series(frame["surface_raw"], normalize_surface)
    frame["round_raw"] = frame["Round"]
    frame["round"] = infer_rounds(frame)
    for column in ODDS_COLUMNS:
        if column in frame.columns:
            frame[column] = normalize_series(frame[column], normalize_odds)
    for column in _INTEGER_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    for column in _DOUBLE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame
