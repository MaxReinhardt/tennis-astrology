"""Download manifest: provenance, checksums, and row counts for every raw file."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from tennisdb.config import RAW_DIR

MANIFEST_PATH = RAW_DIR / "manifest.json"

EXCEL_SUFFIXES = {".xls", ".xlsx"}


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    source_url: str
    sha256: str
    row_count: int
    downloaded_at: str


def sha256_of(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_rows(file: Path) -> int:
    if file.suffix in EXCEL_SUFFIXES:
        return len(pd.read_excel(file))
    with file.open("rb") as handle:
        line_count = sum(1 for _ in handle)
    return max(line_count - 1, 0)


class Manifest:
    def __init__(self, path: Path):
        self._path = path
        self._entries: dict[str, ManifestEntry] = {}

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        manifest = cls(path)
        if path.exists():
            for item in json.loads(path.read_text()):
                entry = ManifestEntry(**item)
                manifest._entries[entry.path] = entry
        return manifest

    @property
    def raw_dir(self) -> Path:
        return self._path.parent

    def has(self, relative_path: str) -> bool:
        return relative_path in self._entries

    def get(self, relative_path: str) -> ManifestEntry | None:
        return self._entries.get(relative_path)

    def entries(self) -> tuple[ManifestEntry, ...]:
        return tuple(self._entries.values())

    def find_with_prefix(self, prefix: str) -> tuple[ManifestEntry, ...]:
        return tuple(
            entry for path, entry in self._entries.items() if path.startswith(prefix)
        )

    def record_download(self, file: Path, source_url: str) -> ManifestEntry:
        entry = ManifestEntry(
            path=file.relative_to(self.raw_dir).as_posix(),
            source_url=source_url,
            sha256=sha256_of(file),
            row_count=count_rows(file),
            downloaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._entries[entry.path] = entry
        self.save()
        return entry

    def save(self) -> None:
        ordered = [asdict(self._entries[path]) for path in sorted(self._entries)]
        temp_path = self._path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(ordered, indent=2) + "\n")
        temp_path.replace(self._path)
