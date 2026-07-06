"""M1 Verify block from PLAN.md — runs against the real data/raw/ after ingestion."""

from pathlib import Path

import pandas as pd
import pytest

from tennisdb.config import CURRENT_SEASON
from tennisdb.ingest.download import HttpDownloader
from tennisdb.ingest.manifest import MANIFEST_PATH, Manifest
from tennisdb.ingest.sackmann import ingest_sackmann
from tennisdb.ingest.tennisdata import FIRST_SEASON, ingest_tennisdata

pytestmark = pytest.mark.m1

FIRST_SACKMANN_SEASON = 1968
LAST_COMPLETE_SEASON = CURRENT_SEASON - 1
ODDS_PAIRS = (("B365W", "B365L"), ("PSW", "PSL"), ("AvgW", "AvgL"))

# Pre-2003 files predate the B365/PS/Avg trio; their odds live in early-2000s
# bookmaker columns instead.
EARLY_ODDS_PAIRS = ODDS_PAIRS + (
    ("CBW", "CBL"),
    ("GBW", "GBL"),
    ("IWW", "IWL"),
    ("SBW", "SBL"),
)
FIRST_TRIO_SEASON = 2003

# Documented waiver: ATP 2001 genuinely carries no odds at all on ~15% of rows.
ODDS_COVERAGE_FLOORS = {("atp", 2001): 0.85}
DEFAULT_ODDS_COVERAGE_FLOOR = 0.90


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.fail(
            "data/raw/manifest.json missing — run `uv run python scripts/ingest_all.py` first"
        )
    return Manifest.load(MANIFEST_PATH)


@pytest.fixture(scope="module")
def tennisdata_frames(manifest):
    frames = {}
    for entry in manifest.find_with_prefix("tennisdata/"):
        file = manifest.raw_dir / entry.path
        tour = file.parent.name
        year = int(file.stem)
        reader = pd.read_csv if file.suffix == ".csv" else pd.read_excel
        frames[(tour, year)] = reader(file)
    return frames


def sackmann_file(manifest, tour, name):
    return manifest.raw_dir / "sackmann" / tour / name


def test_expected_sackmann_files_exist(manifest):
    missing = []
    for tour in ("atp", "wta"):
        for year in range(FIRST_SACKMANN_SEASON, LAST_COMPLETE_SEASON + 1):
            file = sackmann_file(manifest, tour, f"{tour}_matches_{year}.csv")
            if not file.exists():
                missing.append(file.name)
        for name in (f"{tour}_players.csv", f"{tour}_rankings_current.csv"):
            if not sackmann_file(manifest, tour, name).exists():
                missing.append(name)
    assert missing == []


def test_every_sackmann_match_file_parses(manifest):
    for entry in manifest.find_with_prefix("sackmann/"):
        frame = pd.read_csv(manifest.raw_dir / entry.path, dtype=str)
        assert len(frame) == entry.row_count, entry.path


def test_sackmann_match_row_totals(manifest):
    totals = {"atp": 0, "wta": 0}
    for tour in totals:
        for entry in manifest.find_with_prefix(f"sackmann/{tour}/{tour}_matches_"):
            totals[tour] += entry.row_count
    assert totals["atp"] > 180_000, totals
    assert totals["wta"] > 150_000, totals


def test_atp_players_row_count_and_dob_coverage(manifest):
    players = pd.read_csv(
        sackmann_file(manifest, "atp", "atp_players.csv"), dtype={"wikidata_id": str}
    )
    assert len(players) > 50_000

    participant_ids = set()
    for year in range(1981, LAST_COMPLETE_SEASON + 1):
        matches = pd.read_csv(
            sackmann_file(manifest, "atp", f"atp_matches_{year}.csv"),
            usecols=["winner_id", "loser_id"],
        )
        participant_ids.update(matches["winner_id"])
        participant_ids.update(matches["loser_id"])

    tour_players = players[players["player_id"].isin(participant_ids)]
    dob_coverage = tour_players["dob"].notna().mean()
    assert dob_coverage >= 0.90, f"DOB coverage {dob_coverage:.3f}"


def test_expected_tennisdata_seasons_present(tennisdata_frames):
    for tour, first_season in FIRST_SEASON.items():
        expected = set(range(first_season, CURRENT_SEASON + 1))
        present = {year for (frame_tour, year) in tennisdata_frames if frame_tour == tour}
        assert expected - present == set(), tour


def test_tennisdata_atp_row_counts_per_season(tennisdata_frames):
    failures = []
    for year in range(2001, CURRENT_SEASON + 1):
        rows = len(tennisdata_frames[("atp", year)])
        minimum = season_row_floor(year)
        if rows < minimum:
            failures.append(f"atp {year}: {rows} rows < {minimum}")
    assert failures == []


def season_row_floor(year):
    if year == CURRENT_SEASON:
        return 1
    if year == 2020:
        return 1_000  # documented waiver: COVID-suspended season (~1,270 ATP rows)
    if year <= 2019:
        return 2_000
    return 1_500


def test_tennisdata_odds_coverage(tennisdata_frames):
    failures = []
    for (tour, year), frame in tennisdata_frames.items():
        pairs = ODDS_PAIRS if year >= FIRST_TRIO_SEASON else EARLY_ODDS_PAIRS
        floor = ODDS_COVERAGE_FLOORS.get((tour, year), DEFAULT_ODDS_COVERAGE_FLOOR)
        coverage = odds_pair_coverage(frame, pairs)
        if coverage < floor:
            failures.append(f"{tour} {year}: odds coverage {coverage:.3f} < {floor}")
    assert failures == []


def odds_pair_coverage(frame, pairs):
    has_any_pair = pd.Series(False, index=frame.index)
    for winner_column, loser_column in pairs:
        if winner_column in frame.columns and loser_column in frame.columns:
            odds = frame[[winner_column, loser_column]].apply(pd.to_numeric, errors="coerce")
            has_any_pair |= odds.notna().all(axis=1)
    return has_any_pair.mean()


def test_manifest_and_disk_agree(manifest):
    on_disk = {
        file.relative_to(manifest.raw_dir).as_posix()
        for file in manifest.raw_dir.rglob("*")
        if file.is_file() and file.name != "manifest.json"
    }
    in_manifest = {entry.path for entry in manifest.entries()}
    assert on_disk == in_manifest


def test_reingest_is_idempotent(manifest):
    manifest_bytes_before = MANIFEST_PATH.read_bytes()
    http = HttpDownloader()

    fresh_manifest = Manifest.load(MANIFEST_PATH)
    sackmann_report = ingest_sackmann(fresh_manifest, http)
    tennisdata_report = ingest_tennisdata(fresh_manifest, http)

    assert sackmann_report.downloaded == []
    assert tennisdata_report.downloaded == []
    assert MANIFEST_PATH.read_bytes() == manifest_bytes_before


def test_no_partial_downloads_left_behind(manifest):
    leftovers = [str(f) for f in manifest.raw_dir.rglob("*.part")]
    assert leftovers == []


def test_sackmann_current_season_file_note(manifest):
    """Current-season files appear mid-year; absence is tolerated but should be visible."""
    for tour in ("atp", "wta"):
        file = sackmann_file(manifest, tour, f"{tour}_matches_{CURRENT_SEASON}.csv")
        if not file.exists():
            pytest.skip(f"{file.name} not published yet in the Sackmann repo")
        assert Path(file).stat().st_size > 0
