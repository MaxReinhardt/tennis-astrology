"""M3: engine-agnostic migration run — ordering, skipping, checksum enforcement."""

import pytest

from tennisdb.migrate.runner import MigrationChecksumError, run_migrations
from tennisdb.migrate.scripts import MigrationScript

pytestmark = pytest.mark.m3


class StubMigrationTarget:
    name = "stub"

    def __init__(self, already_applied: dict[str, str] | None = None):
        self._already_applied = already_applied or {}
        self.applied_scripts: list[MigrationScript] = []

    def applied_checksums(self) -> dict[str, str]:
        return dict(self._already_applied)

    def apply(self, script: MigrationScript) -> None:
        self.applied_scripts.append(script)

    def close(self) -> None:
        pass


def _script(name: str, checksum: str = "abc") -> MigrationScript:
    return MigrationScript(name=name, checksum=checksum, sql=f"-- {name}")


def test_run_migrations_applies_pending_scripts_in_order():
    scripts = [_script("001_core.sql"), _script("002_odds.sql")]
    target = StubMigrationTarget()

    report = run_migrations(scripts, target)

    assert [script.name for script in target.applied_scripts] == [
        "001_core.sql",
        "002_odds.sql",
    ]
    assert report.applied == ["001_core.sql", "002_odds.sql"]
    assert report.skipped == []


def test_run_migrations_skips_scripts_already_in_ledger():
    scripts = [_script("001_core.sql", checksum="c1"), _script("002_odds.sql", checksum="c2")]
    target = StubMigrationTarget(already_applied={"001_core.sql": "c1"})

    report = run_migrations(scripts, target)

    assert [script.name for script in target.applied_scripts] == ["002_odds.sql"]
    assert report.applied == ["002_odds.sql"]
    assert report.skipped == ["001_core.sql"]


def test_run_migrations_second_pass_reports_zero_changes():
    scripts = [_script("001_core.sql", checksum="c1")]
    target = StubMigrationTarget(already_applied={"001_core.sql": "c1"})

    report = run_migrations(scripts, target)

    assert report.applied == []
    assert any("0 changes" in line for line in report.summary_lines())


def test_run_migrations_checksum_drift_raises_before_applying_anything():
    scripts = [_script("001_core.sql", checksum="edited"), _script("002_odds.sql")]
    target = StubMigrationTarget(already_applied={"001_core.sql": "original"})

    with pytest.raises(MigrationChecksumError, match="001_core.sql"):
        run_migrations(scripts, target)

    assert target.applied_scripts == []


def test_summary_lines_name_applied_scripts_and_total():
    scripts = [_script("001_core.sql")]
    target = StubMigrationTarget()

    report = run_migrations(scripts, target)

    assert report.summary_lines() == ["stub: applied 001_core.sql", "stub: 1 change"]
