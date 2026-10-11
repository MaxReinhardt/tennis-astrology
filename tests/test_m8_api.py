"""M8: the HTTP adapter and the question translator, with a fake match source and a stub
Claude client — no database, no network, no API key."""

import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tennisdb.api.app import create_app
from tennisdb.api.translation import (
    ClaudeQuestionTranslator,
    Coverage,
    Translation,
    TranslationFailedError,
    TranslationRefusedError,
)
from tennisdb.backtest.domain import MatchEvent, MatchOpportunity
from tennisdb.backtest.request import BacktestRequest
from tennisdb.strategy_requests.domain import Issue, StrategyProposal
from tennisdb.strategy_requests.file_request import FileStrategyRequest

pytestmark = pytest.mark.m8


def _event(index: int) -> MatchEvent:
    opportunity = MatchOpportunity(
        match_id=f"m{index}", match_date=date(2019, 1, 1 + index), season=2019, tour="atp",
        surface="Hard", level="A", round="R32", p1_price=1.8, p2_price=2.1,
        p1_consensus_price=1.8, p2_consensus_price=2.1, p1_consensus_prob=0.54,
        p1_elo_prob=0.5, p1_surface_elo_prob=0.5,
    )  # fmt: skip
    return MatchEvent(opportunity, p1_won=index % 2 == 0)


class _FakeSource:
    def __init__(self, count):
        self._count = count

    def events(self, request):
        return iter([_event(index) for index in range(self._count)])


def _factory(count=10):
    @contextmanager
    def open_source():
        yield _FakeSource(count)

    return open_source


class _StubTranslator:
    def translate(self, question):
        request = BacktestRequest.from_dict({"strategy": "back_underdogs"})
        return Translation("Back underdogs.", request)


@pytest.fixture
def studies_directory(tmp_path):
    (tmp_path / "s9_demo.json").write_text(json.dumps({"study_id": "s9_demo"}))
    (tmp_path / "index.json").write_text(json.dumps([{"study_id": "s9_demo"}]))
    return tmp_path


class _FakeTracker:
    def __init__(self, open_issues=()):
        self.open_issues = list(open_issues)
        self.opened = []

    def find_open(self, title):
        return tuple(issue for issue in self.open_issues if issue.title == title)

    def open_issue(self, title, body, labels):
        self.opened.append(title)
        return Issue(f"https://github.com/o/r/issues/{len(self.opened)}", len(self.opened), title)


def _client(studies_directory, translator=None, count=10, tracker=None):
    file_strategy_request = None if tracker is None else FileStrategyRequest(tracker)
    return TestClient(
        create_app(_factory(count), translator, studies_directory, "fake", file_strategy_request)
    )


def test_catalog_lists_the_registered_strategies(studies_directory):
    body = _client(studies_directory).get("/api/catalog").json()

    assert {"back_home_nation", "elo_value"} <= {s["name"] for s in body["strategies"]}


def test_backtest_valid_request_returns_metrics_and_charts_without_the_bet_series(
    studies_directory,
):
    response = _client(studies_directory).post("/api/backtest", json={"strategy": "back_underdogs"})

    body = response.json()
    assert response.status_code == 200
    assert body["universe"]["matches_seen"] == 10
    assert len(body["charts"]) == 7 and "equity_curve" not in body


def test_backtest_unknown_strategy_is_rejected_with_the_validation_message(studies_directory):
    response = _client(studies_directory).post("/api/backtest", json={"strategy": "moon_phase"})

    assert response.status_code == 422 and "moon_phase" in response.json()["detail"]


def test_backtest_with_no_matching_matches_is_a_422(studies_directory):
    response = _client(studies_directory, count=0).post(
        "/api/backtest", json={"strategy": "back_underdogs"}
    )

    assert response.status_code == 422


def test_studies_index_and_detail_are_served_from_the_results_directory(studies_directory):
    client = _client(studies_directory)

    assert client.get("/api/studies").json() == [{"study_id": "s9_demo"}]
    assert client.get("/api/studies/s9_demo").json() == {"study_id": "s9_demo"}


