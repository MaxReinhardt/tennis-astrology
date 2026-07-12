"""M4: staging → tennis.* canonical loader — namespacing, cleaning, idempotency."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.ids import WTA_PLAYER_ID_OFFSET
from tennisdb.load.canonical import load_canonical
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m4

_STAT_COLUMNS = (
    "w_ace", "w_df", "w_svpt", "w_1stIn", "w_1stWon", "w_2ndWon",
    "w_SvGms", "w_bpSaved", "w_bpFaced",
    "l_ace", "l_df", "l_svpt", "l_1stIn", "l_1stWon", "l_2ndWon",
    "l_SvGms", "l_bpSaved", "l_bpFaced",
)  # fmt: skip

_PLAYER_DEFAULTS = {
    "tour": "atp",
    "source_file": "sackmann/atp/atp_players.csv",
    "player_id": 101,
    "name_first": "Novak",
    "name_last": "Djokovic",
    "hand": "R",
    "dob": date(1987, 5, 22),
    "ioc": "SRB",
    "height": 188,
    "wikidata_id": None,
}

_MATCH_DEFAULTS = {
    "tour": "atp",
    "source_file": "sackmann/atp/atp_matches_2019.csv",
    "tourney_id": "2019-540",
    "tourney_name": "Wimbledon",
    "surface": "Grass",
    "draw_size": 128,
    "tourney_level": "G",
    "tourney_date": date(2019, 7, 1),
    "match_num": 226,
    "winner_id": 101,
    "loser_id": 102,
    "score": "7-6(5) 1-6 7-6(4) 4-6 13-12(3)",
    "best_of": 5,
    "round": "F",
    "minutes": 296,
    **dict.fromkeys(_STAT_COLUMNS),
    "winner_rank": 1,
    "winner_rank_points": 12415,
    "loser_rank": 3,
    "loser_rank_points": 7130,
}

_RANKING_DEFAULTS = {
    "tour": "atp",
    "source_file": "sackmann/atp/atp_rankings_10s.csv",
    "ranking_date": date(2019, 7, 1),
    "rank": 1,
    "player": 101,
    "points": 12415,
    "tours": None,
}


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    _create_staging_tables(connection)
    yield connection
    connection.close()


def _create_staging_tables(connection):
    stat_columns = ", ".join(f'"{column}" BIGINT' for column in _STAT_COLUMNS)
    connection.execute("CREATE SCHEMA staging")
    connection.execute(
        "CREATE TABLE staging.sackmann_players ("
        "tour VARCHAR, source_file VARCHAR, player_id BIGINT, name_first VARCHAR, "
        "name_last VARCHAR, hand VARCHAR, dob DATE, ioc VARCHAR, height BIGINT, "
        "wikidata_id VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE staging.sackmann_matches ("
        "tour VARCHAR, source_file VARCHAR, tourney_id VARCHAR, tourney_name VARCHAR, "
        "surface VARCHAR, draw_size BIGINT, tourney_level VARCHAR, tourney_date DATE, "
        "match_num BIGINT, winner_id BIGINT, loser_id BIGINT, score VARCHAR, "
        f"best_of BIGINT, round VARCHAR, minutes BIGINT, {stat_columns}, "
        "winner_rank BIGINT, winner_rank_points BIGINT, "
        "loser_rank BIGINT, loser_rank_points BIGINT)"
    )
    connection.execute(
        "CREATE TABLE staging.sackmann_rankings ("
        "tour VARCHAR, source_file VARCHAR, ranking_date DATE, rank BIGINT, "
        "player BIGINT, points BIGINT, tours BIGINT)"
    )


def _insert(connection, table, values):
    columns = ", ".join(f'"{column}"' for column in values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values())
    )


def add_player(connection, **overrides):
    _insert(connection, "staging.sackmann_players", {**_PLAYER_DEFAULTS, **overrides})


def add_match(connection, **overrides):
    _insert(connection, "staging.sackmann_matches", {**_MATCH_DEFAULTS, **overrides})


def add_ranking(connection, **overrides):
    _insert(connection, "staging.sackmann_rankings", {**_RANKING_DEFAULTS, **overrides})


def seed_standard_match(connection, **match_overrides):
    add_player(connection)
    add_player(connection, player_id=102, name_first="Roger", name_last="Federer")
    add_match(connection, **match_overrides)


def test_players_loaded_with_wta_offset_and_composed_name(connection):
    add_player(connection)
    add_player(connection, tour="wta", player_id=202, name_first="Ashleigh", name_last="Barty")

    load_canonical(connection)

    rows = connection.execute(
        "SELECT player_id, tour, full_name FROM tennis.players ORDER BY player_id"
    ).fetchall()
    assert rows == [
        (101, "atp", "Novak Djokovic"),
        (202 + WTA_PLAYER_ID_OFFSET, "wta", "Ashleigh Barty"),
    ]


def test_invalid_hand_and_height_are_nulled(connection):
    add_player(connection, hand="X", height=90)

    report = load_canonical(connection)

    hand, height = connection.execute("SELECT hand, height_cm FROM tennis.players").fetchone()
    assert (hand, height) == (None, None)
    assert report.nulled["players"] == {"hand": 1, "height_cm": 1}


def test_editions_namespaced_and_season_from_id_prefix(connection):
    seed_standard_match(connection)
    add_player(connection, tour="wta", player_id=202, name_first="Simona", name_last="Halep")
    add_player(connection, tour="wta", player_id=203, name_first="Serena", name_last="Williams")
    add_match(
        connection,
        tour="wta",
        tourney_id="2020-1049",
        tourney_date=date(2019, 12, 30),
        winner_id=202,
        loser_id=203,
    )

    load_canonical(connection)

    rows = connection.execute(
        "SELECT edition_id, tour, season FROM tennis.tournament_editions ORDER BY edition_id"
    ).fetchall()
    assert rows == [("2019-540", "atp", 2019), ("wta-2020-1049", "wta", 2020)]


def test_matches_get_namespaced_ids_and_offset_players(connection):
    add_player(connection, tour="wta", player_id=202, name_first="Simona", name_last="Halep")
    add_player(connection, tour="wta", player_id=203, name_first="Serena", name_last="Williams")
    add_match(connection, tour="wta", tourney_id="2019-540", winner_id=202, loser_id=203)

    load_canonical(connection)

    row = connection.execute(
        "SELECT match_id, edition_id, winner_id, loser_id FROM tennis.matches"
    ).fetchone()
    assert row == (
        "wta-2019-540-226",
        "wta-2019-540",
        202 + WTA_PLAYER_ID_OFFSET,
        203 + WTA_PLAYER_ID_OFFSET,
    )


def test_duplicate_staging_match_rows_keep_first_by_source_file(connection):
    seed_standard_match(connection, score="6-4 6-4 6-4")
    add_match(connection, source_file="sackmann/atp/atp_matches_2019_dup.csv", score="0-0")

    report = load_canonical(connection)

    scores = connection.execute("SELECT score FROM tennis.matches").fetchall()
    assert scores == [("6-4 6-4 6-4",)]
    assert report.dropped["matches"]["duplicate"] == 1


def test_matches_with_null_round_same_player_or_unknown_player_are_dropped(connection):
    seed_standard_match(connection)
    add_match(connection, match_num=1, round=None)
    add_match(connection, match_num=2, winner_id=101, loser_id=101)
    add_match(connection, match_num=3, winner_id=999)

    report = load_canonical(connection)

    assert connection.execute("SELECT count(*) FROM tennis.matches").fetchone()[0] == 1
    assert report.dropped["matches"] == {
        "duplicate": 0,
        "null_round": 1,
        "same_player": 1,
        "unknown_player": 1,
    }


def test_out_of_domain_values_are_nulled(connection):
    seed_standard_match(connection, best_of=1, minutes=0, winner_rank=0, winner_rank_points=-5)

    load_canonical(connection)

    row = connection.execute(
        "SELECT best_of, minutes, winner_rank, winner_rank_points, loser_rank "
        "FROM tennis.matches"
    ).fetchone()
    assert row == (None, None, None, None, 3)


def test_retirement_and_walkover_flags_derive_from_score(connection):
    seed_standard_match(connection, match_num=1, score="6-4 2-1 RET")
    add_match(connection, match_num=2, score="W/O")
    add_match(connection, match_num=3, score="6-4 6-4")

    load_canonical(connection)

    rows = connection.execute(
        "SELECT match_id, retirement, walkover FROM tennis.matches ORDER BY match_id"
    ).fetchall()
    assert rows == [
        ("2019-540-1", True, False),
        ("2019-540-2", False, True),
        ("2019-540-3", False, False),
    ]


def test_match_stats_map_mixed_case_columns_and_skip_statless_rows(connection):
    seed_standard_match(connection, match_num=1, w_ace=25, w_1stIn=80, l_bpFaced=12)
    add_match(connection, match_num=2)

    load_canonical(connection)

    rows = connection.execute(
        "SELECT match_id, w_ace, w_1stin, l_bpfaced FROM tennis.match_stats"
    ).fetchall()
    assert rows == [("2019-540-1", 25, 80, 12)]


def test_rankings_deduped_and_offset(connection):
    add_player(connection)
    add_player(connection, tour="wta", player_id=202, name_first="Ashleigh", name_last="Barty")
    add_ranking(connection)
    add_ranking(connection, rank=2, points=11000)
    add_ranking(connection, tour="wta", player=202, rank=1, points=7000)
    add_ranking(connection, player=999)

    report = load_canonical(connection)

    rows = connection.execute(
        "SELECT player_id, rank FROM tennis.rankings ORDER BY player_id"
    ).fetchall()
    assert rows == [(101, 1), (202 + WTA_PLAYER_ID_OFFSET, 1)]
    assert report.dropped["rankings"] == {"duplicate": 1, "unknown_player": 1}


def test_rerun_is_idempotent(connection):
    seed_standard_match(connection)
    add_ranking(connection)

    first = load_canonical(connection)
    second = load_canonical(connection)

    assert first.table_rows == second.table_rows
    assert connection.execute("SELECT count(*) FROM tennis.matches").fetchone()[0] == 1


def test_load_writes_ingest_log_entry(connection):
    seed_standard_match(connection)

    load_canonical(connection)

    step, stats = connection.execute("SELECT step, stats FROM tennis.ingest_log").fetchone()
    assert step == "load:canonical"
    assert '"matches"' in stats


def test_report_summary_lines_mention_each_table(connection):
    seed_standard_match(connection)

    report = load_canonical(connection)

    summary = "\n".join(report.summary_lines())
    for table in ("players", "tournament_editions", "matches", "match_stats", "rankings"):
        assert table in summary
