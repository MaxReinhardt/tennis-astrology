"""Strategy registry and factory — the composition root for backtest strategies.
Adding a strategy means adding one entry to STRATEGIES; request validation
(request.py) and the natural-language catalog (catalog.py) both read this registry,
so neither can ever offer a strategy the engine cannot actually run.

Labels and descriptions are written for people new to betting: they are what the web UI
shows in its dropdowns and tooltips.
"""

from collections.abc import Mapping

from tennisdb.backtest.strategies.base import ParameterSpec, Strategy, StrategyDefinition
from tennisdb.backtest.strategies.baselines import BackFavorites, BackUnderdogs, RandomBet
from tennisdb.backtest.strategies.elo_value import EloValue
from tennisdb.backtest.strategies.host_nation import BackHomeNation, FadeHomeNation

_PRICE_BAND_PARAMETERS = (
    ParameterSpec(
        "min_price",
        "Lowest odds",
        "number",
        1.01,
        1.01,
        1000.0,
        "Only bet when the odds are at least this. Decimal odds of 1.50 mean a 10 bet "
        "returns 15 if it wins; higher odds mean a less likely player.",
    ),
    ParameterSpec(
        "max_price",
        "Highest odds",
        "number",
        1000.0,
        1.01,
        1000.0,
        "Only bet when the odds are at most this. Lower this to skip long shots.",
    ),
)


def _build_random_bet(parameters: Mapping[str, float]) -> RandomBet:
    return RandomBet(seed=int(parameters["seed"]))


def _build_back_favorites(parameters: Mapping[str, float]) -> BackFavorites:
    return BackFavorites(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_back_underdogs(parameters: Mapping[str, float]) -> BackUnderdogs:
    return BackUnderdogs(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_back_home_nation(parameters: Mapping[str, float]) -> BackHomeNation:
    return BackHomeNation(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_fade_home_nation(parameters: Mapping[str, float]) -> FadeHomeNation:
    return FadeHomeNation(min_price=parameters["min_price"], max_price=parameters["max_price"])


def _build_elo_value(parameters: Mapping[str, float]) -> EloValue:
    return EloValue(theta=parameters["theta"], use_surface_elo=bool(parameters["use_surface_elo"]))


STRATEGIES: dict[str, StrategyDefinition] = {
    "random_bet": StrategyDefinition(
        name="random_bet",
        label="Coin flip (control)",
        description=(
            "Bets on a randomly chosen player in every match. It is a yardstick, not a "
            "strategy: any real idea should do better than a coin flip, which is expected "
            "to lose roughly the bookmaker's margin."
        ),
        factory=_build_random_bet,
        parameters=(
            ParameterSpec(
                "seed",
                "Random seed",
                "integer",
                7,
                0,
                None,
                "Number that fixes the coin flips so a run can be repeated exactly.",
            ),
        ),
    ),
    "back_favorites": StrategyDefinition(
        name="back_favorites",
        label="Always back the favourite",
        description=(
            "Bets on the player the bookmaker thinks is more likely to win, in every match. "
            "Optionally limit it to a range of odds."
        ),
        factory=_build_back_favorites,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "back_underdogs": StrategyDefinition(
        name="back_underdogs",
        label="Always back the underdog",
        description=(
            "Bets on the player the bookmaker thinks is less likely to win, in every match. "
            "Optionally limit it to a range of odds."
        ),
        factory=_build_back_underdogs,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "back_home_nation": StrategyDefinition(
        name="back_home_nation",
        label="Back the home player",
        description=(
            "Bets on the player from the country hosting the tournament, in matches where "
            "exactly one player is local. Optionally limit it to a range of odds."
        ),
        factory=_build_back_home_nation,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "fade_home_nation": StrategyDefinition(
        name="fade_home_nation",
        label="Back the visitor against a home player",
        description=(
            "Bets on the visiting player when their opponent is from the country hosting "
            "the tournament and they are not. Optionally limit it to a range of odds."
        ),
        factory=_build_fade_home_nation,
        parameters=_PRICE_BAND_PARAMETERS,
    ),
    "elo_value": StrategyDefinition(
        name="elo_value",
        label="Back players our rating likes more than the bookmaker",
        description=(
            "Uses an Elo rating (a score that rises with wins and falls with losses) to "
            "estimate each player's chance. Bets when that chance beats the bookmaker's "
            "own estimate by at least the chosen gap."
        ),
        factory=_build_elo_value,
        parameters=(
            ParameterSpec(
                "theta",
                "Required gap (θ)",
                "number",
                0.05,
                0.0,
                0.5,
                "How much higher our win chance must be than the bookmaker's before we bet. "
                "0.05 means 5 percentage points.",
            ),
            ParameterSpec(
                "use_surface_elo",
                "Use surface-specific ratings",
                "integer",
                0,
                0,
                1,
                "0 uses one overall rating per player; 1 uses a separate rating for the "
                "court surface being played.",
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
