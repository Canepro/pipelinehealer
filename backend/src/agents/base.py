"""Base agent configuration and utilities for PipelineHealer."""

import logging
from typing import Any

from azure.identity import DefaultAzureCredential

from ..config import get_settings

logger = logging.getLogger(__name__)


def validate_azure_openai_endpoint(endpoint: str) -> None:
    """Fail fast on common misconfiguration (Foundry project endpoint vs AOAI resource endpoint)."""
    if not endpoint:
        return
    # Foundry project endpoints look like: https://<project>.services.ai.azure.com/api/projects/<id>
    # Azure OpenAI resource endpoints look like: https://<resource>.openai.azure.com/
    if "services.ai.azure.com" in endpoint:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT looks like an Azure AI Foundry *project* endpoint "
            "(...services.ai.azure.com). PipelineHealer currently expects the Azure OpenAI *resource* "
            "endpoint that ends with '.openai.azure.com/'. In Foundry, open the 'Azure OpenAI' "
            "resource entry (not the 'Microsoft Foundry' project endpoint) to copy the correct endpoint."
        )

class NoopAgent:
    """Local fallback agent used when Azure OpenAI is not configured.

    This keeps local dev + unit tests working without cloud credentials.
    """

    async def run(self, prompt: str) -> str:  # pragma: no cover
        _ = prompt
        return ""

class FallbackAgent:
    """Agent wrapper that retries with a fallback agent for known compatibility errors."""

    def __init__(self, primary: Any, fallback: Any):
        self._primary = primary
        self._fallback = fallback

    async def run(self, prompt: str) -> Any:
        try:
            return await self._primary.run(prompt)
        except Exception as exc:
            message = str(exc).lower()
            version_error = "api version not supported" in message
            if not version_error:
                raise

            logger.warning(
                "Primary Azure OpenAI client failed with API-version compatibility error; "
                "retrying with fallback client. error=%s",
                exc,
            )
            return await self._fallback.run(prompt)


def _as_agent_compat(client: Any, *, name: str, instructions: str) -> Any:
    """Build an agent from a client across Agent Framework versions.

    Newer releases expose `client.as_agent(...)`, while some older builds (seen in
    containerized installs) do not for certain client types (for example
    `AzureOpenAIChatClient`).
    """
    as_agent = getattr(client, "as_agent", None)
    if callable(as_agent):
        return as_agent(name=name, instructions=instructions)

    # Compatibility fallback for older Agent Framework versions.
    from agent_framework import ChatAgent

    logger.warning(
        "Client %s has no as_agent(); falling back to ChatAgent compatibility wrapper.",
        type(client).__name__,
    )
    return ChatAgent(client, instructions=instructions, name=name)


def create_cloud_agent(
    *,
    name: str,
    instructions: str,
    credential: DefaultAzureCredential,
    settings: Any = None,
) -> Any:
    """Create an agent-framework ChatAgent from current settings.

    Supports both:
    - Azure OpenAI resources: https://<resource>.openai.azure.com/ (preferred; uses Responses API)
    - Azure AI Services w/ OpenAI deployments: https://<resource>.cognitiveservices.azure.com/ (uses Chat API)
    """
    if settings is None:
        settings = get_settings()

    endpoint = getattr(settings, "azure_openai_endpoint", "") or ""
    deployment_name = getattr(settings, "azure_openai_deployment_name", "") or ""
    api_version = getattr(settings, "azure_openai_api_version", "") or ""
    api_key = getattr(settings, "azure_openai_api_key", "") or ""

    if not endpoint:
        logger.warning("Azure OpenAI endpoint not configured; using NoopAgent.")
        return NoopAgent()

    validate_azure_openai_endpoint(endpoint)

    # Foundry commonly provisions OpenAI deployments behind an "AI Services" endpoint
    # like `https://<name>.cognitiveservices.azure.com/`.
    if "cognitiveservices.azure.com" in endpoint:
        # Foundry deployment pages commonly recommend a dated preview version for chat completions
        # (for example `2024-12-01-preview`). If the user left the default `preview`, prefer that.
        chat_api_version = api_version
        if chat_api_version in ("", "preview"):
            chat_api_version = "2024-12-01-preview"

        from agent_framework.azure import AzureOpenAIChatClient

        chat_client: Any = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=deployment_name,
            api_version=chat_api_version or None,
            api_key=api_key or None,
            credential=credential,
        )
        return _as_agent_compat(chat_client, name=name, instructions=instructions)

    # For classic Azure OpenAI resources (openai.azure.com), use the Responses API.
    from agent_framework.azure import AzureOpenAIChatClient, AzureOpenAIResponsesClient

    # Responses API is enabled only for certain preview versions on some resources.
    # If the user left the default `preview`, prefer a known-working dated preview.
    # Keep this configurable via AZURE_OPENAI_API_VERSION; we only provide safe defaults.
    responses_api_version = api_version
    if responses_api_version in ("", "preview"):
        responses_api_version = "2025-04-01-preview"

    responses_client: Any = AzureOpenAIResponsesClient(
        endpoint=endpoint,
        deployment_name=deployment_name,
        api_version=responses_api_version,
        api_key=api_key or None,
        credential=credential,
    )
    primary_agent = _as_agent_compat(responses_client, name=name, instructions=instructions)

    # Compatibility fallback: certain resources/deployments may reject Responses API versions
    # while still supporting chat completions on a dated preview API version.
    chat_api_version = "2024-12-01-preview"
    chat_client: Any = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment_name,
        api_version=chat_api_version,
        api_key=api_key or None,
        credential=credential,
    )
    fallback_agent = _as_agent_compat(chat_client, name=name, instructions=instructions)

    return FallbackAgent(primary_agent, fallback_agent)


