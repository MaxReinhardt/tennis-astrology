"""M4: per-row match resolution — reason codes, disambiguation, uniqueness, odds."""

from datetime import date

import duckdb
import pytest

from tennisdb import config
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget
from tennisdb.resolve.matches import OddsSourceRow, resolve_matches
from tennisdb.resolve.odds import emit_odds
from tennisdb.resolve.players import PlayerAliasMap
from tennisdb.resolve.tournaments import EditionAliasMap

pytestmark = pytest.mark.m4

_ROW_DEFAULTS = {
    "tour": "atp",
    "season": 2019,
    "Tournament": "Wimbledon",
    "Location": "London",
    "Date": date(2019, 7, 14),
    "round": "F",
    "Winner": "Djokovic N.",
    "Loser": "Federer R.",
    "WRank": 1,
    "LRank": 3,
    "B365W": 1.66,
    "B365L": 2.20,
    "PSW": 1.71,
    "PSL": 2.26,
    "MaxW": 1.73,
    "MaxL": 2.30,
    "AvgW": 1.68,
    "AvgL": 2.22,
    "source_file": "tennisdata/atp/2019.xlsx",
    "source_row": 2,
}


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "CREATE SCHEMA staging;"
        "CREATE TABLE staging.tennisdata_matches ("
        "tour VARCHAR, season BIGINT, Tournament VARCHAR, Location VARCHAR, "
        '"Date" DATE, round VARCHAR, Winner VARCHAR, Loser VARCHAR, '
        "WRank BIGINT, LRank BIGINT, B365W DOUBLE, B365L DOUBLE, PSW DOUBLE, PSL DOUBLE, "
        "MaxW DOUBLE, MaxL DOUBLE, AvgW DOUBLE, AvgL DOUBLE, "
        "source_file VARCHAR, source_row BIGINT)"
    )
    _seed_wimbledon_final(connection)
    yield connection
    connection.close()


def _seed_wimbledon_final(connection):
    connection.execute(
        "INSERT INTO tennis.players VALUES "
        "(101, 'atp', 'Novak Djokovic', 'R', DATE '1987-05-22', 'SRB', 188, NULL), "
        "(102, 'atp', 'Roger Federer', 'R', DATE '1981-08-08', 'SUI', 185, NULL), "
        "(103, 'atp', 'Rafael Nadal', 'L', DATE '1986-06-03', 'ESP', 185, NULL)"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions VALUES "
        "('2019-540', 'atp', 'Wimbledon', 'Grass', 'G', 128, DATE '2019-07-01', 2019)"
    )
    add_canonical_match(connection, "2019-540-226", round="F", winner_id=101, loser_id=102,
                        winner_rank=1, loser_rank=3)


def add_canonical_match(connection, match_id, *, round, winner_id, loser_id,
                        winner_rank=None, loser_rank=None, edition_id="2019-540"):
    connection.execute(
        "INSERT INTO tennis.matches "
        "(match_id, edition_id, round, best_of, match_date, winner_id, loser_id, "
        " winner_rank, loser_rank) "
        "VALUES (?, ?, ?, 5, DATE '2019-07-01', ?, ?, ?, ?)",
        [match_id, edition_id, round, winner_id, loser_id, winner_rank, loser_rank],
    )


def add_source_row(connection, **overrides):
    values = {**_ROW_DEFAULTS, **overrides}
    columns = ", ".join(f'"{column}"' for column in values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO staging.tennisdata_matches ({columns}) VALUES ({placeholders})",
        list(values.values()),
    )


def alias_maps(player_candidates=None, editions=None):
    players = PlayerAliasMap(
        candidates=player_candidates
        if player_candidates is not None
        else {
            ("atp", "djokovic n."): frozenset({101}),
            ("atp", "federer r."): frozenset({102}),
            ("atp", "nadal r."): frozenset({103}),
        },
        unresolved=frozenset(),
    )
    edition_map = EditionAliasMap(
        editions=editions
        if editions is not None
        else {("atp", 2019, "Wimbledon", "London"): "2019-540"},
        unresolved=frozenset(),
    )
    return players, edition_map


def resolved_ids(resolution):
    return [(row.source_row, match_id) for row, match_id in resolution.resolved]


def unmatched_reasons(resolution):
    return [(row.source_row, reason) for row, reason in resolution.unmatched]


def test_happy_path_resolves_to_match_id(connection):
    add_source_row(connection)

    resolution = resolve_matches(connection, *alias_maps())

    assert resolved_ids(resolution) == [(2, "2019-540-226")]
    assert resolution.unmatched == []


def test_unresolved_edition_reason(connection):
    add_source_row(connection)

    resolution = resolve_matches(connection, *alias_maps(editions={}))

    assert unmatched_reasons(resolution) == [(2, "edition_unresolved")]


def test_unresolved_player_reason(connection):
    add_source_row(connection)

    resolution = resolve_matches(
        connection, *alias_maps(player_candidates={("atp", "federer r."): frozenset({102})})
    )

    assert unmatched_reasons(resolution) == [(2, "player_unresolved")]


def test_pair_absent_from_edition_is_no_candidate(connection):
    add_source_row(connection, Loser="Nadal R.")

    resolution = resolve_matches(connection, *alias_maps())

    assert unmatched_reasons(resolution) == [(2, "no_candidate")]


