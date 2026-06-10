"""Local Codex App Server execution for delegated handoff sessions.

When a handoff session targets ``codex_app_server`` and no remote receiver URL
is configured, this module runs the session goal on the in-built Codex App
Server runtime: it clones the activity's repository into a scratch workspace,
runs one workspace-write agent turn, publishes any resulting changes as a
GitHub pull request, and records progress events on the handoff session so the
work is visible from the activity timeline.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from ..config import get_settings
from ..llm.codex_app_server import CodexAppServerAgent, is_loopback_websocket_host
from ..models import (
    HANDOFF_EVENT_STATUS,
    ActivityRecord,
    AgentHandoffAuditEntry,
    AgentHandoffMode,
    AgentHandoffStatus,
    ExternalAgentTarget,
    HandoffEventType,
    HandoffGitHubRefs,
    HandoffMessage,
    HandoffMessageDirection,
    HandoffSession,
    HandoffSessionStatus,
    utcnow,
)
from ..tools.github_tools import GitHubTools

logger = logging.getLogger(__name__)

LOCAL_HANDOFF_ACTOR = "codex_app_server:local"
AUTO_HANDOFF_POLICY = "auto_failed_remediation"

_MAX_AUDIT_ENTRIES = 30
_MAX_PUBLISHED_FILES = 50
_MAX_EVENT_BODY_CHARS = 20000

_EXECUTOR_INSTRUCTIONS = (
    "You are PipelineHealer's delegated fix agent. You are given a local clone "
    "of a repository whose CI pipeline failed. Apply the smallest safe change "
    "that addresses the stated goal by editing files in the workspace. Do not "
    "run package installs or network commands. Finish with a short summary of "
    "what you changed and why, or state that no change is needed."
)

_background_tasks: set[asyncio.Task[None]] = set()
_semaphore: asyncio.Semaphore | None = None
_semaphore_limit = 0


def local_codex_execution_available(settings: Any) -> bool:
    """Return whether local Codex execution may serve codex_app_server sessions.

    Any configured remote receiver wins, including the legacy webhook URL that
    _target_handoff_url falls back to for the codex_app_server target.
    """
    if not bool(getattr(settings, "agent_handoff_local_codex_enabled", False)):
        return False
    remote_url = (
        str(getattr(settings, "codex_app_server_handoff_url", "") or "").strip()
        or str(getattr(settings, "agent_handoff_webhook_url", "") or "").strip()
    )
    return not remote_url


def schedule_local_codex_handoff(
    *,
    session: HandoffSession,
    activity: ActivityRecord,
    context: str,
    storage: Any,
) -> None:
    """Run a handoff session on the local Codex runtime as a background task."""
    task = asyncio.get_running_loop().create_task(
        execute_local_codex_handoff(
            session=session,
            activity=activity,
            context=context,
            storage=storage,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def execute_local_codex_handoff(
    *,
    session: HandoffSession,
    activity: ActivityRecord,
    context: str,
    storage: Any,
) -> None:
    """Execute one handoff session end to end on the local Codex runtime."""
    settings = get_settings()
    async with _get_semaphore(int(settings.agent_handoff_local_max_concurrent)):
        try:
            await _execute(
                session=session,
                activity=activity,
                context=context,
                storage=storage,
                settings=settings,
            )
        except Exception as exc:
            logger.exception("Local Codex handoff session %s failed", session.id)
            with suppress(Exception):
                await _record_event(
                    storage=storage,
                    session=session,
                    activity_id=activity.id,
                    event_type=HandoffEventType.FAILED,
                    body=f"Local Codex execution failed: {_scrub(str(exc))}",
                )


async def create_auto_local_handoff(
    *,
    activity: ActivityRecord,
    storage: Any,
) -> HandoffSession | None:
    """Create and schedule an automatic local handoff session for a failed activity.

    Returns the created session, or None when one already exists for this
    activity or local execution is unavailable.
    """
    settings = get_settings()
    if not (
        settings.agent_handoff_enabled
        and settings.agent_handoff_auto_local
        and local_codex_execution_available(settings)
    ):
        return None
    existing = await storage.list_handoff_sessions_for_activity(activity.id)
    if any(item.policy_decision == AUTO_HANDOFF_POLICY for item in existing):
        return None

    goal = (
        f"Fix the CI failure in {activity.repository_name} "
        f"({activity.workflow_name} run {activity.workflow_run_id})"
    )
    context = _auto_handoff_context(activity)
    session_id = str(uuid4())
    session = HandoffSession(
        id=session_id,
        activity_id=activity.id,
        target=ExternalAgentTarget.CODEX_APP_SERVER,
        status=HandoffSessionStatus.QUEUED,
        goal=goal,
        created_by="auto:orchestrator",
        delivery_id=f"handoff-session:{activity.id}:{session_id}",
        github=HandoffGitHubRefs(
            repository=activity.repository_name,
            run_id=activity.workflow_run_id,
        ),
        labels=[
            "pipelinehealer:detected",
            "pipelinehealer:delegated",
            "pipelinehealer:external-agent",
            "agent:codex",
            "pipelinehealer:auto",
        ],
        policy_decision=AUTO_HANDOFF_POLICY,
        context_sha256=hashlib.sha256(context.encode("utf-8")).hexdigest(),
        context_preview=re.sub(r"\s+", " ", context).strip()[:280],
        metadata={"execution": "local_codex", "trigger": AUTO_HANDOFF_POLICY},
    )
    await storage.upsert_handoff_session(session)
    await storage.append_handoff_message(
        HandoffMessage(
            session_id=session.id,
            event_type=HandoffEventType.DELEGATED,
            direction=HandoffMessageDirection.OUTBOUND,
            actor=session.created_by or "auto:orchestrator",
            body=goal,
            github=session.github,
            labels=session.labels,
        )
    )
    await _append_activity_audit(
        storage=storage,
        activity_id=activity.id,
        session=session,
        status=AgentHandoffStatus.QUEUED,
    )
    schedule_local_codex_handoff(
        session=session,
        activity=activity,
        context=context,
        storage=storage,
    )
    logger.info(
        "Scheduled auto local Codex handoff session %s for activity %s",
        session.id,
        activity.id,
    )
    return session


@dataclass
class _Workspace:
    root: Path
    repo_path: Path
    base_branch: str
    requested_branch: str = ""
    branch_fallback: bool = False

    def fallback_note(self) -> str:
        if not self.branch_fallback:
            return ""
        return (
            f"Requested branch '{self.requested_branch}' was not available; "
            f"this fix targets '{self.base_branch}' instead."
        )


@dataclass
class _ChangeSet:
    upserts: list[tuple[str, str]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.upserts or self.deleted or self.skipped)


def _check_transport_supports_local_workspace(settings: Any) -> None:
    """Reject transports where the app-server cannot see this host's filesystem."""
    transport = str(
        getattr(settings, "codex_app_server_transport", "stdio") or "stdio"
    ).strip().lower()
    if transport != "websocket":
        return
    ws_url = str(getattr(settings, "codex_app_server_ws_url", "") or "").strip()
    host = urlparse(ws_url).hostname or ""
    if not is_loopback_websocket_host(host):
        raise RuntimeError(
            "Local Codex handoff execution requires a Codex App Server that shares "
            "this host's filesystem; use stdio transport or a loopback WebSocket URL"
        )


