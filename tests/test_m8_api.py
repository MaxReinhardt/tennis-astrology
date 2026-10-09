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
    Translation,
    TranslationFailedError,
    TranslationRefusedError,
)
from tennisdb.backtest.domain import MatchEvent, MatchOpportunity
from tennisdb.backtest.request import BacktestRequest

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


def _client(studies_directory, translator=None, count=10):
    return TestClient(create_app(_factory(count), translator, studies_directory, "fake"))


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


def _reply(request: dict, interpretation="ok") -> str:
    return json.dumps({"interpretation": interpretation, "request_json": json.dumps(request)})


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
