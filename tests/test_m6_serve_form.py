"""M6: rolling pre-match serve form — ace/DF/serve-point rates and their consecutive
and trend deltas, computed only over a player's prior matches that recorded a serve
line (tennis.match_stats is sparse), strictly excluding the current match's own stats
(the as-of / no-leak guarantee)."""

from datetime import date

import duckdb
import pandas as pd
import pytest

from tennisdb import config
from tennisdb.features.serve_form import (
    SERVE_FORM_COLUMNS,
    build_serve_form,
    compute_serve_form,
)
from tennisdb.load.publish import SERVE_FORM
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m6

_COLUMNS = [
    "match_id", "edition_id", "winner_id", "loser_id", "order_date", "round",
    "w_ace", "w_df", "w_svpt", "w_1stin", "w_1stwon", "w_2ndwon",
    "w_svgms", "w_bpsaved", "w_bpfaced",
    "l_ace", "l_df", "l_svpt", "l_1stin", "l_1stwon", "l_2ndwon",
    "l_svgms", "l_bpsaved", "l_bpfaced",
]  # fmt: skip


def _matches(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    for column in _COLUMNS:
        if column not in frame:
            frame[column] = None
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


def _stats(role: str, ace=None, df=None, svpt=None, first_in=None, first_won=None,
           second_won=None, sv_games=None, bp_saved=None, bp_faced=None) -> dict:
    prefix = "w" if role == "winner" else "l"
    return {
        f"{prefix}_ace": ace,
        f"{prefix}_df": df,
        f"{prefix}_svpt": svpt,
        f"{prefix}_1stin": first_in,
        f"{prefix}_1stwon": first_won,
        f"{prefix}_2ndwon": second_won,
        f"{prefix}_svgms": sv_games,
        f"{prefix}_bpsaved": bp_saved,
        f"{prefix}_bpfaced": bp_faced,
    }


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    yield connection
    connection.close()


# --- Tier 1: pure-core, no database -----------------------------------------------


def test_first_ever_match_has_no_serve_history():
    row = compute_serve_form(
        _matches([_match("e1-1", 1, 2, "2019-01-07")])
    ).iloc[0]

    assert pd.isna(row.w_ace_rate_3)
    assert pd.isna(row.w_ace_rate_delta_consec)
    assert pd.isna(row.w_ace_rate_delta_trend)
    assert row.w_serve_matches_available == 0


def test_windows_skip_matches_without_a_stats_row():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
                _match("e2-1", 1, 3, "2019-01-08"),  # no stats recorded
                _match("e3-1", 1, 4, "2019-01-15"),  # measured here
            ]
        )
    ).set_index("match_id")

    # The statless match in between must not reset or blank the window.
    assert frame.loc["e3-1"].w_ace_rate_3 == pytest.approx(4 / 40)
    assert frame.loc["e2-1"].w_ace_rate_3 == pytest.approx(4 / 40)


def test_current_match_stats_never_enter_its_own_window():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),  # 0.10
                _match("e2-1", 1, 3, "2019-01-08", **_stats("winner", ace=36, svpt=40)),  # measured
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    # If the current match leaked in, the average of [0.10, 0.90] would be 0.50.
    assert frame.w_ace_rate_3 == pytest.approx(0.10)


def test_single_prior_stat_match_populates_windows_but_leaves_deltas_null():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
                _match("e2-1", 1, 3, "2019-01-08", **_stats("winner", ace=8, svpt=40)),  # measured
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    assert frame.w_ace_rate_3 == pytest.approx(0.10)
    assert frame.w_ace_rate_5 == pytest.approx(0.10)
    assert pd.isna(frame.w_ace_rate_delta_consec)
    assert frame.w_serve_matches_available == 1


