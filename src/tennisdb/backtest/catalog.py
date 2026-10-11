"""The natural-language contract: a JSON-Schema description of every request field,
strategy, stake rule and output metric, assembled directly from the registries so it
can never drift from what the engine actually accepts and returns. This *is* the tool
definition a future cheap-model LLM wrapper would hand to an LLM to translate a
question into a BacktestRequest — there is no separate spec to keep in sync.
"""

import json
from pathlib import Path

import duckdb

from tennisdb import config
from tennisdb.backtest.report import METRIC_SPECS, MetricSpec
from tennisdb.backtest.request import VALID_BOOKMAKERS, VALID_SURFACES, VALID_TOURS
from tennisdb.backtest.staking import STAKE_RULES
from tennisdb.backtest.strategies import STRATEGIES
from tennisdb.backtest.strategies.base import ParameterSpec
from tennisdb.features.ordering import ROUND_ORDINAL


def _parameter_schema(spec: ParameterSpec) -> dict:
    schema: dict = {
        "type": "integer" if spec.kind == "integer" else "number",
        "default": spec.default,
        "description": spec.description,
    }
    if spec.minimum is not None:
        schema["minimum"] = spec.minimum
    if spec.maximum is not None:
        schema["maximum"] = spec.maximum
    return schema


def request_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "BacktestRequest",
        "type": "object",
        "required": ["strategy"],
        "additionalProperties": False,
        "properties": {
            "strategy": {"type": "string", "enum": sorted(STRATEGIES)},
            "strategy_parameters": {
                "type": "object",
                "description": (
                    "Parameters for the chosen strategy; see this strategy's entry "
                    "in the `strategies` catalog for the exact fields allowed."
                ),
            },
            "filters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tour": {"type": ["string", "null"], "enum": [*VALID_TOURS, None]},
                    "surfaces": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(VALID_SURFACES)},
                    },
                    "levels": {"type": "array", "items": {"type": "string"}},
                    "rounds": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(ROUND_ORDINAL)},
                    },
                    "from_season": {"type": ["integer", "null"]},
                    "to_season": {"type": ["integer", "null"]},
                },
            },
            "stake_rule": {"type": "string", "enum": sorted(STAKE_RULES)},
            "stake_parameters": {
                "type": "object",
                "description": (
                    "Parameters for the chosen stake rule; see this rule's entry in "
                    "the `stake_rules` catalog for the exact fields allowed."
                ),
            },
            "fill_preference": {
                "type": "array",
                "items": {"type": "string", "enum": list(VALID_BOOKMAKERS)},
                "minItems": 1,
                "description": (
                    "Bookmakers to fill bets at, in preference order; the first one "
                    "present on a match wins."
                ),
            },
            "slippage": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Fractional price haircut applied to every fill: 0.01 pays 1% worse "
                    "odds than quoted, a stand-in for prices moving before the bet lands."
                ),
            },
            "starting_bankroll": {
                "type": "number",
                "exclusiveMinimum": 0.0,
                "description": "Money the simulation starts with, in the same currency as bets.",
            },
            "bootstrap_draws": {"type": "integer", "minimum": 100, "maximum": 20_000},
            "random_seed": {"type": "integer"},
        },
    }


def _parameter_entry(spec: ParameterSpec) -> dict:
    return {
        "name": spec.name,
        "label": spec.label,
        "type": spec.kind,
        "default": spec.default,
        "minimum": spec.minimum,
        "maximum": spec.maximum,
        "description": spec.description,
    }


def _strategy_entry(name: str) -> dict:
    definition = STRATEGIES[name]
    return {
        "name": definition.name,
        "label": definition.label,
        "description": definition.description,
        "parameters": [_parameter_entry(spec) for spec in definition.parameters],
    }


def _stake_rule_entry(name: str) -> dict:
    definition = STAKE_RULES[name]
    return {
        "name": definition.name,
        "label": definition.label,
        "description": definition.description,
        "parameters": [_parameter_entry(spec) for spec in definition.parameters],
    }


def _metric_entry(spec: MetricSpec) -> dict:
    return {
        "key": spec.key,
        "label": spec.label,
        "unit": spec.unit,
        "description": spec.description,
    }


def _warehouse_summary(connection: duckdb.DuckDBPyConnection) -> dict:
    season_low, season_high = connection.execute(
        "SELECT min(season), max(season) FROM tennis.tournament_editions"
    ).fetchone()
    bookmaker_rows = connection.execute("SELECT DISTINCT bookmaker FROM tennis.odds").fetchall()
    bookmakers = [row[0] for row in bookmaker_rows]
    backtestable_matches = connection.execute(
        "SELECT count(*) FROM analytics.market JOIN analytics.elo_pre USING (match_id)"
    ).fetchone()[0]
    return {
        "season_range": [season_low, season_high],
        "bookmakers": sorted(bookmakers),
        "backtestable_matches": backtestable_matches,
    }


def catalog(connection: duckdb.DuckDBPyConnection | None = None) -> dict:
    document = {
        "request_schema": request_schema(),
        "strategies": [_strategy_entry(name) for name in sorted(STRATEGIES)],
        "stake_rules": [_stake_rule_entry(name) for name in sorted(STAKE_RULES)],
        "filters": {
            "tours": list(VALID_TOURS),
            "surfaces": list(VALID_SURFACES),
            "rounds": list(ROUND_ORDINAL),
            "bookmakers": list(VALID_BOOKMAKERS),
        },
        "metrics": [_metric_entry(spec) for spec in METRIC_SPECS],
    }
    if connection is not None:
        document["warehouse"] = _warehouse_summary(connection)
    return document


def write_catalog(
    path: Path = config.BACKTESTS_DIR / "catalog.json",
    connection: duckdb.DuckDBPyConnection | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog(connection), indent=2, default=str), encoding="utf-8")
    return path
