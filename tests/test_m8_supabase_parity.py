"""M8: the Supabase-backed source and the DuckDB source must produce identical backtests,
so the deployed UI reports the same numbers the local studies do. Runs against the real
warehouse and the live Supabase project (read-only)."""

import duckdb
import pytest

from tennisdb import config
from tennisdb.backtest.engine import run_backtest
from tennisdb.backtest.opportunities import DuckDbOpportunitySource
from tennisdb.backtest.postgres_opportunities import PostgresOpportunitySource
from tennisdb.backtest.request import BacktestRequest

pytestmark = pytest.mark.m8

_REQUESTS = [
    {
        "strategy": "back_underdogs",
        "filters": {"tour": "atp", "from_season": 2015, "to_season": 2019},
    },
    {
        "strategy": "elo_value",
        "filters": {"surfaces": ["Clay"], "from_season": 2017},
        "stake_rule": "flat",
        "starting_bankroll": 1_000_000,
    },
    {
        "strategy": "fade_home_nation",
        "filters": {"from_season": 2012},
        "stake_rule": "flat",
        "starting_bankroll": 1_000_000,
    },
]


@pytest.fixture(scope="module")
def sources():
    if not config.SUPABASE_DB_URL:
        pytest.fail("SUPABASE_DB_URL is not set — see .env.example")
    local = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        remote = PostgresOpportunitySource.connect(config.SUPABASE_DB_URL)
    except Exception as error:  # noqa: BLE001 - any connection failure is the same advice
        local.close()
        pytest.fail(f"Supabase unreachable ({error}) — is the project paused?")
    yield DuckDbOpportunitySource.open(local), remote
    remote.close()
    local.close()


@pytest.mark.parametrize("payload", _REQUESTS, ids=lambda payload: payload["strategy"])
def test_backtest_results_are_identical_across_sources(sources, payload):
    local, remote = sources
    request = BacktestRequest.from_dict(payload)

    local_result = run_backtest(request, local)
    remote_result = run_backtest(request, remote)

    assert remote_result.matches_seen == local_result.matches_seen > 0
    assert remote_result.metrics.bet_count == local_result.metrics.bet_count
    assert remote_result.metrics.roi == pytest.approx(local_result.metrics.roi)
