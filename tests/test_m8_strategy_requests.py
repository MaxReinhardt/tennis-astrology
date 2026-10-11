"""M8: filing a missing strategy as a GitHub issue — the use case against a fake tracker,
and the GitHub adapter against a stubbed HTTP transport. No network, no token."""

import json

import httpx
import pytest

from tennisdb.strategy_requests.domain import Issue, StrategyProposal
from tennisdb.strategy_requests.file_request import (
    FileStrategyRequest,
    InvalidStrategyRequest,
)
from tennisdb.strategy_requests.github import GitHubIssueTracker

pytestmark = pytest.mark.m8


class _FakeTracker:
    def __init__(self, open_issues=()):
        self.open_issues = list(open_issues)
        self.opened = []

    def find_open(self, title):
        return tuple(issue for issue in self.open_issues if issue.title == title)

    def open_issue(self, title, body, labels):
        self.opened.append((title, body, labels))
        return Issue(f"https://github.com/o/r/issues/{len(self.opened)}", len(self.opened), title)


def _proposal(**overrides):
    fields = {
        "title": "Back players after a five-set loss",
        "rule": "Fade a player whose previous match went five sets.",
        "data_needed": "Sets played in each player's previous match.",
    }
    return StrategyProposal(**(fields | overrides))


QUESTION = "Do players who won a five-setter yesterday lose today?"


def test_filing_a_new_proposal_opens_a_labelled_issue_and_reports_it_as_new():
    tracker = _FakeTracker()

    outcome = FileStrategyRequest(tracker).file(QUESTION, _proposal())

    title, body, labels = tracker.opened[0]
    assert title == "Strategy request: Back players after a five-set loss"
    assert labels == ("strategy-request",)
    assert QUESTION in body and "Fade a player" in body and "Sets played" in body
    assert "STRATEGIES" in body
    assert not outcome.already_existed and outcome.number == 1


def test_filing_an_already_requested_proposal_returns_the_existing_issue():
    existing = Issue(
        "https://github.com/o/r/issues/7", 7, "Strategy request: Back players after a five-set loss"
    )
    tracker = _FakeTracker([existing])

    outcome = FileStrategyRequest(tracker).file(QUESTION, _proposal())

    assert tracker.opened == []
    assert outcome.already_existed and outcome.url == existing.url


def test_filing_neutralises_mentions_so_a_public_visitor_cannot_ping_people():
    tracker = _FakeTracker()

    FileStrategyRequest(tracker).file("hey @octocat look", _proposal(rule="ask @someone"))

    body = tracker.opened[0][1]
    assert "@octocat" not in body and "@someone" not in body


@pytest.mark.parametrize(
    "question, overrides",
    [
        ("  ", {}),
        ("q" * 501, {}),
        (QUESTION, {"title": ""}),
        (QUESTION, {"title": "t" * 121}),
        (QUESTION, {"rule": " "}),
        (QUESTION, {"rule": "r" * 2001}),
        (QUESTION, {"data_needed": "d" * 1001}),
    ],
)
def test_filing_rejects_blank_or_oversized_fields_without_opening_an_issue(question, overrides):
    tracker = _FakeTracker()

    with pytest.raises(InvalidStrategyRequest):
        FileStrategyRequest(tracker).file(question, _proposal(**overrides))

    assert tracker.opened == []


def _tracker(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GitHubIssueTracker("secret-token", "owner/repo", client)


def test_github_open_issue_posts_title_body_and_labels_with_the_token():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/owner/repo/issues/3", "number": 3, "title": "T"},
        )

    issue = _tracker(handler).open_issue("T", "body", ("strategy-request",))

    request = seen["request"]
    assert request.method == "POST" and request.url.path == "/repos/owner/repo/issues"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert json.loads(request.content) == {
        "title": "T",
        "body": "body",
        "labels": ["strategy-request"],
    }
    assert issue == Issue("https://github.com/owner/repo/issues/3", 3, "T")


def test_github_find_open_searches_open_labelled_issues_in_the_repository():
    seen = {}

    def handler(request):
        seen["query"] = request.url.params["q"]
        items = [{"html_url": "https://github.com/owner/repo/issues/9", "number": 9, "title": "T"}]
        return httpx.Response(200, json={"items": items})

    issues = _tracker(handler).find_open("T")

    assert "repo:owner/repo" in seen["query"] and "is:open" in seen["query"]
    assert "label:strategy-request" in seen["query"]
    assert issues == (Issue("https://github.com/owner/repo/issues/9", 9, "T"),)


def test_github_error_response_raises_instead_of_returning_a_fake_issue():
    tracker = _tracker(lambda request: httpx.Response(403, json={"message": "nope"}))

    with pytest.raises(httpx.HTTPStatusError):
        tracker.open_issue("T", "b", ("strategy-request",))


def test_filing_ignores_a_fuzzy_search_hit_whose_title_differs():
    class FuzzyTracker(_FakeTracker):
        def find_open(self, title):
            return tuple(self.open_issues)

    other = Issue("https://github.com/o/r/issues/2", 2, "Strategy request: something else")
    tracker = FuzzyTracker([other])

    outcome = FileStrategyRequest(tracker).file(QUESTION, _proposal())

    assert len(tracker.opened) == 1 and not outcome.already_existed


def test_github_find_open_strips_quotes_from_the_search_phrase():
    seen = {}

    def handler(request):
        seen["query"] = request.url.params["q"]
        return httpx.Response(200, json={"items": []})

    _tracker(handler).find_open('Back "hot" players')

    assert 'in:title "Back hot players"' in seen["query"].replace("  ", " ")
