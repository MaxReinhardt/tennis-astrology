"""Run the pre-registered research studies: backtests and market-relative tests, with
results written to studies/results/ and into each study's markdown document."""

import argparse
import json
import sys

from tennisdb import warehouse
from tennisdb.backtest.opportunities import DuckDbOpportunitySource
from tennisdb.research.artifacts import write_study_artifacts
from tennisdb.research.context import EngineBacktestRunner, StudyContext
from tennisdb.research.duckdb_cross_section import DuckDbCrossSection
from tennisdb.research.studies import STUDIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=[*sorted(STUDIES), "all"], default="all")
    parser.add_argument("--no-plots", action="store_true", help="skip PNG rendering")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = sorted(STUDIES) if args.study == "all" else [args.study]
    connection = warehouse.connect()
    context = StudyContext(
        EngineBacktestRunner(DuckDbOpportunitySource.open(connection)),
        DuckDbCrossSection(connection),
    )
    payloads = []
    for study_id in selected:
        study = STUDIES[study_id]
        result = study.run(context)
        write_study_artifacts(study, result, with_plots=not args.no_plots)
        connection.execute(
            "INSERT INTO tennis.ingest_log (step, stats) VALUES ('study:run', CAST(? AS JSON))",
            [json.dumps(result.stats())],
        )
        payloads.append(result.to_dict())
        if not args.json:
            print("\n".join(result.summary_lines()))
    if args.json:
        print(json.dumps(payloads, indent=2))
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
