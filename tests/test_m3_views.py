"""M3: modeling and market views — p1/p2 assignment contract and novig math."""

import hashlib

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m3

P1_HEX_DIGITS = set("01234567")


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    scripts = load_migration_scripts(config.MIGRATIONS_DIR)
    run_migrations(scripts, DuckDbMigrationTarget(connection))
    _seed_matches(connection, count=20)
    yield connection
    connection.close()


def _seed_matches(connection, count):
    connection.execute(
        "INSERT INTO tennis.players VALUES "
        "(101, 'atp', 'Novak Djokovic', 'R', DATE '1987-05-22', 'SRB', 188, NULL), "
        "(102, 'atp', 'Roger Federer', 'R', DATE '1981-08-08', 'SUI', 185, NULL)"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions VALUES "
        "('2019-540', 'atp', 'Wimbledon', 'Grass', 'G', 128, DATE '2019-07-01', 2019)"
    )
    for match_number in range(1, count + 1):
        connection.execute(
            "INSERT INTO tennis.matches "
            "(match_id, edition_id, round, best_of, match_date, winner_id, loser_id) "
            "VALUES (?, '2019-540', 'R32', 3, DATE '2019-07-02', 101, 102)",
            [f"2019-540-{match_number}"],
        )


def _insert_odds(connection, match_id, bookmaker, winner_odds, loser_odds):
    connection.execute(
        "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
        "VALUES (?, ?, ?, ?)",
        [match_id, bookmaker, winner_odds, loser_odds],
    )


def test_matches_model_partitions_winner_and_loser_between_p1_and_p2(connection):
    rows = connection.execute(
        "SELECT model.p1_id, model.p2_id, model.p1_won, matches.winner_id, matches.loser_id "
        "FROM tennis.matches_model AS model "
        "JOIN tennis.matches AS matches USING (match_id)"
    ).fetchall()

    for p1_id, p2_id, p1_won, winner_id, loser_id in rows:
        assert {p1_id, p2_id} == {winner_id, loser_id}
        assert (p1_id == winner_id) is p1_won


def test_matches_model_p1_won_agrees_with_python_md5_hash(connection):
    rows = connection.execute("SELECT match_id, p1_won FROM tennis.matches_model").fetchall()

    assert rows
    for match_id, p1_won in rows:
        first_hex_digit = hashlib.md5(match_id.encode()).hexdigest()[0]
        assert p1_won is (first_hex_digit in P1_HEX_DIGITS)


def test_matches_model_produces_both_orientations(connection):
    orientations = connection.execute(
        "SELECT DISTINCT p1_won FROM tennis.matches_model"
    ).fetchall()

    assert {row[0] for row in orientations} == {True, False}


def test_odds_implied_equal_odds_split_evenly_with_expected_overround(connection):
    _insert_odds(connection, "2019-540-1", "Avg", 1.90, 1.90)

    row = connection.execute(
        "SELECT p_winner_novig, p_loser_novig, overround FROM tennis.odds_implied "
        "WHERE match_id = '2019-540-1'"
    ).fetchone()

    assert row[0] == pytest.approx(0.5)
    assert row[1] == pytest.approx(0.5)
    assert row[2] == pytest.approx(2 / 1.90 - 1)


def test_odds_implied_asymmetric_odds_match_hand_computed_values(connection):
    _insert_odds(connection, "2019-540-2", "PS", 1.30, 3.75)

    row = connection.execute(
        "SELECT raw_winner_prob, raw_loser_prob, p_winner_novig, p_loser_novig, overround "
        "FROM tennis.odds_implied WHERE match_id = '2019-540-2'"
    ).fetchone()

    raw_winner, raw_loser = 1 / 1.30, 1 / 3.75
    assert row[0] == pytest.approx(raw_winner)
    assert row[1] == pytest.approx(raw_loser)
    assert row[2] == pytest.approx(raw_winner / (raw_winner + raw_loser))
    assert row[3] == pytest.approx(raw_loser / (raw_winner + raw_loser))
    assert row[4] == pytest.approx(raw_winner + raw_loser - 1)


def test_odds_implied_novig_probabilities_sum_to_one(connection):
    _insert_odds(connection, "2019-540-3", "B365", 1.44, 2.88)

    row = connection.execute(
        "SELECT p_winner_novig + p_loser_novig FROM tennis.odds_implied "
        "WHERE match_id = '2019-540-3'"
    ).fetchone()

    assert row[0] == pytest.approx(1.0)


def test_odds_implied_omits_rows_missing_either_price(connection):
    _insert_odds(connection, "2019-540-4", "Max", 1.85, None)
    _insert_odds(connection, "2019-540-5", "Max", None, 2.10)

    count = connection.execute(
        "SELECT count(*) FROM tennis.odds_implied WHERE match_id IN "
        "('2019-540-4', '2019-540-5')"
    ).fetchone()[0]

    assert count == 0
