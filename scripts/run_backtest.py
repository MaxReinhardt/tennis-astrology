"""Run one walk-forward backtest against the DuckDB warehouse."""

import argparse
import json
import sys
from pathlib import Path

from tennisdb import warehouse
from tennisdb.backtest.request import BacktestRequest, InvalidBacktestRequest
from tennisdb.backtest.staking import parse_stake_plan
from tennisdb.backtest.strategies import STRATEGIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), help="strategy to run")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="strategy parameter override, repeatable (e.g. --param theta=0.1)",
    )
    parser.add_argument("--stake", default="flat", help="stake plan, e.g. 'flat', 'kelly:0.25'")
    parser.add_argument("--tour", choices=["atp", "wta"], help="restrict to one tour")
    parser.add_argument(
        "--surface",
        action="append",
        default=[],
        dest="surfaces",
        help="restrict to a surface, repeatable",
    )
    parser.add_argument(
        "--round",
        action="append",
        default=[],
        dest="rounds",
        help="restrict to a round, repeatable",
    )
    parser.add_argument("--from", type=int, dest="from_season", help="first season (inclusive)")
    parser.add_argument("--to", type=int, dest="to_season", help="last season (inclusive)")
    parser.add_argument(
        "--fill",
        action="append",
        default=[],
        dest="fill_preference",
        help="bookmaker fill preference, repeatable in priority order (e.g. --fill PS --fill Avg)",
    )
    parser.add_argument("--slippage", type=float, help="fractional price haircut on fill")
    parser.add_argument("--bankroll", type=float, help="starting bankroll")
    parser.add_argument("--request", help="path to a JSON request file, or '-' for stdin")
    parser.add_argument(
        "--json", action="store_true", help="print the result as JSON instead of a table"
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="print the request schema and strategy/stake/metric catalog, then exit",
    )
    return parser.parse_args()


def _parse_param_overrides(pairs: list[str]) -> dict[str, float]:
    overrides = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator:
            raise InvalidBacktestRequest(f"--param {pair!r} must be NAME=VALUE")
        overrides[name] = float(value)
    return overrides


def _request_from_args(args: argparse.Namespace) -> BacktestRequest:
    if args.request:
        source = (
            sys.stdin.read()
            if args.request == "-"
            else Path(args.request).read_text(encoding="utf-8")
        )
        return BacktestRequest.from_dict(json.loads(source))

    if not args.strategy:
        raise InvalidBacktestRequest("--strategy is required unless --request is given")

    stake_rule, stake_parameters = parse_stake_plan(args.stake)
    payload: dict = {
        "strategy": args.strategy,
        "strategy_parameters": _parse_param_overrides(args.param),
        "filters": {
            "tour": args.tour,
            "surfaces": args.surfaces,
            "rounds": args.rounds,
            "from_season": args.from_season,
            "to_season": args.to_season,
        },
        "stake_rule": stake_rule,
        "stake_parameters": stake_parameters,
    }
    if args.fill_preference:
        payload["fill_preference"] = args.fill_preference
    if args.slippage is not None:
        payload["slippage"] = args.slippage
    if args.bankroll is not None:
        payload["starting_bankroll"] = args.bankroll
    return BacktestRequest.from_dict(payload)


def run(request: BacktestRequest, as_json: bool) -> int:
    from tennisdb.backtest.engine import run_backtest
    from tennisdb.backtest.opportunities import DuckDbOpportunitySource
    from tennisdb.backtest.report import write_artifacts

    connection = warehouse.connect()
    try:
        source = DuckDbOpportunitySource.open(connection)
        result = run_backtest(request, source)
        if result.matches_seen == 0:
            print("no matches in the warehouse match these filters")
            return 1
        run_directory = write_artifacts(result)
        connection.execute(
            "INSERT INTO tennis.ingest_log (step, stats) VALUES ('backtest:run', CAST(? AS JSON))",
            [json.dumps(result.stats())],
        )
    finally:
        connection.close()

    if as_json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print("\n".join(result.summary_lines()))
        print(f"artifacts written to {run_directory}")
    return 0


def run_catalog() -> int:
    from tennisdb.backtest.catalog import catalog

    connection = warehouse.connect()
    try:
        document = catalog(connection)
    finally:
        connection.close()
    print(json.dumps(document, indent=2, default=str))
    return 0


def main() -> int:
    args = parse_args()
    if args.catalog:
        return run_catalog()
    if not (args.strategy or args.request):
        print("nothing to do: pass --strategy, --request, or --catalog")
        return 2
    try:
        request = _request_from_args(args)
    except (InvalidBacktestRequest, ValueError) as error:
        print(f"invalid request: {error}")
        return 1
    return run(request, args.json)


if __name__ == "__main__":
    sys.exit(main())
