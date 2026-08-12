"""Publish canonical tennis.* tables from the DuckDB warehouse to Supabase via COPY.

Apply the schema to Supabase first:
    uv run python scripts/migrate.py --target supabase
"""

import argparse
import sys

import psycopg

from tennisdb.load.publish import ALL_TABLES, CORE_TABLES, publish_canonical
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tables = ALL_TABLES if args.include_rankings else CORE_TABLES

    try:
        sink = SupabasePublishSink.open()
    except SupabaseNotConfiguredError as error:
        print(error)
        return 1

    source = DuckDbCanonicalSource.open()
    try:
        report = _publish(source, sink, tables)
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


def _publish(source, sink, tables):
    try:
        report = publish_canonical(source, sink, tables)
        sink.commit()
        return report
    except Exception:
        sink.rollback()
        raise


if __name__ == "__main__":
    sys.exit(main())