def test_delta_consec_measures_the_two_most_recent_recorded_matches():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),  # 0.10
                _match("e2-1", 1, 3, "2019-01-08"),  # statless, must not count as "most recent"
                _match("e3-1", 1, 4, "2019-01-15", **_stats("winner", ace=12, svpt=40)),  # 0.30
                _match("e4-1", 1, 5, "2019-01-22"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e4-1"]

    assert frame.w_ace_rate_delta_consec == pytest.approx(0.30 - 0.10)


def test_delta_trend_equals_short_window_minus_long_window():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
                _match("e2-1", 1, 3, "2019-01-08", **_stats("winner", ace=8, svpt=40)),
                _match("e3-1", 1, 4, "2019-01-15", **_stats("winner", ace=20, svpt=40)),
                _match("e4-1", 1, 5, "2019-01-22"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e4-1"]

    assert frame.w_ace_rate_delta_trend == pytest.approx(frame.w_ace_rate_3 - frame.w_ace_rate_5)


def test_second_serve_points_won_divides_by_serve_points_minus_first_serves_in():
    frame = compute_serve_form(
        _matches(
            [
                _match(
                    "e1-1", 1, 2, "2019-01-01",
                    **_stats("winner", svpt=40, first_in=25, second_won=9),
                ),
                _match("e2-1", 1, 3, "2019-01-08"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    assert frame.w_second_won_pct_2 == pytest.approx(9 / (40 - 25))


def test_break_points_saved_is_null_when_no_break_points_were_faced():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", bp_saved=0, bp_faced=0)),
                _match("e2-1", 1, 3, "2019-01-08"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    assert pd.isna(frame.w_bp_saved_pct_2)


def test_break_point_history_survives_a_match_with_no_break_points_faced():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", bp_saved=2, bp_faced=4)),
                _match("e2-1", 1, 3, "2019-01-08", **_stats("winner", bp_saved=0, bp_faced=0)),
                _match("e3-1", 1, 4, "2019-01-15"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e3-1"]

    # The 0/0 match must not blank the metric for later matches.
    assert frame.w_bp_saved_pct_2 == pytest.approx(2 / 4)


def test_zero_serve_points_yields_null_rather_than_infinity():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=0, svpt=0)),
                _match("e2-1", 1, 3, "2019-01-08"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e2-1"]

    assert pd.isna(frame.w_ace_rate_3)
    assert frame.w_serve_matches_available == 0


def test_features_never_cross_a_player_boundary():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
                _match("e2-1", 1, 3, "2019-01-08", **_stats("winner", ace=8, svpt=40)),
                _match("e3-1", 3, 4, "2019-01-15"),  # player 4 debuts after player 1's history
            ]
        )
    ).set_index("match_id").loc["e3-1"]

    assert pd.isna(frame.l_ace_rate_3)
    assert frame.l_serve_matches_available == 0


def test_compute_is_independent_of_input_row_order():
    rows = [
        _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
        _match("e2-1", 2, 3, "2019-01-08", **_stats("winner", bp_saved=1, bp_faced=2)),
        _match("e3-1", 1, 3, "2019-01-15", **_stats("loser", ace=6, svpt=50)),
    ]

    ordered = compute_serve_form(_matches(rows)).set_index("match_id").sort_index()
    shuffled = compute_serve_form(_matches(list(reversed(rows)))).set_index("match_id").sort_index()

    pd.testing.assert_frame_equal(ordered, shuffled)


def test_same_day_matches_order_by_round():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", round="R32", **_stats("winner", ace=4, svpt=40)),
                _match("e1-2", 1, 3, "2019-01-01", round="Q3", **_stats("winner", ace=20, svpt=40)),
            ]
        )
    ).set_index("match_id")

    # Q3 precedes R32 within the same day (ordering.ROUND_ORDINAL).
    assert pd.isna(frame.loc["e1-2"].w_ace_rate_3)
    assert frame.loc["e1-1"].w_ace_rate_3 == pytest.approx(20 / 40)


def test_availability_counts_only_prior_matches_with_a_recorded_serve_line():
    frame = compute_serve_form(
        _matches(
            [
                _match("e1-1", 1, 2, "2019-01-01", **_stats("winner", ace=4, svpt=40)),
                _match("e2-1", 1, 3, "2019-01-08"),  # statless
                _match("e3-1", 1, 4, "2019-01-15", **_stats("winner", ace=8, svpt=40)),
                _match("e4-1", 1, 5, "2019-01-22"),  # measured here
            ]
        )
    ).set_index("match_id").loc["e4-1"]

    assert frame.w_serve_matches_available == 2


def test_generated_columns_match_the_publish_tuple():
    assert SERVE_FORM.columns == ("match_id", *SERVE_FORM_COLUMNS)


def test_serve_form_has_fifty_nine_columns():
    assert len(SERVE_FORM_COLUMNS) + 1 == 59  # +1 for match_id


# --- Tier 2: in-memory DuckDB, the builder -----------------------------------------


def _add_player(connection, player_id, name):
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name) VALUES (?, 'atp', ?)",
        [player_id, name],
    )


