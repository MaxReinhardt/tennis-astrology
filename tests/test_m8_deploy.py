"""M8: the Vercel CLI ignores .gitignore and uploads whatever .vercelignore admits, so
this guards the allowlist that keeps data/ (multi-GB) and .env (secrets) out of uploads."""

import json

import pytest

from tennisdb import config

pytestmark = pytest.mark.m8


def _rules() -> list[str]:
    path = config.PROJECT_ROOT / ".vercelignore"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _admitted() -> set[str]:
    return {rule[1:].strip("/") for rule in _rules() if rule.startswith("!")}


def test_vercelignore_is_an_allowlist_that_starts_by_ignoring_everything():
    assert _rules()[0] == "/*"


@pytest.mark.parametrize("forbidden", ["data", ".env", ".venv", "tests", "notebooks"])
def test_vercelignore_never_admits_local_data_or_secrets(forbidden):
    assert forbidden not in _admitted()


def test_vercelignore_admits_every_service_root_and_the_config():
    services = json.loads((config.PROJECT_ROOT / "vercel.json").read_text())["services"]
    roots = {service["root"].strip("/") for service in services.values()}

    assert roots | {"vercel.json"} <= _admitted()


def test_vercelignore_excludes_virtualenvs_nested_inside_a_service_root():
    assert "**/.venv" in _rules()
