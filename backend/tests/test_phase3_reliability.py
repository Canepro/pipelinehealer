"""Phase 3 reliability tests: retries/backoff, timeouts, and log handling."""

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime

import httpx
import pytest

from src.agents.log_analyzer import LogAnalyzerAgent
from src.agents.orchestrator import OrchestratorAgent
from src.config import get_settings, reset_settings
from src.models import (
    GitHubRepository,
    GitHubWorkflowRun,
    RemediationStatus,
    WorkflowRunEvent,
)
from src.storage import InMemoryStorage
from src.tools.github_tools import GitHubTools


class FakeAsyncClient:
    """Minimal async client compatible with GitHubTools._request tests."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise RuntimeError("No fake response available")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class DummyGitHubTools:
    """Placeholder GitHub tools for unit tests that patch behavior directly."""

    pass


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    reset_settings()
    yield
    reset_settings()


def _event() -> WorkflowRunEvent:
    repo = GitHubRepository(
        id=1,
        name="demo",
        full_name="octo/demo",
        owner={"login": "octo"},
        default_branch="main",
        html_url="https://github.com/octo/demo",
    )
    run = GitHubWorkflowRun(
        id=99,
        name="CI",
        workflow_id=1,
        head_branch="main",
        head_sha="deadbeef",
        status="completed",
        conclusion="failure",
        html_url="https://github.com/octo/demo/actions/runs/99",
        created_at=datetime(2026, 2, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 2, 10, 0, 1, tzinfo=UTC),
        run_attempt=1,
        run_number=1,
    )
    return WorkflowRunEvent(action="completed", workflow_run=run, repository=repo, sender={})


def _response(
    status_code: int,
    *,
    json_body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/test")
    return httpx.Response(status_code, request=request, json=json_body or {}, headers=headers)


@pytest.mark.asyncio
async def test_github_request_retries_on_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = GitHubTools(token="x")
    fake_client = FakeAsyncClient(
        responses=[
            _response(503),
            _response(200, json_body={"ok": True}),
        ]
    )
    gh._client = fake_client  # type: ignore[assignment]

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.tools.github_tools.asyncio.sleep", _no_sleep)

    response = await gh._request("GET", "/repos/octo/demo/actions/runs/1")
    assert response.status_code == 200
    assert len(fake_client.calls) == 2


@pytest.mark.asyncio
async def test_github_request_does_not_retry_non_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = GitHubTools(token="x")
    fake_client = FakeAsyncClient(responses=[_response(404)])
    gh._client = fake_client  # type: ignore[assignment]

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.tools.github_tools.asyncio.sleep", _no_sleep)

    with pytest.raises(httpx.HTTPStatusError):
        await gh._request("GET", "/repos/octo/demo/contents/missing.txt")

    assert len(fake_client.calls) == 1


@pytest.mark.asyncio
async def test_github_request_retries_on_transient_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = GitHubTools(token="x")
    request = httpx.Request("GET", "https://api.github.com/test")
    fake_client = FakeAsyncClient(
        responses=[
            httpx.ConnectError("temporary network issue", request=request),
            _response(200, json_body={"ok": True}),
        ]
    )
    gh._client = fake_client  # type: ignore[assignment]

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.tools.github_tools.asyncio.sleep", _no_sleep)

    response = await gh._request("GET", "/repos/octo/demo/actions/runs/1")
    assert response.status_code == 200
    assert len(fake_client.calls) == 2


@pytest.mark.asyncio
async def test_get_failed_jobs_logs_includes_timed_out_jobs() -> None:
    gh = GitHubTools(token="x")

    async def fake_jobs(
        owner: str,
        repo: str,
        run_id: int,
        filter: str = "all",
    ) -> list[dict[str, object]]:
        _ = owner, repo, run_id, filter
        return [
            {"id": 1, "name": "failure-job", "conclusion": "failure"},
            {"id": 2, "name": "timedout-job", "conclusion": "timed_out"},
            {"id": 3, "name": "success-job", "conclusion": "success"},
        ]

    async def fake_job_logs(owner: str, repo: str, job_id: int) -> str:
        _ = owner, repo
        return f"log-{job_id}"

    gh.get_workflow_jobs = fake_jobs  # type: ignore[method-assign]
    gh.get_job_logs = fake_job_logs  # type: ignore[method-assign]

    logs = await gh.get_failed_jobs_logs("octo", "demo", 123)
    assert logs == {
        "failure-job": "log-1",
        "timedout-job": "log-2",
    }


@pytest.mark.asyncio
async def test_orchestrator_marks_step_timeout_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_STEP_TIMEOUT_SECONDS", "0.01")
    reset_settings()

    storage = InMemoryStorage()
    orchestrator = OrchestratorAgent(github_tools=DummyGitHubTools(), storage=storage)  # type: ignore[arg-type]

    async def slow_analyze(owner: str, repo: str, run_id: int) -> list[object]:
        _ = owner, repo, run_id
        await asyncio.sleep(0.05)
        return []

    orchestrator._log_analyzer.analyze = slow_analyze  # type: ignore[method-assign]

    result = await orchestrator.process_workflow_failure(_event())
    assert result.status == RemediationStatus.FAILED
    assert result.error is not None
    assert "Analyze step timed out" in result.error


def test_prompt_truncation_preserves_tail_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_PROMPT_MAX_CHARS", "20")
    monkeypatch.setenv("LOG_PROMPT_HEAD_CHARS", "8")
    monkeypatch.setenv("LOG_PROMPT_TAIL_CHARS", "8")
    reset_settings()

    agent = LogAnalyzerAgent(github_tools=DummyGitHubTools())  # type: ignore[arg-type]
    raw = "0123456789ABCDEFGHIJ0123456789"

    truncated = agent._truncate_for_prompt(raw)
    assert truncated.startswith("01234567")
    assert truncated.endswith("23456789")
    assert "[truncated" in truncated
