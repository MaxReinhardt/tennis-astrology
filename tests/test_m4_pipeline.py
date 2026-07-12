"""M4: end-to-end resolution pipeline on a miniature in-memory warehouse."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.load.canonical import load_canonical
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget
from tennisdb.resolve.pipeline import run_resolution

pytestmark = pytest.mark.m4

_STAT_COLUMNS = ", ".join(
    f'"{column}" BIGINT'
    for column in (
        "w_ace", "w_df", "w_svpt", "w_1stIn", "w_1stWon", "w_2ndWon",
        "w_SvGms", "w_bpSaved", "w_bpFaced",
        "l_ace", "l_df", "l_svpt", "l_1stIn", "l_1stWon", "l_2ndWon",
        "l_SvGms", "l_bpSaved", "l_bpFaced",
    )
)


@pytest.fixture
def connection(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SEED_DIR", tmp_path / "seed")
    monkeypatch.setattr(config, "QUALITY_DIR", tmp_path / "quality")
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    _create_and_fill_staging(connection)
    load_canonical(connection)
    yield connection
    connection.close()


def _create_and_fill_staging(connection):
    connection.execute(
        "CREATE SCHEMA staging;"
        "CREATE TABLE staging.sackmann_players ("
        "tour VARCHAR, source_file VARCHAR, player_id BIGINT, name_first VARCHAR, "
        "name_last VARCHAR, hand VARCHAR, dob DATE, ioc VARCHAR, height BIGINT, "
        "wikidata_id VARCHAR);"
        "CREATE TABLE staging.sackmann_matches ("
        "tour VARCHAR, source_file VARCHAR, tourney_id VARCHAR, tourney_name VARCHAR, "
        "surface VARCHAR, draw_size BIGINT, tourney_level VARCHAR, tourney_date DATE, "
        "match_num BIGINT, winner_id BIGINT, loser_id BIGINT, score VARCHAR, "
        f"best_of BIGINT, round VARCHAR, minutes BIGINT, {_STAT_COLUMNS}, "
        "winner_rank BIGINT, winner_rank_points BIGINT, "
        "loser_rank BIGINT, loser_rank_points BIGINT);"
        "CREATE TABLE staging.sackmann_rankings ("
        "tour VARCHAR, source_file VARCHAR, ranking_date DATE, rank BIGINT, "
        "player BIGINT, points BIGINT, tours BIGINT);"
        "CREATE TABLE staging.tennisdata_matches ("
        "tour VARCHAR, season BIGINT, Tournament VARCHAR, Location VARCHAR, "
        '"Date" DATE, round VARCHAR, Winner VARCHAR, Loser VARCHAR, '
        "WRank BIGINT, LRank BIGINT, B365W DOUBLE, B365L DOUBLE, PSW DOUBLE, PSL DOUBLE, "
        "MaxW DOUBLE, MaxL DOUBLE, AvgW DOUBLE, AvgL DOUBLE, "
        "source_file VARCHAR, source_row BIGINT)"
    )
    connection.execute(
        "INSERT INTO staging.sackmann_players (tour, player_id, name_first, name_last) VALUES "
        "('atp', 104925, 'Novak', 'Djokovic'), ('atp', 103819, 'Roger', 'Federer')"
    )
    connection.execute(
        "INSERT INTO staging.sackmann_matches "
        "(tour, source_file, tourney_id, tourney_name, surface, tourney_level, tourney_date, "
        " match_num, winner_id, loser_id, score, best_of, round, winner_rank, loser_rank) VALUES "
        "('atp', 'f', '2019-540', 'Wimbledon', 'Grass', 'G', DATE '2019-07-01', "
        " 226, 104925, 103819, '7-6(5) 1-6 7-6(4) 4-6 13-12(3)', 5, 'F', 1, 3)"
    )
    connection.execute(
        "INSERT INTO staging.tennisdata_matches VALUES "
        "('atp', 2019, 'Wimbledon', 'London', DATE '2019-07-14', 'F', 'Djokovic N.', "
        " 'Federer R.', 1, 3, 1.66, 2.2, 1.71, 2.26, 1.73, 2.3, 1.68, 2.22, "
        " 'tennisdata/atp/2019.xlsx', 55), "
        "('atp', 2019, 'Wimbledon', 'London', DATE '2019-07-13', 'SF', 'Nobody X.', "
        " 'Federer R.', 999, 3, 2.0, 1.8, NULL, NULL, NULL, NULL, 2.0, 1.8, "
        " 'tennisdata/atp/2019.xlsx', 54)"
    )


def test_pipeline_emits_odds_aliases_report_and_unmatched_csv(connection):
    report = run_resolution(connection)

    assert report.total_rows == 2
    assert report.resolved_rows == 1
    assert report.odds_rows == 4
    assert report.reason_counts == {"player_unresolved": 1}
    assert report.season_tour_counts == {(2019, "atp"): (1, 2)}

    odds = connection.execute(
        "SELECT match_id, bookmaker FROM tennis.odds ORDER BY bookmaker"
    ).fetchall()
    assert odds == [
        ("2019-540-226", "Avg"), ("2019-540-226", "B365"),
        ("2019-540-226", "Max"), ("2019-540-226", "PS"),
    ]
    player_aliases = connection.execute(
        "SELECT alias, tour, player_id FROM tennis.player_aliases ORDER BY alias"
    ).fetchall()
    assert ("djokovic n.", "atp", 104925) in player_aliases
    assert connection.execute("SELECT alias, season, tour, edition_id "
                              "FROM tennis.edition_aliases").fetchall() == [
        ("wimbledon @ london", 2019, "atp", "2019-540")
    ]

    unmatched_lines = report.unmatched_path.read_text().strip().splitlines()
    assert len(unmatched_lines) == 2
    assert unmatched_lines[1].startswith("player_unresolved,atp,2019,Wimbledon,London")

    steps = [row[0] for row in connection.execute("SELECT step FROM tennis.ingest_log").fetchall()]
    assert "resolve:matches" in steps


def test_rerunning_resolution_is_idempotent(connection):
    first = run_resolution(connection)
    second = run_resolution(connection)

    assert first.odds_rows == second.odds_rows
    assert connection.execute("SELECT count(*) FROM tennis.odds").fetchone()[0] == 4


def test_summary_lines_carry_rate_and_reasons(connection):
    report = run_resolution(connection)

    summary = "\n".join(report.summary_lines())
    assert "resolved 1/2" in summary
    assert "player_unresolved" in summary
    assert "2019: atp 50.0%" in summary
