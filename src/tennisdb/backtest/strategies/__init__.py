"""Strategy registry and factory — the composition root for backtest strategies.
Adding a strategy means adding one entry to STRATEGIES; request validation
(request.py) and the natural-language catalog (catalog.py) both read this registry,
so neither can ever offer a strategy the engine cannot actually run.
"""

from collections.abc import Mapping

from tennisdb.backtest.strategies.base import ParameterSpec, Strategy, StrategyDefinition
from tennisdb.backtest.strategies.baselines import BackFavorites, BackUnderdogs, RandomBet
from tennisdb.backtest.strategies.elo_value import EloValue

_PRICE_BAND_PARAMETERS = (
    ParameterSpec(
        "min_price", "number", 1.01, 1.01, 1000.0, "minimum decimal price eligible to back"
    ),
    ParameterSpec(
        "max_price", "number", 1000.0, 1.01, 1000.0, "maximum decimal price eligible to back"
    ),
)


def _build_random_bet(parameters: Mapping[str, float]) -> RandomBet:
    return RandomBet(seed=int(parameters["seed"]))


def _build_back_favorites(parameters: Mapping[str, float]) -> BackFavorites:
    return BackFavorites(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_back_underdogs(parameters: Mapping[str, float]) -> BackUnderdogs:
    return BackUnderdogs(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_elo_value(parameters: Mapping[str, float]) -> EloValue:
    return EloValue(theta=parameters["theta"], use_surface_elo=bool(parameters["use_surface_elo"]))


STRATEGIES: dict[str, StrategyDefinition] = {
    "random_bet": StrategyDefinition(
        name="random_bet",
        description=(
            "Control strategy: picks a side by coin flip. Expected to lose approximately "
            "the bookmaker's overround and show ~zero CLV — a canary for the engine's "
            "accounting and the merge's correctness, not a strategy to trade."
        ),
        factory=_build_random_bet,
        parameters=(
            ParameterSpec("seed", "integer", 7, 0, None, "random seed for the coin flip"),
        ),
    ),
    "back_favorites": StrategyDefinition(
        name="back_favorites",
        description=(
            "Back the fill book's favourite on every match, within an optional price band."
        ),
        factory=_build_back_favorites,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "back_underdogs": StrategyDefinition(
        name="back_underdogs",
        description=(
            "Back the fill book's underdog on every match, within an optional price band."
        ),
        factory=_build_back_underdogs,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "elo_value": StrategyDefinition(
        name="elo_value",
        description=(
            "Back the side whose pre-match Elo win probability exceeds the no-vig "
            "consensus probability by at least theta."
        ),
        factory=_build_elo_value,
        parameters=(
            ParameterSpec(
                "theta", "number", 0.05, 0.0, 0.5, "required edge over the consensus market"
            ),
            ParameterSpec(
                "use_surface_elo",
                "integer",
                0,
                0,
                1,
                "1 to use surface Elo instead of overall Elo",
            ),
        ),
    ),
}


def build_strategy(name: str, parameters: Mapping[str, float]) -> Strategy:
    definition = STRATEGIES[name]
    resolved = {
        spec.name: parameters.get(spec.name, spec.default) for spec in definition.parameters
    }
    return definition.factory(resolved)
