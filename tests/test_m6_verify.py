"""M6 Verify block from PLAN.md — the feature layer, built into the real warehouse,
predicts as well as expected and carries no lookahead.

Requires `uv run python scripts/build_db.py --all --features` first.
"""

import numpy as np
import pandas as pd
import pytest

from tennisdb.config import DUCKDB_PATH
from tennisdb.features.elo import compute_elo_pre, read_matches

pytestmark = pytest.mark.m6

_BIG_FOUR = {"Novak Djokovic", "Roger Federer", "Rafael Nadal", "Andy Murray"}

_ATP_DECADE = """
JOIN tennis.matches_model AS m USING (match_id)
JOIN tennis.tournament_editions AS te ON te.edition_id = m.edition_id
WHERE te.tour = 'atp' AND te.season BETWEEN 2010 AND 2019
"""

_ELO_CORRECT = "CASE WHEN (e.p1_elo_pre > e.p2_elo_pre) = m.p1_won THEN 1.0 ELSE 0.0 END"


@pytest.fixture(scope="module")
def connection():
    import duckdb

    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--all --features` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    if con.execute("SELECT count(*) FROM analytics.elo_pre").fetchone()[0] == 0:
        pytest.fail(
            "analytics.elo_pre is empty — run `uv run python scripts/build_db.py --features`"
        )
    yield con
    con.close()


def test_elo_leaders_are_the_expected_era_players(connection):
    leaders = {
        name
        for (name,) in connection.execute(
            """
            WITH sides AS (
              SELECT m.p1_id AS player_id, e.p1_elo_pre AS elo
              FROM analytics.elo_pre e JOIN tennis.matches_model m USING (match_id)
              JOIN tennis.tournament_editions te ON te.edition_id = m.edition_id
              WHERE te.tour = 'atp' AND te.season BETWEEN 2015 AND 2019
              UNION ALL
              SELECT m.p2_id, e.p2_elo_pre
              FROM analytics.elo_pre e JOIN tennis.matches_model m USING (match_id)
              JOIN tennis.tournament_editions te ON te.edition_id = m.edition_id
              WHERE te.tour = 'atp' AND te.season BETWEEN 2015 AND 2019
            )
            SELECT p.full_name
            FROM sides JOIN tennis.players p ON p.player_id = sides.player_id
            GROUP BY p.full_name ORDER BY max(sides.elo) DESC LIMIT 6
            """
        ).fetchall()
    }

    assert _BIG_FOUR <= leaders


def test_higher_pre_match_elo_clears_the_predictive_floor(connection):
    accuracy = connection.execute(
        f"SELECT avg({_ELO_CORRECT}) FROM analytics.elo_pre e {_ATP_DECADE}"
    ).fetchone()[0]

    assert accuracy >= 0.63


def test_elo_predicts_at_least_as_well_as_official_rank(connection):
    rank_accuracy, elo_accuracy = connection.execute(
        f"""
        SELECT
          avg(CASE WHEN (m.p1_rank < m.p2_rank) = m.p1_won THEN 1.0 ELSE 0.0 END),
          avg({_ELO_CORRECT})
        FROM analytics.elo_pre e {_ATP_DECADE}
          AND m.p1_rank IS NOT NULL AND m.p2_rank IS NOT NULL
        """
    ).fetchone()

    assert 0.60 <= rank_accuracy <= 0.70
    assert elo_accuracy >= rank_accuracy


def test_closing_market_beats_the_elo_model(connection):
    market_accuracy, elo_accuracy = connection.execute(
        f"""
        SELECT
          avg(CASE WHEN (k.p1_market_prob > 0.5) = m.p1_won THEN 1.0 ELSE 0.0 END),
          avg({_ELO_CORRECT})
        FROM analytics.market k
        JOIN analytics.elo_pre e USING (match_id)
        {_ATP_DECADE}
        """
    ).fetchone()

    assert market_accuracy > elo_accuracy


def test_withholding_future_matches_reproduces_identical_elo(connection):
    matches = read_matches(connection)
    matches["order_date"] = pd.to_datetime(matches["order_date"])
    stored = connection.execute(
        """
        SELECT e.match_id,
          CASE WHEN m.p1_won THEN e.p1_elo_pre ELSE e.p2_elo_pre END AS w_elo_pre,
          CASE WHEN m.p1_won THEN e.p1_surface_elo_pre ELSE e.p2_surface_elo_pre END
            AS w_surface_elo_pre
        FROM analytics.elo_pre e JOIN tennis.matches_model m USING (match_id)
        """
    ).fetch_df().set_index("match_id")

    withheld = compute_elo_pre(
        matches[matches["order_date"] < pd.Timestamp("2015-01-01")]
    ).set_index("match_id")
    sample = withheld.sample(1000, random_state=0).join(stored, rsuffix="_stored")

    assert np.allclose(sample["w_elo_pre"], sample["w_elo_pre_stored"], atol=1e-9)
    assert np.allclose(sample["w_surface_elo_pre"], sample["w_surface_elo_pre_stored"], atol=1e-9)
