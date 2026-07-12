"""M4: tennis-data (Tournament, Location, season, tour) → Sackmann edition ids."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget
from tennisdb.resolve.tournaments import resolve_editions

pytestmark = pytest.mark.m4


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "CREATE SCHEMA staging;"
        "CREATE TABLE staging.tennisdata_matches "
        "(tour VARCHAR, season BIGINT, Tournament VARCHAR, Location VARCHAR, Date DATE)"
    )
    yield connection
    connection.close()


@pytest.fixture
def seed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SEED_DIR", tmp_path)
    return tmp_path


def add_edition(connection, edition_id, tour, name, start_date, season, level="A"):
    connection.execute(
        "INSERT INTO tennis.tournament_editions VALUES (?, ?, ?, 'Hard', ?, 32, ?, ?)",
        [edition_id, tour, name, level, start_date, season],
    )


def add_group_row(connection, tour, season, tournament, location, match_date):
    connection.execute(
        "INSERT INTO staging.tennisdata_matches VALUES (?, ?, ?, ?, ?)",
        [tour, season, tournament, location, match_date],
    )


def test_unique_overlapping_candidate_resolves(connection, seed_dir):
    add_edition(connection, "2019-540", "atp", "Wimbledon", date(2019, 7, 1), 2019, level="G")
    add_group_row(connection, "atp", 2019, "Wimbledon", "London", date(2019, 7, 14))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "Wimbledon", "London") == "2019-540"


def test_sponsor_name_resolves_via_location(connection, seed_dir):
    add_edition(connection, "2019-404", "atp", "Indian Wells Masters", date(2019, 3, 4), 2019)
    add_group_row(connection, "atp", 2019, "BNP Paribas Open", "Indian Wells", date(2019, 3, 8))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "BNP Paribas Open", "Indian Wells") == "2019-404"


def test_date_window_excludes_distant_edition_with_same_name(connection, seed_dir):
    add_edition(connection, "2021-001", "atp", "Belgrade", date(2021, 4, 19), 2021)
    add_edition(connection, "2021-002", "atp", "Belgrade 2", date(2021, 10, 18), 2021)
    add_group_row(connection, "atp", 2021, "Serbia Open", "Belgrade", date(2021, 4, 21))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2021, "Serbia Open", "Belgrade") == "2021-001"


def test_same_week_same_score_candidates_stay_unresolved(connection, seed_dir):
    add_edition(connection, "2020-8888", "atp", "Cologne 1", date(2020, 10, 12), 2020)
    add_edition(connection, "2020-8889", "atp", "Cologne 2", date(2020, 10, 19), 2020)
    add_group_row(connection, "atp", 2020, "bett1HULKS Indoors", "Cologne", date(2020, 10, 14))
    add_group_row(connection, "atp", 2020, "bett1HULKS Indoors", "Cologne", date(2020, 10, 18))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2020, "bett1HULKS Indoors", "Cologne") is None
    assert ("atp", 2020, "bett1HULKS Indoors", "Cologne") in editions.unresolved


def test_best_score_with_clear_margin_wins(connection, seed_dir):
    add_edition(connection, "2019-403", "atp", "Miami Masters", date(2019, 3, 20), 2019)
    add_edition(connection, "2019-404", "atp", "Indian Wells Masters", date(2019, 3, 4), 2019)
    add_group_row(connection, "atp", 2019, "Miami Open", "Miami", date(2019, 3, 21))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "Miami Open", "Miami") == "2019-403"


def test_known_synonym_bridges_french_open_to_roland_garros(connection, seed_dir):
    add_edition(connection, "2019-520", "atp", "Roland Garros", date(2019, 5, 27), 2019, level="G")
    add_edition(connection, "2019-7161", "atp", "Lyon", date(2019, 5, 19), 2019)
    add_group_row(connection, "atp", 2019, "French Open", "Paris", date(2019, 5, 28))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "French Open", "Paris") == "2019-520"


def test_tournament_name_outranks_city_named_neighbour(connection, seed_dir):
    add_edition(connection, "2022-580", "atp", "Australian Open", date(2022, 1, 17), 2022,
                level="G")
    add_edition(connection, "2022-8998", "atp", "Melbourne", date(2022, 1, 4), 2022)
    add_group_row(connection, "atp", 2022, "Australian Open", "Melbourne", date(2022, 1, 18))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2022, "Australian Open", "Melbourne") == "2022-580"


def test_davis_cup_editions_are_not_candidates(connection, seed_dir):
    add_edition(connection, "2019-D001", "atp", "Davis Cup: London Tie", date(2019, 7, 10), 2019,
                level="D")
    add_group_row(connection, "atp", 2019, "London Tie", "London", date(2019, 7, 12))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "London Tie", "London") is None


def test_wrong_season_is_not_a_candidate(connection, seed_dir):
    add_edition(connection, "2018-540", "atp", "Wimbledon", date(2018, 7, 2), 2018, level="G")
    add_group_row(connection, "atp", 2019, "Wimbledon", "London", date(2019, 7, 3))

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "Wimbledon", "London") is None


def test_null_group_dates_skip_the_window_filter(connection, seed_dir):
    add_edition(connection, "2019-540", "atp", "Wimbledon", date(2019, 7, 1), 2019, level="G")
    add_group_row(connection, "atp", 2019, "Wimbledon", "London", None)

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2019, "Wimbledon", "London") == "2019-540"


def test_seed_overrides_scoring(connection, seed_dir):
    add_edition(connection, "2020-8888", "atp", "Cologne 1", date(2020, 10, 12), 2020)
    add_edition(connection, "2020-8889", "atp", "Cologne 2", date(2020, 10, 19), 2020)
    add_group_row(connection, "atp", 2020, "bett1HULKS Indoors", "Cologne", date(2020, 10, 14))
    (seed_dir / "edition_aliases.csv").write_text(
        "alias,season,tour,edition_id,comment\n"
        "bett1hulks indoors @ cologne,2020,atp,2020-8888,first Cologne week\n"
    )

    editions = resolve_editions(connection)

    assert editions.lookup("atp", 2020, "bett1HULKS Indoors", "Cologne") == "2020-8888"


def test_alias_rows_use_folded_group_alias(connection, seed_dir):
    add_edition(connection, "2019-540", "atp", "Wimbledon", date(2019, 7, 1), 2019, level="G")
    add_group_row(connection, "atp", 2019, "Wimbledon", "London", date(2019, 7, 14))

    editions = resolve_editions(connection)

    assert editions.alias_rows() == [("wimbledon @ london", 2019, "atp", "2019-540")]
