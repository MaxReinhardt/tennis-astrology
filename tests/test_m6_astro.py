"""M6: zodiac features — sign boundaries (including the year-end Capricorn wrap),
element mapping, and null handling for players without a birth date."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.features.astro import build_astro, element_of, zodiac_sign
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m6


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    yield connection
    connection.close()


@pytest.mark.parametrize(
    ("dob", "expected"),
    [
        (date(1987, 5, 22), "Gemini"),
        (date(1987, 5, 21), "Gemini"),  # first day of Gemini
        (date(1987, 5, 20), "Taurus"),  # last day of Taurus
        (date(1990, 1, 1), "Capricorn"),  # year-start still Capricorn
        (date(1990, 1, 19), "Capricorn"),  # last day of Capricorn
        (date(1990, 1, 20), "Aquarius"),  # first day of Aquarius
        (date(1990, 12, 25), "Capricorn"),  # year-end wrap
    ],
)
def test_zodiac_sign_maps_birthdate_including_boundaries(dob, expected):
    assert zodiac_sign(dob) == expected


def test_zodiac_sign_is_none_without_a_birthdate():
    assert zodiac_sign(None) is None


def test_element_maps_sign_and_tolerates_none():
    assert element_of("Aries") == "fire"
    assert element_of("Cancer") == "water"
    assert element_of(None) is None


def test_build_astro_writes_sign_element_and_month(connection):
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name, dob) VALUES "
        "(1, 'atp', 'Alpha', DATE '1987-05-22')"
    )

    rows = build_astro(connection)

    assert rows == 1
    record = connection.execute(
        "SELECT zodiac_sign, element, birth_month FROM analytics.player_astro"
    ).fetchone()
    assert record == ("Gemini", "air", 5)


def test_build_astro_leaves_features_null_for_missing_dob(connection):
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name, dob) VALUES "
        "(1, 'atp', 'Alpha', NULL)"
    )

    build_astro(connection)

    record = connection.execute(
        "SELECT zodiac_sign, element, birth_month FROM analytics.player_astro"
    ).fetchone()
    assert record == (None, None, None)
