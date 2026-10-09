"""Host-nation strategies (M8 S4): back, or bet against, the player who shares the
tournament host's nationality. They bet only when exactly one player is "at home" —
with both or neither, nationality carries no asymmetry to test. Like the other
baselines they have no probability view of their own and use the market's consensus."""

from dataclasses import dataclass
from typing import ClassVar

from tennisdb.backtest.domain import Bet, MatchOpportunity, Side
from tennisdb.backtest.strategies.baselines import _bet_within_band


def _home_side(opportunity: MatchOpportunity) -> Side | None:
    if opportunity.is_home("p1") == opportunity.is_home("p2"):
        return None
    return "p1" if opportunity.is_home("p1") else "p2"


@dataclass
class BackHomeNation:
    name: ClassVar[str] = "back_home_nation"
    min_price: float = 1.01
    max_price: float = 1000.0

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        home = _home_side(opportunity)
        if home is None:
            return None
        return _bet_within_band(opportunity, home, self.min_price, self.max_price)


@dataclass
class FadeHomeNation:
    name: ClassVar[str] = "fade_home_nation"
    min_price: float = 1.01
    max_price: float = 1000.0

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        home = _home_side(opportunity)
        if home is None:
            return None
        visitor: Side = "p2" if home == "p1" else "p1"
        return _bet_within_band(opportunity, visitor, self.min_price, self.max_price)
