"""M7: DuckDbOpportunitySource against a real (in-memory) migrated warehouse — fill
preference and fallback, filter push-down, chronological ordering, and the reference
strategies' side selection, all driven off genuine analytics.elo_pre/analytics.market
rows built by the real M6 feature builders."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.backtest.opportunities import DuckDbOpportunitySource
from tennisdb.backtest.request import BacktestRequest
from tennisdb.backtest.strategies import build_strategy
from tennisdb.features.elo import build_elo
from tennisdb.features.market import build_market
from tennisdb.migrate.runner import run_migrations
from tennisdb.migrate.scripts import load_migration_scripts
from tennisdb.migrate.targets import DuckDbMigrationTarget

pytestmark = pytest.mark.m7


@pytest.fixture
def connection():
    connection = duckdb.connect(":memory:")
    run_migrations(load_migration_scripts(config.MIGRATIONS_DIR), DuckDbMigrationTarget(connection))
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name) VALUES "
        "(1, 'atp', 'Alpha'), (2, 'atp', 'Bravo')"
    )
    connection.execute(
        "INSERT INTO tennis.tournament_editions "
        "(edition_id, tour, name, surface, level, season, start_date) VALUES "
        "('2019-1', 'atp', 'Open', 'Hard', 'A', 2019, DATE '2019-01-01')"
    )
    yield connection
    connection.close()


def _add_match(connection, match_id, match_date, round_, winner=1, loser=2, edition_id="2019-1"):
    connection.execute(
        "INSERT INTO tennis.matches (match_id, edition_id, round, match_date, "
        "winner_id, loser_id) VALUES (?, ?, ?, ?, ?, ?)",
        [match_id, edition_id, round_, match_date, winner, loser],
    )


def _add_odds(connection, match_id, bookmaker, winner_odds, loser_odds):
    connection.execute(
        "INSERT INTO tennis.odds (match_id, bookmaker, winner_odds, loser_odds) "
        "VALUES (?, ?, ?, ?)",
        [match_id, bookmaker, winner_odds, loser_odds],
    )


def _events(connection, **request_overrides):
    build_elo(connection)
    build_market(connection)
    source = DuckDbOpportunitySource.open(connection)
    request = BacktestRequest.from_dict({"strategy": "random_bet", **request_overrides})
    return list(source.events(request))


def test_events_respect_date_then_round_ordering(connection):
    # Same date, two rounds: R32 must sort before QF regardless of insertion order.
    _add_match(connection, "2019-1-2", "2019-01-07", "QF")
    _add_match(connection, "2019-1-1", "2019-01-07", "R32")
    _add_match(connection, "2019-1-3", "2019-01-14", "F")
    for match_id in ("2019-1-1", "2019-1-2", "2019-1-3"):
        _add_odds(connection, match_id, "Avg", 1.8, 2.2)

    events = _events(connection)

    assert [event.opportunity.match_id for event in events] == ["2019-1-1", "2019-1-2", "2019-1-3"]


def test_fill_preference_prefers_the_first_book_present(connection):
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "PS", 1.8, 2.2)
    _add_odds(connection, "2019-1-1", "Avg", 1.9, 2.1)

    events = _events(connection, fill_preference=["PS", "Avg"])
    opportunity = events[0].opportunity

    assert {opportunity.p1_price, opportunity.p2_price} == {1.8, 2.2}


def test_fill_preference_falls_back_when_the_preferred_book_is_absent(connection):
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "Avg", 1.9, 2.1)

    events = _events(connection, fill_preference=["PS", "Avg"])
    opportunity = events[0].opportunity

    assert {opportunity.p1_price, opportunity.p2_price} == {1.9, 2.1}


def test_filters_select_only_the_requested_season_and_tour(connection):
    connection.execute(
        "INSERT INTO tennis.tournament_editions "
        "(edition_id, tour, name, surface, level, season, start_date) VALUES "
        "('2021-1', 'wta', 'Other Open', 'Clay', 'A', 2021, DATE '2021-01-01')"
    )
    connection.execute(
        "INSERT INTO tennis.players (player_id, tour, full_name) VALUES "
        "(10000001, 'wta', 'Carol'), (10000002, 'wta', 'Dana')"
    )
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "Avg", 1.8, 2.2)
    _add_match(
        connection,
        "2021-1-1",
        "2021-01-07",
        "F",
        winner=10000001,
        loser=10000002,
        edition_id="2021-1",
    )
    _add_odds(connection, "2021-1-1", "Avg", 1.8, 2.2)

    events = _events(connection, filters={"tour": "atp", "from_season": 2019, "to_season": 2019})

    assert [event.opportunity.match_id for event in events] == ["2019-1-1"]


def test_back_favorites_and_back_underdogs_pick_opposite_sides(connection):
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)
    [event] = _events(connection)

    favorites_bet = build_strategy("back_favorites", {}).evaluate(event.opportunity)
    underdogs_bet = build_strategy("back_underdogs", {}).evaluate(event.opportunity)

    assert favorites_bet.side != underdogs_bet.side
    favorite_price = event.opportunity.price(favorites_bet.side)
    underdog_price = event.opportunity.price(underdogs_bet.side)
    assert favorite_price < underdog_price


def test_back_favorites_respects_the_price_band(connection):
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)
    [event] = _events(connection)

    bet = build_strategy("back_favorites", {"max_price": 1.4}).evaluate(event.opportunity)

    assert bet is None


def test_elo_value_only_bets_when_the_edge_clears_theta(connection):
    _add_match(connection, "2019-1-1", "2019-01-07", "F")
    _add_odds(connection, "2019-1-1", "Avg", 1.5, 2.5)
    [event] = _events(connection)

    permissive = build_strategy("elo_value", {"theta": 0.0}).evaluate(event.opportunity)
    impossible = build_strategy("elo_value", {"theta": 0.5}).evaluate(event.opportunity)

    assert permissive is not None
    assert impossible is None
