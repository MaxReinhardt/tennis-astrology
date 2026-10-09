"""M8 Verify block, against the real warehouse and the committed study results: the
host-nation data supports S4, the LEFT JOINs left the backtest universe untouched, and
the generated study results honour the protocol (S3 rejects the astrology null)."""

import json

import duckdb
import pytest

from tennisdb import config
from tennisdb.backtest.engine import run_backtest
from tennisdb.backtest.opportunities import DuckDbOpportunitySource
from tennisdb.backtest.request import BacktestRequest
from tennisdb.research.studies import STUDIES

pytestmark = pytest.mark.m8

RESULTS = config.STUDIES_DIR / "results"
# matches_seen of the pre-M8 M7 run over 2015–2019 (both tours), recorded in its result.json
BASELINE_2015_2019_MATCHES = 25_391


@pytest.fixture(scope="module")
def connection():
    if not config.DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--all --features` first"
        )
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    yield con
    con.close()


def _load(study_id):
    path = RESULTS / study_id / "result.json"
    if not path.exists():
        pytest.fail(f"{path} missing — run `uv run python scripts/run_study.py`")
    return json.loads(path.read_text())


def test_every_odds_era_edition_has_a_host_country(connection):
    missing = connection.execute(
        "SELECT count(*) FROM analytics.edition_geo WHERE host_country_ioc IS NULL"
    ).fetchone()[0]

    assert missing == 0


def test_host_nation_study_has_enough_one_home_player_matches(connection):
    rows = connection.execute(
        "SELECT count(*) FROM tennis.matches_model m JOIN analytics.market USING (match_id) "
        "JOIN analytics.edition_geo g USING (edition_id) "
        "JOIN tennis.players p1 ON p1.player_id = m.p1_id "
        "JOIN tennis.players p2 ON p2.player_id = m.p2_id "
        "WHERE (p1.country_ioc = g.host_country_ioc) <> (p2.country_ioc = g.host_country_ioc)"
    ).fetchone()[0]

    assert rows >= 10_000


def test_geography_joins_leave_the_backtest_universe_unchanged(connection):
    request = BacktestRequest.from_dict(
        {
            "strategy": "random_bet",
            "filters": {"from_season": 2015, "to_season": 2019},
        }
    )

    result = run_backtest(request, DuckDbOpportunitySource.open(connection))

    assert result.matches_seen == BASELINE_2015_2019_MATCHES


def test_every_registered_study_has_committed_results():
    for study_id in STUDIES:
        assert _load(study_id)["study_id"] == study_id


def test_zodiac_study_reports_no_corrected_p_value_below_five_percent():
    table = _load("s3_zodiac_null")["tables"][0]
    bonferroni_column = table["columns"].index("p (Bonf.)")

    assert min(float(row[bonferroni_column]) for row in table["rows"]) > 0.05
    assert _load("s3_zodiac_null")["verdict"] == "not_supported"


def test_clv_study_documents_that_raw_clv_is_not_edge():
    result = _load("s1_clv_persistence")

    assert result["verdict"] != "supported"
