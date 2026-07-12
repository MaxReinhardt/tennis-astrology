"""Build the local DuckDB warehouse from raw files + manifest."""

import argparse
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


def main() -> int:
    args = parse_args()
    steps = [
        (args.stage, run_stage),
        (args.load, run_load),
        (args.resolve, run_resolve),
    ]
    if not any(requested for requested, _ in steps):
        print("nothing to do: pass --stage, --load and/or --resolve")
        return 2
    for requested, run_step in steps:
        if requested:
            print("\n".join(run_step()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
