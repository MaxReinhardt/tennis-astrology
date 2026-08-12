"""Compose the M6 feature builders — elo → form → market → astro — into the analytics
schema and log the row counts to tennis.ingest_log."""

import json
from dataclasses import dataclass, field

import duckdb

from tennisdb.features.astro import build_astro
from tennisdb.features.elo import build_elo
from tennisdb.features.form import build_form
from tennisdb.features.market import build_market

_BUILDERS = (
    ("elo_pre", build_elo),
    ("form", build_form),
    ("market", build_market),
    ("player_astro", build_astro),
)


@dataclass
class FeaturesReport:
    table_rows: dict[str, int] = field(default_factory=dict)

    def stats(self) -> dict:
        return {"table_rows": self.table_rows}

    def summary_lines(self) -> list[str]:
        return [f"analytics.{table}: {count} rows" for table, count in self.table_rows.items()]


def build_features(connection: duckdb.DuckDBPyConnection) -> FeaturesReport:
    report = FeaturesReport()
    for table, builder in _BUILDERS:
        report.table_rows[table] = builder(connection)
    connection.execute(
        "INSERT INTO tennis.ingest_log (step, stats) VALUES ('features:build', CAST(? AS JSON))",
        [json.dumps(report.stats())],
    )
    return report
