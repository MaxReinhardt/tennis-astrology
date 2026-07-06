"""Outcome summary shared by all ingesters."""

from dataclasses import dataclass, field


@dataclass
class IngestReport:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def extend(self, other: "IngestReport") -> None:
        self.downloaded.extend(other.downloaded)
        self.skipped.extend(other.skipped)
        self.failed.extend(other.failed)
        self.warnings.extend(other.warnings)

    def summary_lines(self) -> list[str]:
        lines = [
            f"downloaded: {len(self.downloaded)}",
            f"skipped:    {len(self.skipped)}",
            f"failed:     {len(self.failed)}",
        ]
        lines.extend(f"  FAILED  {item}" for item in self.failed)
        lines.extend(f"  WARNING {message}" for message in self.warnings)
        return lines
