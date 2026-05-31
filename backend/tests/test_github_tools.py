"""Tests for GitHubTools helper methods used by diagnosis correlation."""

from typing import Any

import pytest

from src.config import reset_settings
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
async def test_enable_pull_request_auto_merge_uses_graphql_mutation() -> None:
    gh = GitHubTools(token="test-token")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(
            {
                "data": {
                    "enablePullRequestAutoMerge": {
                        "clientMutationId": "ph-123",
                        "pullRequest": {"number": 42},
                    }
                }
            }
        )

    gh._request = fake_request  # type: ignore[method-assign]

    result = await gh.enable_pull_request_auto_merge(
        pull_request_id="PR_node_42",
        expected_head_oid="abc123",
        merge_method="SQUASH",
        client_mutation_id="ph-123",
    )

    assert result["clientMutationId"] == "ph-123"
    assert captured["method"] == "POST"
    assert captured["url"] == "/graphql"
    body = captured["kwargs"]["json"]
    assert "enablePullRequestAutoMerge" in body["query"]
    assert body["variables"]["input"] == {
        "pullRequestId": "PR_node_42",
        "mergeMethod": "SQUASH",
        "expectedHeadOid": "abc123",
        "clientMutationId": "ph-123",
    }


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


@pytest.mark.asyncio
async def test_update_pull_request_rejects_empty_payload() -> None:
    gh = GitHubTools(token="test-token")

    with pytest.raises(ValueError, match="at least one mutable field"):
        await gh.update_pull_request(
            owner="Canepro",
            repo="pipelinehealer",
            pr_number=42,
        )


@pytest.mark.asyncio
async def test_update_issue_rejects_empty_payload() -> None:
    gh = GitHubTools(token="test-token")

    with pytest.raises(ValueError, match="at least one mutable field"):
        await gh.update_issue(
            owner="Canepro",
            repo="pipelinehealer",
            issue_number=42,
        )


@pytest.mark.asyncio
async def test_refresh_runtime_settings_rebuilds_client_when_pat_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "first-token")
    reset_settings()

    gh = GitHubTools()
    client_one = await gh._get_client()
    assert client_one.headers["Authorization"] == "Bearer first-token"

    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "second-token")
    reset_settings()

    gh.refresh_runtime_settings()
    client_two = await gh._get_client()

    assert client_two is not client_one
    assert client_two.headers["Authorization"] == "Bearer second-token"
    await gh.close()


@pytest.mark.asyncio
async def test_refresh_runtime_settings_preserves_explicit_constructor_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "env-token")
    reset_settings()

    gh = GitHubTools(token="explicit-token")
    client_one = await gh._get_client()
    assert client_one.headers["Authorization"] == "Bearer explicit-token"

    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "new-env-token")
    reset_settings()

    gh.refresh_runtime_settings()
    client_two = await gh._get_client()

    assert client_two is client_one
    assert client_two.headers["Authorization"] == "Bearer explicit-token"
    await gh.close()
