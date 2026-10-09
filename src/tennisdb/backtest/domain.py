"""Core backtest entities: the pre-match view a strategy sees, the bet it places, and
the settled outcome. Framework-free — no duckdb, no pandas, no I/O.

MatchOpportunity and MatchEvent are deliberately separate types: a Strategy's `evaluate`
is typed to take only a MatchOpportunity, so "a strategy cannot see the outcome" is a
type-level guarantee, not a convention to remember.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

Side = Literal["p1", "p2"]


@dataclass(frozen=True)
class MatchOpportunity:
    """Everything known strictly before the match starts, oriented to the leak-free
    p1/p2 of tennis.matches_model. Prices are decimal odds from the strategy's fill
    book; consensus prices/probability are from the closing book analytics.market
    picked (Avg, else Pinnacle) — the benchmark CLV and fair_value_edge are judged
    against."""

    match_id: str
    match_date: date
    season: int
    tour: str
    surface: str | None
    level: str | None
    round: str
    p1_price: float
    p2_price: float
    p1_consensus_price: float
    p2_consensus_price: float
    p1_consensus_prob: float
    p1_elo_prob: float
    p1_surface_elo_prob: float
    p1_is_home: bool = False
    p2_is_home: bool = False

    def price(self, side: Side) -> float:
        return self.p1_price if side == "p1" else self.p2_price

    def is_home(self, side: Side) -> bool:
        """Whether `side` shares nationality with the tournament's host country. False
        whenever host country or a player's nationality is unknown (M8 S4)."""
        return self.p1_is_home if side == "p1" else self.p2_is_home

    def consensus_price(self, side: Side) -> float:
        return self.p1_consensus_price if side == "p1" else self.p2_consensus_price

    def consensus_prob(self, side: Side) -> float:
        return self.p1_consensus_prob if side == "p1" else 1.0 - self.p1_consensus_prob

    def elo_prob(self, side: Side, use_surface_elo: bool = False) -> float:
        prob = self.p1_surface_elo_prob if use_surface_elo else self.p1_elo_prob
        return prob if side == "p1" else 1.0 - prob


@dataclass(frozen=True)
class MatchEvent:
    """A MatchOpportunity plus its settlement. The engine sees this; a Strategy never
    does — only `event.opportunity` is passed to `Strategy.evaluate`."""

    opportunity: MatchOpportunity
    p1_won: bool

    def won(self, side: Side) -> bool:
        return self.p1_won if side == "p1" else not self.p1_won


@dataclass(frozen=True)
class Bet:
    """A strategy's edge view: which side, and the probability backing that choice.
    Staking (see staking.py) turns (probability, price, bankroll) into a stake —
    a strategy with no independent probability view returns the market's own
    consensus probability, which sizes a flat/fractional stake normally but makes
    Kelly correctly bet near zero (no edge, no size)."""

    side: Side
    probability: float


@dataclass(frozen=True)
class SettledBet:
    match_id: str
    match_date: date
    side: Side
    probability: float
    price: float
    fill_price: float
    consensus_price: float
    consensus_prob: float
    stake: float
    profit: float
    won: bool
    bankroll_after: float
    surface: str | None = None


@dataclass(frozen=True)
class EquityPoint:
    match_date: date
    bankroll: float
