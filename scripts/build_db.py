"""Build the local DuckDB warehouse from raw files + manifest."""

import argparse
import sys

from tennisdb import warehouse
from tennisdb.ingest.manifest import MANIFEST_PATH, Manifest
from tennisdb.ingest.staging import build_staging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", action="store_true", help="build the DuckDB staging schema from raw files"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.stage:
        print("nothing to do: pass --stage")
        return 2
    if not MANIFEST_PATH.exists():
        print("data/raw/manifest.json missing — run `uv run python scripts/ingest_all.py` first")
        return 1
    manifest = Manifest.load(MANIFEST_PATH)
    connection = warehouse.connect()
    try:
        report = build_staging(manifest, warehouse.Warehouse(connection))
    finally:
        connection.close()
    print("\n".join(report.summary_lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