@pytest.mark.parametrize("study_id", ["nope", "..", "s9_demo/../../x"])
def test_unknown_or_unsafe_study_id_is_a_404(studies_directory, study_id):
    assert _client(studies_directory).get(f"/api/studies/{study_id}").status_code in {404, 422}


def test_translate_without_a_translator_is_503_and_health_says_so(studies_directory):
    client = _client(studies_directory)

    assert client.post("/api/translate", json={"question": "hi"}).status_code == 503
    assert client.get("/api/health").json()["translation_enabled"] is False


def test_translate_returns_interpretation_and_a_valid_request(studies_directory):
    response = _client(studies_directory, _StubTranslator()).post(
        "/api/translate", json={"question": "do underdogs pay?"}
    )

    assert response.json()["request"]["strategy"] == "back_underdogs"
    assert response.json()["interpretation"] == "Back underdogs."


def test_translate_blank_question_is_a_422(studies_directory):
    response = _client(studies_directory, _StubTranslator()).post(
        "/api/translate", json={"question": "  "}
    )

    assert response.status_code == 422


class _StubClaude:
    """Returns scripted replies in order; records what it was sent."""

    def __init__(self, *replies, stop_reason="end_turn"):
        self._replies = list(replies)
        self._stop_reason = stop_reason
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._replies.pop(0)
        return SimpleNamespace(
            stop_reason=self._stop_reason, content=[SimpleNamespace(type="text", text=text)]
        )


def _reply(request: dict, interpretation="ok", coverage="exact", proposals=()) -> str:
    return json.dumps(
        {
            "interpretation": interpretation,
            "coverage": coverage,
            "strategy_proposals": list(proposals),
            "request_json": json.dumps(request),
        }
    )


_PROPOSAL = {
    "title": "Fade five-set winners",
    "rule": "Bet against a player whose previous match went five sets.",
    "data_needed": "Sets played in each player's previous match.",
}


def test_translator_valid_reply_becomes_a_validated_request():
    client = _StubClaude(_reply({"strategy": "elo_value", "strategy_parameters": {"theta": 0.1}}))

    translation = ClaudeQuestionTranslator(client).translate("value bets?")

    assert translation.request.strategy == "elo_value"
    assert translation.request.strategy_parameters["theta"] == 0.1


def test_translator_invalid_first_reply_is_retried_with_the_error_fed_back():
    client = _StubClaude(_reply({"strategy": "moon_phase"}), _reply({"strategy": "random_bet"}))

    translation = ClaudeQuestionTranslator(client).translate("?")

    assert translation.request.strategy == "random_bet"
    assert "moon_phase" in client.calls[1]["messages"][-1]["content"]


def test_translator_two_invalid_replies_raise_translation_failed():
    client = _StubClaude(_reply({"strategy": "x"}), _reply({"strategy": "y"}))

    with pytest.raises(TranslationFailedError):
        ClaudeQuestionTranslator(client).translate("?")


def test_translator_refusal_raises_before_reading_content():
    client = _StubClaude("ignored", stop_reason="refusal")

    with pytest.raises(TranslationRefusedError):
        ClaudeQuestionTranslator(client).translate("?")


