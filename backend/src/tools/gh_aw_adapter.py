"""Adapter contracts for optional GitHub Agentic Workflows diagnostics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Protocol

from ..config import get_settings
from ..models import ExternalDiagnostic, ExternalDiagnosticStatus
from .github_tools import GitHubTools

logger = logging.getLogger(__name__)

_MIN_STRONG_MATCH_SCORE = 90


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
        run_number: int | None = None,
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
        run_number: int | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = run_number
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
    def _parse_issue_timestamp(issue: Mapping[str, object]) -> str:
        # GitHub timestamps are ISO-8601; keep canonical string for deterministic sorting.
        for key in ("updated_at", "created_at"):
            value = str(issue.get(key, "")).strip()
            if value:
                return value
        return ""

    @staticmethod
    def _match_score_from_blob(
        blob: str,
        *,
        run_id: int,
        head_sha: str,
        run_number: int | None,
    ) -> tuple[int, str]:
        run_id_token = str(run_id)
        run_url_fragment = f"/actions/runs/{run_id}"
        if run_url_fragment in blob:
            return (120, "run_url")
        if run_id_token in blob:
            return (110, "run_id")

        if run_number is not None:
            for token in (f"run #{run_number}", f"run {run_number}"):
                if token in blob:
                    return (90, "run_number")
            # Standalone run number is weaker than explicit "run #<n>" text.
            if str(run_number) in blob:
                return (70, "run_number_token")

        sha_prefixes = [head_sha.lower()[:12], head_sha.lower()[:7], head_sha.lower()]
        if any(prefix and prefix in blob for prefix in sha_prefixes):
            return (20, "sha")

        return (0, "none")

    @classmethod
    def _issue_match_score(
        cls,
        issue: Mapping[str, object],
        *,
        run_id: int,
        head_sha: str,
        run_number: int | None,
    ) -> tuple[int, str]:
        blob = (
            str(issue.get("title", "")).lower()
            + "\n"
            + str(issue.get("body", "")).lower()
        )
        return cls._match_score_from_blob(
            blob,
            run_id=run_id,
            head_sha=head_sha,
            run_number=run_number,
        )

    @classmethod
    def _issue_matches_run(
        cls,
        issue: Mapping[str, object],
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
    ) -> bool:
        score, _ = cls._issue_match_score(
            issue,
            run_id=run_id,
            head_sha=head_sha,
            run_number=run_number,
        )
        return score > 0

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
    ) -> list[ExternalDiagnostic]:
        run_number_query = f'"run #{run_number}"' if run_number is not None else ""
        query_candidates = [
            f'label:"ci-doctor" "{run_id}" "{head_sha[:12]}"',
            f'"[CI Failure Doctor]" "{run_id}" "{head_sha[:12]}"',
            f'"[CI Failure Doctor]" {run_number_query}'.strip(),
            'label:"ci-doctor"',
            '"[CI Failure Doctor]"',
        ]
        issues: list[dict[str, object]] = []
        seen_numbers: set[int] = set()
        for query in query_candidates:
            if not query:
                continue
            found = await self._github_tools.search_issues(
                owner=owner,
                repo=repo,
                query=query,
                state="all",
                per_page=20,
            )
            logger.info(
                "ci-doctor query %r returned %d issues for run %s",
                query, len(found), run_id,
            )
            for issue in found:
                number = issue.get("number")
                if not isinstance(number, int):
                    continue
                if number in seen_numbers:
                    continue
                seen_numbers.add(number)
                issues.append(issue)
        # GitHub Search can lag indexing for freshly created/updated issues.
        # Fallback to the repo issues listing endpoint for low-latency visibility.
        list_issues = getattr(self._github_tools, "list_issues", None)
        if list_issues is not None:
            try:
                listed = await list_issues(
                    owner,
                    repo,
                    state="all",
                    labels="ci-doctor",
                    sort="updated",
                    direction="desc",
                    per_page=30,
                )
                for issue in listed:
                    number = issue.get("number")
                    if not isinstance(number, int):
                        continue
                    if number in seen_numbers:
                        continue
                    seen_numbers.add(number)
                    issues.append(issue)
            except Exception as exc:
                logger.warning("Fallback list_issues failed for %s/%s: %s", owner, repo, type(exc).__name__)

        candidates: list[tuple[int, str, str, dict[str, object]]] = []
        for issue in issues:
            number = issue.get("number")
            score, match_basis = self._issue_match_score(
                issue,
                run_id=run_id,
                head_sha=head_sha,
                run_number=run_number,
            )
            if score <= 0:
                if not isinstance(number, int):
                    continue
                logger.info(
                    "Issue #%s title/body did not match run %s; checking comments",
                    number, run_id,
                )
                score, match_basis = await self._issue_comments_match_run(
                    owner=owner,
                    repo=repo,
                    issue_number=number,
                    run_id=run_id,
                    head_sha=head_sha,
                    run_number=run_number,
                )
                if score <= 0:
                    logger.info("Issue #%s comments also did not match run %s; skipping", number, run_id)
                    continue
                logger.info("Issue #%s matched run %s via comments (%s)", number, run_id, match_basis)
            if score < _MIN_STRONG_MATCH_SCORE:
                logger.info(
                    "Issue #%s matched run %s only weakly (%s, score=%s); skipping",
                    number,
                    run_id,
                    match_basis,
                    score,
                )
                continue
            issue_ts = self._parse_issue_timestamp(issue)
            candidates.append((score, issue_ts, match_basis, issue))

        if not candidates:
            return []

        # Prefer strongest correlation first, then newest issue activity.
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, _, best_basis, best_issue = candidates[0]
        logger.info(
            "Selected ci-doctor issue #%s for run %s with score=%s basis=%s among %d candidates",
            best_issue.get("number"),
            run_id,
            best_score,
            best_basis,
            len(candidates),
        )

        diagnostics: list[ExternalDiagnostic] = []
        number = best_issue.get("number")
        issue = best_issue
        if best_score > 0:
            if not isinstance(number, int):
                return []
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
                        "match_basis": best_basis,
                    },
                )
            )

        return diagnostics

    async def _issue_comments_match_run(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        run_id: int,
        head_sha: str,
        run_number: int | None,
    ) -> tuple[int, str]:
        list_comments = getattr(self._github_tools, "list_issue_comments", None)
        if list_comments is None:
            logger.debug("list_issue_comments not available on github_tools")
            return (0, "none")
        try:
            comments = await list_comments(owner, repo, issue_number, 10)
        except Exception as exc:
            logger.warning("Failed to fetch comments for issue #%s: %s", issue_number, exc)
            return (0, "none")
        logger.info(
            "Fetched %d comments for issue #%s to match run %s",
            len(comments), issue_number, run_id,
        )
        for comment in comments:
            blob = str(comment.get("body", "")).lower()
            score, basis = self._match_score_from_blob(
                blob,
                run_id=run_id,
                head_sha=head_sha,
                run_number=run_number,
            )
            if score > 0:
                return (score, f"comment_{basis}")
        return (0, "none")


def create_gh_aw_adapter(*, github_tools: GitHubTools) -> GHAWAdapter:
    """Return an adapter instance for external diagnostics collection."""
    settings = get_settings()
    if not settings.gh_aw_tools_enabled or settings.gh_aw_ingestion_mode != "passive":
        return NullGHAWAdapter(reason="external diagnostics disabled by runtime settings")
    return PassiveIssueGHAWAdapter(
        github_tools=github_tools,
        known_workflows=settings.gh_aw_known_workflows,
    )
