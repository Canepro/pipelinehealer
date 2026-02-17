"""Minimal MCP provider registry and health scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import Settings


@dataclass
class MCPHealthStatus:
    """Normalized MCP provider health status."""

    provider: str
    enabled: bool
    read_only: bool
    available: bool
    reason: str
    message: str
    configured_tools: list[str]


class MCPToolProvider(Protocol):
    """Interface for MCP tool providers."""

    def health(self, settings: Settings) -> MCPHealthStatus: ...


class DisabledMCPProvider:
    """No-op provider used when MCP is disabled."""

    def health(self, settings: Settings) -> MCPHealthStatus:
        return MCPHealthStatus(
            provider="disabled",
            enabled=False,
            read_only=settings.mcp_read_only,
            available=False,
            reason="disabled",
            message="MCP integration is disabled.",
            configured_tools=[],
        )


class GitHubMCPProvider:
    """Scaffold provider for GitHub MCP integration."""

    def health(self, settings: Settings) -> MCPHealthStatus:
        has_token = bool(settings.github_personal_access_token)
        if not settings.mcp_enabled:
            return MCPHealthStatus(
                provider="github",
                enabled=False,
                read_only=settings.mcp_read_only,
                available=False,
                reason="disabled",
                message="MCP provider is configured as github but MCP is disabled.",
                configured_tools=[],
            )
        if not has_token:
            return MCPHealthStatus(
                provider="github",
                enabled=True,
                read_only=settings.mcp_read_only,
                available=False,
                reason="missing_github_token",
                message="GITHUB_PERSONAL_ACCESS_TOKEN is required for GitHub MCP provider.",
                configured_tools=[],
            )
        return MCPHealthStatus(
            provider="github",
            enabled=True,
            read_only=settings.mcp_read_only,
            available=True,
            reason="ok",
            message="GitHub MCP provider scaffolding is configured.",
            configured_tools=[
                "fetch_failure_context",
                "publish_artifact",
                "rerun_pipeline",
            ],
        )


class AzureMonitorMCPProvider:
    """Scaffold provider for Azure Monitor MCP integration."""

    def health(self, settings: Settings) -> MCPHealthStatus:
        if not settings.mcp_enabled:
            return MCPHealthStatus(
                provider="azure_monitor",
                enabled=False,
                read_only=settings.mcp_read_only,
                available=False,
                reason="disabled",
                message="MCP provider is configured as azure_monitor but MCP is disabled.",
                configured_tools=[],
            )
        return MCPHealthStatus(
            provider="azure_monitor",
            enabled=True,
            read_only=settings.mcp_read_only,
            available=False,
            reason="not_implemented",
            message="Azure Monitor MCP provider is scaffolded but not implemented yet.",
            configured_tools=[],
        )


class CustomMCPProvider:
    """Scaffold provider for custom MCP gateway."""

    def health(self, settings: Settings) -> MCPHealthStatus:
        if not settings.mcp_enabled:
            return MCPHealthStatus(
                provider="custom",
                enabled=False,
                read_only=settings.mcp_read_only,
                available=False,
                reason="disabled",
                message="MCP provider is configured as custom but MCP is disabled.",
                configured_tools=[],
            )
        return MCPHealthStatus(
            provider="custom",
            enabled=True,
            read_only=settings.mcp_read_only,
            available=False,
            reason="not_implemented",
            message="Custom MCP provider is scaffolded but not implemented yet.",
            configured_tools=[],
        )


def get_mcp_provider(settings: Settings) -> MCPToolProvider:
    """Resolve MCP provider adapter from runtime settings."""
    provider = (settings.mcp_provider or "disabled").strip().lower()
    if provider == "github":
        return GitHubMCPProvider()
    if provider == "azure_monitor":
        return AzureMonitorMCPProvider()
    if provider == "custom":
        return CustomMCPProvider()
    return DisabledMCPProvider()

