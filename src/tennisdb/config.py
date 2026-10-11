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
QUALITY_DIR = DATA_DIR / "quality"
BACKTESTS_DIR = DATA_DIR / "backtests"
STUDIES_DIR = PROJECT_ROOT / "studies"
API_STUDY_RESULTS_DIR = Path(__file__).resolve().parent / "api" / "study_results"
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
SEED_DIR = PROJECT_ROOT / "db" / "seed"

load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_READ_URL = os.environ.get("SUPABASE_READ_URL")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY") or "MaxReinhardt/tennis-astrology"

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


try:
    ensure_data_directories()
except OSError:
    pass  # read-only serverless filesystem: only the ingest scripts need these directories
