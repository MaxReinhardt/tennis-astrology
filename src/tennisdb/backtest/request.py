"""The one JSON-serializable request the engine accepts, and its single validation
gate. BacktestRequest.from_dict is where untrusted input — a CLI flag parser, a JSON
file, or a future LLM wrapper's tool call — turns into a request the engine trusts.
Validation is driven by the same ParameterSpec/StakeDefinition tables the catalog
(catalog.py) publishes, so a rejection message always names the actual allowed
values: a wrapper can retry from the error text alone, with no separate spec to keep
in sync.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from tennisdb.backtest.staking import STAKE_RULES
from tennisdb.backtest.strategies import STRATEGIES
from tennisdb.backtest.strategies.base import ParameterSpec
from tennisdb.features.ordering import ROUND_ORDINAL

VALID_TOURS = ("atp", "wta")
VALID_SURFACES = ("Hard", "Clay", "Grass", "Carpet")
VALID_BOOKMAKERS = ("B365", "PS", "Max", "Avg")

_FILTER_FIELDS = frozenset(
    {"tour", "surfaces", "levels", "rounds", "from_season", "to_season"}
)
_REQUEST_FIELDS = frozenset(
    {
        "strategy", "strategy_parameters", "filters", "stake_rule", "stake_parameters",
        "fill_preference", "slippage", "starting_bankroll", "bootstrap_draws", "random_seed",
    }
)  # fmt: skip


class InvalidBacktestRequest(ValueError):
    pass


def _reject_unknown_keys(scope: str, payload: Mapping, allowed: frozenset[str]) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise InvalidBacktestRequest(
            f"{scope}: unknown field(s) {sorted(unknown)}; allowed: {sorted(allowed)}"
        )


def _validate_choice(field_name: str, value, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    if value not in allowed:
        raise InvalidBacktestRequest(f"{field_name}: {value!r} is not one of {allowed}")
    return value


def _validate_choices(field_name: str, values, allowed: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(values)
    invalid = [value for value in result if value not in allowed]
    if invalid:
        raise InvalidBacktestRequest(f"{field_name}: {invalid} not in {allowed}")
    return result


def _validate_bounded(field_name: str, value, minimum: float, maximum: float) -> float:
    number = float(value)
    if not (minimum <= number <= maximum):
        raise InvalidBacktestRequest(f"{field_name}: {number} outside [{minimum}, {maximum}]")
    return number


def _validate_positive(field_name: str, value) -> float:
    number = float(value)
    if number <= 0:
        raise InvalidBacktestRequest(f"{field_name}: {number} must be positive")
    return number


def _require_registered(field_name: str, value, registry: Mapping[str, object]) -> str:
    if value not in registry:
        raise InvalidBacktestRequest(f"{field_name}: {value!r} is not one of {sorted(registry)}")
    return value


def _validate_parameters(
    scope: str, payload: Mapping, specs: tuple[ParameterSpec, ...]
) -> dict[str, float]:
    allowed = {spec.name: spec for spec in specs}
    unknown = set(payload) - allowed.keys()
    if unknown:
        raise InvalidBacktestRequest(
            f"{scope}: unknown parameter(s) {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    return {
        name: _validate_parameter_value(f"{scope}.{name}", payload.get(name, spec.default), spec)
        for name, spec in allowed.items()
    }


def _validate_parameter_value(field_name: str, value, spec: ParameterSpec) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidBacktestRequest(f"{field_name}: {value!r} is not a number")
    number = float(value)
    if spec.minimum is not None and number < spec.minimum:
        raise InvalidBacktestRequest(f"{field_name}: {number} is below minimum {spec.minimum}")
    if spec.maximum is not None and number > spec.maximum:
        raise InvalidBacktestRequest(f"{field_name}: {number} is above maximum {spec.maximum}")
    return number


@dataclass(frozen=True)
class MatchFilter:
    tour: str | None = None
    surfaces: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    rounds: tuple[str, ...] = ()
    from_season: int | None = None
    to_season: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping) -> "MatchFilter":
        _reject_unknown_keys("filters", payload, _FILTER_FIELDS)
        tour = _validate_choice("filters.tour", payload.get("tour"), VALID_TOURS)
        surfaces = _validate_choices(
            "filters.surfaces", payload.get("surfaces", ()), VALID_SURFACES
        )
        rounds = _validate_choices(
            "filters.rounds", payload.get("rounds", ()), tuple(ROUND_ORDINAL)
        )
        levels = tuple(payload.get("levels", ()))
        from_season = payload.get("from_season")
        to_season = payload.get("to_season")
        if from_season is not None and to_season is not None and from_season > to_season:
            raise InvalidBacktestRequest(
                f"filters: from_season ({from_season}) must not exceed to_season ({to_season})"
            )
        return cls(
            tour=tour,
            surfaces=surfaces,
            levels=levels,
            rounds=rounds,
            from_season=from_season,
            to_season=to_season,
        )

    def to_dict(self) -> dict:
        return {
            "tour": self.tour,
            "surfaces": list(self.surfaces),
            "levels": list(self.levels),
            "rounds": list(self.rounds),
            "from_season": self.from_season,
            "to_season": self.to_season,
        }


@dataclass(frozen=True)
class BacktestRequest:
    strategy: str
    strategy_parameters: Mapping[str, float] = field(default_factory=dict)
    filters: MatchFilter = field(default_factory=MatchFilter)
    stake_rule: str = "flat"
    stake_parameters: Mapping[str, float] = field(default_factory=dict)
    fill_preference: tuple[str, ...] = ("PS", "Avg")
    slippage: float = 0.01
    starting_bankroll: float = 1000.0
    bootstrap_draws: int = 2000
    random_seed: int = 7

    @classmethod
    def from_dict(cls, payload: Mapping) -> "BacktestRequest":
        _reject_unknown_keys("request", payload, _REQUEST_FIELDS)
        strategy = _require_registered("strategy", payload.get("strategy"), STRATEGIES)
        strategy_parameters = _validate_parameters(
            "strategy_parameters",
            payload.get("strategy_parameters", {}),
            STRATEGIES[strategy].parameters,
        )
        filters = MatchFilter.from_dict(payload.get("filters", {}))
        stake_rule = _require_registered(
            "stake_rule", payload.get("stake_rule", "flat"), STAKE_RULES
        )
        stake_parameters = _validate_parameters(
            "stake_parameters",
            payload.get("stake_parameters", {}),
            STAKE_RULES[stake_rule].parameters,
        )
        fill_preference = _validate_choices(
            "fill_preference", payload.get("fill_preference", ("PS", "Avg")), VALID_BOOKMAKERS
        )
        if not fill_preference:
            raise InvalidBacktestRequest("fill_preference: must name at least one bookmaker")
        slippage = _validate_bounded("slippage", payload.get("slippage", 0.01), 0.0, 1.0)
        starting_bankroll = _validate_positive(
            "starting_bankroll", payload.get("starting_bankroll", 1000.0)
        )
        bootstrap_draws = int(
            _validate_bounded("bootstrap_draws", payload.get("bootstrap_draws", 2000), 100, 20_000)
        )
        random_seed = int(payload.get("random_seed", 7))
        return cls(
            strategy=strategy,
            strategy_parameters=strategy_parameters,
            filters=filters,
            stake_rule=stake_rule,
            stake_parameters=stake_parameters,
            fill_preference=fill_preference,
            slippage=slippage,
            starting_bankroll=starting_bankroll,
            bootstrap_draws=bootstrap_draws,
            random_seed=random_seed,
        )

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "strategy_parameters": dict(self.strategy_parameters),
            "filters": self.filters.to_dict(),
            "stake_rule": self.stake_rule,
            "stake_parameters": dict(self.stake_parameters),
            "fill_preference": list(self.fill_preference),
            "slippage": self.slippage,
            "starting_bankroll": self.starting_bankroll,
            "bootstrap_draws": self.bootstrap_draws,
            "random_seed": self.random_seed,
        }
