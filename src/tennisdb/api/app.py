"""HTTP adapter: validates and routes requests, then delegates. The engine, the
translator and the match source are injected, so the app is testable without a database
or an API key."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, HTTPException

from tennisdb import config
from tennisdb.api import sources
from tennisdb.api.translation import (
    QuestionTranslator,
    TranslationFailedError,
    TranslationRefusedError,
)
from tennisdb.backtest.catalog import catalog
from tennisdb.backtest.engine import OpportunitySource, run_backtest
from tennisdb.backtest.request import BacktestRequest, InvalidBacktestRequest
from tennisdb.strategy_requests.domain import StrategyProposal
from tennisdb.strategy_requests.file_request import FileStrategyRequest, InvalidStrategyRequest

SourceFactory = Callable[[], AbstractContextManager[OpportunitySource]]


def create_app(
    source_factory: SourceFactory,
    translator: QuestionTranslator | None,
    study_results_directory: Path,
    source_label: str,
    file_strategy_request: FileStrategyRequest | None,
) -> FastAPI:
    app = FastAPI(title="Tennis research API")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "source": source_label,
            "translation_enabled": translator is not None,
            "strategy_requests_enabled": file_strategy_request is not None,
        }

    @app.get("/api/catalog")
    def get_catalog() -> dict:
        return catalog()

    @app.post("/api/backtest")
    def backtest(payload: dict = Body(...)) -> dict:
        request = _parse_request(payload)
        with source_factory() as source:
            result = run_backtest(request, source)
        if result.matches_seen == 0:
            raise HTTPException(422, "no matches in the warehouse match these filters")
        summary = result.to_dict()
        del summary["equity_curve"]
        return summary

    @app.post("/api/translate")
    def translate(payload: dict = Body(...)) -> dict:
        if translator is None:
            raise HTTPException(503, "translation is disabled: ANTHROPIC_API_KEY is not set")
        question = str(payload.get("question", "")).strip()
        if not question:
            raise HTTPException(422, "question must not be empty")
        try:
            translation = translator.translate(question)
        except TranslationRefusedError as error:
            raise HTTPException(422, str(error)) from error
        except TranslationFailedError as error:
            raise HTTPException(422, f"could not build a valid request: {error}") from error
        return {
            "interpretation": translation.interpretation,
            "request": translation.request.to_dict(),
            "coverage": translation.coverage.value,
            "proposals": [proposal.to_dict() for proposal in translation.proposals],
        }

    @app.post("/api/strategy-requests")
    def request_strategy(payload: dict = Body(...)) -> dict:
        if file_strategy_request is None:
            raise HTTPException(503, "strategy requests are disabled: GITHUB_TOKEN is not set")
        question, proposal = _parse_strategy_request(payload)
        try:
            outcome = file_strategy_request.file(question, proposal)
        except InvalidStrategyRequest as error:
            raise HTTPException(422, str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(502, "could not reach GitHub to file the request") from error
        return outcome.to_dict()

    @app.get("/api/studies")
    def list_studies() -> list:
        return _read_json(study_results_directory / "index.json", default=[])

    @app.get("/api/studies/{study_id}")
    def get_study(study_id: str) -> dict:
        path = study_results_directory / f"{study_id}.json"
        if not study_id.isidentifier() or not path.exists():
            raise HTTPException(404, f"unknown study {study_id!r}")
        return _read_json(path)

    return app


def _parse_request(payload: dict) -> BacktestRequest:
    try:
        return BacktestRequest.from_dict(payload)
    except InvalidBacktestRequest as error:
        raise HTTPException(422, str(error)) from error


def _parse_strategy_request(payload: dict) -> tuple[str, StrategyProposal]:
    try:
        proposal = payload["proposal"]
        return str(payload["question"]), StrategyProposal(
            str(proposal["title"]), str(proposal["rule"]), str(proposal["data_needed"])
        )
    except (KeyError, TypeError) as error:
        raise HTTPException(
            422, "question and proposal (title, rule, data_needed) are required"
        ) from error


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _default_translator() -> QuestionTranslator | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    from anthropic import Anthropic

    from tennisdb.api.translation import ClaudeQuestionTranslator

    return ClaudeQuestionTranslator(Anthropic())


def _default_file_strategy_request() -> FileStrategyRequest | None:
    if not config.GITHUB_TOKEN:
        return None
    from tennisdb.strategy_requests.github import GitHubIssueTracker

    tracker = GitHubIssueTracker(
        config.GITHUB_TOKEN, config.GITHUB_REPOSITORY, httpx.Client(timeout=10.0)
    )
    return FileStrategyRequest(tracker)


app = create_app(
    sources.open_source,
    _default_translator(),
    config.API_STUDY_RESULTS_DIR,
    sources.source_name(),
    _default_file_strategy_request(),
)
