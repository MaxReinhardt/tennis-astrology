"""Persist a study run: result.json, PNG charts, the catalogue index the web UI reads,
and the study's markdown document."""

import json
import shutil
from pathlib import Path

from tennisdb import config
from tennisdb.backtest.plots import render_charts
from tennisdb.research.documents import write_study_document
from tennisdb.research.protocol import Study, StudyResult

INDEX_FILE = "index.json"


def write_study_artifacts(
    study: Study,
    result: StudyResult,
    studies_directory: Path = config.STUDIES_DIR,
    with_plots: bool = True,
    api_directory: Path = config.API_STUDY_RESULTS_DIR,
) -> Path:
    results_directory = studies_directory / "results" / result.study_id
    results_directory.mkdir(parents=True, exist_ok=True)
    (results_directory / "result.json").write_text(
        json.dumps(result.to_dict(), indent=2), encoding="utf-8"
    )
    charts_directory = "results/" + result.study_id + "/charts" if with_plots else None
    if with_plots:
        render_charts(result.charts, results_directory / "charts")
    write_study_document(
        study, result, studies_directory / f"{result.study_id}.md", charts_directory
    )
    _refresh_index(studies_directory / "results")
    _mirror_for_api(studies_directory / "results", result.study_id, api_directory)
    return results_directory


def _mirror_for_api(results_directory: Path, study_id: str, api_directory: Path) -> None:
    """The deployed API's bundle contains only src/, so it serves the JSON from a copy
    that lives inside the package. The PNGs stay in studies/ for the markdown."""
    api_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(results_directory / study_id / "result.json", api_directory / f"{study_id}.json")
    shutil.copy2(results_directory / INDEX_FILE, api_directory / INDEX_FILE)


def _refresh_index(results_directory: Path) -> None:
    entries = []
    for result_file in sorted(results_directory.glob("*/result.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        entries.append({key: payload[key] for key in ("study_id", "title", "verdict", "conclusion")}
                       | {"statement": payload["hypothesis"]["statement"]})  # fmt: skip
    (results_directory / INDEX_FILE).write_text(json.dumps(entries, indent=2), encoding="utf-8")
