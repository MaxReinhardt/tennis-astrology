"""Staking rules turn a strategy's edge view into a stake. Each rule is a small
Strategy object (composition, not a branch on stake_rule) selected by name from
STAKE_RULES — the same registry/factory shape as backtest.strategies.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Protocol

from tennisdb.backtest.strategies.base import ParameterSpec


@dataclass(frozen=True)
class WagerContext:
    probability: float
    price: float
    bankroll: float


class StakingStrategy(Protocol):
    name: str

    def stake(self, wager: WagerContext) -> float: ...


@dataclass(frozen=True)
class FlatStake:
    """Bet a fixed currency amount every time, capped at the remaining bankroll."""

    name: ClassVar[str] = "flat"
    amount: float = 10.0

    def stake(self, wager: WagerContext) -> float:
        return min(max(self.amount, 0.0), wager.bankroll)


@dataclass(frozen=True)
class FixedFractionStake:
    """Bet a fixed fraction of the current bankroll every time."""

    name: ClassVar[str] = "fixed_fraction"
    fraction: float = 0.01

    def stake(self, wager: WagerContext) -> float:
        return wager.bankroll * max(self.fraction, 0.0)


@dataclass(frozen=True)
class FractionalKellyStake:
    """Fractional Kelly: size by edge over the price taken, capped at `cap` of
    bankroll. Zero edge or zero/negative price never produces a positive stake."""

    name: ClassVar[str] = "kelly"
    multiplier: float = 0.25
    cap: float = 0.05

    def stake(self, wager: WagerContext) -> float:
        if wager.price <= 1.0:
            return 0.0
        edge = wager.probability * (wager.price - 1.0) - (1.0 - wager.probability)
        full_kelly = edge / (wager.price - 1.0)
        fraction = min(max(full_kelly, 0.0) * self.multiplier, self.cap)
        return wager.bankroll * fraction


@dataclass(frozen=True)
class StakeDefinition:
    name: str
    description: str
    factory: Callable[[Mapping[str, float]], StakingStrategy]
    parameters: tuple[ParameterSpec, ...]


def _build_flat(parameters: Mapping[str, float]) -> FlatStake:
    return FlatStake(amount=parameters["amount"])


def _build_fixed_fraction(parameters: Mapping[str, float]) -> FixedFractionStake:
    return FixedFractionStake(fraction=parameters["fraction"])


def _build_kelly(parameters: Mapping[str, float]) -> FractionalKellyStake:
    return FractionalKellyStake(multiplier=parameters["multiplier"], cap=parameters["cap"])


STAKE_RULES: dict[str, StakeDefinition] = {
    "flat": StakeDefinition(
        name="flat",
        description="Bet a fixed currency amount on every signal.",
        factory=_build_flat,
        parameters=(
            ParameterSpec(
                "amount", "number", 10.0, 0.0, None, "stake per bet, in bankroll currency"
            ),
        ),
    ),
    "fixed_fraction": StakeDefinition(
        name="fixed_fraction",
        description="Bet a fixed fraction of the current bankroll on every signal.",
        factory=_build_fixed_fraction,
        parameters=(
            ParameterSpec(
                "fraction", "number", 0.01, 0.0, 1.0, "fraction of bankroll staked per bet"
            ),
        ),
    ),
    "kelly": StakeDefinition(
        name="kelly",
        description="Fractional Kelly: size by edge over the price taken, capped.",
        factory=_build_kelly,
        parameters=(
            ParameterSpec("multiplier", "number", 0.25, 0.0, 1.0, "fraction of full Kelly to bet"),
            ParameterSpec(
                "cap", "number", 0.05, 0.0, 1.0, "maximum bankroll fraction staked per bet"
            ),
        ),
    ),
}


def build_staking(name: str, parameters: Mapping[str, float]) -> StakingStrategy:
    definition = STAKE_RULES[name]
    resolved = {
        spec.name: parameters.get(spec.name, spec.default) for spec in definition.parameters
    }
    return definition.factory(resolved)


def parse_stake_plan(plan: str) -> tuple[str, dict[str, float]]:
    """Parse the CLI's `--stake kelly:0.25` shorthand into (stake_rule, stake_parameters),
    overriding that rule's first parameter. The structured JSON request always uses
    stake_rule + stake_parameters directly — this shorthand exists only for the command
    line, so it raises a plain ValueError rather than the request's own error type."""
    name, _, raw_value = plan.partition(":")
    if name not in STAKE_RULES:
        raise ValueError(f"stake plan: {name!r} is not one of {sorted(STAKE_RULES)}")
    if not raw_value:
        return name, {}
    primary_parameter = STAKE_RULES[name].parameters[0].name
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"stake plan: {raw_value!r} is not a number") from error
    return name, {primary_parameter: value}
