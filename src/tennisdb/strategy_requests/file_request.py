"""Use case: turn an unsupported question into one GitHub issue, once."""

from tennisdb.strategy_requests.domain import FilingOutcome, IssueTracker, StrategyProposal

LABEL = "strategy-request"
TITLE_PREFIX = "Strategy request: "
MAX_TITLE_LENGTH = 120
MAX_QUESTION_LENGTH = 500
MAX_RULE_LENGTH = 2000
MAX_DATA_NEEDED_LENGTH = 1000

_BODY_TEMPLATE = """\
## Question asked

> {question}

## Proposed rule

{rule}

## Data needed

{data_needed}

## Checklist

- [ ] Strategy class in `src/tennisdb/backtest/strategies/`
- [ ] One entry in `STRATEGIES` (with plain-language labels and descriptions)
- [ ] Tests in `tests/test_m7_strategies.py`

_Filed from the research UI. The text above was written by a visitor and a language model._
"""


class InvalidStrategyRequest(ValueError):
    pass


class FileStrategyRequest:
    def __init__(self, tracker: IssueTracker):
        self._tracker = tracker

    def file(self, question: str, proposal: StrategyProposal) -> FilingOutcome:
        _validate(question, proposal)
        title = TITLE_PREFIX + proposal.title.strip()
        existing = [issue for issue in self._tracker.find_open(title) if issue.title == title]
        if existing:
            return FilingOutcome(existing[0].url, existing[0].number, already_existed=True)
        issue = self._tracker.open_issue(title, _body(question, proposal), (LABEL,))
        return FilingOutcome(issue.url, issue.number, already_existed=False)


def _validate(question: str, proposal: StrategyProposal) -> None:
    limits = (
        ("question", question, MAX_QUESTION_LENGTH),
        ("title", proposal.title, MAX_TITLE_LENGTH),
        ("rule", proposal.rule, MAX_RULE_LENGTH),
        ("data_needed", proposal.data_needed, MAX_DATA_NEEDED_LENGTH),
    )
    for name, text, maximum in limits:
        if len(text) > maximum:
            raise InvalidStrategyRequest(f"{name} must be at most {maximum} characters")
    for name, text in (("question", question), ("title", proposal.title), ("rule", proposal.rule)):
        if not text.strip():
            raise InvalidStrategyRequest(f"{name} must not be empty")


def _defuse_mentions(text: str) -> str:
    return text.replace("@", "@​")


def _body(question: str, proposal: StrategyProposal) -> str:
    return _BODY_TEMPLATE.format(
        question=_defuse_mentions(question.strip()).replace("\n", "\n> "),
        rule=_defuse_mentions(proposal.rule.strip()),
        data_needed=_defuse_mentions(proposal.data_needed.strip()) or "Not specified.",
    )
