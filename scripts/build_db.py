"""Build the local DuckDB warehouse from raw files + manifest."""

import argparse
import json
import sys

from tennisdb import warehouse
from tennisdb.ingest.manifest import MANIFEST_PATH, Manifest
from tennisdb.ingest.staging import build_staging
from tennisdb.load.canonical import load_canonical


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", action="store_true", help="build the DuckDB staging schema from raw files"
    )
    parser.add_argument(
        "--load", action="store_true", help="rebuild canonical tennis.* tables from staging"
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="resolve tennis-data rows onto canonical matches and emit tennis.odds",
    )
    parser.add_argument(
        "--features",
        action="store_true",
        help="build the analytics feature tables (elo, form, market, astro)",
    )
    parser.add_argument(
        "--quality",
        action="store_true",
        help="run the data-quality suite and write data/quality/quality_report.json",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="run stage, load, resolve, features and quality in order",
    )
    return parser.parse_args()


def run_stage() -> list[str]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            "data/raw/manifest.json missing — run `uv run python scripts/ingest_all.py` first"
        )
    manifest = Manifest.load(MANIFEST_PATH)
    connection = warehouse.connect()
    try:
        report = build_staging(manifest, warehouse.Warehouse(connection))
    finally:
        connection.close()
    return report.summary_lines()


def run_load() -> list[str]:
    connection = warehouse.connect()
    try:
        report = load_canonical(connection)
    finally:
        connection.close()
    return report.summary_lines()


def run_resolve() -> list[str]:
    from tennisdb.resolve.pipeline import run_resolution

    connection = warehouse.connect()
    try:
        report = run_resolution(connection)
    finally:
        connection.close()
    return report.summary_lines()


def run_features() -> list[str]:
    from tennisdb.features.pipeline import build_features

    connection = warehouse.connect()
    try:
        report = build_features(connection)
    finally:
        connection.close()
    return report.summary_lines()


def run_quality() -> tuple[list[str], bool]:
    from tennisdb.quality.checks import REPORT_PATH, run_quality_suite, write_report

    connection = warehouse.connect()
    try:
        report = run_quality_suite(connection)
        write_report(report)
        stats = {"passed": report.passed(), "waived": [r.name for r in report.waived()]}
        connection.execute(
            "INSERT INTO tennis.ingest_log (step, stats) "
            "VALUES ('quality:checks', CAST(? AS JSON))",
            [json.dumps(stats)],
        )
    finally:
        connection.close()
    return report.summary_lines() + [f"report written to {REPORT_PATH}"], report.passed()


def main() -> int:
    args = parse_args()
    if args.all:
        args.stage = args.load = args.resolve = args.features = args.quality = True
    if not (args.stage or args.load or args.resolve or args.features or args.quality):
        print("nothing to do: pass --stage, --load, --resolve, --features, --quality and/or --all")
        return 2
    build_steps = (
        (args.stage, run_stage),
        (args.load, run_load),
        (args.resolve, run_resolve),
        (args.features, run_features),
    )
    for requested, run_step in build_steps:
        if requested:
            print("\n".join(run_step()))
    if args.quality:
        lines, passed = run_quality()
        print("\n".join(lines))
        if not passed:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
