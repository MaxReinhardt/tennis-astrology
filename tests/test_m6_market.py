"""M6: market features — closing-book selection, novig p1/p2 orientation, Max/Avg
dispersion, and exclusion of matches without odds."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.features.market import build_market
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m6


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name) VALUES "
        "(1, 'atp', 'Alpha'), (2, 'atp', 'Bravo')"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions (edition_id, tour, name, surface, season) "
        "VALUES ('2019-1', 'atp', 'Open', 'Hard', 2019)"
    )
    yield connection
    connection.close()


def _add_match(connection, match_id, winner=1, loser=2):
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, winner_id, "
        "loser_id) VALUES (?, '2019-1', 'F', ?, ?, ?)",
        [match_id, date(2019, 1, 7), winner, loser],
    )


def _add_odds(connection, match_id, bookmaker, winner_odds, loser_odds):
    connection.execute(
        "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
        "VALUES (?, ?, ?, ?)",
        [match_id, bookmaker, winner_odds, loser_odds],
    )


def test_market_probability_is_oriented_to_the_actual_winner(connection):
    _add_match(connection, "2019-1-1")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)

    build_market(connection)

    winner_prob = connection.execute(
        "SELECT CASE WHEN m.p1_won THEN k.p1_market_prob ELSE k.p2_market_prob END "
        "FROM analytics.market k JOIN tennis.matches_model m USING (match_id)"
    ).fetchone()[0]
    assert winner_prob == pytest.approx(0.625, abs=1e-3)


def test_probabilities_sum_to_one(connection):
    _add_match(connection, "2019-1-1")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)

    build_market(connection)

    p1, p2 = connection.execute(
        "SELECT p1_market_prob, p2_market_prob FROM analytics.market"
    ).fetchone()
    assert p1 + p2 == pytest.approx(1.0)


def test_average_book_is_preferred_over_pinnacle(connection):
    _add_match(connection, "2019-1-1")
    _add_odds(connection, "2019-1-1", "PS", 1.6, 2.4)
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)

    build_market(connection)

    assert connection.execute("SELECT bookmaker FROM analytics.market").fetchone()[0] == "Avg"


def test_pinnacle_is_used_when_average_is_absent(connection):
    _add_match(connection, "2019-1-1")
    _add_odds(connection, "2019-1-1", "PS", 1.6, 2.4)

    build_market(connection)

    assert connection.execute("SELECT bookmaker FROM analytics.market").fetchone()[0] == "PS"


def test_dispersion_measures_max_versus_average_novig_gap(connection):
    _add_match(connection, "2019-1-1")
    _add_odds(connection, "2019-1-1", "Avg", 2.0, 2.0)  # winner novig prob 0.5
    _add_odds(connection, "2019-1-1", "Max", 2.5, 1.8)  # winner novig prob ~0.4186

    build_market(connection)

    dispersion = connection.execute(
        "SELECT max_avg_dispersion FROM analytics.market"
    ).fetchone()[0]
    assert dispersion == pytest.approx(0.0814, abs=1e-3)


def test_matches_without_odds_are_absent(connection):
    _add_match(connection, "2019-1-1")
    _add_match(connection, "2019-1-2")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)

    build_market(connection)

    present = connection.execute("SELECT match_id FROM analytics.market").fetchall()
    assert present == [("2019-1-1",)]
