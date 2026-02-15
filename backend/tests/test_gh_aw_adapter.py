"""Tests for gh-aw passive diagnostics adapter behavior."""

import pytest

from src.models import ExternalDiagnosticStatus
from src.tools.gh_aw_adapter import PassiveIssueGHAWAdapter


class _FakeGitHubTools:
    def __init__(self) -> None:
        self.workflows = []
        self.issues = []

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
        _ = owner, repo, query, state, per_page
        return self.issues


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
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].matched_run_id == 4242
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer/issues/101"
