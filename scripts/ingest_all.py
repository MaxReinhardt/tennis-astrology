"""Download all raw source data: Sackmann GitHub CSVs and tennis-data.co.uk odds files."""

import argparse
import sys

from tennisdb.ingest.download import HttpDownloader
from tennisdb.ingest.manifest import MANIFEST_PATH, Manifest
from tennisdb.ingest.report import IngestReport
from tennisdb.ingest.sackmann import ingest_sackmann
from tennisdb.ingest.tennisdata import ingest_tennisdata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-download files that already exist"
    )
    parser.add_argument("--source", choices=("sackmann", "tennisdata", "all"), default="all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = Manifest.load(MANIFEST_PATH)
    http = HttpDownloader()
    report = IngestReport()
    if args.source in ("sackmann", "all"):
        report.extend(ingest_sackmann(manifest, http, force=args.force))
    if args.source in ("tennisdata", "all"):
        report.extend(ingest_tennisdata(manifest, http, force=args.force))
    print("\n".join(report.summary_lines()))
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
