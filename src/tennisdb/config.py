"""Project paths, environment loading, and shared constants."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

CURRENT_SEASON = date.today().year

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

# The upstream JeffSackmann/tennis_{atp,wta} repos vanished from GitHub in
# mid-2026; these are the freshest surviving forks (ATP synced 2026-06,
# WTA 2026-05). Overridable so a returning upstream is a one-line .env change.
SACKMANN_REPOS = {
    "atp": os.environ.get("SACKMANN_ATP_REPO") or "racketbracket/tennis_atp",
    "wta": os.environ.get("SACKMANN_WTA_REPO") or "VictorSquidWei/tennis_wta",
}


def ensure_data_directories() -> None:
    for directory in (SACKMANN_RAW_DIR, TENNISDATA_RAW_DIR):
        directory.mkdir(parents=True, exist_ok=True)


ensure_data_directories()
