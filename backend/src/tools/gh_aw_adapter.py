"""Adapter contracts for optional GitHub Agentic Workflows diagnostics.

Supports multi-source collection: each gh-aw workflow that creates GitHub
Issues (ci-doctor, breaking-change-checker, etc.) is a separate diagnostic
source with its own label, title prefix, match threshold, and confidence
delta.  Findings are tagged with the originating source name so the
dashboard can clearly attribute them.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ..config import get_settings
from ..models import ExternalDiagnostic, ExternalDiagnosticStatus
from .github_tools import GitHubTools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Diagnostic source registry
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DiagnosticSourceConfig:
    """Configuration for a single gh-aw diagnostic source that creates Issues."""

    name: str
    label: str
    title_prefix: str
    confidence_delta: float = 0.08
    min_match_score: int = 90


# Known gh-aw workflows that publish findings as GitHub Issues.
# ci-doctor: run-specific analysis (triggered by CI failure) — needs strong match.
# breaking-change-checker: ambient analysis (schedule/manual) — SHA match is enough.
KNOWN_ISSUE_SOURCES: tuple[DiagnosticSourceConfig, ...] = (
    DiagnosticSourceConfig(
        name="ci-doctor",
        label="ci-doctor",
        title_prefix="[CI Failure Doctor]",
        confidence_delta=0.08,
        min_match_score=90,
    ),
    DiagnosticSourceConfig(
        name="breaking-change-checker",
        label="breaking-change",
        title_prefix="[breaking-change]",
        confidence_delta=0.05,
        min_match_score=20,
    ),
)

# Lookup by workflow slug for quick access during capability discovery.
_SOURCE_BY_SLUG: dict[str, DiagnosticSourceConfig] = {
    src.name: src for src in KNOWN_ISSUE_SOURCES
}


@dataclass(slots=True)
class GHAWCapability:
    """Capability state for a monitored repository."""

    repo_full_name: str
    is_available: bool
    available_workflows: list[str] = field(default_factory=list)
    available_sources: list[DiagnosticSourceConfig] = field(default_factory=list)
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
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        """Collect structured external diagnostics for a workflow run.

        When *sources* is provided, only those sources are searched.
        When ``None``, the adapter discovers available sources automatically.
        """


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
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        _ = run_number, sources
        return []


class PassiveIssueGHAWAdapter:
    """Passive adapter that ingests gh-aw issue evidence from multiple sources."""

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
        """Discover which gh-aw diagnostic sources are present in the repo."""
        repo_full_name = f"{owner}/{repo}"
        try:
            workflows = await self._github_tools.list_repo_workflows(owner, repo)
        except Exception as exc:
            return GHAWCapability(
                repo_full_name=repo_full_name,
                is_available=False,
                reason=f"workflow_list_failed:{type(exc).__name__}",
            )

        slugs: set[str] = set()
        for workflow in workflows:
            path = str(workflow.get("path", "")).strip()
            if not path:
                continue
            slug = self._workflow_slug_from_path(path)
            if slug:
                slugs.add(slug)

        # Match discovered slugs against known diagnostic sources.
        discovered_sources: list[DiagnosticSourceConfig] = []
        for slug in sorted(slugs):
            source_cfg = _SOURCE_BY_SLUG.get(slug)
            if source_cfg is not None:
                discovered_sources.append(source_cfg)

        available_workflows = sorted(slugs & set(self._known_workflows) | {s.name for s in discovered_sources})
        is_available = len(discovered_sources) > 0

        return GHAWCapability(
            repo_full_name=repo_full_name,
            is_available=is_available,
            available_workflows=available_workflows,
            available_sources=discovered_sources,
            reason=None if is_available else "no_known_diagnostic_sources_found",
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

    # Section header pattern: "## Title" at start of line.
    _SECTION_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)

    # Footer HTML comment from gh-aw containing engine/model/run info.
    _FOOTER_RE = re.compile(
        r"<!--\s*gh-aw-agentic-workflow:\s*(?P<workflow>[^,]+),\s*"
        r"engine:\s*(?P<engine>[^,]+),\s*"
        r"model:\s*(?P<model>[^,]+),\s*"
        r"run:\s*(?P<run_url>\S+)\s*-->",
    )

    # Patterns to strip from section bodies before persisting.
    _HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
    _BLOCKQUOTE_FOOTER_RE = re.compile(
        r"^>\s*AI generated by\b.*$", re.MULTILINE | re.IGNORECASE,
    )
    # gh-aw setup hints and expiry markers injected into issue bodies.
    _GH_AW_SETUP_RE = re.compile(
        r"^>\s*To add this workflow\b.*$", re.MULTILINE | re.IGNORECASE,
    )
    _GH_AW_USAGE_RE = re.compile(
        r"^>\s*-.*(?:usage guide|packaging-imports).*$", re.MULTILINE | re.IGNORECASE,
    )
    _EXPIRY_RE = re.compile(
        r"^(?:>\s*)?-\s*\[[ x]\]\s*expires?\b.*$", re.MULTILINE | re.IGNORECASE,
    )
    # Inline temp/memory file paths (with or without backtick wrappers).
    _INLINE_TEMP_PATH_RE = re.compile(
        r"`?/(?:tmp|var|home)/\S+?\.(?:json|log|txt)`?",
    )
    # Lines whose only useful content is a temp-file path.
    _STANDALONE_TEMP_PATH_RE = re.compile(
        r"^\s*`?/(?:tmp|var|home)/\S+\.(?:json|log|txt)`?\s*$",
    )

    @classmethod
    def _sanitize_section(cls, text: str) -> str:
        """Remove internal boilerplate from a section body.

        Strips HTML comments, ``> AI generated by …`` footer lines,
        temp-file paths (both standalone lines and inline references),
        and collapses excess blank lines.
        """
        text = cls._HTML_COMMENT_RE.sub("", text)
        text = cls._BLOCKQUOTE_FOOTER_RE.sub("", text)
        text = cls._GH_AW_SETUP_RE.sub("", text)
        text = cls._GH_AW_USAGE_RE.sub("", text)
        text = cls._EXPIRY_RE.sub("", text)

        # Remove inline temp-file path references (e.g. `/tmp/memory/...json`).
        text = cls._INLINE_TEMP_PATH_RE.sub("", text)

        # Remove lines that are now empty after path stripping, or were
        # standalone path references.
        cleaned_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if cls._STANDALONE_TEMP_PATH_RE.match(stripped):
                continue
            cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)

        # Strip leftover "documented in" or "logged at" phrases pointing nowhere.
        text = re.sub(r"\b(?:documented|logged|stored)\s+(?:in|at)\s*[.]*\s*$", "", text, flags=re.MULTILINE)

        # Collapse runs of 3+ blank lines into 2.
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def _extract_issue_details(cls, body: str) -> dict[str, object]:
        """Parse a ci-doctor issue body into structured detail fields.

        Extracts well-known markdown sections (Summary, Root Cause Analysis,
        Recommended Actions, etc.) and the gh-aw footer metadata.  Sections
        are sanitized (HTML comments, footer markers, temp paths removed)
        and trimmed to 2000 chars to stay within reasonable storage limits.
        """
        if not body:
            return {}

        # Split body into {heading: content} pairs.
        sections: dict[str, str] = {}
        parts = cls._SECTION_RE.split(body)
        # parts alternates: [preamble, heading1, content1, heading2, content2, ...]
        for i in range(1, len(parts) - 1, 2):
            heading = parts[i].strip()
            content = parts[i + 1].strip()
            sections[heading] = content

        details: dict[str, object] = {}

        # Map well-known sections to structured keys.
        section_map = {
            "Summary": "summary",
            "Root Cause Analysis": "root_cause",
            "Failed Jobs and Errors": "failed_jobs",
            "Investigation Findings": "investigation_findings",
            "Recommended Actions": "recommended_actions",
            "Prevention Strategies": "prevention_strategies",
            "AI Team Self-Improvement": "ai_self_improvement",
            "Historical Context": "historical_context",
        }
        for heading, key in section_map.items():
            raw = sections.get(heading, "")
            text = cls._sanitize_section(raw)
            if text:
                details[key] = text[:2000]

        # Extract structured fields from Failure Details section.
        failure_details = sections.get("Failure Details", "")
        if failure_details:
            for line in failure_details.splitlines():
                line_lower = line.strip().lower()
                if line_lower.startswith("- **trigger**"):
                    trigger = line.split(":", 1)[-1].strip().strip("`")
                    if trigger:
                        details["trigger"] = trigger

        # Parse gh-aw footer for doctor workflow metadata (before stripping).
        footer_match = cls._FOOTER_RE.search(body)
        if footer_match:
            details["doctor_engine"] = footer_match.group("engine").strip()
            details["doctor_model"] = footer_match.group("model").strip()
            details["doctor_run_url"] = footer_match.group("run_url").strip()

        return details

    # ------------------------------------------------------------------
    # Multi-source collection
    # ------------------------------------------------------------------

    async def _collect_from_source(
        self,
        source: DiagnosticSourceConfig,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None,
    ) -> list[ExternalDiagnostic]:
        """Search for issues from a single diagnostic source and match to the run."""
        run_number_query = f'"run #{run_number}"' if run_number is not None else ""
        label = source.label
        prefix = source.title_prefix

        query_candidates = [
            f'label:"{label}" "{run_id}" "{head_sha[:12]}"',
            f'"{prefix}" "{run_id}" "{head_sha[:12]}"',
            f'"{prefix}" {run_number_query}'.strip(),
            f'label:"{label}"',
            f'"{prefix}"',
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
                "%s query %r returned %d issues for run %s",
                source.name, query, len(found), run_id,
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
                    labels=label,
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
                logger.warning(
                    "Fallback list_issues for %s failed for %s/%s: %s",
                    source.name, owner, repo, type(exc).__name__,
                )

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
                    "%s issue #%s title/body did not match run %s; checking comments",
                    source.name, number, run_id,
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
                    logger.info(
                        "%s issue #%s comments also did not match run %s; skipping",
                        source.name, number, run_id,
                    )
                    continue
                logger.info(
                    "%s issue #%s matched run %s via comments (%s)",
                    source.name, number, run_id, match_basis,
                )
            if score < source.min_match_score:
                logger.info(
                    "%s issue #%s matched run %s only weakly (%s, score=%s < min %s); skipping",
                    source.name, number, run_id, match_basis, score, source.min_match_score,
                )
                continue
            issue_ts = self._parse_issue_timestamp(issue)
            candidates.append((score, issue_ts, match_basis, issue))

        if not candidates:
            return []

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, _, best_basis, best_issue = candidates[0]
        logger.info(
            "Selected %s issue #%s for run %s with score=%s basis=%s among %d candidates",
            source.name,
            best_issue.get("number"),
            run_id,
            best_score,
            best_basis,
            len(candidates),
        )

        number = best_issue.get("number")
        if not isinstance(number, int):
            return []

        title = str(best_issue.get("title", "")).strip()
        issue_url = str(best_issue.get("html_url", "")).strip() or None
        state = str(best_issue.get("state", "")).strip().lower()
        body = str(best_issue.get("body", ""))

        metadata: dict[str, object] = {
            "issue_number": number,
            "issue_state": state,
            "match_basis": best_basis,
        }

        details = self._extract_issue_details(body)
        if details:
            metadata["details"] = details

        return [
            ExternalDiagnostic(
                source=source.name,
                status=ExternalDiagnosticStatus.AVAILABLE,
                summary=title or f"{source.name} findings available",
                url=issue_url,
                matched_run_id=run_id,
                confidence_delta=source.confidence_delta,
                metadata=metadata,
            )
        ]

    async def collect_external_diagnostics(
        self,
        owner: str,
        repo: str,
        run_id: int,
        head_sha: str,
        run_number: int | None = None,
        *,
        sources: list[DiagnosticSourceConfig] | None = None,
    ) -> list[ExternalDiagnostic]:
        """Collect diagnostics from gh-aw sources for a run.

        When *sources* is provided, only those sources are searched.
        When ``None``, capability discovery runs automatically.
        """
        if sources is None:
            capability = await self.discover_capability(owner, repo)
            sources = capability.available_sources
        if not sources:
            return []

        all_diagnostics: list[ExternalDiagnostic] = []
        for source in sources:
            try:
                findings = await self._collect_from_source(
                    source=source,
                    owner=owner,
                    repo=repo,
                    run_id=run_id,
                    head_sha=head_sha,
                    run_number=run_number,
                )
                all_diagnostics.extend(findings)
            except Exception as exc:
                logger.warning(
                    "Error collecting from %s for %s/%s run %s: %s",
                    source.name, owner, repo, run_id, exc,
                )
        return all_diagnostics

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
