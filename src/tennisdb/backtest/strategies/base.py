"""Strategy contract: a Strategy sees only a MatchOpportunity and returns a Bet or
None. ParameterSpec is the single source of truth for a strategy's tunable knobs —
request validation (request.py) and the natural-language catalog (catalog.py) both
read it, so neither can drift from what the strategy can actually accept.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from tennisdb.backtest.domain import Bet, MatchOpportunity


class Strategy(Protocol):
    name: str

    def evaluate(self, opportunity: MatchOpportunity) -> Bet | None: ...


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    kind: str  # 'number' | 'integer'
    default: float
    minimum: float | None
    maximum: float | None
    description: str


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    label: str
    description: str
    factory: Callable[[Mapping[str, float]], Strategy]
    parameters: tuple[ParameterSpec, ...]
