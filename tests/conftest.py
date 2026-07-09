"""Shared fixtures: synthetic raw files registered in a manifest under a temp raw dir."""

import pandas as pd
import pytest

from tennisdb.ingest.manifest import EXCEL_SUFFIXES, Manifest


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path


@pytest.fixture
def manifest(raw_dir):
    return Manifest.load(raw_dir / "manifest.json")


@pytest.fixture
def record_file(manifest):
    def record(relative_path: str, frame: pd.DataFrame):
        file = manifest.raw_dir / relative_path
        file.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix in EXCEL_SUFFIXES:
            frame.to_excel(file, index=False)
        else:
            frame.to_csv(file, index=False)
        manifest.record_download(file, f"http://test/{relative_path}")
        return file

    return record
