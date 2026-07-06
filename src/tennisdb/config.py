"""Project paths, environment loading, and shared constants."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SACKMANN_RAW_DIR = RAW_DIR / "sackmann"
TENNISDATA_RAW_DIR = RAW_DIR / "tennisdata"
DUCKDB_PATH = DATA_DIR / "warehouse.duckdb"
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
SEED_DIR = PROJECT_ROOT / "db" / "seed"

load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")


def ensure_data_directories() -> None:
    for directory in (SACKMANN_RAW_DIR, TENNISDATA_RAW_DIR):
        directory.mkdir(parents=True, exist_ok=True)


ensure_data_directories()
