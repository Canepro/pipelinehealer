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


@pytest.mark.asyncio
async def test_collect_external_diagnostics_prefers_latest_run_specific_issue_over_stale_sha_matches() -> None:
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 75,
            "title": "[CI Failure Doctor] CI Failure Investigation - Run #135",
            "body": "Commit 0329e474de4d2ec312b0c8660b03c3210a4e87ac",
            "html_url": "https://github.com/Canepro/pipelinehealer-demo/issues/75",
            "state": "closed",
            "updated_at": "2026-02-15T07:36:00Z",
        }
    ]
    gh.listed_issues = [
        {
            "number": 83,
            "title": "[CI Failure Doctor] CI Failure Investigation - Run #139",
            "body": "Run: 22032840035\nhttps://github.com/Canepro/pipelinehealer-demo/actions/runs/22032840035",
            "html_url": "https://github.com/Canepro/pipelinehealer-demo/issues/83",
            "state": "open",
            "updated_at": "2026-02-15T08:58:00Z",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer-demo",
        run_id=22032840035,
        head_sha="0329e474de4d2ec312b0c8660b03c3210a4e87ac",
        run_number=139,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].status == ExternalDiagnosticStatus.AVAILABLE
    assert diagnostics[0].url == "https://github.com/Canepro/pipelinehealer-demo/issues/83"
    assert diagnostics[0].metadata["issue_number"] == 83
    assert diagnostics[0].metadata["match_basis"] in {"run_url", "run_id"}


@pytest.mark.asyncio
async def test_collect_external_diagnostics_ignores_sha_only_matches_without_run_correlation() -> None:
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 75,
            "title": "[CI Failure Doctor] CI Failure Investigation - historical thread",
            "body": "Commit 0329e474de4d2ec312b0c8660b03c3210a4e87ac only",
            "html_url": "https://github.com/Canepro/pipelinehealer-demo/issues/75",
            "state": "closed",
            "updated_at": "2026-02-15T07:36:00Z",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer-demo",
        run_id=22039999999,
        head_sha="0329e474de4d2ec312b0c8660b03c3210a4e87ac",
        run_number=999,
    )

    assert diagnostics == []


# ---------------------------------------------------------------------------
# _extract_issue_details unit tests
# ---------------------------------------------------------------------------

_SAMPLE_CI_DOCTOR_BODY = """\
## Summary
The build job intentionally aborts when requiring `left-pad` because the dependency is missing.

## Failure Details
- **Run**: [22044458052](https://github.com/Canepro/pipelinehealer-demo/actions/runs/22044458052)
- **Commit**: e3cbc1f685c95ce9c7b114574ced127bed9f4e35
- **Trigger**: workflow_dispatch

## Root Cause Analysis
The `Check dependencies (may fail)` step runs `node -e "require('left-pad')"` but `left-pad` is not in package.json.

## Failed Jobs and Errors
- **build**: `Error: Cannot find module 'left-pad'` during `Check dependencies (may fail)`.

## Investigation Findings
- The build job installs dependencies via Bun, but the manifest contains zero deps.

## Recommended Actions
- [x] Publish `left-pad` as a dependency in package.json.

## Prevention Strategies
Keep any modules referenced by failure-simulation scripts present in the dependency list.

## AI Team Self-Improvement
Ensure CI failure simulations do not require undeclared modules.

## Historical Context
First occurrence documented in `/tmp/memory/investigations/2026-02-15-22-45-45-274-22044458052.json`.

> AI generated by [CI Failure Doctor](https://github.com/Canepro/pipelinehealer-demo/actions/runs/22044461989)

<!-- gh-aw-agentic-workflow: CI Failure Doctor, engine: copilot, model: gpt-5.1-codex-mini, run: https://github.com/Canepro/pipelinehealer-demo/actions/runs/22044461989 -->
"""


def test_extract_issue_details_parses_all_sections() -> None:
    details = PassiveIssueGHAWAdapter._extract_issue_details(_SAMPLE_CI_DOCTOR_BODY)

    assert "summary" in details
    assert "left-pad" in str(details["summary"])

    assert "root_cause" in details
    assert "require('left-pad')" in str(details["root_cause"])

    assert "failed_jobs" in details
    assert "Cannot find module" in str(details["failed_jobs"])

    assert "investigation_findings" in details
    assert "recommended_actions" in details
    assert "prevention_strategies" in details
    assert "ai_self_improvement" in details

    assert "historical_context" in details
    assert "First occurrence" in str(details["historical_context"])
    # Temp file paths should be stripped from the stored text.
    assert "/tmp/memory/" not in str(details["historical_context"])

    assert details.get("trigger") == "workflow_dispatch"
    assert details.get("doctor_engine") == "copilot"
    assert details.get("doctor_model") == "gpt-5.1-codex-mini"
    assert "22044461989" in str(details.get("doctor_run_url", ""))


def test_extract_issue_details_handles_empty_body() -> None:
    assert PassiveIssueGHAWAdapter._extract_issue_details("") == {}
    assert PassiveIssueGHAWAdapter._extract_issue_details("No sections here") == {}


def test_extract_issue_details_truncates_long_sections() -> None:
    long_body = "## Root Cause Analysis\n" + ("x" * 5000) + "\n## Summary\nShort."
    details = PassiveIssueGHAWAdapter._extract_issue_details(long_body)
    assert len(str(details.get("root_cause", ""))) <= 2000
    assert details.get("summary") == "Short."


def test_sanitize_section_strips_html_comments_and_footer() -> None:
    raw = (
        "Some analysis text.\n"
        "<!-- internal marker: expiry=2026-03-01 -->\n"
        "> AI generated by [CI Failure Doctor](https://example.com)\n"
        "More useful content."
    )
    cleaned = PassiveIssueGHAWAdapter._sanitize_section(raw)
    assert "<!--" not in cleaned
    assert "AI generated by" not in cleaned
    assert "Some analysis text." in cleaned
    assert "More useful content." in cleaned


def test_sanitize_section_strips_standalone_temp_paths() -> None:
    raw = (
        "Investigation logged.\n"
        "/tmp/memory/investigations/2026-02-15.json\n"
        "The root cause is a missing dep."
    )
    cleaned = PassiveIssueGHAWAdapter._sanitize_section(raw)
    assert "/tmp/memory/" not in cleaned
    assert "Investigation logged." in cleaned
    assert "root cause" in cleaned


@pytest.mark.asyncio
async def test_collect_external_diagnostics_includes_details() -> None:
    """Verify that collected diagnostics include extracted issue body details."""
    gh = _FakeGitHubTools()
    gh.issues = [
        {
            "number": 88,
            "title": "[CI Failure Doctor] CI Failure Investigation - Run #142",
            "body": _SAMPLE_CI_DOCTOR_BODY,
            "html_url": "https://github.com/Canepro/pipelinehealer-demo/issues/88",
            "state": "open",
            "updated_at": "2026-02-15T22:57:00Z",
        }
    ]
    adapter = PassiveIssueGHAWAdapter(gh, known_workflows=["ci-doctor"])

    diagnostics = await adapter.collect_external_diagnostics(
        owner="Canepro",
        repo="pipelinehealer-demo",
        run_id=22044458052,
        head_sha="e3cbc1f685c95ce9c7b114574ced127bed9f4e35",
        run_number=142,
    )

    assert len(diagnostics) == 1
    meta = diagnostics[0].metadata
    assert "details" in meta
    details = meta["details"]
    assert "root_cause" in details
    assert "historical_context" in details
    assert details.get("doctor_engine") == "copilot"
