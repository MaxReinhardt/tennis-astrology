"""Publish canonical tennis.* tables from the DuckDB warehouse to Supabase via COPY.

Apply the schema to Supabase first:
    uv run python scripts/migrate.py --target supabase
"""

import argparse
import sys

import psycopg

from tennisdb.load.publish import (
    ALL_TABLES,
    CORE_TABLES,
    publish_canonical,
    publish_features,
)
from tennisdb.load.supabase import (
    DuckDbCanonicalSource,
    SupabaseNotConfiguredError,
    SupabasePublishSink,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-rankings",
        action="store_true",
        help="also publish the 5.5M-row rankings table (likely exceeds the free tier)",
    )
    parser.add_argument(
        "--features",
        action="store_true",
        help="publish the analytics feature tables instead of the canonical tables",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        sink = SupabasePublishSink.open()
    except SupabaseNotConfiguredError as error:
        print(error)
        return 1

    source = DuckDbCanonicalSource.open()
    try:
        report = _publish(source, sink, args)
    except psycopg.errors.UndefinedTable:
        print(
            "target schema missing — run `uv run python scripts/migrate.py "
            "--target supabase` first"
        )
        return 1
    finally:
        sink.close()
        source.close()

    print("\n".join(report.summary_lines()))
    return 0


def _publish(source, sink, args):
    try:
        report = _run_publish(source, sink, args)
        sink.commit()
        return report
    except Exception:
        sink.rollback()
        raise


def _run_publish(source, sink, args):
    if args.features:
        return publish_features(source, sink)
    tables = ALL_TABLES if args.include_rankings else CORE_TABLES
    return publish_canonical(source, sink, tables)


if __name__ == "__main__":
    sys.exit(main())
