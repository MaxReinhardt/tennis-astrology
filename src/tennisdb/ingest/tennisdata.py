"""Ingest tennis-data.co.uk yearly bookmaker-odds files (ATP 2001+, WTA 2007+)."""

import re
from pathlib import Path

import pandas as pd

from tennisdb.config import CURRENT_SEASON
from tennisdb.ingest.download import DownloadError
from tennisdb.ingest.manifest import Manifest
from tennisdb.ingest.report import IngestReport

BASE_URL = "http://www.tennis-data.co.uk"
INDEX_URL = f"{BASE_URL}/alldata.php"
FIRST_SEASON = {"atp": 2001, "wta": 2007}
TOUR_PATH_SUFFIX = {"atp": "", "wta": "w"}

SEASON_LINK = re.compile(
    r"href=[\"']?(?:https?://www\.tennis-data\.co\.uk/)?(\d{4})(w?)/(\d{4})\.(xlsx|xls|csv)"
)


def default_seasons() -> dict[str, range]:
    return {tour: range(first, CURRENT_SEASON + 1) for tour, first in FIRST_SEASON.items()}


def discover_season_urls(index_html: str) -> dict[tuple[str, int], str]:
    urls: dict[tuple[str, int], str] = {}
    for match in SEASON_LINK.finditer(index_html):
        directory_year, wta_suffix, file_year, extension = match.groups()
        if directory_year != file_year:
            continue
        tour = "wta" if wta_suffix else "atp"
        url = f"{BASE_URL}/{directory_year}{wta_suffix}/{file_year}.{extension}"
        urls.setdefault((tour, int(file_year)), url)
    return urls


def candidate_urls(tour: str, year: int) -> list[str]:
    directory = f"{year}{TOUR_PATH_SUFFIX[tour]}"
    return [f"{BASE_URL}/{directory}/{year}.{extension}" for extension in ("xlsx", "xls")]


def ingest_tennisdata(
    manifest: Manifest, http, *, seasons: dict | None = None, force: bool = False
) -> IngestReport:
    seasons = seasons if seasons is not None else default_seasons()
    report = IngestReport()
    index = _LazySeasonIndex(http)
    for tour, years in seasons.items():
        for year in years:
            _ingest_season(manifest, http, index, (tour, year), force, report)
    return report


class _LazySeasonIndex:
    """Fetches the site index once, and only if some season actually needs downloading."""

    def __init__(self, http):
        self._http = http
        self._urls: dict[tuple[str, int], str] | None = None

    def lookup(self, tour: str, year: int) -> str | None:
        if self._urls is None:
            self._urls = self._fetch()
        return self._urls.get((tour, year))

    def _fetch(self) -> dict[tuple[str, int], str]:
        try:
            return discover_season_urls(self._http.get_text(INDEX_URL))
        except DownloadError:
            return {}


def _ingest_season(
    manifest: Manifest,
    http,
    index: _LazySeasonIndex,
    season: tuple[str, int],
    force: bool,
    report: IngestReport,
) -> None:
    tour, year = season
    existing = [
        entry
        for entry in manifest.find_with_prefix(f"tennisdata/{tour}/{year}.")
        if (manifest.raw_dir / entry.path).exists()
    ]
    if existing and not force:
        report.skipped.extend(entry.path for entry in existing)
        return

    urls = _unique_urls([index.lookup(tour, year), *candidate_urls(tour, year)])
    for url in urls:
        destination = manifest.raw_dir / "tennisdata" / tour / f"{year}{Path(url).suffix}"
        try:
            http.download(url, destination)
            _assert_parses(destination)
        except DownloadError as error:
            destination.unlink(missing_ok=True)
            report.warnings.append(str(error))
            continue
        entry = manifest.record_download(destination, url)
        report.downloaded.append(entry.path)
        return
    report.failed.append(f"tennisdata/{tour}/{year}")


def _unique_urls(urls: list[str | None]) -> list[str]:
    return list(dict.fromkeys(url for url in urls if url))


def _assert_parses(file: Path) -> None:
    head = file.read_bytes()[:4096].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        raise DownloadError(f"{file.name} is an HTML page, not a data file")
    try:
        if file.suffix == ".csv":
            if b"\x00" in head:
                raise ValueError("binary content in csv")
            pd.read_csv(file, nrows=5)
        else:
            pd.read_excel(file, nrows=5)
    except Exception as error:
        raise DownloadError(f"{file.name} does not parse as {file.suffix}: {error}") from error