def get_azure_openai_config() -> dict[str, Any]:
    """Get Azure OpenAI configuration for agents.

    Returns:
        Configuration dictionary for Azure OpenAI
    """
    settings = get_settings()

    return {
        "endpoint": settings.azure_openai_endpoint,
        "deployment_name": settings.azure_openai_deployment_name,
        "api_version": settings.azure_openai_api_version,
    }


def get_credential() -> DefaultAzureCredential:
    """Get Azure credential for authentication.

    Returns:
        Azure credential object
    """
    return DefaultAzureCredential()


# System prompts for each agent type
AGENT_PROMPTS = {
    "log_analyzer": """You are a Log Analyzer Agent specialized in parsing CI/CD build logs.

Your role is to:
1. Parse raw build logs from GitHub Actions workflows
2. Extract error messages, warnings, and key events
3. Identify the specific lines and steps where failures occurred
4. Summarize the log content for downstream agents

When analyzing logs, focus on:
- Error messages (lines containing "error", "failed", "exception")
- Stack traces and their root causes
- Failed test names and assertion messages
- Dependency resolution failures
- Build tool error codes
- Timeout indicators

Output format:
- Provide a structured summary of errors found
- List the most relevant error lines
- Identify which build step failed
- Note any patterns that suggest the failure type""",
    "diagnosis": """You are a Diagnosis Agent specialized in root cause analysis of CI/CD failures.

Your role is to:
1. Analyze the processed log information from the Log Analyzer
2. Classify the failure into one of these categories:
   - dependency: Package/dependency related issues
   - test: Test failures (including flaky tests)
   - lint: Linting/formatting violations
   - build_config: Configuration errors (missing env vars, wrong paths)
   - timeout: Timeout/resource exhaustion issues
   - unknown: Cannot determine the cause

3. Determine the root cause with confidence level (0.0-1.0)
4. Identify affected files if possible
5. Assess whether this is auto-fixable

When diagnosing:
- Look for specific error patterns
- Consider the build step context
- Check for common issues (version mismatches, missing dependencies)
- Identify if the issue is likely transient (flaky) or persistent

Output your diagnosis with:
- failure_type: The category of failure
- confidence: How confident you are (0.0-1.0)
- root_cause: Clear explanation of what went wrong
- affected_files: List of files involved (if identifiable)
- is_auto_fixable: Whether this can be automatically fixed
- suggested_fix: High-level suggestion for fixing""",
    "remediation": """You are a Remediation Agent specialized in fixing CI/CD failures.

Your role is to:
1. Take the diagnosis from the Diagnosis Agent
2. Generate appropriate remediation actions:
   - CREATE_PR: Create a pull request with a fix
   - CREATE_ISSUE: Create a detailed issue for manual fix
   - RETRY_WORKFLOW: Retry the workflow (for transient issues)
   - SKIP: Skip remediation (for issues that should be ignored)

3. For PRs, generate:
   - Appropriate branch name
   - Clear PR title and description
   - File changes needed

4. For Issues, generate:
   - Descriptive title
   - Detailed body with diagnosis and suggestions

Guidelines:
- Only create PRs for issues you're confident can be auto-fixed
- Dependency updates are usually safe to auto-fix
- Test failures usually need human investigation
- Always provide clear documentation of what was found

Be conservative - when in doubt, create an issue rather than a potentially broken PR.""",
    "orchestrator": """You are the Orchestrator Agent for PipelineHealer, a CI/CD self-healing system.

Your role is to:
1. Coordinate the workflow between specialized agents
2. Receive workflow failure events from GitHub
3. Route tasks to appropriate agents:
   - Log Analyzer: First, to parse the failure logs
   - Diagnosis: Second, to determine root cause
   - Remediation: Finally, to generate fixes

4. Track the overall progress and handle errors
5. Ensure results are properly stored and reported

You orchestrate the healing pipeline:
Event → Log Analysis → Diagnosis → Remediation → Result

Make decisions about:
- Whether to proceed with remediation based on confidence
- Whether to skip certain failures (e.g., already being handled)
- How to handle agent errors gracefully

Always maintain context about:
- The repository and workflow that failed
- What has been tried before
- The current state of the healing process""",
}


def get_agent_prompt(agent_type: str) -> str:
    """Get the system prompt for an agent type.

    Args:
        agent_type: Type of agent (log_analyzer, diagnosis, remediation, orchestrator)

    Returns:
        System prompt string
    """
    return AGENT_PROMPTS.get(agent_type, "")
