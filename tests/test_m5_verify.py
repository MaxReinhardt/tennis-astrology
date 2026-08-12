"""M5 Verify block from PLAN.md — the quality suite runs clean against the real
warehouse (no unwaived failures), and the merge-integrity metrics land in band.

Requires `uv run python scripts/build_db.py --all` first.
"""

import duckdb
import pytest

from tennisdb.config import DUCKDB_PATH
from tennisdb.quality.checks import CHECKS, run_quality_suite

pytestmark = pytest.mark.m5


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py --all` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    if con.execute("SELECT count(*) FROM tennis.odds").fetchone()[0] == 0:
        pytest.fail(
            "tennis.odds is empty — run `uv run python scripts/build_db.py --load --resolve`"
        )
    yield con
    con.close()


@pytest.fixture(scope="module")
def report(connection):
    return run_quality_suite(connection)


def test_quality_suite_runs_every_registered_check(report):
    assert len(report.results) == len(CHECKS)


def test_quality_suite_has_no_unwaived_failures(report):
    failures = report.failing()

    assert failures == [], "failing checks:\n" + "\n".join(
        f"  {result.name}: {result.detail}" for result in failures
    )


def test_favorite_win_rate_lands_in_the_integrity_band(report):
    result = next(item for item in report.results if item.name == "odds_favorite_win_rate")

    assert result.passed, result.detail


def test_legacy_duplicate_pairings_are_waived_not_failing(report):
    waived_names = {result.name for result in report.waived()}

    assert "matches_no_duplicate_pairings" in waived_names
