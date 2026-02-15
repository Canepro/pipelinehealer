"""Adapter contracts for optional GitHub Agentic Workflows diagnostics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from ..config import get_settings
from ..models import ExternalDiagnostic, ExternalDiagnosticStatus
from .github_tools import GitHubTools

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GHAWCapability:
    """Capability state for a monitored repository."""

    repo_full_name: str
    is_available: bool
    available_workflows: list[str] = field(default_factory=list)
    reason: str | None = None


class GHAWAdapter(Protocol):
    """Contract for external diagnostics adapters."""

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        """Inspect whether external diagnostics are available for a repository."""

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
    ) -> list[ExternalDiagnostic]:
        """Collect structured external diagnostics for a workflow run."""


class NullGHAWAdapter:
    """No-op adapter used until passive ingestion is implemented."""

    def __init__(self, *, reason: str = "external diagnostics adapter is not configured") -> None:
        self._reason = reason

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        return GHAWCapability(
            repo_full_name=f"{owner}/{repo}",
            is_available=False,
            reason=self._reason,
        )

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
    ) -> list[ExternalDiagnostic]:
        return []


class PassiveIssueGHAWAdapter:
    """Passive adapter that ingests ci-doctor issue evidence when available."""

    def __init__(self, github_tools: GitHubTools, known_workflows: list[str]) -> None:
        self._github_tools = github_tools
        self._known_workflows = [w.strip().lower() for w in known_workflows if w.strip()]

    @staticmethod
    def _workflow_slug_from_path(path: str) -> str:
        path_value = path.strip().lower()
        if not path_value:
            return ""
        filename = path_value.rsplit("/", 1)[-1]
        for suffix in (".lock.yml", ".yml", ".yaml", ".md"):
            if filename.endswith(suffix):
                return filename[: -len(suffix)]
        return filename

    async def discover_capability(self, owner: str, repo: str) -> GHAWCapability:
        repo_full_name = f"{owner}/{repo}"
        try:
            workflows = await self._github_tools.list_repo_workflows(owner, repo)
        except Exception as exc:
            return GHAWCapability(
                repo_full_name=repo_full_name,
                is_available=False,
                reason=f"workflow_list_failed:{type(exc).__name__}",
            )

        matched: list[str] = []
        for workflow in workflows:
            path = str(workflow.get("path", "")).strip()
            if not path:
                continue
            slug = self._workflow_slug_from_path(path)
            if slug in self._known_workflows:
                matched.append(slug)

        unique = sorted(set(matched))
        has_ci_doctor = "ci-doctor" in unique

        return GHAWCapability(
            repo_full_name=repo_full_name,
            is_available=has_ci_doctor,
            available_workflows=unique,
            reason=None if has_ci_doctor else "ci_doctor_workflow_not_found",
        )

    @staticmethod
    def _issue_matches_run(issue: dict[str, object], run_id: int, head_sha: str) -> bool:
        blob = (
            str(issue.get("title", "")).lower()
            + "\n"
            + str(issue.get("body", "")).lower()
        )
        sha_prefixes = [head_sha.lower()[:7], head_sha.lower()[:12], head_sha.lower()]
        return (str(run_id) in blob) or any(prefix and prefix in blob for prefix in sha_prefixes)

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
    ) -> list[ExternalDiagnostic]:
        # Strong query first: explicit run correlation.
        query = f'label:"ci-doctor" "{run_id}" "{head_sha[:12]}"'
        issues = await self._github_tools.search_issues(
            owner=owner,
            repo=repo,
            query=query,
            state="all",
            per_page=10,
        )
        if not issues:
            # Fallback: recent ci-doctor issues, then filter locally.
            issues = await self._github_tools.search_issues(
                owner=owner,
                repo=repo,
                query='label:"ci-doctor"',
                state="all",
                per_page=20,
            )

        diagnostics: list[ExternalDiagnostic] = []
        for issue in issues:
            if not self._issue_matches_run(issue, run_id, head_sha):
                continue
            number = issue.get("number")
            title = str(issue.get("title", "")).strip()
            issue_url = str(issue.get("html_url", "")).strip() or None
            state = str(issue.get("state", "")).strip().lower()
            diagnostics.append(
                ExternalDiagnostic(
                    source="ci-doctor",
                    status=ExternalDiagnosticStatus.AVAILABLE,
                    summary=title or "ci-doctor findings available",
                    url=issue_url,
                    matched_run_id=run_id,
                    confidence_delta=0.08,
                    metadata={
                        "issue_number": number,
                        "issue_state": state,
                    },
                )
            )

        return diagnostics


def create_gh_aw_adapter(*, github_tools: GitHubTools) -> GHAWAdapter:
    """Return an adapter instance for external diagnostics collection."""
    settings = get_settings()
    if not settings.gh_aw_tools_enabled or settings.gh_aw_ingestion_mode != "passive":
        return NullGHAWAdapter(reason="external diagnostics disabled by runtime settings")
    return PassiveIssueGHAWAdapter(
        github_tools=github_tools,
        known_workflows=settings.gh_aw_known_workflows,
    )
