"""Base agent configuration and utilities for PipelineHealer."""

import asyncio
import logging
import random
import time
from typing import Any, Literal

from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..llm.openai_compatible import OpenAICompatibleAgent
from ..llm.providers import LLMProviderName, resolve_llm_provider
from ..llm.telemetry import record_llm_call

logger = logging.getLogger(__name__)

LLMTaskName = Literal["default", "analysis", "diagnosis", "remediation", "orchestrator"]

# Retry settings for transient LLM errors (429, 5xx, network).
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_SECONDS = 1.0
_LLM_RETRY_MAX_SECONDS = 16.0
_LLM_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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

def _is_retryable_llm_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a transient/rate-limited LLM error worth retrying."""
    message = str(exc).lower()

    # Check for HTTP status codes embedded in exception messages.
    for code in _LLM_RETRYABLE_STATUS_CODES:
        if str(code) in message:
            return True

    # Common transient error signals.
    retryable_phrases = (
        "rate limit",
        "too many requests",
        "server error",
        "temporarily unavailable",
        "connection error",
        "timeout",
    )
    return any(phrase in message for phrase in retryable_phrases)


async def _run_with_llm_retry(agent: Any, prompt: str) -> Any:
    """Run an agent with retry/backoff for transient LLM errors (429, 5xx, network)."""
    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            return await agent.run(prompt)
        except Exception as exc:
            if not _is_retryable_llm_error(exc) or attempt >= _LLM_MAX_RETRIES:
                raise

            delay = min(
                _LLM_RETRY_BASE_SECONDS * (2 ** attempt) + random.uniform(0, 0.5),
                _LLM_RETRY_MAX_SECONDS,
            )
            logger.warning(
                "Transient LLM error on attempt %d/%d; retrying in %.1fs. error=%s",
                attempt + 1,
                _LLM_MAX_RETRIES + 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Unreachable, but keeps type checkers happy.
    raise RuntimeError("LLM retry loop exited unexpectedly")  # pragma: no cover


class FallbackAgent:
    """Agent wrapper that retries with a fallback agent for known compatibility errors.

    After the primary agent fails with an API-version error once, all subsequent
    calls -- across ALL agent instances -- go directly to the fallback to avoid
    repeated 400/round-trip noise in logs.

    All calls include retry/backoff for transient LLM errors (429, 5xx, network).
    """

    _primary_failed: bool = False  # class-level: shared across all instances

    def __init__(self, primary: Any, fallback: Any):
        self._primary = primary
        self._fallback = fallback
        self._last_call_used_fallback = False

    @property
    def last_call_used_fallback(self) -> bool:
        return self._last_call_used_fallback

    async def run(self, prompt: str) -> Any:
        self._last_call_used_fallback = False
        if self._primary_failed:
            self._last_call_used_fallback = True
            result = await _run_with_llm_retry(self._fallback, prompt)
            logger.debug("[debug-mode] Using cached fallback agent (Chat)")
            return result

        try:
            result = await _run_with_llm_retry(self._primary, prompt)
            logger.debug("[debug-mode] Primary agent (Responses) succeeded")
            return result
        except Exception as exc:
            message = str(exc).lower()
            version_error = "api version not supported" in message
            if not version_error:
                raise

            logger.warning(
                "Primary Azure OpenAI client failed with API-version compatibility error; "
                "switching ALL agents to fallback client (Chat). error=%s",
                exc,
            )
            FallbackAgent._primary_failed = True
            self._last_call_used_fallback = True
            result = await _run_with_llm_retry(self._fallback, prompt)
            logger.debug("[debug-mode] Fallback agent (Chat) succeeded")
            return result


class ObservedAgent:
    """Wrapper that emits per-call model-path telemetry for active activities."""

    def __init__(self, *, agent: Any, provider: str, model: str):
        self._agent = agent
        self._provider = provider
        self._model = model

    async def run(self, prompt: str) -> Any:
        started = time.perf_counter()
        success = False
        fallback_used = False
        try:
            result = await self._agent.run(prompt)
            success = True
            return result
        finally:
            fallback_used = bool(getattr(self._agent, "last_call_used_fallback", False))
            record_llm_call(
                provider=self._provider,
                model=self._model,
                fallback_used=fallback_used,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                success=success,
            )


def _resolve_model_for_task(*, settings: Any, provider: LLMProviderName, task: LLMTaskName) -> str:
    """Resolve effective model/deployment for a task with fallback to provider default."""
    override_attr_by_task: dict[LLMTaskName, str] = {
        "analysis": "llm_model_analysis",
        "diagnosis": "llm_model_diagnosis",
        "remediation": "llm_model_remediation",
        "default": "",
        "orchestrator": "",
    }
    override_attr = override_attr_by_task.get(task, "")
    override_value = (
        str(getattr(settings, override_attr, "") or "").strip() if override_attr else ""
    )
    if override_value:
        return override_value

    if provider == LLMProviderName.OPENAI_COMPATIBLE:
        return str(getattr(settings, "openai_compatible_model", "") or "").strip()
    return str(getattr(settings, "azure_openai_deployment_name", "") or "").strip()


def _as_agent_compat(client: Any, *, name: str, instructions: str) -> Any:
    """Build an agent from a client across Agent Framework versions.

    Newer releases expose `client.as_agent(...)`, while some older builds (seen in
    containerized installs) do not for certain client types (for example
    `AzureOpenAIChatClient`).
    """
    as_agent = getattr(client, "as_agent", None)
    if callable(as_agent):
        return as_agent(name=name, instructions=instructions)

    # Compatibility fallback for Agent Framework versions where `as_agent` is absent.
    import agent_framework

    chat_agent_cls = getattr(agent_framework, "ChatAgent", None)
    if chat_agent_cls is not None:
        logger.warning(
            "Client %s has no as_agent(); falling back to ChatAgent compatibility wrapper.",
            type(client).__name__,
        )
        return chat_agent_cls(client, instructions=instructions, name=name)

    agent_cls = getattr(agent_framework, "Agent", None)
    if agent_cls is None:
        raise RuntimeError(
            f"Client {type(client).__name__} has no as_agent(), and agent_framework "
            "exports neither ChatAgent nor Agent."
        )

    logger.warning(
        "Client %s has no as_agent(); ChatAgent is unavailable, using Agent wrapper.",
        type(client).__name__,
    )
    return agent_cls(client, instructions=instructions, name=name)


def create_cloud_agent(
    *,
    name: str,
    instructions: str,
    credential: DefaultAzureCredential,
    task: LLMTaskName = "default",
    settings: Any = None,
) -> Any:
    """Create an agent-framework ChatAgent from current settings."""
    if settings is None:
        settings = get_settings()

    provider = resolve_llm_provider(getattr(settings, "llm_provider", "azure_openai"))
    effective_model = _resolve_model_for_task(
        settings=settings,
        provider=provider,
        task=task,
    )
    if provider == LLMProviderName.OPENAI_COMPATIBLE:
        base_url = getattr(settings, "openai_compatible_base_url", "") or ""
        api_key = getattr(settings, "openai_compatible_api_key", "") or ""
        model = effective_model
        if not (base_url and api_key and model):
            logger.warning(
                "OpenAI-compatible provider selected but missing config; "
                "OPENAI_COMPATIBLE_BASE_URL, OPENAI_COMPATIBLE_API_KEY, and "
                "a task/default model are required. Falling back to NoopAgent."
            )
            return NoopAgent()
        return ObservedAgent(
            agent=OpenAICompatibleAgent(
                base_url=base_url,
                api_key=api_key,
                model=model,
                instructions=instructions,
            ),
            provider=provider.value,
            model=model,
        )

    if provider == LLMProviderName.CUSTOM:
        logger.warning(
            "LLM provider '%s' is scaffolded but not implemented yet; using NoopAgent.",
            provider.value,
        )
        return NoopAgent()
    azure_agent = _create_azure_cloud_agent(
        name=name,
        instructions=instructions,
        credential=credential,
        deployment_name=effective_model,
        settings=settings,
    )
    return ObservedAgent(
        agent=azure_agent,
        provider=provider.value,
        model=effective_model or "unknown",
    )


def _create_azure_cloud_agent(
    *,
    name: str,
    instructions: str,
    credential: DefaultAzureCredential,
    deployment_name: str | None = None,
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
    resolved_deployment_name = deployment_name or getattr(settings, "azure_openai_deployment_name", "") or ""
    api_version = getattr(settings, "azure_openai_api_version", "") or ""
    chat_api_version = getattr(settings, "azure_openai_chat_api_version", "") or ""
    api_key = getattr(settings, "azure_openai_api_key", "") or ""

    if not endpoint:
        logger.warning("Azure OpenAI endpoint not configured; using NoopAgent.")
        return NoopAgent()

    validate_azure_openai_endpoint(endpoint)

    # Foundry commonly provisions OpenAI deployments behind an "AI Services" endpoint
    # like `https://<name>.cognitiveservices.azure.com/`.
    if "cognitiveservices.azure.com" in endpoint:
        # For cognitiveservices endpoints, prefer the chat API version from config.
        # Fall back to the primary api_version if chat version is unset.
        effective_chat_version = chat_api_version or api_version

        from agent_framework.azure import AzureOpenAIChatClient

        foundry_chat_client: Any = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=resolved_deployment_name,
            api_version=effective_chat_version or None,
            api_key=api_key or None,
            credential=credential,
        )
        return _as_agent_compat(foundry_chat_client, name=name, instructions=instructions)

    # For classic Azure OpenAI resources (openai.azure.com), use the Responses API.
    from agent_framework.azure import AzureOpenAIChatClient, AzureOpenAIResponsesClient

    # Primary version comes from AZURE_OPENAI_API_VERSION (env-driven).
    responses_api_version = api_version

    responses_client: Any = AzureOpenAIResponsesClient(
        endpoint=endpoint,
        deployment_name=resolved_deployment_name,
        api_version=responses_api_version,
        api_key=api_key or None,
        credential=credential,
    )
    primary_agent = _as_agent_compat(responses_client, name=name, instructions=instructions)

    # Compatibility fallback: certain resources/deployments may reject Responses API versions
    # while still supporting chat completions. Version from AZURE_OPENAI_CHAT_API_VERSION.
    fallback_chat_version = chat_api_version or api_version
    fallback_chat_client: Any = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=resolved_deployment_name,
        api_version=fallback_chat_version,
        api_key=api_key or None,
        credential=credential,
    )
    fallback_agent = _as_agent_compat(fallback_chat_client, name=name, instructions=instructions)

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
