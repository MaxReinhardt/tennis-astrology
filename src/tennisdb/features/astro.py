"""Static zodiac features per player, derived from date of birth.

This is the repo's deliberate null-hypothesis demonstrator (M8 study S3): cheap to build,
astrologically meaningless, and a clean target for showing the research harness rejects
spurious signals. Players with no recorded birth date get null features.
"""

from datetime import date

import duckdb
import pandas as pd

# (month, day) each sign begins; Capricorn brackets the year-end wrap.
_SIGN_STARTS = [
    (1, 1, "Capricorn"), (1, 20, "Aquarius"), (2, 19, "Pisces"), (3, 21, "Aries"),
    (4, 20, "Taurus"), (5, 21, "Gemini"), (6, 21, "Cancer"), (7, 23, "Leo"),
    (8, 23, "Virgo"), (9, 23, "Libra"), (10, 23, "Scorpio"), (11, 22, "Sagittarius"),
    (12, 22, "Capricorn"),
]  # fmt: skip

_ELEMENTS = {
    "Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
    "Taurus": "earth", "Virgo": "earth", "Capricorn": "earth",
    "Gemini": "air", "Libra": "air", "Aquarius": "air",
    "Cancer": "water", "Scorpio": "water", "Pisces": "water",
}  # fmt: skip


def zodiac_sign(dob: date | None) -> str | None:
    if dob is None:
        return None
    latest = [sign for month, day, sign in _SIGN_STARTS if (month, day) <= (dob.month, dob.day)]
    return latest[-1]


def element_of(sign: str | None) -> str | None:
    return _ELEMENTS.get(sign) if sign else None


def build_astro(connection: duckdb.DuckDBPyConnection) -> int:
    players = connection.execute("SELECT player_id, dob FROM tennis.players").fetch_df()
    birth_dates = pd.to_datetime(players["dob"], errors="coerce")
    players["dob"] = [value.date() if pd.notna(value) else None for value in birth_dates]
    players["zodiac_sign"] = players["dob"].map(zodiac_sign)
    players["element"] = players["zodiac_sign"].map(element_of)
    players["birth_month"] = (
        players["dob"].map(lambda value: value.month if value else None).astype("Int64")
    )
    astro = players[["player_id", "zodiac_sign", "element", "birth_month"]]
    connection.execute("DELETE FROM analytics.player_astro")
    connection.register("_astro_rows", astro)
    try:
        return connection.execute(
            "INSERT INTO analytics.player_astro SELECT * FROM _astro_rows"
        ).fetchone()[0]
    finally:
        connection.unregister("_astro_rows")
