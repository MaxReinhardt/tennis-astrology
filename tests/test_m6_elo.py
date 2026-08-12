"""M6: pre-match Elo — new players at 1500, sequential updates, surface independence,
leak-free p1/p2 orientation, and order-independence (the as-of guarantee)."""

from datetime import date

import duckdb
import pandas as pd
import pytest

from tennisdb import config
from tennisdb.features.elo import build_elo, compute_elo_pre
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m6

_COLUMNS = ["match_id", "edition_id", "winner_id", "loser_id", "surface", "order_date", "round"]


def _matches(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=_COLUMNS)
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    return frame


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    yield connection
    connection.close()


def _add_player(connection, player_id, name):
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name) VALUES (?, 'atp', ?)",
        [player_id, name],
    )


def _add_edition(connection, edition_id, surface, start=date(2019, 1, 7)):
    connection.execute(
        "INSERT INTO tennis.tournament_editions (edition_id, tour, name, surface, season, "
        "start_date) VALUES (?, 'atp', ?, ?, 2019, ?)",
        [edition_id, edition_id, surface, start],
    )


def _add_match(connection, match_id, edition_id, winner_id, loser_id, match_date):
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, winner_id, "
        "loser_id) VALUES (?, ?, 'F', ?, ?, ?)",
        [match_id, edition_id, match_date, winner_id, loser_id],
    )


def test_first_ever_match_snapshots_both_players_at_the_base_rating():
    ratings = compute_elo_pre(
        _matches([("m1", "e1", 1, 2, "Hard", "2019-01-07", "F")])
    )

    row = ratings.iloc[0]
    assert row.w_elo_pre == 1500.0
    assert row.l_elo_pre == 1500.0
    assert row.w_surface_elo_pre == 1500.0
    assert row.l_surface_elo_pre == 1500.0


def test_winner_gains_and_loser_loses_symmetrically_from_equal_ratings():
    ratings = compute_elo_pre(
        _matches(
            [
                ("m1", "e1", 1, 2, "Hard", "2019-01-07", "F"),
                ("m2", "e2", 1, 2, "Hard", "2019-02-07", "F"),
            ]
        )
    )

    second = ratings.set_index("match_id").loc["m2"]
    assert second.w_elo_pre > 1500.0 > second.l_elo_pre
    assert second.w_elo_pre + second.l_elo_pre == pytest.approx(3000.0)


def test_surface_ladder_is_independent_of_the_overall_ladder():
    ratings = compute_elo_pre(
        _matches(
            [
                ("m1", "e1", 1, 2, "Clay", "2019-01-07", "F"),
                ("m2", "e2", 1, 2, "Hard", "2019-02-07", "F"),
            ]
        )
    ).set_index("match_id")

    hard = ratings.loc["m2"]
    assert hard.w_elo_pre > 1500.0  # overall carried over from the clay win
    assert hard.w_surface_elo_pre == 1500.0  # hard-court ladder still fresh
    assert hard.l_surface_elo_pre == 1500.0


def test_compute_is_independent_of_input_row_order():
    rows = [
        ("m1", "e1", 1, 2, "Hard", "2019-01-07", "F"),
        ("m2", "e2", 2, 3, "Clay", "2019-02-07", "F"),
        ("m3", "e3", 1, 3, "Hard", "2019-03-07", "F"),
    ]

    ordered = compute_elo_pre(_matches(rows)).set_index("match_id").sort_index()
    shuffled = compute_elo_pre(_matches(list(reversed(rows)))).set_index("match_id").sort_index()

    pd.testing.assert_frame_equal(ordered, shuffled)


def test_build_elo_orients_ratings_to_the_leak_free_p1_p2(connection):
    for player_id, name in ((1, "Alpha"), (2, "Bravo")):
        _add_player(connection, player_id, name)
    _add_edition(connection, "2019-1", "Hard")
    _add_edition(connection, "2019-2", "Hard")
    _add_match(connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7))
    _add_match(connection, "2019-2-1", "2019-2", 1, 2, date(2019, 2, 7))

    rows = build_elo(connection)

    assert rows == 2
    favored_matches_winner = connection.execute(
        "SELECT bool_and((e.p1_elo_pre > e.p2_elo_pre) = m.p1_won) "
        "FROM analytics.elo_pre e JOIN tennis.matches_model m USING (match_id) "
        "WHERE e.match_id = '2019-2-1'"
    ).fetchone()[0]
    assert favored_matches_winner


def test_build_elo_is_idempotent(connection):
    for player_id, name in ((1, "Alpha"), (2, "Bravo")):
        _add_player(connection, player_id, name)
    _add_edition(connection, "2019-1", "Hard")
    _add_match(connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7))

    build_elo(connection)
    build_elo(connection)

    assert connection.execute("SELECT count(*) FROM analytics.elo_pre").fetchone()[0] == 1
