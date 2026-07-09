"""Apply db/migrations/*.sql to the DuckDB warehouse and, when configured, Supabase."""

import argparse
import sys

from tennisdb import config
from tennisdb.migrate.runner import MigrationChecksumError, MigrationTarget, run_migrations
from tennisdb.migrate.scripts import MigrationScript, load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget, PostgresMigrationTarget

TARGET_FACTORIES: dict[str, type[DuckDbMigrationTarget] | type[PostgresMigrationTarget]] = {
    "duckdb": DuckDbMigrationTarget,
    "supabase": PostgresMigrationTarget,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=["duckdb", "supabase", "all"],
        default="all",
        help="which database(s) to migrate (default: all)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scripts = load_migration_scripts(config.MIGRATIONS_DIR)

    if args.target == "supabase" and not config.SUPABASE_DB_URL:
        print(
            "supabase: SUPABASE_DB_URL not set — create a Supabase project and copy "
            ".env.example to .env with its connection string"
        )
        return 1

    target_names = ["duckdb", "supabase"] if args.target == "all" else [args.target]
    try:
        for target_name in target_names:
            if target_name == "supabase" and not config.SUPABASE_DB_URL:
                print("supabase: skipped (SUPABASE_DB_URL not set)")
                continue
            _migrate(target_name, scripts)
    except MigrationChecksumError as error:
        print(error)
        return 1
    return 0


def _migrate(target_name: str, scripts: list[MigrationScript]) -> None:
    target: MigrationTarget = TARGET_FACTORIES[target_name].open()
    try:
        report = run_migrations(scripts, target)
    finally:
        target.close()
    print("\n".join(report.summary_lines()))


if __name__ == "__main__":
    sys.exit(main())
