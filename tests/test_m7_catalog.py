"""M7: the natural-language contract regression suite. These tests exist so a new
request field, strategy, stake rule or metric can never be added without the catalog
(the future LLM wrapper's tool definition) automatically picking it up."""

import dataclasses
import json
from datetime import date

import pytest

from tennisdb.backtest.catalog import catalog, request_schema
from tennisdb.backtest.domain import SettledBet
from tennisdb.backtest.metrics import BacktestMetrics
from tennisdb.backtest.report import METRIC_SPECS, build_result
from tennisdb.backtest.request import BacktestRequest
from tennisdb.backtest.staking import STAKE_RULES
from tennisdb.backtest.strategies import STRATEGIES

pytestmark = pytest.mark.m7


def test_every_backtest_request_field_is_in_the_schema():
    request_fields = {field.name for field in dataclasses.fields(BacktestRequest)}
    schema_properties = set(request_schema()["properties"])

    assert request_fields <= schema_properties


def test_every_strategy_appears_in_the_catalog_with_its_parameters():
    document = catalog()
    catalog_strategies = {entry["name"]: entry for entry in document["strategies"]}

    assert set(catalog_strategies) == set(STRATEGIES)
    for name, definition in STRATEGIES.items():
        catalog_parameters = {p["name"] for p in catalog_strategies[name]["parameters"]}
        assert catalog_parameters == {spec.name for spec in definition.parameters}


def test_every_stake_rule_appears_in_the_catalog_with_its_parameters():
    document = catalog()
    catalog_rules = {entry["name"]: entry for entry in document["stake_rules"]}

    assert set(catalog_rules) == set(STAKE_RULES)
    for name, definition in STAKE_RULES.items():
        catalog_parameters = {p["name"] for p in catalog_rules[name]["parameters"]}
        assert catalog_parameters == {spec.name for spec in definition.parameters}


def test_every_metric_spec_key_exists_on_backtest_metrics():
    metrics_fields = {field.name for field in dataclasses.fields(BacktestMetrics)}

    assert {spec.key for spec in METRIC_SPECS} <= metrics_fields


def test_a_request_built_from_schema_defaults_validates_for_every_strategy():
    for name in STRATEGIES:
        request = BacktestRequest.from_dict({"strategy": name})
        assert request.strategy == name


def test_catalog_is_json_serializable():
    document = catalog()

    serialized = json.dumps(document)

    assert "elo_value" in serialized


def test_strategy_enum_in_schema_matches_the_registry():
    schema = request_schema()

    assert set(schema["properties"]["strategy"]["enum"]) == set(STRATEGIES)


def test_result_to_dict_is_json_serializable_with_every_metric_formatted():
    request = BacktestRequest.from_dict({"strategy": "random_bet"})
    bets = [
        SettledBet(
            match_id="m0", match_date=date(2020, 1, 1), side="p1", probability=0.6,
            price=2.0, fill_price=2.0, consensus_price=2.0, consensus_prob=0.6,
            stake=10.0, profit=10.0, won=True, bankroll_after=1010.0,
        ),
        SettledBet(
            match_id="m1", match_date=date(2020, 1, 2), side="p2", probability=0.4,
            price=1.8, fill_price=1.8, consensus_price=1.8, consensus_prob=0.4,
            stake=10.0, profit=-10.0, won=False, bankroll_after=1000.0,
        ),
    ]  # fmt: skip

    result = build_result(request, matches_seen=2, bets=bets)
    document = result.to_dict()

    json.dumps(document)
    assert all(metric["formatted"] for metric in document["metrics"])


def test_every_strategy_stake_rule_and_parameter_has_a_plain_label():
    document = catalog()

    definitions = [*document["strategies"], *document["stake_rules"]]
    assert all(entry["label"].strip() for entry in definitions)
    assert all(
        parameter["label"].strip() for entry in definitions for parameter in entry["parameters"]
    )


def test_every_metric_has_a_plain_description():
    assert all(spec.description.strip() for spec in METRIC_SPECS)
    assert all(entry["description"].strip() for entry in catalog()["metrics"])


def test_result_metrics_carry_their_description():
    request = BacktestRequest.from_dict({"strategy": "random_bet"})

    document = build_result(request, matches_seen=0, bets=[]).to_dict()

    assert all(metric["description"] for metric in document["metrics"])
