"""Adapter contracts for optional GitHub Agentic Workflows diagnostics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from ..models import ExternalDiagnostic
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


def create_gh_aw_adapter(*, github_tools: GitHubTools) -> GHAWAdapter:
    """Return an adapter instance for external diagnostics collection.

    PR A intentionally ships a no-op adapter contract only; behavior is wired in later phases.
    """
    _ = github_tools
    return NullGHAWAdapter(reason="passive gh-aw ingestion not enabled in this phase")

