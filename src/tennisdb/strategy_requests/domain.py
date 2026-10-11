"""Entities and the gateway interface for asking the maintainers to build a strategy the
backtest engine does not have yet. Framework-free: the GitHub adapter implements
IssueTracker, so the use case never knows which tracker it talks to."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StrategyProposal:
    title: str
    rule: str
    data_needed: str

    def to_dict(self) -> dict:
        return {"title": self.title, "rule": self.rule, "data_needed": self.data_needed}


@dataclass(frozen=True)
class Issue:
    url: str
    number: int
    title: str


@dataclass(frozen=True)
class FilingOutcome:
    url: str
    number: int
    already_existed: bool

    def to_dict(self) -> dict:
        return {"url": self.url, "number": self.number, "already_existed": self.already_existed}


class IssueTracker(Protocol):
    def find_open(self, title: str) -> tuple[Issue, ...]: ...

    def open_issue(self, title: str, body: str, labels: tuple[str, ...]) -> Issue: ...