def test_date_outside_edition_window_is_no_candidate(connection):
    add_source_row(connection, Date=date(2019, 8, 30))

    resolution = resolve_matches(connection, *alias_maps())

    assert unmatched_reasons(resolution) == [(2, "no_candidate")]


def test_reversed_winner_is_winner_mismatch(connection):
    add_source_row(connection, Winner="Federer R.", Loser="Djokovic N.", WRank=3, LRank=1)

    resolution = resolve_matches(connection, *alias_maps())

    assert unmatched_reasons(resolution) == [(2, "winner_mismatch")]


def test_round_disambiguates_round_robin_rematch(connection):
    add_canonical_match(connection, "2019-540-101", round="RR", winner_id=101, loser_id=102)
    add_source_row(connection, round="RR")
    add_source_row(connection, round="F", source_row=3)

    resolution = resolve_matches(connection, *alias_maps())

    assert resolved_ids(resolution) == [(2, "2019-540-101"), (3, "2019-540-226")]


def test_multi_candidate_alias_resolves_structurally(connection):
    ambiguous_djokovic = {
        ("atp", "djokovic n."): frozenset({101, 999}),
        ("atp", "federer r."): frozenset({102}),
    }
    add_source_row(connection)

    resolution = resolve_matches(connection, *alias_maps(player_candidates=ambiguous_djokovic))

    assert resolved_ids(resolution) == [(2, "2019-540-226")]


def test_rank_proximity_breaks_same_round_tie(connection):
    add_canonical_match(connection, "2019-540-102", round="RR", winner_id=101, loser_id=102,
                        winner_rank=1, loser_rank=3)
    add_canonical_match(connection, "2019-540-103", round="RR", winner_id=101, loser_id=102,
                        winner_rank=50, loser_rank=60)
    add_source_row(connection, round="RR", WRank=48, LRank=61)

    resolution = resolve_matches(connection, *alias_maps())

    assert resolved_ids(resolution) == [(2, "2019-540-103")]


def test_unbreakable_tie_is_ambiguous(connection):
    add_canonical_match(connection, "2019-540-102", round="RR", winner_id=101, loser_id=102)
    add_canonical_match(connection, "2019-540-103", round="RR", winner_id=101, loser_id=102)
    add_source_row(connection, round="RR")

    resolution = resolve_matches(connection, *alias_maps())

    assert unmatched_reasons(resolution) == [(2, "ambiguous")]


def test_two_rows_claiming_one_match_are_both_demoted(connection):
    add_source_row(connection)
    add_source_row(connection, source_row=3)

    resolution = resolve_matches(connection, *alias_maps())

    assert resolution.resolved == []
    assert sorted(unmatched_reasons(resolution)) == [(2, "ambiguous"), (3, "ambiguous")]


def test_reason_and_season_counts(connection):
    add_source_row(connection)
    add_source_row(connection, source_row=3, Loser="Nadal R.")

    resolution = resolve_matches(connection, *alias_maps())

    assert resolution.reason_counts() == {"no_candidate": 1}
    assert resolution.season_tour_counts() == {(2019, "atp"): (1, 2)}


def _source_row_fixture(**overrides):
    values = {**_ROW_DEFAULTS, **overrides}
    return OddsSourceRow(
        tour=values["tour"],
        season=values["season"],
        tournament=values["Tournament"],
        location=values["Location"],
        match_date=values["Date"],
        round=values["round"],
        winner=values["Winner"],
        loser=values["Loser"],
        winner_rank=values["WRank"],
        loser_rank=values["LRank"],
        bookmaker_odds={
            "B365": (values["B365W"], values["B365L"]),
            "PS": (values["PSW"], values["PSL"]),
            "Max": (values["MaxW"], values["MaxL"]),
            "Avg": (values["AvgW"], values["AvgL"]),
        },
        source_file=values["source_file"],
        source_row=values["source_row"],
    )


def test_emit_odds_writes_long_format_rows(connection):
    row = _source_row_fixture()

    inserted = emit_odds(connection, [(row, "2019-540-226")])

    assert inserted == 4
    rows = connection.execute(
        "SELECT bookmaker, winner_odds, loser_odds, is_closing, source, source_row "
        "FROM tennis.odds ORDER BY bookmaker"
    ).fetchall()
    assert [row[0] for row in rows] == ["Avg", "B365", "Max", "PS"]
    assert all(source == "tennisdata" for _, _, _, _, source, _ in rows)
    assert all(is_closing for _, _, _, is_closing, _, _ in rows)
    assert rows[1][5] == "tennisdata/atp/2019.xlsx:2"


def test_emit_odds_skips_one_sided_bookmakers(connection):
    row = _source_row_fixture(PSL=None, MaxW=None, MaxL=None)

    inserted = emit_odds(connection, [(row, "2019-540-226")])

    assert inserted == 2
    bookmakers = [r[0] for r in connection.execute(
        "SELECT bookmaker FROM tennis.odds ORDER BY bookmaker"
    ).fetchall()]
    assert bookmakers == ["Avg", "B365"]


def test_emit_odds_with_nothing_resolved_is_a_no_op(connection):
    assert emit_odds(connection, []) == 0