async def _execute(
    *,
    session: HandoffSession,
    activity: ActivityRecord,
    context: str,
    storage: Any,
    settings: Any,
) -> None:
    _check_transport_supports_local_workspace(settings)
    await _record_event(
        storage=storage,
        session=session,
        activity_id=activity.id,
        event_type=HandoffEventType.STARTED_WORK,
        body="Local Codex App Server execution started",
    )
    workspace = await _prepare_workspace(activity=activity, session=session, settings=settings)
    try:
        agent = _create_agent(settings)
        timeout_seconds = max(
            60.0, int(settings.agent_handoff_local_codex_timeout_ms) / 1000.0
        )
        summary = await agent.run_agentic(
            _build_prompt(activity=activity, session=session, context=context, workspace=workspace),
            cwd=str(workspace.repo_path),
            timeout_seconds=timeout_seconds,
        )
        changes = await _collect_changes(workspace.repo_path)
        pr_url: str | None = None
        if changes.upserts and settings.agent_handoff_local_codex_open_pr:
            pr_url = await _publish_changes(
                activity=activity,
                session=session,
                workspace=workspace,
                changes=changes,
                summary=summary,
            )
            session.github.pr_url = pr_url
            await _record_event(
                storage=storage,
                session=session,
                activity_id=activity.id,
                event_type=HandoffEventType.PR_OPENED,
                body=f"Opened pull request {pr_url}",
            )
        await _record_event(
            storage=storage,
            session=session,
            activity_id=activity.id,
            event_type=HandoffEventType.COMPLETED,
            body=_completion_body(
                summary=summary,
                changes=changes,
                pr_url=pr_url,
                branch_note=workspace.fallback_note(),
            ),
        )
    finally:
        _cleanup_workspace(workspace)