def _add_edition(connection, edition_id, start=date(2019, 1, 7)):
    connection.execute(
        "INSERT INTO tennis.tournament_editions (edition_id, tour, name, surface, season, "
        "start_date) VALUES (?, 'atp', ?, 'Hard', 2019, ?)",
        [edition_id, edition_id, start],
    )


def _add_match_with_stats(
    connection, match_id, edition_id, winner_id, loser_id, match_date, **stats
):
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, winner_id, "
        "loser_id) VALUES (?, ?, 'F', ?, ?, ?)",
        [match_id, edition_id, match_date, winner_id, loser_id],
    )
    if stats:
        columns = ", ".join(stats)
        placeholders = ", ".join("?" for _ in stats)
        connection.execute(
            f"INSERT INTO tennis.match_stats (match_id, {columns}) VALUES (?, {placeholders})",
            [match_id, *stats.values()],
        )


def _seed_players_and_edition(connection):
    for player_id, name in ((1, "Alpha"), (2, "Bravo"), (3, "Charlie")):
        _add_player(connection, player_id, name)
    _add_edition(connection, "2019-1")


def test_build_serve_form_writes_one_row_per_match_including_statless_ones(connection):
    _seed_players_and_edition(connection)
    _add_match_with_stats(
        connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7), w_ace=4, w_svpt=40
    )
    _add_match_with_stats(connection, "2019-1-2", "2019-1", 1, 3, date(2019, 1, 14))

    rows = build_serve_form(connection)

    assert rows == 2


def test_build_serve_form_orients_features_to_the_leak_free_p1_p2(connection):
    _seed_players_and_edition(connection)
    _add_match_with_stats(
        connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7), w_ace=4, w_svpt=40
    )
    _add_match_with_stats(
        connection, "2019-1-2", "2019-1", 1, 3, date(2019, 1, 14), w_ace=36, w_svpt=40
    )

    build_serve_form(connection)

    oriented = connection.execute(
        "SELECT CASE WHEN m.p1_won THEN s.p1_ace_rate_3 ELSE s.p2_ace_rate_3 END "
        "FROM analytics.serve_form s JOIN tennis.matches_model m USING (match_id) "
        "WHERE s.match_id = '2019-1-2'"
    ).fetchone()[0]

    assert oriented == pytest.approx(4 / 40)


def test_build_serve_form_leaves_a_debut_match_null(connection):
    _seed_players_and_edition(connection)
    _add_match_with_stats(
        connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7), w_ace=4, w_svpt=40
    )

    build_serve_form(connection)

    row = connection.execute(
        "SELECT p1_ace_rate_3, p2_ace_rate_3 FROM analytics.serve_form "
        "WHERE match_id = '2019-1-1'"
    ).fetchone()
    assert row == (None, None)


def test_serve_matches_available_is_zero_not_null_for_a_debut(connection):
    _seed_players_and_edition(connection)
    _add_match_with_stats(connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7))

    build_serve_form(connection)

    row = connection.execute(
        "SELECT p1_serve_matches_available, p2_serve_matches_available FROM analytics.serve_form "
        "WHERE match_id = '2019-1-1'"
    ).fetchone()
    assert row == (0, 0)


def test_build_serve_form_is_idempotent(connection):
    _seed_players_and_edition(connection)
    _add_match_with_stats(
        connection, "2019-1-1", "2019-1", 1, 2, date(2019, 1, 7), w_ace=4, w_svpt=40
    )

    build_serve_form(connection)
    build_serve_form(connection)

    assert connection.execute("SELECT count(*) FROM analytics.serve_form").fetchone()[0] == 1


def test_migration_column_order_matches_the_generated_column_order(connection):
    actual = connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'analytics' AND table_name = 'serve_form' "
        "ORDER BY ordinal_position"
    ).fetchall()

    assert tuple(row[0] for row in actual) == ("match_id", *SERVE_FORM_COLUMNS)
