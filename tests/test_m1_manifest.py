import json

import pandas as pd
import pytest

from tennisdb.ingest.manifest import Manifest, count_rows, sha256_of


@pytest.fixture
def raw_dir(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    return raw


@pytest.fixture
def manifest(raw_dir):
    return Manifest.load(raw_dir / "manifest.json")


def write_csv(directory, name, rows):
    file = directory / name
    file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["col_a,col_b"] + [f"a{i},b{i}" for i in range(rows)]
    file.write_text("\n".join(lines) + "\n")
    return file


@pytest.mark.m1
def test_load_missing_file_returns_empty_manifest(manifest):
    assert manifest.entries() == ()


@pytest.mark.m1
def test_record_download_computes_checksum_and_row_count(manifest, raw_dir):
    file = write_csv(raw_dir, "source/data.csv", rows=3)

    entry = manifest.record_download(file, "http://example.com/data.csv")

    assert entry.path == "source/data.csv"
    assert entry.source_url == "http://example.com/data.csv"
    assert entry.sha256 == sha256_of(file)
    assert entry.row_count == 3
    assert entry.downloaded_at


@pytest.mark.m1
def test_record_download_persists_across_reload(manifest, raw_dir):
    file = write_csv(raw_dir, "source/data.csv", rows=2)
    manifest.record_download(file, "http://example.com/data.csv")

    reloaded = Manifest.load(raw_dir / "manifest.json")

    assert reloaded.has("source/data.csv")
    assert reloaded.get("source/data.csv").row_count == 2


@pytest.mark.m1
def test_has_returns_false_for_unknown_path(manifest):
    assert not manifest.has("nope/missing.csv")
    assert manifest.get("nope/missing.csv") is None


@pytest.mark.m1
def test_find_with_prefix_returns_only_matching_entries(manifest, raw_dir):
    manifest.record_download(write_csv(raw_dir, "a/x.csv", 1), "http://e.com/x")
    manifest.record_download(write_csv(raw_dir, "a/y.csv", 1), "http://e.com/y")
    manifest.record_download(write_csv(raw_dir, "b/z.csv", 1), "http://e.com/z")

    found = manifest.find_with_prefix("a/")

    assert sorted(entry.path for entry in found) == ["a/x.csv", "a/y.csv"]


@pytest.mark.m1
def test_saved_manifest_is_valid_json_with_no_leftover_temp_files(manifest, raw_dir):
    manifest.record_download(write_csv(raw_dir, "a/x.csv", 1), "http://e.com/x")

    payload = json.loads((raw_dir / "manifest.json").read_text())

    assert isinstance(payload, list)
    assert [f.name for f in raw_dir.glob("manifest*")] == ["manifest.json"]


@pytest.mark.m1
def test_count_rows_csv_excludes_header(raw_dir):
    file = write_csv(raw_dir, "data.csv", rows=5)
    assert count_rows(file) == 5


@pytest.mark.m1
def test_count_rows_empty_csv_is_zero(raw_dir):
    file = raw_dir / "empty.csv"
    file.write_text("col_a,col_b\n")
    assert count_rows(file) == 0


@pytest.mark.m1
def test_count_rows_xlsx(raw_dir):
    file = raw_dir / "data.xlsx"
    pd.DataFrame({"Winner": ["A", "B"], "Loser": ["C", "D"]}).to_excel(file, index=False)
    assert count_rows(file) == 2


@pytest.mark.m1
def test_sha256_changes_when_content_changes(raw_dir):
    file = write_csv(raw_dir, "data.csv", rows=1)
    before = sha256_of(file)
    write_csv(raw_dir, "data.csv", rows=2)
    assert sha256_of(file) != before
