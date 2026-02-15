"""Tests for gh-aw passive diagnostics adapter behavior."""

import pytest

from src.models import ExternalDiagnosticStatus
from src.tools.gh_aw_adapter import PassiveIssueGHAWAdapter


class _FakeGitHubTools:
    def __init__(self) -> None:
        self.workflows = []
        self.issues = []
        self.queries: list[str] = []
        self.issue_comments: dict[int, list[dict[str, object]]] = {}
        self.listed_issues: list[dict[str, object]] = []

    async def list_repo_workflows(self, owner: str, repo: str):
        _ = owner, repo
        return self.workflows

    async def search_issues(
        self,
        owner: str,
        repo: str,
        query: str,
        state: str = "all",
        per_page: int = 10,
    ):
        _ = owner, repo, state, per_page
        self.queries.append(query)
        return self.issues

    async def list_issue_comments(self, owner: str, repo: str, issue_number: int, per_page: int = 30):
        _ = owner, repo, per_page
        return self.issue_comments.get(issue_number, [])

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        labels: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ):
        _ = owner, repo, state, labels, sort, direction, per_page
        return self.listed_issues


@pytest.mark.asyncio
async def test_discover_capability_detects_ci_doctor_lock_workflow() -> None:
    gh = _FakeGitHubTools()
    gh.workflows = [
        {"path": ".github/workflows/ci-doctor.lock.yml"},
        {"path": ".github/workflows/other.lock.yml"},
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    capability = await adapter.discover_capability("Canepro", "pipelinehealer")
    assert capability.is_available is True
    assert "ci-doctor" in capability.available_workflows


@pytest.mark.asyncio
async def test_discover_capability_unavailable_without_ci_doctor() -> None:
    gh = _FakeGitHubTools()
    gh.workflows = [{"path": ".github/workflows/lint.yml"}]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    capability = await adapter.discover_capability("Canepro", "pipelinehealer")
    assert capability.is_available is False
    assert capability.reason == "ci_doctor_workflow_not_found"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_filters_by_run_and_sha() -> None:
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 101,
            "title": "CI Doctor: run 4242 failed",
            "body": "Investigated run 4242 for sha abcdef1234567890",
            "html_url": "https://github.com/Canepro/pipelinehealer/issues/101",
            "state": "open",
        },
        {
            "number": 102,
            "title": "CI Doctor: unrelated run",
            "body": "run 9000 sha deadbeef",
            "html_url": "https://github.com/Canepro/pipelinehealer/issues/102",
            "state": "open",
        },
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer",
        run_id=4242,
        head_sha="abcdef1234567890",
        run_number=7,
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].matched_run_id == 4242
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer/issues/101"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_matches_run_url_and_title_prefix_without_label() -> None:
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 205,
            "title": "[CI Failure Doctor] Build workflow investigation",
            "body": "See details at https://github.com/Canepro/pipelinehealer/actions/runs/4242",
            "html_url": "https://github.com/Canepro/pipelinehealer/issues/205",
            "state": "open",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer",
        run_id=4242,
        head_sha="abcdef1234567890",
        run_number=7,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].matched_run_id == 4242
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer/issues/205"
    assert any('[CI Failure Doctor]' in q for q in gh.queries)


@pytest.mark.asyncio
async def test_collect_external_diagnostics_matches_from_issue_comment() -> None:
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 300,
            "title": "[CI Failure Doctor] Existing investigation thread",
            "body": "No direct run-id in issue body",
            "html_url": "https://github.com/Canepro/pipelinehealer/issues/300",
            "state": "open",
        }
    ]
    gh.issue_comments[300] = [
        {
            "body": "Observed same signature for run 4242: https://github.com/Canepro/pipelinehealer/actions/runs/4242",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer",
        run_id=4242,
        head_sha="abcdef1234567890",
        run_number=7,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].matched_run_id == 4242
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer/issues/300"


@pytest.mark.asyncio
async def test_collect_external_diagnostics_uses_list_issues_fallback_when_search_lags() -> None:
    gh = _FakeGitHubTools()
    gh.issues = []
    gh.listed_issues = [
        {
            "number": 400,
            "title": "[CI Failure Doctor] fresh investigation",
            "body": "Run URL: https://github.com/Canepro/pipelinehealer/actions/runs/4242",
            "html_url": "https://github.com/Canepro/pipelinehealer/issues/400",
            "state": "open",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer",
        run_id=4242,
        head_sha="abcdef1234567890",
        run_number=7,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer/issues/400"
