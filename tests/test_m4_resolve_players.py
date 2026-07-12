"""M4: tennis-data player names → canonical Sackmann ids (seed > exact > fuzzy)."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.ids import WTA_PLAYER_ID_OFFSET
from tennisdb.resolve.players import resolve_player_aliases

pytestmark = pytest.mark.m4

_ACTIVE_DATE = date(2019, 7, 1)


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE SCHEMA staging")
    connection.execute(
        "CREATE TABLE staging.sackmann_players "
        "(tour VARCHAR, player_id BIGINT, name_first VARCHAR, name_last VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE staging.sackmann_matches "
        "(tour VARCHAR, tourney_date DATE, winner_id BIGINT, loser_id BIGINT)"
    )
    connection.execute(
        "CREATE TABLE staging.tennisdata_matches (tour VARCHAR, Winner VARCHAR, Loser VARCHAR)"
    )
    yield connection
    connection.close()


@pytest.fixture
def seed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SEED_DIR", tmp_path)
    return tmp_path


def add_player(connection, tour, player_id, name_first, name_last, active_on=_ACTIVE_DATE):
    connection.execute(
        "INSERT INTO staging.sackmann_players VALUES (?, ?, ?, ?)",
        [tour, player_id, name_first, name_last],
    )
    connection.execute(
        "INSERT INTO staging.sackmann_matches VALUES (?, ?, ?, 0)",
        [tour, active_on, player_id],
    )


def add_tennisdata_name(connection, tour, name):
    connection.execute(
        "INSERT INTO staging.tennisdata_matches VALUES (?, ?, NULL)", [tour, name]
    )


def test_exact_folded_key_resolves_single_player(connection, seed_dir):
    add_player(connection, "atp", 103819, "Roger", "Federer")
    add_tennisdata_name(connection, "atp", "Federer R.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Federer R.") == frozenset({103819})


def test_hyphen_folding_matches_compound_last_names(connection, seed_dir):
    add_player(connection, "atp", 104755, "Guillermo", "Garcia-Lopez")
    add_tennisdata_name(connection, "atp", "Garcia-Lopez G.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Garcia-Lopez G.") == frozenset({104755})


def test_wta_candidate_ids_are_offset(connection, seed_dir):
    add_player(connection, "wta", 202, "Ashleigh", "Barty")
    add_tennisdata_name(connection, "wta", "Barty A.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("wta", "Barty A.") == frozenset({202 + WTA_PLAYER_ID_OFFSET})


def test_shared_initial_keeps_both_candidates(connection, seed_dir):
    add_player(connection, "wta", 301, "Sloane", "Stephens")
    add_player(connection, "wta", 302, "Samantha", "Stephens")
    add_tennisdata_name(connection, "wta", "Stephens S.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("wta", "Stephens S.") == frozenset(
        {301 + WTA_PLAYER_ID_OFFSET, 302 + WTA_PLAYER_ID_OFFSET}
    )


def test_prefix_initials_disambiguate_shared_first_letter(connection, seed_dir):
    add_player(connection, "wta", 401, "Karolina", "Pliskova")
    add_player(connection, "wta", 402, "Kristyna", "Pliskova")
    add_tennisdata_name(connection, "wta", "Pliskova Ka.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("wta", "Pliskova Ka.") == frozenset({401 + WTA_PLAYER_ID_OFFSET})


def test_fuzzy_fallback_resolves_near_identical_alias(connection, seed_dir):
    add_player(connection, "atp", 105453, "Philipp", "Kohlschreiber")
    add_tennisdata_name(connection, "atp", "Kohlschreiber P")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Kohlschreiber P") == frozenset({105453})


def test_fuzzy_below_threshold_stays_unresolved(connection, seed_dir):
    add_player(connection, "atp", 105138, "Roberto", "Bautista Agut")
    add_tennisdata_name(connection, "atp", "Bautista R.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Bautista R.") is None
    assert ("atp", "bautista r.") in aliases.unresolved


def test_inactive_players_are_not_candidates(connection, seed_dir):
    add_player(connection, "atp", 501, "Bjorn", "Borg", active_on=date(1980, 7, 1))
    add_tennisdata_name(connection, "atp", "Borg B.")

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Borg B.") is None


def test_seed_overrides_exact_and_fuzzy(connection, seed_dir):
    add_player(connection, "atp", 105138, "Roberto", "Bautista Agut")
    add_player(connection, "atp", 601, "Rodrigo", "Bautista")
    add_tennisdata_name(connection, "atp", "Bautista R.")
    (seed_dir / "player_aliases.csv").write_text(
        "alias,tour,player_id,player_name\nBautista R.,atp,105138,Roberto Bautista Agut\n"
    )

    aliases = resolve_player_aliases(connection)

    assert aliases.lookup("atp", "Bautista R.") == frozenset({105138})


def test_single_id_rows_exclude_multi_candidate_aliases(connection, seed_dir):
    add_player(connection, "atp", 103819, "Roger", "Federer")
    add_player(connection, "wta", 301, "Sloane", "Stephens")
    add_player(connection, "wta", 302, "Samantha", "Stephens")
    add_tennisdata_name(connection, "atp", "Federer R.")
    add_tennisdata_name(connection, "wta", "Stephens S.")

    aliases = resolve_player_aliases(connection)

    assert aliases.single_id_rows() == [("federer r.", "atp", 103819)]