def _create_agent(settings: Any) -> CodexAppServerAgent:
    return CodexAppServerAgent(settings=settings, instructions=_EXECUTOR_INSTRUCTIONS)


def _get_semaphore(limit: int) -> asyncio.Semaphore:
    global _semaphore, _semaphore_limit
    if _semaphore is None or _semaphore_limit != limit:
        _semaphore = asyncio.Semaphore(max(1, limit))
        _semaphore_limit = limit
    return _semaphore


def _github_token(settings: Any) -> str:
    return (
        str(getattr(settings, "github_personal_access_token", "") or "").strip()
        or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    )


def _scrub(text: str) -> str:
    """Remove credentials from text destined for stored events or logs."""
    settings = get_settings()
    for token in (
        _github_token(settings),
        os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
    ):
        if token:
            text = text.replace(token, "[REDACTED]")
    text = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "[REDACTED_GITHUB_TOKEN]", text)
    return re.sub(r"x-access-token:[^@\s]+@", "x-access-token:[REDACTED]@", text)


async def _run_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _prepare_workspace(
    *,
    activity: ActivityRecord,
    session: HandoffSession,
    settings: Any,
) -> _Workspace:
    root_setting = str(
        getattr(settings, "agent_handoff_local_codex_workspace_root", "") or ""
    ).strip()
    base_dir = Path(root_setting) if root_setting else Path(tempfile.gettempdir())
    root = base_dir / f"ph-handoff-{session.id[:8]}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    repo_path = root / "repo"

    token = _github_token(settings)
    full_name = activity.repository_name.strip()
    if "/" not in full_name:
        raise RuntimeError(f"Activity repository '{full_name}' is not an owner/repo name")
    clone_url = (
        f"https://x-access-token:{token}@github.com/{full_name}.git"
        if token
        else f"https://github.com/{full_name}.git"
    )
    branch = str(activity.source_metadata.get("branch") or "").strip()
    clone_args = ["clone", "--depth", "50"]
    if branch:
        clone_args += ["--branch", branch]
    clone_args += [clone_url, str(repo_path)]
    code, _, stderr = await _run_git(clone_args)
    branch_fallback = False
    if code != 0 and branch:
        # The recorded branch may have been deleted since the run failed. Fall
        # back to the default branch, but mark it so the session events and PR
        # body state the retarget instead of hiding it.
        logger.info(
            "Clone of branch %r failed for session %s; retrying default branch",
            branch,
            session.id,
        )
        with suppress(Exception):
            shutil.rmtree(repo_path)
        code, _, stderr = await _run_git(
            ["clone", "--depth", "50", clone_url, str(repo_path)]
        )
        branch_fallback = code == 0
    if code != 0:
        _cleanup_root(root)
        raise RuntimeError(f"git clone failed: {_scrub(stderr.strip())}")

    code, stdout, stderr = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if code != 0:
        _cleanup_root(root)
        raise RuntimeError(f"git rev-parse failed: {_scrub(stderr.strip())}")
    return _Workspace(
        root=root,
        repo_path=repo_path,
        base_branch=stdout.strip() or "main",
        requested_branch=branch,
        branch_fallback=branch_fallback,
    )


