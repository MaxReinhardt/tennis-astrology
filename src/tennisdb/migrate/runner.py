"""Engine-agnostic migration use case: apply pending scripts through a MigrationTarget."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from tennisdb.migrate.scripts import MigrationScript


class MigrationTarget(Protocol):
    name: str

    def applied_checksums(self) -> dict[str, str]: ...

    def apply(self, script: MigrationScript) -> None: ...

    def close(self) -> None: ...


class MigrationChecksumError(RuntimeError):
    pass


@dataclass
class MigrationReport:
    target_name: str
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [f"{self.target_name}: applied {name}" for name in self.applied]
        noun = "change" if len(self.applied) == 1 else "changes"
        lines.append(f"{self.target_name}: {len(self.applied)} {noun}")
        return lines


def run_migrations(
    scripts: Sequence[MigrationScript], target: MigrationTarget
) -> MigrationReport:
    applied_checksums = target.applied_checksums()
    _reject_checksum_drift(scripts, applied_checksums)
    report = MigrationReport(target_name=target.name)
    for script in scripts:
        if script.name in applied_checksums:
            report.skipped.append(script.name)
            continue
        target.apply(script)
        report.applied.append(script.name)
    return report


def _reject_checksum_drift(
    scripts: Sequence[MigrationScript], applied_checksums: dict[str, str]
) -> None:
    for script in scripts:
        recorded = applied_checksums.get(script.name)
        if recorded is not None and recorded != script.checksum:
            raise MigrationChecksumError(
                f"{script.name} changed after being applied "
                f"(ledger {recorded}, file {script.checksum}); "
                "applied migrations are immutable — add a new numbered migration instead"
            )
