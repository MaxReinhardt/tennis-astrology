"""Orchestrates building every staging table from raw files + manifest."""

from dataclasses import dataclass, field

import pandas as pd

from tennisdb.ingest import stage_sackmann, stage_tennisdata
from tennisdb.ingest.manifest import Manifest
from tennisdb.warehouse import Warehouse

STAGING_SCHEMA = "staging"

_TABLE_BUILDERS = {
    "sackmann_matches": stage_sackmann.stage_matches,
    "sackmann_players": stage_sackmann.stage_players,
    "sackmann_rankings": stage_sackmann.stage_rankings,
    "tennisdata_matches": stage_tennisdata.stage_matches,
}


@dataclass
class StagingReport:
    table_rows: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [f"{table}: {count} rows" for table, count in sorted(self.table_rows.items())]
        lines.extend(f"  WARNING {message}" for message in self.warnings)
        return lines


def build_staging(manifest: Manifest, warehouse: Warehouse) -> StagingReport:
    warehouse.ensure_schema(STAGING_SCHEMA)
    report = StagingReport()
    for table, build_frame in _TABLE_BUILDERS.items():
        frame = build_frame(manifest)
        warehouse.replace_table(f"{STAGING_SCHEMA}.{table}", frame)
        report.table_rows[table] = len(frame)
        report.warnings.extend(_unmapped_round_warnings(table, frame))
    return report


def _unmapped_round_warnings(table: str, frame: pd.DataFrame) -> list[str]:
    if "round" not in frame.columns or "round_raw" not in frame.columns:
        return []
    unmapped = frame.loc[frame["round"].isna() & frame["round_raw"].notna(), "round_raw"]
    if unmapped.empty:
        return []
    return [
        f"{table}: {count} rows round_raw={raw!r} unmapped"
        for raw, count in unmapped.value_counts().items()
    ]
