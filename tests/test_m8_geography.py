"""M8: host-country geography — the seed file and the edition_geo builder."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.features.geography import build_edition_geo, load_host_countries
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m8


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "INSERT INTO tennis.tournament_editions (edition_id, tour, name, season) VALUES "
        "('2019-1', 'atp', 'Paris Masters', 2019), ('2019-2', 'atp', 'Nowhereville Open', 2019)"
    )
    connection.execute(
        "INSERT INTO tennis.edition_aliases VALUES "
        "('paris masters @ paris', 2019, 'atp', '2019-1'), "
        "('nowhereville open @ nowhereville', 2019, 'atp', '2019-2')"
    )
    yield connection
    connection.close()


def test_host_country_seed_all_codes_are_three_uppercase_letters():
    codes = load_host_countries().values()

    assert all(len(code) == 3 and code.isupper() for code in codes)


def test_build_edition_geo_known_city_gets_its_host_country(connection):
    build_edition_geo(connection)

    row = connection.execute(
        "SELECT host_city, host_country_ioc FROM analytics.edition_geo WHERE edition_id = '2019-1'"
    ).fetchone()
    assert row == ("paris", "FRA")


def test_build_edition_geo_city_missing_from_the_seed_gets_a_null_country_not_a_guess(connection):
    build_edition_geo(connection)

    row = connection.execute(
        "SELECT host_country_ioc FROM analytics.edition_geo WHERE edition_id = '2019-2'"
    ).fetchone()
    assert row == (None,)


def test_build_edition_geo_rebuild_is_idempotent(connection):
    build_edition_geo(connection)
    build_edition_geo(connection)

    assert connection.execute("SELECT count(*) FROM analytics.edition_geo").fetchone() == (2,)
