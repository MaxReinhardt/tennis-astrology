"""Adapter: IssueTracker over the GitHub REST API."""

import httpx

from tennisdb.strategy_requests.domain import Issue
from tennisdb.strategy_requests.file_request import LABEL

API_ROOT = "https://api.github.com"


class GitHubIssueTracker:
    def __init__(self, token: str, repository: str, client: httpx.Client):
        self._repository = repository
        self._client = client
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def find_open(self, title: str) -> tuple[Issue, ...]:
        phrase = " ".join(title.replace('"', " ").split())
        query = f'repo:{self._repository} is:issue is:open label:{LABEL} in:title "{phrase}"'
        response = self._client.get(
            f"{API_ROOT}/search/issues", params={"q": query}, headers=self._headers
        )
        response.raise_for_status()
        return tuple(_issue(item) for item in response.json()["items"])

    def open_issue(self, title: str, body: str, labels: tuple[str, ...]) -> Issue:
        response = self._client.post(
            f"{API_ROOT}/repos/{self._repository}/issues",
            json={"title": title, "body": body, "labels": list(labels)},
            headers=self._headers,
        )
        response.raise_for_status()
        return _issue(response.json())


def _issue(payload: dict) -> Issue:
    return Issue(payload["html_url"], payload["number"], payload["title"])
