"""EloValue: bet the side whose pre-match Elo win probability exceeds the no-vig
consensus probability by at least theta — the classic "is the market wrong" value
strategy, and the one M7's no-lookahead canary test exercises."""

from dataclasses import dataclass
from typing import ClassVar

from tennisdb.backtest.domain import Bet, MatchOpportunity, Side


@dataclass
class EloValue:
    name: ClassVar[str] = "elo_value"
    theta: float = 0.05
    use_surface_elo: bool = False

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None:
        for side in ("p1", "p2"):
            if self._edge(opportunity, side) >= self.theta:
                return Bet(side=side, probability=opportunity.elo_prob(side, self.use_surface_elo))
        return None

    def _edge(self, opportunity: MatchOpportunity, side: Side) -> float:
        elo_probability = opportunity.elo_prob(side, self.use_surface_elo)
        consensus_probability = opportunity.consensus_prob(side)
        return elo_probability - consensus_probability
