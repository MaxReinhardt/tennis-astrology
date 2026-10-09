"""M8: the market-relative cross section, on a tiny migrated in-memory warehouse."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget
from tennisdb.research.duckdb_cross_section import DIMENSIONS, DuckDbCrossSection

pytestmark = pytest.mark.m8


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name, country_ioc) VALUES "
        "(1, 'atp', 'Home Hero', 'FRA'), (2, 'atp', 'Visitor', 'ESP')"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions (edition_id, tour, name, season, start_date) "
        "VALUES ('2019-1', 'atp', 'Paris', 2019, DATE '2019-01-01')"
    )
    connection.execute("INSERT INTO analytics.edition_geo VALUES ('2019-1', 'paris', 'FRA')")
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, winner_id, "
        "loser_id) VALUES ('2019-1-1', '2019-1', 'F', DATE '2019-01-02', 1, 2)"
    )
    connection.execute(
        "INSERT INTO analytics.market (match_id, bookmaker, p1_market_prob, p2_market_prob) "
        "SELECT match_id, 'Avg', 0.5, 0.5 FROM tennis.matches"
    )
    yield connection
    connection.close()


def test_host_nation_cross_section_splits_home_and_visitor_observations(connection):
    outcomes = {o.group: o for o in DuckDbCrossSection(connection).outcomes("host_nation")}

    assert {name: (o.trials, o.successes) for name, o in outcomes.items()} == {
        "home": (1, 1),
        "visitor": (1, 0),
    }
    assert outcomes["home"].expected_successes == pytest.approx(0.5)


def test_host_nation_cross_section_both_players_at_home_is_excluded(connection):
    connection.execute("UPDATE tennis.players SET country_ioc = 'FRA'")

    assert DuckDbCrossSection(connection).outcomes("host_nation") == []


def test_every_registered_dimension_executes(connection):
    for name in DIMENSIONS:
        DuckDbCrossSection(connection).outcomes(name)