def _cleanup_workspace(workspace: _Workspace) -> None:
    _cleanup_root(workspace.root)


def _cleanup_root(root: Path) -> None:
    with suppress(Exception):
        shutil.rmtree(root)


async def _collect_changes(repo_path: Path) -> _ChangeSet:
    code, stdout, stderr = await _run_git(
        ["status", "--porcelain=v1", "-uall"], cwd=repo_path
    )
    if code != 0:
        raise RuntimeError(f"git status failed: {_scrub(stderr.strip())}")

    changes = _ChangeSet()
    for line in stdout.splitlines():
        if len(line) < 4:
            continue
        status, raw_path = line[:2], line[3:].strip()
        if " -> " in raw_path:
            old_path, raw_path = raw_path.split(" -> ", 1)
            changes.deleted.append(old_path.strip().strip('"'))
        path = raw_path.strip('"')
        if "D" in status:
            changes.deleted.append(path)
            continue
        absolute = repo_path / path
        if not absolute.is_file():
            continue
        if len(changes.upserts) >= _MAX_PUBLISHED_FILES:
            changes.skipped.append(path)
            continue
        try:
            changes.upserts.append((path, absolute.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            changes.skipped.append(path)
    return changes


def _build_prompt(
    *,
    activity: ActivityRecord,
    session: HandoffSession,
    context: str,
    workspace: _Workspace,
) -> str:
    diagnosis = activity.diagnosis
    sections = [
        f"Repository: {activity.repository_name} (branch {workspace.base_branch})",
        f"Failing workflow: {activity.workflow_name} (run {activity.workflow_run_id})",
        f"Goal: {session.goal}",
    ]
    if diagnosis is not None:
        if diagnosis.root_cause:
            sections.append(f"Diagnosed root cause: {diagnosis.root_cause}")
        if diagnosis.suggested_fix:
            sections.append(f"Suggested fix: {diagnosis.suggested_fix}")
    if context.strip():
        sections.append(f"Additional context:\n{context.strip()}")
    sections.append(
        "Apply the fix by editing files in the current workspace, then summarize "
        "your changes."
    )
    return "\n\n".join(sections)


async def _publish_changes(
    *,
    activity: ActivityRecord,
    session: HandoffSession,
    workspace: _Workspace,
    changes: _ChangeSet,
    summary: str,
) -> str:
    owner, repo = activity.repository_name.split("/", 1)
    branch_name = f"pipelinehealer/codex-handoff-{session.id[:8]}"
    github = GitHubTools()
    try:
        await github.create_branch(owner, repo, branch_name, from_ref=workspace.base_branch)
        for path, content in changes.upserts:
            await github.create_or_update_file(
                owner,
                repo,
                path,
                content,
                message=f"fix: {session.goal[:60]} (PipelineHealer handoff)",
                branch=branch_name,
            )
        body_lines = [
            "Automated fix produced by the PipelineHealer local Codex App Server handoff.",
            "",
            f"Goal: {session.goal}",
            f"Handoff session: {session.id}",
            f"Activity: {session.activity_id}",
        ]
        if workspace.branch_fallback:
            body_lines += ["", workspace.fallback_note()]
        if summary.strip():
            body_lines += ["", "Agent summary:", _scrub(summary.strip())[:4000]]
        if changes.deleted or changes.skipped:
            body_lines.append("")
            if changes.deleted:
                body_lines.append(
                    "Deletions are not published automatically: " + ", ".join(changes.deleted[:10])
                )
            if changes.skipped:
                body_lines.append(
                    "Skipped (binary or over file cap): " + ", ".join(changes.skipped[:10])
                )
        pr = await github.create_pull_request(
            owner,
            repo,
            title=f"fix: {session.goal[:80]}",
            body="\n".join(body_lines),
            head=branch_name,
            base=workspace.base_branch,
        )
        pr_url = str(pr.get("html_url") or "").strip()
        if not pr_url:
            raise RuntimeError("GitHub did not return a pull request URL")
        return pr_url
    finally:
        with suppress(Exception):
            await github.close()


def _completion_body(
    *,
    summary: str,
    changes: _ChangeSet,
    pr_url: str | None,
    branch_note: str = "",
) -> str:
    if pr_url:
        lead = f"Completed with changes; pull request opened: {pr_url}"
    elif changes.upserts:
        lead = (
            f"Completed with {len(changes.upserts)} changed file(s); "
            "pull request publishing is disabled"
        )
    elif changes:
        lead = "Completed; only unpublishable changes were produced (deletions or binary files)"
    else:
        lead = "Completed without file changes"
    body = lead
    if branch_note:
        body += f"\n\n{branch_note}"
    if summary.strip():
        body += f"\n\nAgent summary:\n{_scrub(summary.strip())}"
    return body[:_MAX_EVENT_BODY_CHARS]


async def _record_event(
    *,
    storage: Any,
    session: HandoffSession,
    activity_id: str,
    event_type: HandoffEventType,
    body: str,
) -> None:
    next_status = HANDOFF_EVENT_STATUS.get(event_type)
    if next_status is not None:
        session.status = next_status
    session.updated_at = utcnow()
    message = HandoffMessage(
        session_id=session.id,
        event_type=event_type,
        direction=HandoffMessageDirection.INTERNAL,
        actor=LOCAL_HANDOFF_ACTOR,
        body=body[:_MAX_EVENT_BODY_CHARS],
        github=session.github.model_copy(deep=True),
        labels=list(session.labels),
    )
    await storage.upsert_handoff_session(session)
    await storage.append_handoff_message(message)
    audit_status = (
        AgentHandoffStatus.FAILED
        if session.status == HandoffSessionStatus.FAILED
        else AgentHandoffStatus.QUEUED
    )
    await _append_activity_audit(
        storage=storage,
        activity_id=activity_id,
        session=session,
        status=audit_status,
        error=body[:280] if audit_status == AgentHandoffStatus.FAILED else None,
    )


async def _append_activity_audit(
    *,
    storage: Any,
    activity_id: str,
    session: HandoffSession,
    status: AgentHandoffStatus,
    error: str | None = None,
) -> None:
    activity = await storage.get_activity(activity_id)
    if activity is None:
        return
    activity.agent_handoff_audit.append(
        AgentHandoffAuditEntry(
            status=status,
            mode=AgentHandoffMode.LOCAL,
            actor=LOCAL_HANDOFF_ACTOR,
            request_id=session.request_id,
            context_chars=len(session.context_preview),
            context_sha256=session.context_sha256,
            context_preview=session.context_preview,
            delivery_id=session.delivery_id,
            destination_host="local",
            error=error,
        )
    )
    activity.agent_handoff_audit = activity.agent_handoff_audit[-_MAX_AUDIT_ENTRIES:]
    await storage.update_activity(activity)


def _auto_handoff_context(activity: ActivityRecord) -> str:
    lines = []
    if activity.failure_type is not None:
        lines.append(f"Failure type: {activity.failure_type.value}")
    diagnosis = activity.diagnosis
    if diagnosis is not None:
        if diagnosis.root_cause:
            lines.append(f"Root cause: {diagnosis.root_cause}")
        if diagnosis.suggested_fix:
            lines.append(f"Suggested fix: {diagnosis.suggested_fix}")
    remediation = activity.remediation_result
    if remediation is not None and remediation.error_message:
        lines.append(f"Remediation error: {remediation.error_message}")
    if activity.error:
        lines.append(f"Activity error: {activity.error}")
    return "\n".join(lines)
