"""Ingest Jeff Sackmann's tennis_atp / tennis_wta repos (main-tour files only)."""

import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from tennisdb.config import CURRENT_SEASON, SACKMANN_REPOS
from tennisdb.ingest.download import DownloadError
from tennisdb.ingest.manifest import Manifest
from tennisdb.ingest.report import IngestReport

TOURS = ("atp", "wta")

WANTED_MEMBER = re.compile(r"/(atp|wta)_(matches_\d{4}|players|rankings_[0-9a-z]+)\.csv$")


def tarball_url(tour: str) -> str:
    return f"https://codeload.github.com/{SACKMANN_REPOS[tour]}/tar.gz/refs/heads/master"


def is_wanted_member(member_name: str) -> bool:
    return WANTED_MEMBER.search(member_name) is not None


def ingest_sackmann(
    manifest: Manifest, http, *, tours: tuple[str, ...] = TOURS, force: bool = False
) -> IngestReport:
    report = IngestReport()
    for tour in tours:
        _ingest_tour(manifest, http, tour, force, report)
    return report


def _ingest_tour(
    manifest: Manifest, http, tour: str, force: bool, report: IngestReport
) -> None:
    existing = manifest.find_with_prefix(f"sackmann/{tour}/")
    files_present = all((manifest.raw_dir / entry.path).exists() for entry in existing)
    if existing and files_present and not force:
        report.skipped.extend(entry.path for entry in existing)
        return

    url = tarball_url(tour)
    extracted = _download_and_extract(http, url, manifest.raw_dir / "sackmann" / tour, report)
    if not extracted:
        report.failed.append(f"sackmann/{tour}")
        return

    for file in sorted(extracted):
        entry = manifest.record_download(file, url)
        report.downloaded.append(entry.path)

    current_season_file = f"{tour}_matches_{CURRENT_SEASON}.csv"
    if current_season_file not in {file.name for file in extracted}:
        report.warnings.append(f"{current_season_file} not present in the {tour} repo yet")


def _download_and_extract(
    http, url: str, destination_dir: Path, report: IngestReport
) -> list[Path]:
    with tempfile.TemporaryDirectory() as scratch:
        tarball = Path(scratch) / "repo.tar.gz"
        try:
            http.download(url, tarball)
        except DownloadError as error:
            report.warnings.append(str(error))
            return []
        return _extract_wanted_members(tarball, destination_dir)


def _extract_wanted_members(tarball: Path, destination_dir: Path) -> list[Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar:
            if not (member.isfile() and is_wanted_member(member.name)):
                continue
            destination = destination_dir / Path(member.name).name
            with tar.extractfile(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(destination)
    return extracted