def test_translator_system_prompt_is_cached_and_carries_the_catalog():
    client = _StubClaude(_reply({"strategy": "random_bet"}))

    ClaudeQuestionTranslator(client).translate("?")

    system = client.calls[0]["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "back_home_nation" in system["text"]


def test_service_requirements_are_a_subset_of_the_projects_pinned_dependencies():
    import re
    import tomllib

    from tennisdb import config

    project = tomllib.loads((config.PROJECT_ROOT / "pyproject.toml").read_text())
    declared = {re.split(r"[\[<>=]", dep)[0] for dep in project["project"]["dependencies"]}
    service = (config.PROJECT_ROOT / "src" / "requirements.txt").read_text().split()

    assert {re.split(r"[\[<>=]", dep)[0] for dep in service} <= declared


def test_translator_exact_reply_has_exact_coverage_and_no_proposals():
    client = _StubClaude(_reply({"strategy": "random_bet"}))

    translation = ClaudeQuestionTranslator(client).translate("?")

    assert translation.coverage is Coverage.EXACT and translation.proposals == ()


def test_translator_unsupported_reply_carries_the_strategy_proposal():
    reply = _reply({"strategy": "random_bet"}, coverage="unsupported", proposals=[_PROPOSAL])
    client = _StubClaude(reply)

    translation = ClaudeQuestionTranslator(client).translate("five-setters?")

    assert translation.coverage is Coverage.UNSUPPORTED
    assert translation.proposals == (StrategyProposal(**_PROPOSAL),)


def test_translator_unknown_coverage_is_retried_with_the_error_fed_back():
    client = _StubClaude(
        _reply({"strategy": "random_bet"}, coverage="maybe"), _reply({"strategy": "random_bet"})
    )

    translation = ClaudeQuestionTranslator(client).translate("?")

    assert translation.coverage is Coverage.EXACT
    assert "maybe" in client.calls[1]["messages"][-1]["content"]


def test_translator_instructions_tell_the_model_about_coverage_and_proposals():
    client = _StubClaude(_reply({"strategy": "random_bet"}))

    ClaudeQuestionTranslator(client).translate("?")

    system_text = client.calls[0]["system"][0]["text"]
    assert "unsupported" in system_text and "strategy_proposals" in system_text


class _ProposingTranslator:
    def translate(self, question):
        request = BacktestRequest.from_dict({"strategy": "back_underdogs"})
        return Translation(
            "Closest run: underdogs.", request, Coverage.UNSUPPORTED,
            (StrategyProposal(**_PROPOSAL),),
        )  # fmt: skip


def test_translate_response_includes_coverage_and_proposals(studies_directory):
    response = _client(studies_directory, _ProposingTranslator()).post(
        "/api/translate", json={"question": "five-setters?"}
    )

    body = response.json()
    assert body["coverage"] == "unsupported" and body["proposals"] == [_PROPOSAL]


def test_translate_response_for_a_covered_question_is_exact_with_no_proposals(studies_directory):
    response = _client(studies_directory, _StubTranslator()).post(
        "/api/translate", json={"question": "do underdogs pay?"}
    )

    assert response.json()["coverage"] == "exact" and response.json()["proposals"] == []


def test_health_reports_whether_strategy_requests_are_enabled(studies_directory):
    without = _client(studies_directory).get("/api/health").json()
    with_tracker = _client(studies_directory, tracker=_FakeTracker()).get("/api/health").json()

    assert without["strategy_requests_enabled"] is False
    assert with_tracker["strategy_requests_enabled"] is True


def _filing_payload(**overrides):
    return {"question": "five-setters?", "proposal": _PROPOSAL | overrides}


def test_strategy_request_without_a_tracker_is_503(studies_directory):
    response = _client(studies_directory).post("/api/strategy-requests", json=_filing_payload())

    assert response.status_code == 503


def test_strategy_request_opens_an_issue_and_returns_its_link(studies_directory):
    tracker = _FakeTracker()

    response = _client(studies_directory, tracker=tracker).post(
        "/api/strategy-requests", json=_filing_payload()
    )

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://github.com/o/r/issues/1", "number": 1, "already_existed": False,
    }  # fmt: skip


def test_strategy_request_for_an_existing_title_returns_that_issue(studies_directory):
    existing = Issue(
        "https://github.com/o/r/issues/5", 5, "Strategy request: Fade five-set winners"
    )
    tracker = _FakeTracker([existing])

    response = _client(studies_directory, tracker=tracker).post(
        "/api/strategy-requests", json=_filing_payload()
    )

    assert response.json()["already_existed"] is True and tracker.opened == []


def test_strategy_request_with_an_overlong_title_is_a_422(studies_directory):
    response = _client(studies_directory, tracker=_FakeTracker()).post(
        "/api/strategy-requests", json=_filing_payload(title="t" * 500)
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload", [{}, {"question": "q"}, {"question": "q", "proposal": {"title": "t"}}]
)
def test_strategy_request_with_a_malformed_payload_is_a_422(studies_directory, payload):
    response = _client(studies_directory, tracker=_FakeTracker()).post(
        "/api/strategy-requests", json=payload
    )

    assert response.status_code == 422
