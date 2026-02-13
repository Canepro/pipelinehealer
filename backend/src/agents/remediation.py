"""Remediation Agent for generating fixes for CI/CD failures."""

import base64
import json
import logging
import re
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    Diagnosis,
    RemediationAction,
    RemediationPlan,
    RemediationResult,
)
from ..tools.fix_generators import FixGenerators, NotAutoApplyReason
from ..tools.github_tools import GitHubTools
from .base import create_cloud_agent, get_agent_prompt

logger = logging.getLogger(__name__)


class RemediationAgent:
    """Agent for generating and applying fixes for CI/CD failures.

    This agent takes diagnosis results and generates appropriate
    remediation actions (PRs, issues, or workflow retries).
    """

    def __init__(
        self,
        github_tools: GitHubTools,
        fix_generators: FixGenerators | None = None,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the Remediation Agent.

        Args:
            github_tools: GitHub tools for creating PRs/issues
            fix_generators: Fix generators for different failure types
            azure_credential: Azure credential for OpenAI
        """
        self._github_tools = github_tools
        self._credential = azure_credential or DefaultAzureCredential()
        self._settings = get_settings()
        # Default fix generators to settings-driven behavior (safe vs demo).
        self._fix_generators = fix_generators or FixGenerators(heal_mode=self._settings.heal_mode)
        self._agent: Any | None = None

    async def _get_agent(self) -> Any:
        """Get or create the agent instance."""
        if self._agent is None:
            self._agent = create_cloud_agent(
                name="Remediation",
                instructions=get_agent_prompt("remediation"),
                credential=self._credential,
                settings=self._settings,
            )

        return self._agent

    def refresh_runtime_settings(self) -> None:
        """Apply mutable runtime settings without restarting the process."""
        self._settings = get_settings()
        self._fix_generators.set_heal_mode(self._settings.heal_mode)

    async def remediate(
        self,
        diagnosis: Diagnosis,
        repository_info: dict[str, Any],
        workflow_run_id: int,
        dry_run: bool = False,
    ) -> RemediationResult:
        """Generate and apply remediation for a diagnosed failure.

        Args:
            diagnosis: The diagnosis of the failure
            repository_info: Information about the repository
            workflow_run_id: ID of the workflow run
            dry_run: If True, generate plan but don't apply

        Returns:
            Result of the remediation attempt
        """
        logger.info(
            f"Remediating {diagnosis.failure_type.value} failure "
            f"(confidence: {diagnosis.confidence:.0%}, auto-fixable: {diagnosis.is_auto_fixable})"
        )

        # Low-confidence cases are escalated as review-only issues with a proposed fix section.
        if diagnosis.confidence < 0.5:
            logger.info(f"Creating review issue due to low confidence: {diagnosis.confidence}")
            low_conf_plan = self._fix_generators.generate_review_issue(
                diagnosis=diagnosis,
                repository_info=repository_info,
                not_auto_reason=(
                    f"Confidence too low ({diagnosis.confidence:.0%}) for automatic remediation."
                ),
                reason_code=NotAutoApplyReason.LOW_CONFIDENCE,
            )
            if dry_run:
                return RemediationResult(
                    success=True,
                    action_taken=low_conf_plan.action,
                    details={"plan": low_conf_plan.model_dump(), "dry_run": True},
                )
            try:
                return await self._apply_remediation(low_conf_plan, repository_info, workflow_run_id)
            except Exception as e:
                logger.exception(f"Failed to create low-confidence issue: {e}")
                return RemediationResult(
                    success=False,
                    action_taken=RemediationAction.CREATE_ISSUE,
                    error_message=f"Failed to create low-confidence issue: {e}",
                )

        # Generate the remediation plan
        try:
            plan = await self._fix_generators.generate_fix(diagnosis, repository_info)
        except Exception as e:
            logger.error(f"Failed to generate fix plan: {e}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.SKIP,
                error_message=f"Failed to generate fix plan: {e}",
            )

        logger.info(f"Generated remediation plan: {plan.action.value} - {plan.description}")

        if dry_run:
            return RemediationResult(
                success=True,
                action_taken=plan.action,
                details={
                    "plan": plan.model_dump(),
                    "dry_run": True,
                },
            )

        # Apply the remediation
        try:
            result = await self._apply_remediation(plan, repository_info, workflow_run_id)
            return result
        except Exception as e:
            logger.exception(f"Failed to apply remediation: {e}")
            return RemediationResult(
                success=False,
                action_taken=plan.action,
                error_message=f"Failed to apply remediation: {e}",
            )

    async def _apply_remediation(
        self,
        plan: RemediationPlan,
        repository_info: dict[str, Any],
        workflow_run_id: int,
    ) -> RemediationResult:
        """Apply a remediation plan.

        Args:
            plan: The remediation plan to apply
            repository_info: Information about the repository
            workflow_run_id: ID of the workflow run

        Returns:
            Result of the remediation
        """
        owner = repository_info.get("owner", {}).get("login", "")
        repo = repository_info.get("name", "")
        default_branch = repository_info.get("default_branch", "main")

        if plan.action == RemediationAction.CREATE_PR:
            return await self._create_pull_request(
                plan,
                owner,
                repo,
                default_branch,
                workflow_run_id=workflow_run_id,
            )
        elif plan.action == RemediationAction.CREATE_ISSUE:
            return await self._create_issue(plan, owner, repo, workflow_run_id)
        elif plan.action == RemediationAction.RETRY_WORKFLOW:
            return await self._retry_workflow(owner, repo, workflow_run_id)
        elif plan.action == RemediationAction.NOTIFY:
            return await self._create_issue(plan, owner, repo, workflow_run_id)
        else:
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.SKIP,
                error_message=f"Unknown action: {plan.action}",
            )

    def _branch_name_for_run(self, base_branch_name: str, workflow_run_id: int) -> str:
        """Return a stable unique branch name for a workflow run to avoid ref collisions."""
        candidate = f"{base_branch_name}-run-{workflow_run_id}"
        # Keep branch names under common platform limits.
        return candidate[:240]

    async def _create_pull_request(
        self,
        plan: RemediationPlan,
        owner: str,
        repo: str,
        base_branch: str,
        workflow_run_id: int,
    ) -> RemediationResult:
        """Create a pull request with the fix.

        Args:
            plan: The remediation plan
            owner: Repository owner
            repo: Repository name
            base_branch: Base branch for the PR
            workflow_run_id: ID of the workflow run

        Returns:
            Result of the PR creation
        """
        if not plan.branch_name:
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.CREATE_PR,
                error_message="No branch name specified in plan",
            )

        try:
            tracking_issue_number: int | None = None
            tracking_issue_url: str | None = None
            run_branch_name = self._branch_name_for_run(plan.branch_name, workflow_run_id)

            # Materialize structured file changes into full file contents.
            try:
                rendered_changes = await self._render_file_changes(
                    owner=owner,
                    repo=repo,
                    base_ref=base_branch,
                    file_changes=plan.file_changes,
                )
            except Exception as e:
                logger.warning(f"Failed to render file changes; falling back to issue: {e}")
                return await self._create_auto_fix_blocked_issue(
                    owner=owner,
                    repo=repo,
                    workflow_run_id=workflow_run_id,
                    plan=plan,
                    reason=f"Failed to render file changes: {e}",
                )
            if not rendered_changes:
                # Don't hard-fail the pipeline if our structured changes couldn't be applied.
                # Fall back to an issue so the dashboard still shows something actionable.
                logger.warning("No applicable file changes to commit; falling back to issue")
                return await self._create_auto_fix_blocked_issue(
                    owner=owner,
                    repo=repo,
                    workflow_run_id=workflow_run_id,
                    plan=plan,
                    reason="No applicable file changes to commit",
                )

            # Create a new branch
            await self._github_tools.create_branch(
                owner=owner,
                repo=repo,
                branch_name=run_branch_name,
                from_ref=base_branch,
            )
            logger.info(f"Created branch: {run_branch_name}")

            # Apply file changes
            for change in rendered_changes:
                file_path = change.get("file", "")
                content = change.get("content", "")

                if file_path and content:
                    await self._github_tools.create_or_update_file(
                        owner=owner,
                        repo=repo,
                        path=file_path,
                        content=content,
                        message=f"fix: {plan.description}",
                        branch=run_branch_name,
                    )
                    logger.info(f"Updated file: {file_path}")

            # Create tracking issue only after we know we can produce a real PR.
            if self._settings.auto_create_tracking_issue_for_prs:
                try:
                    issue_title = f"[PipelineHealer] Auto-fix: {plan.pr_title or plan.description}"
                    issue_body = (
                        "## Auto-fix Tracking\n\n"
                        "PipelineHealer is generating an automated fix PR for this CI failure.\n\n"
                        f"**Workflow Run:** https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n\n"
                        "When the PR merges, GitHub will auto-close this issue.\n\n"
                        "### Proposed Fix\n\n"
                        f"{plan.pr_body or plan.description}\n"
                    )
                    issue_result = await self._github_tools.create_issue(
                        owner=owner,
                        repo=repo,
                        title=issue_title,
                        body=issue_body,
                        labels=["ci-failure", "pipelinehealer"],
                    )
                    tracking_issue_number = issue_result.get("number")
                    tracking_issue_url = issue_result.get("html_url", "")
                    logger.info(f"Created tracking issue: {tracking_issue_url}")
                except Exception as e:
                    logger.warning(f"Failed to create tracking issue (continuing): {e}")

            # Create the pull request
            pr_body = plan.pr_body or "Automated fix by PipelineHealer"
            if tracking_issue_number:
                pr_body = f"{pr_body}\n\nCloses #{tracking_issue_number}\n"

            pr_result = await self._github_tools.create_pull_request(
                owner=owner,
                repo=repo,
                title=plan.pr_title or f"[PipelineHealer] {plan.description}",
                body=pr_body,
                head=run_branch_name,
                base=base_branch,
            )

            pr_url = pr_result.get("html_url", "")
            logger.info(f"Created PR: {pr_url}")

            return RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_PR,
                pr_url=pr_url,
                issue_url=tracking_issue_url,
                details={
                    "pr_number": pr_result.get("number"),
                    "tracking_issue_number": tracking_issue_number,
                    "branch_name": run_branch_name,
                },
            )

        except Exception as e:
            logger.exception(f"Failed to create PR: {e}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.CREATE_PR,
                error_message=str(e),
            )

    async def _create_auto_fix_blocked_issue(
        self,
        owner: str,
        repo: str,
        workflow_run_id: int,
        plan: RemediationPlan,
        reason: str,
    ) -> RemediationResult:
        """Create a fallback issue when PR-style remediation can't be applied safely."""
        fallback_issue_body = (
            "## Auto-fix Could Not Be Applied\n\n"
            "PipelineHealer planned to open an auto-fix PR, but it could not safely apply changes.\n\n"
            f"**Reason:** {reason}\n\n"
            f"**Workflow Run:** https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n\n"
            "### Planned Fix\n\n"
            f"{plan.pr_body or plan.description}\n\n"
            "### Notes\n\n"
            "- This commonly happens when a workflow/file path is different than expected.\n"
            "- Consider adding a placeholder config in the workflow so PipelineHealer can patch it deterministically.\n"
        )
        issue_result = await self._github_tools.create_issue(
            owner=owner,
            repo=repo,
            title=f"[PipelineHealer] Auto-fix blocked: {plan.pr_title or plan.description}",
            body=fallback_issue_body,
            labels=["ci-failure", "pipelinehealer"],
        )
        return RemediationResult(
            success=True,
            action_taken=RemediationAction.CREATE_ISSUE,
            issue_url=issue_result.get("html_url", ""),
            details={
                "issue_number": issue_result.get("number"),
                "fallback_from": "create_pr",
                "reason": reason,
            },
        )

    async def _render_file_changes(
        self,
        owner: str,
        repo: str,
        base_ref: str,
        file_changes: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Convert structured change requests into concrete {file, content} updates.

        Supports:
        - {file, content}: raw content replacement
        - type=json_update: update a dotted JSON path (e.g. dependencies.foo)
        - type=line_update: regex replace a matching line, or append if missing
        """
        rendered_by_file: dict[str, str] = {}
        render_order: list[str] = []
        working_files: dict[str, str] = {}
        working_exists: dict[str, bool] = {}

        for change in file_changes:
            # Support both:
            # - {"file": "..."} (single file)
            # - {"files": ["a", "b", ...]} (first existing file wins)
            file_candidates: list[str] = []
            files_value = change.get("files")
            if isinstance(files_value, list):
                file_candidates = [str(p) for p in files_value if p]
            file_path = str(change.get("file") or "")
            if file_path:
                file_candidates = [file_path]
            if not file_candidates:
                continue

            # Determine which file to apply the change to.
            require_existing = bool(change.get("require_existing", False))
            selected_path: str | None = None
            selected_text: str = ""
            selected_exists: bool = False
            for candidate in file_candidates:
                if candidate in working_files:
                    selected_path = candidate
                    selected_text = working_files[candidate]
                    selected_exists = working_exists.get(candidate, True)
                    break
                text, exists = await self._get_text_file_if_exists(owner, repo, candidate, ref=base_ref)
                if exists:
                    selected_path = candidate
                    selected_text = text
                    selected_exists = True
                    break
                if not require_existing and selected_path is None:
                    # If we allow creating files, tentatively choose the first candidate.
                    selected_path = candidate
                    selected_text = text
                    selected_exists = False
            if selected_path is None:
                continue

            if "content" in change and change.get("content") is not None:
                rendered_by_file[selected_path] = str(change["content"])
                if selected_path not in render_order:
                    render_order.append(selected_path)
                working_files[selected_path] = str(change["content"])
                working_exists[selected_path] = True
                continue

            change_type = str(change.get("type") or "")
            if not change_type:
                continue

            # Use the selected file content (already fetched above).
            current_text = selected_text
            if require_existing and not selected_exists:
                # Explicitly skip when the caller requires an existing file.
                continue

            if change_type == "json_update":
                dotted_path = str(change.get("path") or "")
                value = change.get("value")
                if not dotted_path:
                    raise ValueError(f"json_update missing path for {selected_path}")

                doc = json.loads(current_text) if current_text.strip() else {}
                if not isinstance(doc, dict):
                    raise ValueError(f"json_update expected object at root for {selected_path}")

                parts = dotted_path.split(".")
                cursor: Any = doc
                for key in parts[:-1]:
                    if key not in cursor or not isinstance(cursor[key], dict):
                        cursor[key] = {}
                    cursor = cursor[key]
                cursor[parts[-1]] = value

                new_text = json.dumps(doc, indent=2, sort_keys=False) + "\n"
                rendered_by_file[selected_path] = new_text
                if selected_path not in render_order:
                    render_order.append(selected_path)
                working_files[selected_path] = new_text
                working_exists[selected_path] = True

            elif change_type == "line_update":
                pattern = str(change.get("pattern") or "")
                replacement = str(change.get("replacement") or "")
                if not pattern or not replacement:
                    raise ValueError(f"line_update missing pattern/replacement for {selected_path}")

                lines = current_text.splitlines(keepends=False)
                out: list[str] = []
                matched = False
                all_matches = bool(change.get("all_matches", False))
                append_if_missing = bool(change.get("append_if_missing", True))
                rx = re.compile(pattern)
                for line in lines:
                    if matched and not all_matches:
                        out.append(line)
                        continue
                    if rx.search(line):
                        out.append(rx.sub(replacement, line))
                        matched = True
                        continue
                    out.append(line)
                if (not matched) and append_if_missing:
                    out.append(replacement)

                new_text = "\n".join(out).rstrip("\n") + "\n"
                rendered_by_file[selected_path] = new_text
                if selected_path not in render_order:
                    render_order.append(selected_path)
                working_files[selected_path] = new_text
                working_exists[selected_path] = True

            else:
                logger.warning(
                    "Unsupported file change type '%s' for path '%s'; skipping change.",
                    change_type,
                    selected_path,
                )
                continue

        return [{"file": path, "content": rendered_by_file[path]} for path in render_order]

    async def _get_text_file_if_exists(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> tuple[str, bool]:
        """Fetch a repo file and decode it as UTF-8 text; return (text, exists)."""
        try:
            data = await self._github_tools.get_file_contents(owner=owner, repo=repo, path=path, ref=ref)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return "", False
            raise
        encoding = data.get("encoding")
        content = data.get("content", "")
        if encoding != "base64":
            raise ValueError(f"Unsupported encoding for {path}: {encoding}")
        raw = base64.b64decode(content)
        return raw.decode("utf-8"), True

    async def _get_text_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        """Fetch a repo file and decode it as UTF-8 text."""
        try:
            data = await self._github_tools.get_file_contents(
                owner=owner, repo=repo, path=path, ref=ref
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ""
            raise
        encoding = data.get("encoding")
        content = data.get("content", "")
        if encoding != "base64":
            raise ValueError(f"Unsupported encoding for {path}: {encoding}")
        raw = base64.b64decode(content)
        return raw.decode("utf-8")

    async def _create_issue(
        self,
        plan: RemediationPlan,
        owner: str,
        repo: str,
        workflow_run_id: int,
    ) -> RemediationResult:
        """Create an issue with the diagnosis details.

        Args:
            plan: The remediation plan
            owner: Repository owner
            repo: Repository name
            workflow_run_id: ID of the workflow run

        Returns:
            Result of the issue creation
        """
        try:
            # Add workflow run link to the issue body
            body = plan.issue_body or ""
            body += f"\n\n**Workflow Run:** https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}"
            includes_proposed_fix = "### Proposed Fix (For Review Only)" in body
            reason_code_match = re.search(r"Reason Code:\s*([A-Z_]+)", body)
            not_auto_reason_code = reason_code_match.group(1) if reason_code_match else None
            reason_detail_match = re.search(r"Detail:\s*(.+)", body)
            not_auto_reason_detail = reason_detail_match.group(1).strip() if reason_detail_match else None

            issue_result = await self._github_tools.create_issue(
                owner=owner,
                repo=repo,
                title=plan.issue_title or "[PipelineHealer] CI Failure Analysis",
                body=body,
                labels=["ci-failure", "pipelinehealer"],
            )

            issue_url = issue_result.get("html_url", "")
            logger.info(f"Created issue: {issue_url}")

            return RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                issue_url=issue_url,
                details={
                    "issue_number": issue_result.get("number"),
                    "includes_proposed_fix": includes_proposed_fix,
                    "not_auto_reason_code": not_auto_reason_code,
                    "not_auto_reason_detail": not_auto_reason_detail,
                },
            )

        except Exception as e:
            logger.exception(f"Failed to create issue: {e}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.CREATE_ISSUE,
                error_message=str(e),
            )

    async def _retry_workflow(
        self,
        owner: str,
        repo: str,
        workflow_run_id: int,
    ) -> RemediationResult:
        """Retry the failed workflow.

        Args:
            owner: Repository owner
            repo: Repository name
            workflow_run_id: ID of the workflow run

        Returns:
            Result of the retry attempt
        """
        try:
            await self._github_tools.rerun_failed_jobs(owner, repo, workflow_run_id)
            logger.info(f"Triggered workflow retry for run {workflow_run_id}")

            return RemediationResult(
                success=True,
                action_taken=RemediationAction.RETRY_WORKFLOW,
                details={"workflow_run_id": workflow_run_id, "action": "rerun_failed_jobs"},
            )

        except Exception as e:
            logger.exception(f"Failed to retry workflow: {e}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.RETRY_WORKFLOW,
                error_message=str(e),
            )
