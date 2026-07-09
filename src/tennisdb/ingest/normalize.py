"""Pure value normalizers for staging, plus a vectorized helper to apply them to Series."""

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd

MIN_VALID_ODDS = 1.001
MAX_VALID_ODDS = 1001.0

CANONICAL_ROUNDS = frozenset(
    {"F", "SF", "QF", "R16", "R32", "R64", "R128", "RR", "Q1", "Q2", "Q3", "BR"}
)

TENNISDATA_FIXED_ROUNDS = {
    "The Final": "F",
    "Semifinals": "SF",
    "Quarterfinals": "QF",
    "Round Robin": "RR",
    "Third Place": "BR",
}

_SURFACES = {
    "hard": "Hard",
    "clay": "Clay",
    "grass": "Grass",
    "carpet": "Carpet",
    "greenset": "Hard",
}

_COMMA_DECIMAL = re.compile(r"^\d+,\d+$")
_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}
_LARGEST_CANONICAL_DRAW = 128


def parse_yyyymmdd(value: Any) -> date | None:
    text = str(value).strip() if value is not None else ""
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def normalize_odds(value: Any) -> float | None:
    price = _to_float(value)
    if price is None or not MIN_VALID_ODDS <= price < MAX_VALID_ODDS:
        return None
    return price


def _to_float(value: Any) -> float | None:
    if isinstance(value, str) and _COMMA_DECIMAL.match(value.strip()):
        value = value.strip().replace(",", ".")
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return None if price != price else price


def normalize_surface(value: Any) -> str | None:
    if value is None:
        return None
    return _SURFACES.get(str(value).strip().casefold())


def normalize_sackmann_round(value: Any) -> str | None:
    if value is None:
        return None
    code = str(value).strip()
    return code if code in CANONICAL_ROUNDS else None


def numbered_round_codes(deepest: int) -> dict[str, str]:
    """Map 'Nth Round' labels to draw-size codes, given that the deepest numbered
    round of an event is the round of 16 (the next round is always Quarterfinals)."""
    codes = {}
    for ordinal in range(1, deepest + 1):
        draw_size = 2 ** (4 + deepest - ordinal)
        if draw_size > _LARGEST_CANONICAL_DRAW:
            continue
        suffix = _ORDINAL_SUFFIXES.get(ordinal, "th")
        codes[f"{ordinal}{suffix} Round"] = f"R{draw_size}"
    return codes


def normalize_series(series: pd.Series, normalizer: Callable[[Any], Any]) -> pd.Series:
    """Apply a normalizer over the unique values only — orders of magnitude faster
    than Series.map(normalizer) on large columns with few distinct values."""
    mapping = {value: normalizer(value) for value in series.dropna().unique()}
    return series.map(mapping)
