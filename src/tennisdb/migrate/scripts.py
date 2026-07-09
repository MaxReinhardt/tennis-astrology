"""Migration SQL files as immutable, checksummed value objects."""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MigrationScript:
    name: str
    checksum: str
    sql: str


def load_migration_scripts(directory: Path) -> list[MigrationScript]:
    if not directory.is_dir():
        raise FileNotFoundError(f"migrations directory not found: {directory}")
    return [_read_script(path) for path in sorted(directory.glob("*.sql"))]


def _read_script(path: Path) -> MigrationScript:
    raw_bytes = path.read_bytes()
    return MigrationScript(
        name=path.name,
        checksum=hashlib.sha256(raw_bytes).hexdigest(),
        sql=raw_bytes.decode("utf-8"),
    )
