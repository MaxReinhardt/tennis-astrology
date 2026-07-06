import io
import tarfile

import pytest

from tennisdb.ingest.download import DownloadError
from tennisdb.ingest.manifest import Manifest
from tennisdb.ingest.sackmann import ingest_sackmann, is_wanted_member, tarball_url
from tennisdb.ingest.tennisdata import (
    candidate_urls,
    discover_season_urls,
    ingest_tennisdata,
)

INDEX_HTML = """
<html><body>
<a href="2005/2005.xls">ATP 2005</a>
<a href="2019/2019.xlsx">ATP 2019</a>
<a href="2019w/2019.xlsx">WTA 2019</a>
<a href="2019/2019.zip">ATP 2019 zip</a>
<a href="http://www.tennis-data.co.uk/2020/2020.xlsx">ATP 2020 absolute</a>
</body></html>
"""


class FakeHttp:
    def __init__(self, index_html="", files=None):
        self.index_html = index_html
        self.files = files or {}
        self.download_calls = []
        self.index_calls = 0

    def get_text(self, url):
        self.index_calls += 1
        return self.index_html

    def download(self, url, destination):
        self.download_calls.append(url)
        if url not in self.files:
            raise DownloadError(f"404 for {url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.files[url])


def tarball_bytes(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture
def manifest(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    return Manifest.load(raw / "manifest.json")


@pytest.mark.m1
def test_discover_season_urls_parses_relative_and_absolute_links():
    urls = discover_season_urls(INDEX_HTML)

    assert urls[("atp", 2005)] == "http://www.tennis-data.co.uk/2005/2005.xls"
    assert urls[("atp", 2019)] == "http://www.tennis-data.co.uk/2019/2019.xlsx"
    assert urls[("wta", 2019)] == "http://www.tennis-data.co.uk/2019w/2019.xlsx"
    assert urls[("atp", 2020)] == "http://www.tennis-data.co.uk/2020/2020.xlsx"


@pytest.mark.m1
def test_discover_season_urls_ignores_zip_links():
    urls = discover_season_urls('<a href="2019/2019.zip">zip only</a>')
    assert urls == {}


@pytest.mark.m1
def test_candidate_urls_prefers_xlsx_and_uses_wta_suffix():
    assert candidate_urls("atp", 2010) == [
        "http://www.tennis-data.co.uk/2010/2010.xlsx",
        "http://www.tennis-data.co.uk/2010/2010.xls",
    ]
    assert candidate_urls("wta", 2010)[0] == "http://www.tennis-data.co.uk/2010w/2010.xlsx"


@pytest.mark.m1
@pytest.mark.parametrize(
    "member,wanted",
    [
        ("tennis_atp-master/atp_matches_2019.csv", True),
        ("tennis_atp-master/atp_players.csv", True),
        ("tennis_atp-master/atp_rankings_current.csv", True),
        ("tennis_wta-master/wta_rankings_80s.csv", True),
        ("tennis_atp-master/atp_matches_qual_chall_2019.csv", False),
        ("tennis_atp-master/atp_matches_doubles_2019.csv", False),
        ("tennis_atp-master/atp_matches_futures_2019.csv", False),
        ("tennis_atp-master/README.md", False),
    ],
)
def test_is_wanted_member_selects_main_tour_files_only(member, wanted):
    assert is_wanted_member(member) is wanted


CSV_BODY = "Winner,Loser,B365W,B365L\nPlayer A,Player B,1.5,2.5\n"


def tennisdata_index_and_files(years):
    links = "".join(f'<a href="{year}/{year}.csv">ATP {year}</a>' for year in years)
    files = {
        f"http://www.tennis-data.co.uk/{year}/{year}.csv": CSV_BODY.encode() for year in years
    }
    return links, files


@pytest.mark.m1
def test_ingest_tennisdata_downloads_and_records(manifest):
    index, files = tennisdata_index_and_files([2018, 2019])
    http = FakeHttp(index_html=index, files=files)

    report = ingest_tennisdata(manifest, http, seasons={"atp": [2018, 2019]})

    assert sorted(report.downloaded) == ["tennisdata/atp/2018.csv", "tennisdata/atp/2019.csv"]
    assert manifest.has("tennisdata/atp/2018.csv")
    assert (manifest.raw_dir / "tennisdata" / "atp" / "2019.csv").exists()


@pytest.mark.m1
def test_ingest_tennisdata_second_run_skips_without_network(manifest):
    index, files = tennisdata_index_and_files([2019])
    http = FakeHttp(index_html=index, files=files)
    ingest_tennisdata(manifest, http, seasons={"atp": [2019]})
    downloads_after_first_run = len(http.download_calls)
    index_calls_after_first_run = http.index_calls

    report = ingest_tennisdata(manifest, http, seasons={"atp": [2019]})

    assert report.skipped == ["tennisdata/atp/2019.csv"]
    assert report.downloaded == []
    assert len(http.download_calls) == downloads_after_first_run
    assert http.index_calls == index_calls_after_first_run


@pytest.mark.m1
def test_ingest_tennisdata_force_redownloads(manifest):
    index, files = tennisdata_index_and_files([2019])
    http = FakeHttp(index_html=index, files=files)
    ingest_tennisdata(manifest, http, seasons={"atp": [2019]})

    report = ingest_tennisdata(manifest, http, seasons={"atp": [2019]}, force=True)

    assert report.downloaded == ["tennisdata/atp/2019.csv"]


@pytest.mark.m1
def test_ingest_tennisdata_records_failure_when_all_urls_404(manifest):
    http = FakeHttp(index_html="", files={})

    report = ingest_tennisdata(manifest, http, seasons={"atp": [2019]})

    assert report.downloaded == []
    assert report.failed == ["tennisdata/atp/2019"]
    assert not manifest.has("tennisdata/atp/2019.xlsx")


@pytest.mark.m1
def test_ingest_tennisdata_rejects_unparseable_download(manifest):
    index, _ = tennisdata_index_and_files([2019])
    broken = {"http://www.tennis-data.co.uk/2019/2019.csv": b"\x00\x01 not a csv \x00"}
    http = FakeHttp(index_html=index, files=broken)

    report = ingest_tennisdata(manifest, http, seasons={"atp": [2019]})

    assert report.failed == ["tennisdata/atp/2019"]
    assert not (manifest.raw_dir / "tennisdata" / "atp" / "2019.csv").exists()


SACKMANN_MEMBERS = {
    "tennis_atp-master/atp_matches_2018.csv": "tourney_id,winner_id\nx,1\n",
    "tennis_atp-master/atp_matches_2019.csv": "tourney_id,winner_id\nx,1\ny,2\n",
    "tennis_atp-master/atp_players.csv": "player_id,name_first\n1,Roger\n",
    "tennis_atp-master/atp_rankings_10s.csv": "ranking_date,rank\n20190101,1\n",
    "tennis_atp-master/atp_matches_qual_chall_2019.csv": "tourney_id\nq\n",
    "tennis_atp-master/README.md": "readme",
}


def sackmann_http():
    tarball = tarball_bytes(SACKMANN_MEMBERS)
    return FakeHttp(files={tarball_url("atp"): tarball})


@pytest.mark.m1
def test_tarball_url_targets_configured_github_repo():
    url = tarball_url("atp")
    assert url.startswith("https://codeload.github.com/")
    assert url.endswith("/tar.gz/refs/heads/master")


@pytest.mark.m1
def test_ingest_sackmann_extracts_only_wanted_members(manifest):
    report = ingest_sackmann(manifest, sackmann_http(), tours=("atp",))

    extracted = sorted(f.name for f in (manifest.raw_dir / "sackmann" / "atp").iterdir())
    assert extracted == [
        "atp_matches_2018.csv",
        "atp_matches_2019.csv",
        "atp_players.csv",
        "atp_rankings_10s.csv",
    ]
    assert sorted(report.downloaded) == [
        "sackmann/atp/atp_matches_2018.csv",
        "sackmann/atp/atp_matches_2019.csv",
        "sackmann/atp/atp_players.csv",
        "sackmann/atp/atp_rankings_10s.csv",
    ]


@pytest.mark.m1
def test_ingest_sackmann_records_row_counts(manifest):
    ingest_sackmann(manifest, sackmann_http(), tours=("atp",))

    assert manifest.get("sackmann/atp/atp_matches_2019.csv").row_count == 2


@pytest.mark.m1
def test_ingest_sackmann_second_run_skips_without_network(manifest):
    http = sackmann_http()
    ingest_sackmann(manifest, http, tours=("atp",))
    downloads_after_first_run = len(http.download_calls)

    report = ingest_sackmann(manifest, http, tours=("atp",))

    assert report.downloaded == []
    assert len(report.skipped) == 4
    assert len(http.download_calls) == downloads_after_first_run


@pytest.mark.m1
def test_ingest_sackmann_force_redownloads(manifest):
    http = sackmann_http()
    ingest_sackmann(manifest, http, tours=("atp",))

    report = ingest_sackmann(manifest, http, tours=("atp",), force=True)

    assert len(report.downloaded) == 4
    assert report.skipped == []


@pytest.mark.m1
def test_ingest_sackmann_failed_tour_is_reported(manifest):
    http = FakeHttp(files={})

    report = ingest_sackmann(manifest, http, tours=("atp",))

    assert report.failed == ["sackmann/atp"]
