"""M6: rolling pre-match form — win%, rest days, recent load, head-to-head, age, all
strictly excluding the current match (the as-of / no-leak guarantee)."""

import duckdb
import pandas as pd
import pytest

from tennisdb import config
from tennisdb.features.form import build_form, compute_form
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m6

_COLUMNS = [
    "match_id", "edition_id", "winner_id", "loser_id",
    "order_date", "round", "winner_dob", "loser_dob",
]  # fmt: skip


def _matches(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ("order_date", "winner_dob", "loser_dob"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    for column in _COLUMNS:
        if column not in frame:
            frame[column] = pd.NaT if "dob" in column else None
    return frame[_COLUMNS]


def _match(match_id, winner, loser, order_date, **extra) -> dict:
    return {
        "match_id": match_id,
        "edition_id": match_id.rsplit("-", 1)[0],
        "winner_id": winner,
        "loser_id": loser,
        "order_date": order_date,
        "round": "F",
        **extra,
    }


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    yield connection
    connection.close()


def test_first_ever_match_has_no_prior_form():
    form = compute_form(_matches([_match("e1-1", 1, 2, "2019-01-07")])).iloc[0]

    assert pd.isna(form.w_win_pct_10)
    assert pd.isna(form.w_rest_days)
    assert form.w_matches_14d == 0
    assert form.w_prior_wins == 0
    assert form.l_prior_wins == 0


def test_win_percentage_averages_only_prior_results():
    form = compute_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-07"),  # player 1 wins
                _match("e2-1", 3, 1, "2019-01-14"),  # player 1 loses
                _match("e3-1", 1, 2, "2019-01-21"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e3-1"]

    assert form.w_win_pct_10 == pytest.approx(0.5)  # player 1: mean of [win, loss]
    assert form.l_win_pct_10 == pytest.approx(0.0)  # player 2: only a prior loss


def test_rest_days_measures_the_gap_since_a_players_previous_match():
    form = compute_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-07"),
                _match("e2-1", 1, 3, "2019-01-14"),
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    assert form.w_rest_days == 7


def test_recent_match_count_only_spans_the_trailing_window():
    form = compute_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01"),
                _match("e2-1", 1, 3, "2019-01-07"),
                _match("e3-1", 1, 4, "2019-01-20"),
            ]
        )
    ).set_index("match_id")

    assert form.loc["e2-1"].w_matches_14d == 1  # Jan 1 within 14 days
    assert form.loc["e3-1"].w_matches_14d == 1  # only Jan 7 within 14 days of Jan 20


def test_head_to_head_counts_prior_meetings_by_eventual_result():
    form = compute_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-07"),  # 1 beats 2
                _match("e2-1", 2, 1, "2019-01-14"),  # 2 beats 1
                _match("e3-1", 1, 2, "2019-01-21"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e3-1"]

    assert form.w_prior_wins == 1  # player 1 had beaten player 2 once
    assert form.l_prior_wins == 1  # player 2 had beaten player 1 once


def test_age_derives_from_date_of_birth():
    form = compute_form(
        _matches(
            [_match("e1-1", 1, 2, "2020-01-01", winner_dob="2000-01-01")]
        )
    ).iloc[0]

    assert form.w_age_years == pytest.approx(20.0, abs=0.05)


def _seed_two_meetings(connection):
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name, dob) VALUES "
        "(1, 'atp', 'Alpha', DATE '1990-01-01'), (2, 'atp', 'Bravo', DATE '1992-06-01')"
    )
    for edition in ("2019-1", "2019-2"):
        connection.execute(
            "INSERT INTO tennis.tournament_editions (edition_id, tour, name, surface, season, "
            "start_date) VALUES (?, 'atp', ?, 'Hard', 2019, DATE '2019-01-07')",
            [edition, edition],
        )
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, winner_id, "
        "loser_id) VALUES ('2019-1-1', '2019-1', 'F', DATE '2019-01-07', 1, 2), "
        "('2019-2-1', '2019-2', 'F', DATE '2019-02-07', 2, 1)"
    )


def test_build_form_populates_head_to_head_and_rest_for_a_rematch(connection):
    _seed_two_meetings(connection)

    rows = build_form(connection)

    assert rows == 2
    rematch = connection.execute(
        "SELECT h2h_total, p1_rest_days, p2_rest_days FROM analytics.form "
        "WHERE match_id = '2019-2-1'"
    ).fetchone()
    assert rematch == (1, 31, 31)


def test_build_form_leaves_first_match_form_null(connection):
    _seed_two_meetings(connection)

    build_form(connection)

    first = connection.execute(
        "SELECT p1_win_pct_10, p2_win_pct_10, h2h_total FROM analytics.form "
        "WHERE match_id = '2019-1-1'"
    ).fetchone()
    assert first == (None, None, 0)
