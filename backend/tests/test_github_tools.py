"""Tests for GitHubTools helper methods used by diagnosis correlation."""

from typing import Any

import pytest

from src.tools.github_tools import GitHubTools


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


@pytest.mark.asyncio
async def test_search_issues_builds_repo_scoped_query() -> None:
    gh = GitHubTools(token="test-token")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse({"items": [{"number": 1, "title": "CI Doctor report"}]})

    gh._request = fake_request  # type: ignore[method-assign]

    issues = await gh.search_issues(
        owner="Canepro",
        repo="pipelinehealer",
        query="in:title,body timeout",
        state="all",
        per_page=5,
    )

    assert len(issues) == 1
    assert captured["method"] == "GET"
    assert captured["url"] == "/search/issues"
    q = captured["kwargs"]["params"]["q"]
    assert "repo:Canepro/pipelinehealer" in q
    assert "is:issue" in q
    assert "state:all" in q
    assert "in:title,body timeout" in q


@pytest.mark.asyncio
async def test_get_pull_request_files_uses_pulls_files_endpoint() -> None:
    gh = GitHubTools(token="test-token")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse([{"filename": "src/app.py"}])

    gh._request = fake_request  # type: ignore[method-assign]

    files = await gh.get_pull_request_files(
        owner="Canepro",
        repo="pipelinehealer",
        pr_number=42,
    )

    assert files == [{"filename": "src/app.py"}]
    assert captured["method"] == "GET"
    assert captured["url"] == "/repos/Canepro/pipelinehealer/pulls/42/files"
    assert captured["kwargs"]["params"]["per_page"] == 100


@pytest.mark.asyncio
async def test_get_recent_commits_passes_since_parameter() -> None:
    gh = GitHubTools(token="test-token")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse([{"sha": "abc123"}])

    gh._request = fake_request  # type: ignore[method-assign]

    commits = await gh.get_recent_commits(
        owner="Canepro",
        repo="pipelinehealer",
        since="2026-02-01T00:00:00Z",
        per_page=7,
    )

    assert commits == [{"sha": "abc123"}]
    assert captured["method"] == "GET"
    assert captured["url"] == "/repos/Canepro/pipelinehealer/commits"
    assert captured["kwargs"]["params"]["since"] == "2026-02-01T00:00:00Z"
    assert captured["kwargs"]["params"]["per_page"] == 7
