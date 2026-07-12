"""M4 Verify block from PLAN.md — runs against the real DuckDB warehouse.

Requires `uv run python scripts/build_db.py --stage --load --resolve` first.
"""

import csv
from collections import Counter

import duckdb
import pytest

from tennisdb.config import CURRENT_SEASON, DUCKDB_PATH, QUALITY_DIR
from tennisdb.resolve.pipeline import UNMATCHED_FILE
from tennisdb.resolve.text import fold

pytestmark = pytest.mark.m4

OVERALL_MATCH_RATE_FLOOR = 0.93
MODERN_MATCH_RATE_FLOOR = 0.97
MODERN_FROM_SEASON = 2010
RANK_TOLERANCE = 2
RANK_AGREEMENT_FLOOR = 0.95
WINNER_CHECK_COVERAGE_FLOOR = 0.95


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--stage --load --resolve` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    if con.execute("SELECT count(*) FROM tennis.odds").fetchone()[0] == 0:
        pytest.fail(
            "tennis.odds is empty — run `uv run python scripts/build_db.py --load --resolve`"
        )
    yield con
    con.close()


@pytest.fixture(scope="module")
def unmatched_rows():
    path = QUALITY_DIR / UNMATCHED_FILE
    if not path.exists():
        pytest.fail(f"{path} missing — run `uv run python scripts/build_db.py --resolve` first")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_overall_match_rate_meets_floor(connection, unmatched_rows):
    total = connection.execute("SELECT count(*) FROM staging.tennisdata_matches").fetchone()[0]

    match_rate = 1 - len(unmatched_rows) / total

    assert match_rate >= OVERALL_MATCH_RATE_FLOOR, f"overall match rate {match_rate:.2%}"


def test_modern_seasons_meet_per_season_floor(connection, unmatched_rows):
    """The in-progress season is excluded: Sackmann's files trail tennis-data by
    weeks mid-season, so its tail of rows has no canonical matches to attach to."""
    totals = {
        (int(season), tour): count
        for season, tour, count in connection.execute(
            "SELECT season, tour, count(*) FROM staging.tennisdata_matches GROUP BY 1, 2"
        ).fetchall()
    }
    unmatched = Counter((int(row["season"]), row["tour"]) for row in unmatched_rows)

    failures = []
    for (season, tour), total in sorted(totals.items()):
        if not MODERN_FROM_SEASON <= season < CURRENT_SEASON:
            continue
        rate = 1 - unmatched[(season, tour)] / total
        if rate < MODERN_MATCH_RATE_FLOOR:
            failures.append(f"{season} {tour}: {rate:.2%}")
    if failures:
        examples = Counter(
            (row["season"], row["tour"], row["tournament"], row["reason"])
            for row in unmatched_rows
            if f"{row['season']} {row['tour']}" in {line.split(':')[0] for line in failures}
        )
        pytest.fail(
            "seasons under the 97% floor:\n  "
            + "\n  ".join(failures)
            + "\ntop unmatched:\n  "
            + "\n  ".join(str(item) for item in examples.most_common(10))
        )


def test_no_match_is_claimed_by_two_tennisdata_rows(connection):
    doubly_claimed = connection.execute(
        "SELECT match_id FROM tennis.odds GROUP BY match_id "
        "HAVING count(DISTINCT source_row) > 1"
    ).fetchall()

    assert doubly_claimed == []


def test_winner_agreement_is_total_on_resolved_rows(connection):
    """Re-derives the winner independently: tennis-data's Winner name, folded and
    looked up in tennis.player_aliases, must be the canonical match's winner_id.
    Multi-candidate aliases are absent from the table, so assert the check still
    covers nearly all resolved rows."""
    aliases = {
        (tour, alias): player_id
        for alias, tour, player_id in connection.execute(
            "SELECT alias, tour, player_id FROM tennis.player_aliases"
        ).fetchall()
    }
    resolved = connection.execute(
        "SELECT DISTINCT o.match_id, t.tour, t.Winner, m.winner_id "
        "FROM tennis.odds AS o "
        "JOIN staging.tennisdata_matches AS t "
        "  ON o.source_row = t.source_file || ':' || t.source_row "
        "JOIN tennis.matches AS m USING (match_id)"
    ).fetchall()

    disagreements = []
    checked = 0
    for match_id, tour, winner_name, winner_id in resolved:
        alias_player = aliases.get((tour, fold(winner_name)))
        if alias_player is None:
            continue
        checked += 1
        if alias_player != winner_id:
            disagreements.append((match_id, winner_name))

    assert disagreements == []
    assert checked / len(resolved) >= WINNER_CHECK_COVERAGE_FLOOR


def test_ranks_agree_within_tolerance_where_both_sources_report(connection):
    winner_side, loser_side = connection.execute(
        f"""
        WITH resolved AS (SELECT DISTINCT match_id, source_row FROM tennis.odds)
        SELECT
            avg((abs(m.winner_rank - t.WRank) <= {RANK_TOLERANCE})::int)
                FILTER (WHERE m.winner_rank IS NOT NULL AND t.WRank IS NOT NULL),
            avg((abs(m.loser_rank - t.LRank) <= {RANK_TOLERANCE})::int)
                FILTER (WHERE m.loser_rank IS NOT NULL AND t.LRank IS NOT NULL)
        FROM resolved
        JOIN staging.tennisdata_matches AS t
          ON resolved.source_row = t.source_file || ':' || t.source_row
        JOIN tennis.matches AS m USING (match_id)
        """
    ).fetchone()

    assert winner_side >= RANK_AGREEMENT_FLOOR
    assert loser_side >= RANK_AGREEMENT_FLOOR
