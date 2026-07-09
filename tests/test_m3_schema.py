"""M3: canonical tennis schema — expected objects, idempotency, constraint enforcement."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m3

EXPECTED_TENNIS_OBJECTS = {
    "players",
    "tournament_editions",
    "matches",
    "match_stats",
    "rankings",
    "odds",
    "player_aliases",
    "edition_aliases",
    "ingest_log",
    "schema_migrations",
    "matches_model",
    "odds_implied",
}


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    scripts = load_migration_scripts(config.MIGRATIONS_DIR)
    run_migrations(scripts, DuckDbMigrationTarget(connection))
    yield connection
    connection.close()


def _seed_one_match(connection):
    connection.execute(
        "INSERT INTO tennis.players VALUES "
        "(101, 'atp', 'Novak Djokovic', 'R', DATE '1987-05-22', 'SRB', 188, NULL), "
        "(102, 'atp', 'Roger Federer', 'R', DATE '1981-08-08', 'SUI', 185, NULL)"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions VALUES "
        "('2019-540', 'atp', 'Wimbledon', 'Grass', 'G', 128, DATE '2019-07-01', 2019)"
    )
    connection.execute(
        "INSERT INTO tennis.matches "
        "(match_id, edition_id, round, best_of, match_date, winner_id, loser_id, score) "
        "VALUES ('2019-540-701', '2019-540', 'F', 5, DATE '2019-07-14', 101, 102, "
        "'7-6(5) 1-6 7-6(4) 4-6 13-12(3)')"
    )


def test_migrations_create_expected_tennis_objects(connection):
    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'tennis'"
    ).fetchall()

    assert {row[0] for row in rows} == EXPECTED_TENNIS_OBJECTS


def test_rerunning_migrations_applies_nothing(connection):
    scripts = load_migration_scripts(config.MIGRATIONS_DIR)

    report = run_migrations(scripts, DuckDbMigrationTarget(connection))

    assert report.applied == []
    assert report.summary_lines() == ["duckdb: 0 changes"]


def test_odds_with_unknown_match_id_violates_foreign_key(connection):
    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
            "VALUES ('no-such-match', 'B365', 1.5, 2.5)"
        )


def test_odds_at_or_below_one_violates_check(connection):
    _seed_one_match(connection)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
            "VALUES ('2019-540-701', 'B365', 1.0, 2.5)"
        )


def test_odds_above_thousand_violates_check(connection):
    _seed_one_match(connection)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
            "VALUES ('2019-540-701', 'B365', 1.5, 1500)"
        )


def test_duplicate_match_bookmaker_pair_violates_primary_key(connection):
    _seed_one_match(connection)
    insert = (
        "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
        "VALUES ('2019-540-701', 'B365', 1.5, 2.5)"
    )
    connection.execute(insert)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(insert)


def test_player_tour_outside_atp_wta_violates_check(connection):
    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.players VALUES "
            "(1, 'itf', 'Nobody Real', 'R', NULL, NULL, NULL, NULL)"
        )


def test_best_of_four_violates_check(connection):
    _seed_one_match(connection)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.matches "
            "(match_id, edition_id, round, best_of, winner_id, loser_id) "
            "VALUES ('2019-540-702', '2019-540', 'SF', 4, 101, 102)"
        )


def test_unknown_round_violates_check(connection):
    _seed_one_match(connection)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.matches "
            "(match_id, edition_id, round, best_of, winner_id, loser_id) "
            "VALUES ('2019-540-702', '2019-540', 'R256', 3, 101, 102)"
        )


def test_winner_equals_loser_violates_check(connection):
    _seed_one_match(connection)

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            "INSERT INTO tennis.matches "
            "(match_id, edition_id, round, best_of, winner_id, loser_id) "
            "VALUES ('2019-540-702', '2019-540', 'SF', 3, 101, 101)"
        )
