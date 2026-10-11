"""Natural-language question -> validated BacktestRequest, via one cheap Claude call.

The model is never trusted: its output is a JSON string that BacktestRequest.from_dict
must accept, and a rejection is fed back once so the model can correct itself. The
system prompt is the engine's own catalog, so it cannot offer what the engine cannot run."""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from tennisdb.backtest.catalog import catalog
from tennisdb.backtest.request import BacktestRequest, InvalidBacktestRequest
from tennisdb.strategy_requests.domain import StrategyProposal

MODEL = "claude-opus-5"
MAX_ATTEMPTS = 2
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "interpretation": {
            "type": "string",
            "description": "One or two plain sentences: what you will test and any "
            "assumption or approximation you made.",
        },
        "coverage": {
            "type": "string",
            "enum": ["exact", "approximate", "unsupported"],
            "description": "How well the catalog can express the question.",
        },
        "strategy_proposals": {
            "type": "array",
            "maxItems": 1,
            "description": "One proposed new strategy when coverage is unsupported, else empty.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short name, under 80 characters."},
                    "rule": {
                        "type": "string",
                        "description": "The betting rule in plain words: who to bet on and when.",
                    },
                    "data_needed": {
                        "type": "string",
                        "description": "Data the rule needs that may not be in the catalog.",
                    },
                },
                "required": ["title", "rule", "data_needed"],
                "additionalProperties": False,
            },
        },
        "request_json": {
            "type": "string",
            "description": "A JSON object string: a BacktestRequest.",
        },
    },
    "required": ["interpretation", "coverage", "strategy_proposals", "request_json"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """\
You translate a question about tennis betting into one backtest request for an engine.
Reply with `interpretation`, `coverage`, `strategy_proposals` and `request_json`
(a BacktestRequest as a JSON string). Write `interpretation` for readers who know nothing
about betting: no jargon without a few plain words of explanation.

Rules:
- Use only strategies, stake rules and parameters listed in the catalog below.
- Odds exist for ATP from 2001 and WTA from 2007; seasons are calendar years.
- Unless the user asks for a particular staking plan, use stake_rule "flat" with
  stake_parameters {"amount": 10} and starting_bankroll 1000000, so a small bankroll
  cannot go bust and cut the sample short.
- "Home nation" / "host country" questions use back_home_nation or fade_home_nation.
- `coverage` is "exact" when the catalog expresses the question as asked, "approximate"
  when only a filter or parameter had to be adjusted, and "unsupported" when the core
  selection idea (who to bet on, and why) is missing from the strategy list.
- If the question cannot be expressed exactly, still run the closest request and say in
  `interpretation` what you changed. Never invent fields.
- When coverage is "unsupported", put exactly one entry in `strategy_proposals` describing
  the missing strategy; otherwise leave `strategy_proposals` empty.

Catalog:
"""


class TranslationRefusedError(RuntimeError):
    pass


class TranslationFailedError(RuntimeError):
    pass


class Coverage(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Translation:
    interpretation: str
    request: BacktestRequest
    coverage: Coverage = Coverage.EXACT
    proposals: tuple[StrategyProposal, ...] = ()


class QuestionTranslator(Protocol):
    def translate(self, question: str) -> Translation: ...


class ClaudeQuestionTranslator:
    def __init__(self, client):
        self._client = client
        self._system = [
            {
                "type": "text",
                "text": _INSTRUCTIONS + json.dumps(catalog(), indent=1),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def translate(self, question: str) -> Translation:
        messages: list[dict] = [{"role": "user", "content": question}]
        last_error = "no attempt made"
        for _ in range(MAX_ATTEMPTS):
            reply = self._ask(messages)
            try:
                payload = json.loads(reply)
                return Translation(
                    payload["interpretation"],
                    BacktestRequest.from_dict(json.loads(payload["request_json"])),
                    Coverage(payload["coverage"]),
                    tuple(StrategyProposal(**item) for item in payload["strategy_proposals"]),
                )
            except (InvalidBacktestRequest, ValueError, KeyError, TypeError) as error:
                last_error = str(error)
                messages += [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"That request was rejected: {last_error}. "
                     "Reply again with a corrected request."},
                ]  # fmt: skip
        raise TranslationFailedError(last_error)

    def _ask(self, messages: list[dict]) -> str:
        response = self._client.beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=self._system,
            messages=messages,
            output_config={"effort": "low", "format": {"type": "json_schema",
                                                       "schema": _RESPONSE_SCHEMA}},
            betas=[_FALLBACK_BETA],
            extra_body={"fallbacks": "default"},
        )  # fmt: skip
        if response.stop_reason == "refusal":
            raise TranslationRefusedError("the model declined to translate this question")
        return next(block.text for block in response.content if block.type == "text")
