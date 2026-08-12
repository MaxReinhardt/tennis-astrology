"""M5: the declarative quality-check engine — pass/fail, tolerance, samples, waivers."""

import duckdb
import pytest

from tennisdb.quality.checks import (
    CheckResult,
    MetricCheck,
    QualityReport,
    ViolationCheck,
    load_waivers,
)

pytestmark = pytest.mark.m5


@pytest.fixture
def numbers():
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE t (x INTEGER)")
    connection.executemany("INSERT INTO t VALUES (?)", [(value,) for value in range(100)])
    yield connection
    connection.close()


def _violation(offenders: str, **kwargs) -> ViolationCheck:
    return ViolationCheck(
        name="check", scope="t", offenders=offenders, population="SELECT count(*) FROM t", **kwargs
    )


def test_violation_check_passes_when_no_offenders(numbers):
    result = _violation("SELECT x FROM t WHERE x < 0").evaluate(numbers)

    assert result.passed
    assert result.sample == ()


def test_violation_check_fails_and_captures_a_bounded_sample(numbers):
    result = _violation("SELECT x FROM t WHERE x < 3", sample_size=2).evaluate(numbers)

    assert not result.passed
    assert len(result.sample) == 2


def test_violation_check_tolerates_offenders_below_max_fraction(numbers):
    result = _violation("SELECT x FROM t WHERE x < 3", max_fraction=0.05).evaluate(numbers)

    assert result.passed


def test_metric_check_passes_within_bounds(numbers):
    check = MetricCheck("avg", "t", metric="SELECT avg(x) FROM t", low=40.0, high=60.0)

    assert check.evaluate(numbers).passed


def test_metric_check_fails_below_lower_bound(numbers):
    check = MetricCheck("avg", "t", metric="SELECT avg(x) FROM t", low=60.0)

    assert not check.evaluate(numbers).passed


def test_metric_check_supports_open_upper_bound(numbers):
    check = MetricCheck("max", "t", metric="SELECT max(x) FROM t", low=90.0)

    assert check.evaluate(numbers).passed


def test_report_treats_waived_failure_as_passing_but_records_it():
    failing = CheckResult("dupes", "matches", passed=False, detail="")
    passing = CheckResult("ok", "matches", passed=True, detail="")
    report = QualityReport(results=(failing, passing), waivers={"dupes": "known legacy dups"})

    assert report.passed()
    assert report.failing() == []
    assert [result.name for result in report.waived()] == ["dupes"]


def test_report_unwaived_failure_fails_the_suite():
    report = QualityReport(
        results=(CheckResult("leak", "odds", passed=False, detail=""),), waivers={}
    )

    assert not report.passed()
    assert [result.name for result in report.failing()] == ["leak"]


def test_load_waivers_reads_documented_reasons():
    waivers = load_waivers()

    assert waivers.get("matches_no_duplicate_pairings")
