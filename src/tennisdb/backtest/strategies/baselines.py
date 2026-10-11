"""Reference baseline strategies. RandomBet is the control (expected to lose
approximately the bookmaker's overround with ~zero CLV — a canary for the engine's
accounting, not a strategy to trade). BackFavorites/BackUnderdogs are the classic
favourite–longshot-bias benchmarks, each with an optional price band for odds-bucket
studies (M8 S2).
"""

import random
from dataclasses import dataclass, field
from typing import ClassVar

from tennisdb.backtest.domain import Bet, MatchOpportunity, Side


@dataclass
class RandomBet:
    """Picks a side by coin flip, using the market's own consensus probability as its
    probability view — so a Kelly stake sizes it the same way the market would."""

    name: ClassVar[str] = "random_bet"
    seed: int = 7
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        side: Side = "p1" if self._rng.random() < 0.5 else "p2"
        return Bet(side=side, probability=opportunity.consensus_prob(side))


def _favorite_side(opportunity: MatchOpportunity) -> Side:
    return "p1" if opportunity.p1_price < opportunity.p2_price else "p2"


def _bet_within_band(
    opportunity: MatchOpportunity, side: Side, min_price: float, max_price: float
) -> Bet | None:
    price = opportunity.price(side)
    if not (min_price <= price <= max_price):
        return None
    return Bet(side=side, probability=opportunity.consensus_prob(side))


@dataclass
class BackFavorites:
    """Back whichever side the fill book prices as favourite, within an optional price
    band. Has no independent probability view, so it uses the market's own consensus
    probability — a Kelly stake then sizes it near zero, the correct behaviour for a
    strategy with no edge of its own."""

    name: ClassVar[str] = "back_favorites"
    min_price: float = 1.01
    max_price: float = 1000.0

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        return _bet_within_band(
            opportunity, _favorite_side(opportunity), self.min_price, self.max_price
        )


@dataclass
class BackUnderdogs:
    """Back whichever side the fill book prices as underdog, within an optional price
    band — see BackFavorites for the probability-view rationale."""

    name: ClassVar[str] = "back_underdogs"
    min_price: float = 1.01
    max_price: float = 1000.0

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        favorite = _favorite_side(opportunity)
        underdog: Side = "p2" if favorite == "p1" else "p1"
        return _bet_within_band(opportunity, underdog, self.min_price, self.max_price)
