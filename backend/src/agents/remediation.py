"""Remediation Agent for generating fixes for CI/CD failures."""

import base64
import hashlib
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
        self._patch_drafting_agent: Any | None = None

    async def _get_agent(self) -> Any:
        """Get or create the agent instance."""
        if self._agent is None:
            self._agent = create_cloud_agent(
                name="Remediation",
                instructions=get_agent_prompt("remediation"),
                credential=self._credential,
                task="remediation",
                settings=self._settings,
            )

        return self._agent

    async def _get_patch_drafting_agent(self) -> Any:
        """Get or create the bounded patch drafting agent instance."""
        if self._patch_drafting_agent is None:
            self._patch_drafting_agent = create_cloud_agent(
                name="PatchDrafting",
                instructions=get_agent_prompt("patch_drafting"),
                credential=self._credential,
                task="patch_drafting",
                settings=self._settings,
            )

        return self._patch_drafting_agent

    def refresh_runtime_settings(self) -> None:
        """Apply mutable runtime settings without restarting the process."""
        self._settings = get_settings()
        self._fix_generators.set_heal_mode(self._settings.heal_mode)
        self._agent = None
        self._patch_drafting_agent = None

    @staticmethod
    def _extract_github_error_message(response: httpx.Response) -> str:
        """Return a concise GitHub API error message from a failed response."""
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        text = response.text.strip()
        return text or "GitHub API request failed"

    def _classify_output_artifact_exception(self, exc: Exception) -> dict[str, Any] | None:
        """Classify expected artifact-publication failures as non-fatal outcomes."""
        if not isinstance(exc, httpx.HTTPStatusError):
            return None
        response = exc.response
        request = exc.request
        if response is None:
            return None

        status_code = response.status_code
        endpoint = str(request.url.path if request is not None else "").lower()
        message = self._extract_github_error_message(response)
        message_l = message.lower()

        if status_code == 410 and endpoint.endswith("/issues"):
            return {
                "reason_code": "OUTPUT_ISSUES_DISABLED",
                "reason_detail": (
                    "Repository has GitHub Issues disabled; PipelineHealer completed diagnosis "
                    "but could not publish an issue artifact."
                ),
                "github_http_status": status_code,
                "github_endpoint": endpoint,
                "github_message": message,
            }

        if (
            endpoint.endswith("/pulls")
            and status_code in {410, 422}
            and "pull request" in message_l
            and "disabled" in message_l
        ):
            return {
                "reason_code": "OUTPUT_PULL_REQUESTS_DISABLED",
                "reason_detail": (
                    "Repository pull requests are disabled; PipelineHealer completed diagnosis "
                    "but could not publish a pull request artifact."
                ),
                "github_http_status": status_code,
                "github_endpoint": endpoint,
                "github_message": message,
            }

        if status_code == 403 and ("archived" in message_l or "read-only" in message_l):
            return {
                "reason_code": "OUTPUT_REPOSITORY_READ_ONLY",
                "reason_detail": (
                    "Repository is archived/read-only; PipelineHealer completed diagnosis "
                    "but cannot publish PR/issue artifacts."
                ),
                "github_http_status": status_code,
                "github_endpoint": endpoint,
                "github_message": message,
            }

        return None

    def _build_output_unavailable_result(
        self,
        *,
        attempted_action: RemediationAction,
        classification: dict[str, Any],
        extra_details: dict[str, Any] | None = None,
    ) -> RemediationResult:
        """Return a successful SKIP result for output-channel constraints."""
        details: dict[str, Any] = {
            "attempted_action": attempted_action.value,
            **classification,
        }
        if extra_details:
            details.update(extra_details)
        return RemediationResult(
            success=True,
            action_taken=RemediationAction.SKIP,
            details=details,
        )

    def _is_action_enabled(self, action: RemediationAction) -> bool:
        """Return whether *action* is currently allowed by runtime settings."""
        if action == RemediationAction.CREATE_PR:
            return bool(self._settings.auto_create_pr)
        if action in {RemediationAction.CREATE_ISSUE, RemediationAction.NOTIFY}:
            return bool(self._settings.auto_create_issue)
        if action == RemediationAction.RETRY_WORKFLOW:
            return bool(self._settings.auto_retry_workflow)
        return True

    def _build_action_disabled_result(self, *, action: RemediationAction) -> RemediationResult:
        """Return a consistent skip result when an action is policy-disabled."""
        if action == RemediationAction.CREATE_PR:
            reason_code = "ACTION_DISABLED_CREATE_PR"
            detail = (
                "PR publishing is disabled by runtime policy "
                "(auto_create_pr=false)."
            )
        elif action in {RemediationAction.CREATE_ISSUE, RemediationAction.NOTIFY}:
            reason_code = "ACTION_DISABLED_CREATE_ISSUE"
            detail = (
                "Issue publishing is disabled by runtime policy "
                "(auto_create_issue=false)."
            )
        elif action == RemediationAction.RETRY_WORKFLOW:
            reason_code = "ACTION_DISABLED_RETRY_WORKFLOW"
            detail = (
                "Workflow retries are disabled by runtime policy "
                "(auto_retry_workflow=false)."
            )
        else:
            reason_code = "ACTION_DISABLED_POLICY"
            detail = "Action is disabled by runtime policy."

        return RemediationResult(
            success=True,
            action_taken=RemediationAction.SKIP,
            details={
                "attempted_action": action.value,
                "reason_code": reason_code,
                "reason_detail": detail,
            },
        )

    def _is_jenkins_bridge_issue_only(self, repository_info: dict[str, Any]) -> bool:
        """Return True when Jenkins bridge flow should stay issue-first by default."""
        source_selection_path = str(repository_info.get("source_selection_path") or "").strip().lower()
        if source_selection_path != "jenkins_bridge":
            return False
        return not (self._settings.auto_create_pr and self._settings.jenkins_bridge_allow_pr)

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

        if plan.action == RemediationAction.CREATE_PR and self._is_jenkins_bridge_issue_only(
            repository_info
        ):
            logger.info(
                "Converting Jenkins bridge PR remediation to review issue "
                "(requires AUTO_CREATE_PR=true and JENKINS_BRIDGE_ALLOW_PR=true)"
            )
            plan = self._fix_generators.generate_review_issue(
                diagnosis=diagnosis,
                repository_info=repository_info,
                not_auto_reason=(
                    "Jenkins bridge PR publishing requires both AUTO_CREATE_PR=true and "
                    "JENKINS_BRIDGE_ALLOW_PR=true."
                ),
                reason_code=NotAutoApplyReason.SAFETY_BOUND,
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

        if not self._is_action_enabled(plan.action):
            logger.info(
                "Skipping remediation action %s for %s/%s due to runtime policy",
                plan.action.value,
                owner,
                repo,
            )
            return self._build_action_disabled_result(action=plan.action)

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

    @staticmethod
    def _fingerprint_for_plan(plan: RemediationPlan, workflow_run_id: int) -> str:
        """Return a stable remediation fingerprint for find-or-create behavior."""
        payload = {
            "run_id": workflow_run_id,
            "action": plan.action.value,
            "branch_name": plan.branch_name or "",
            "pr_title": plan.pr_title or "",
            "issue_title": plan.issue_title or "",
            "description": plan.description,
            "files": sorted(str(change.get("file", "")) for change in plan.file_changes if change.get("file")),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _fingerprint_marker(fingerprint: str) -> str:
        return f"<!-- pipelinehealer:fingerprint:{fingerprint} -->"

    @staticmethod
    def _extract_patch_drafting_trace(rendered_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract bounded patch trace records from rendered file changes."""
        traces: list[dict[str, Any]] = []
        for change in rendered_changes:
            trace = change.get("patch_drafting_trace")
            if isinstance(trace, dict):
                traces.append(trace)
        return traces

    @staticmethod
    def _branch_suffix(base_branch_name: str, attempt: int) -> str:
        """Generate collision-safe branch suffix while staying under common limits."""
        if attempt <= 1:
            return base_branch_name
        suffix = f"-r{attempt}"
        max_base = max(1, 240 - len(suffix))
        return f"{base_branch_name[:max_base]}{suffix}"

    @staticmethod
    def _is_ref_exists_conflict(exc: Exception) -> bool:
        """True when GitHub reports branch ref already exists (422 git/refs)."""
        if not isinstance(exc, httpx.HTTPStatusError):
            return False
        response = exc.response
        request = exc.request
        if response is None:
            return False
        endpoint = str(request.url.path if request is not None else "").lower()
        if response.status_code != 422 or not endpoint.endswith("/git/refs"):
            return False
        try:
            message = str(response.json().get("message", "")).lower()
        except Exception:
            message = response.text.lower()
        return "reference already exists" in message

    async def _find_existing_open_pr(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        marker: str,
        expected_files: set[str],
    ) -> dict[str, Any] | None:
        """Find an existing open PR for this remediation fingerprint/branch."""
        prs = await self._github_tools.list_pull_requests(
            owner=owner,
            repo=repo,
            state="open",
            head=f"{owner}:{head_branch}",
            per_page=20,
        )
        if not prs:
            prs = await self._github_tools.list_pull_requests(
                owner=owner,
                repo=repo,
                state="open",
                per_page=50,
            )

        for pr in prs:
            body = str(pr.get("body", "") or "")
            head = pr.get("head") or {}
            ref = str(head.get("ref", "")) if isinstance(head, dict) else ""
            if ref and ref != head_branch and marker not in body:
                continue

            if expected_files and isinstance(pr.get("number"), int):
                try:
                    changed_files = await self._github_tools.get_pull_request_files(
                        owner=owner,
                        repo=repo,
                        pr_number=int(pr["number"]),
                    )
                    pr_paths = {str(item.get("filename", "")) for item in changed_files}
                    if not (pr_paths & expected_files):
                        continue
                except Exception:
                    if marker not in body:
                        continue

            return pr
        return None

    async def _find_existing_tracking_issue(
        self,
        *,
        owner: str,
        repo: str,
        marker: str,
    ) -> dict[str, Any] | None:
        """Find an existing open tracking issue by fingerprint marker."""
        issues = await self._github_tools.list_issues(
            owner=owner,
            repo=repo,
            state="open",
            labels="pipelinehealer",
            per_page=100,
        )
        for issue in issues:
            body = str(issue.get("body", "") or "")
            title = str(issue.get("title", "") or "").lower()
            if marker in body and "auto-fix tracking" in title:
                return issue
        return None

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
            base_run_branch_name = self._branch_name_for_run(plan.branch_name, workflow_run_id)
            remediation_fp = self._fingerprint_for_plan(plan, workflow_run_id)
            fp_marker = self._fingerprint_marker(remediation_fp)
            expected_files = {
                str(change.get("file", ""))
                for change in plan.file_changes
                if isinstance(change, dict) and change.get("file")
            }

            existing_pr = await self._find_existing_open_pr(
                owner=owner,
                repo=repo,
                head_branch=base_run_branch_name,
                marker=fp_marker,
                expected_files=expected_files,
            )
            if existing_pr is not None:
                existing_issue = await self._find_existing_tracking_issue(
                    owner=owner,
                    repo=repo,
                    marker=fp_marker,
                )
                logger.info(
                    "Reusing existing remediation PR #%s for run %s (%s/%s)",
                    existing_pr.get("number"),
                    workflow_run_id,
                    owner,
                    repo,
                )
                return RemediationResult(
                    success=True,
                    action_taken=RemediationAction.CREATE_PR,
                    pr_url=str(existing_pr.get("html_url", "") or ""),
                    issue_url=(
                        str(existing_issue.get("html_url", "") or "")
                        if existing_issue is not None
                        else None
                    ),
                    details={
                        "pr_number": existing_pr.get("number"),
                        "tracking_issue_number": (
                            existing_issue.get("number") if existing_issue is not None else None
                        ),
                        "branch_name": str(
                            (existing_pr.get("head") or {}).get("ref", base_run_branch_name)
                        ),
                        "reused_existing_pr": True,
                        "remediation_fingerprint": remediation_fp,
                    },
                )

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
            patch_drafting_trace = self._extract_patch_drafting_trace(rendered_changes)

            run_branch_name: str | None = None
            for attempt in range(1, 5):
                candidate_branch_name = self._branch_suffix(base_run_branch_name, attempt)
                try:
                    await self._github_tools.create_branch(
                        owner=owner,
                        repo=repo,
                        branch_name=candidate_branch_name,
                        from_ref=base_branch,
                    )
                    run_branch_name = candidate_branch_name
                    logger.info(f"Created branch: {run_branch_name}")
                    break
                except Exception as e:
                    if not self._is_ref_exists_conflict(e):
                        raise
                    existing_pr = await self._find_existing_open_pr(
                        owner=owner,
                        repo=repo,
                        head_branch=candidate_branch_name,
                        marker=fp_marker,
                        expected_files=expected_files,
                    )
                    if existing_pr is not None:
                        existing_issue = await self._find_existing_tracking_issue(
                            owner=owner,
                            repo=repo,
                            marker=fp_marker,
                        )
                        logger.info(
                            "Ref collision resolved by reusing PR #%s on branch %s",
                            existing_pr.get("number"),
                            candidate_branch_name,
                        )
                        return RemediationResult(
                            success=True,
                            action_taken=RemediationAction.CREATE_PR,
                            pr_url=str(existing_pr.get("html_url", "") or ""),
                            issue_url=(
                                str(existing_issue.get("html_url", "") or "")
                                if existing_issue is not None
                                else None
                            ),
                            details={
                                "pr_number": existing_pr.get("number"),
                                "tracking_issue_number": (
                                    existing_issue.get("number")
                                    if existing_issue is not None
                                    else None
                                ),
                                "branch_name": str(
                                    (existing_pr.get("head") or {}).get(
                                        "ref",
                                        candidate_branch_name,
                                    )
                                ),
                                "reused_existing_pr": True,
                                "remediation_fingerprint": remediation_fp,
                            },
                        )
                    logger.info(
                        "Branch %s already exists for run %s; trying suffix attempt %s",
                        candidate_branch_name,
                        workflow_run_id,
                        attempt + 1,
                    )
            if run_branch_name is None:
                return RemediationResult(
                    success=False,
                    action_taken=RemediationAction.CREATE_PR,
                    error_message=(
                        "Unable to allocate remediation branch after repeated ref collisions"
                    ),
                    details={"remediation_fingerprint": remediation_fp},
                )

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
            if self._settings.auto_create_tracking_issue_for_prs and self._settings.auto_create_issue:
                try:
                    issue_title = f"[PipelineHealer] Auto-fix: {plan.pr_title or plan.description}"
                    issue_body = (
                        "## Auto-fix Tracking\n\n"
                        "PipelineHealer is generating an automated fix PR for this CI failure.\n\n"
                        f"**Workflow Run:** https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n\n"
                        "When the PR merges, GitHub will auto-close this issue.\n\n"
                        "### Proposed Fix\n\n"
                        f"{plan.pr_body or plan.description}\n\n"
                        f"{fp_marker}\n"
                    )
                    existing_tracking_issue = await self._find_existing_tracking_issue(
                        owner=owner,
                        repo=repo,
                        marker=fp_marker,
                    )
                    if existing_tracking_issue is not None:
                        issue_number_raw = existing_tracking_issue.get("number")
                        if isinstance(issue_number_raw, int):
                            tracking_issue_number = issue_number_raw
                        tracking_issue_url = str(existing_tracking_issue.get("html_url", ""))
                        logger.info(f"Reusing tracking issue: {tracking_issue_url}")
                    else:
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
            elif self._settings.auto_create_tracking_issue_for_prs and not self._settings.auto_create_issue:
                logger.info(
                    "Skipping tracking issue creation for %s/%s because auto_create_issue=false",
                    owner,
                    repo,
                )

            # Create the pull request
            pr_body = plan.pr_body or "Automated fix by PipelineHealer"
            if tracking_issue_number:
                pr_body = f"{pr_body}\n\nCloses #{tracking_issue_number}\n"
            pr_body = f"{pr_body}\n\n{fp_marker}\n"

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
                    "reused_existing_pr": False,
                    "remediation_fingerprint": remediation_fp,
                    "patch_drafting_trace": patch_drafting_trace,
                },
            )

        except Exception as e:
            classified = self._classify_output_artifact_exception(e)
            if classified is not None:
                logger.warning(
                    "PR artifact unavailable for %s/%s (run %s): %s",
                    owner,
                    repo,
                    workflow_run_id,
                    classified["reason_code"],
                )
                return self._build_output_unavailable_result(
                    attempted_action=RemediationAction.CREATE_PR,
                    classification=classified,
                )
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
        if not self._settings.auto_create_issue:
            return self._build_action_disabled_result(action=RemediationAction.CREATE_ISSUE)

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
        try:
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
        except Exception as e:
            classified = self._classify_output_artifact_exception(e)
            if classified is not None:
                logger.warning(
                    "Fallback issue artifact unavailable for %s/%s (run %s): %s",
                    owner,
                    repo,
                    workflow_run_id,
                    classified["reason_code"],
                )
                return self._build_output_unavailable_result(
                    attempted_action=RemediationAction.CREATE_ISSUE,
                    classification=classified,
                    extra_details={
                        "fallback_from": "create_pr",
                        "fallback_reason": reason,
                    },
                )
            raise

    async def _render_file_changes(
        self,
        owner: str,
        repo: str,
        base_ref: str,
        file_changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert structured change requests into concrete {file, content} updates.

        Supports:
        - {file, content}: raw content replacement
        - type=json_update: update a dotted JSON path (e.g. dependencies.foo)
        - type=line_update: regex replace a matching line, or append if missing
        - type=bounded_patch: bounded AI-assisted draft with validation and deterministic fallback
        """
        rendered_by_file: dict[str, str] = {}
        trace_by_file: dict[str, dict[str, Any]] = {}
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

            elif change_type == "bounded_patch":
                new_text, trace = await self._render_bounded_patch_change(
                    file_path=selected_path,
                    current_text=current_text,
                    change=change,
                )
                rendered_by_file[selected_path] = new_text
                trace_by_file[selected_path] = trace
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

        rendered_output: list[dict[str, Any]] = []
        for path in render_order:
            item: dict[str, Any] = {"file": path, "content": rendered_by_file[path]}
            trace = trace_by_file.get(path)
            if trace is not None:
                item["patch_drafting_trace"] = trace
            rendered_output.append(item)
        return rendered_output

    async def _render_bounded_patch_change(
        self,
        *,
        file_path: str,
        current_text: str,
        change: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Render one bounded patch change with validation and deterministic fallback."""
        instructions = str(change.get("instructions") or "").strip()
        if not instructions:
            raise ValueError(f"bounded_patch missing instructions for {file_path}")

        draft_kind = str(change.get("draft_kind") or "bounded_patch").strip() or "bounded_patch"
        fallback_content = str(change.get("fallback_content") or "")
        validation = change.get("validation")
        if not isinstance(validation, dict):
            raise ValueError(f"bounded_patch missing validation metadata for {file_path}")

        trace: dict[str, Any] = {
            "file": file_path,
            "task": "patch_drafting",
            "draft_kind": draft_kind,
            "validation": {
                "must_contain": list(validation.get("must_contain") or []),
                "max_bytes": validation.get("max_bytes"),
            },
            "outcome": "not_attempted",
        }

        try:
            agent = await self._get_patch_drafting_agent()
            response = await agent.run(
                self._build_bounded_patch_prompt(
                    file_path=file_path,
                    current_text=current_text,
                    instructions=instructions,
                    validation=validation,
                )
            )
            drafted_text = self._extract_bounded_patch_content(str(response or ""))
            self._validate_bounded_patch_content(
                file_path=file_path,
                content=drafted_text,
                validation=validation,
            )
            trace["outcome"] = "drafted"
            trace["used_fallback"] = False
            return drafted_text if drafted_text.endswith("\n") else f"{drafted_text}\n", trace
        except Exception as exc:
            trace["draft_error"] = str(exc)
            if fallback_content:
                self._validate_bounded_patch_content(
                    file_path=file_path,
                    content=fallback_content,
                    validation=validation,
                )
                trace["outcome"] = "fallback_content"
                trace["used_fallback"] = True
                return (
                    fallback_content if fallback_content.endswith("\n") else f"{fallback_content}\n",
                    trace,
                )
            trace["outcome"] = "validation_failed"
            raise ValueError(f"bounded_patch failed for {file_path}: {exc}") from exc

    @staticmethod
    def _build_bounded_patch_prompt(
        *,
        file_path: str,
        current_text: str,
        instructions: str,
        validation: dict[str, Any],
    ) -> str:
        """Build a constrained patch-drafting prompt for one file."""
        must_contain = [str(item).strip() for item in validation.get("must_contain", []) if str(item).strip()]
        max_bytes = validation.get("max_bytes")
        current_block = current_text if current_text.strip() else "<new file>"
        return (
            "Draft the full contents for exactly one repository file.\n\n"
            f"Target file: {file_path}\n"
            "Edit mode: bounded single-file draft\n\n"
            "Instructions:\n"
            f"{instructions}\n\n"
            "Validation requirements:\n"
            f"- Required substrings: {must_contain or ['<none>']}\n"
            f"- Max bytes: {max_bytes if max_bytes is not None else 'unspecified'}\n\n"
            "Current file contents:\n"
            f"{current_block}\n\n"
            'Return JSON only: {"content":"<full file contents>"}'
        )

    @staticmethod
    def _extract_bounded_patch_content(response: str) -> str:
        """Extract full-file content from a bounded patch drafting response."""
        cleaned = response.strip()
        if not cleaned:
            raise ValueError("empty patch draft response")

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                payload = json.loads(cleaned[start : end + 1])
            else:
                return cleaned

        if not isinstance(payload, dict):
            raise ValueError("patch draft response must be a JSON object")

        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("patch draft response missing non-empty content")
        return content

    @staticmethod
    def _validate_bounded_patch_content(
        *,
        file_path: str,
        content: str,
        validation: dict[str, Any],
    ) -> None:
        """Validate bounded patch output before it is written to the repo."""
        normalized = content if content.endswith("\n") else f"{content}\n"
        max_bytes = validation.get("max_bytes")
        if isinstance(max_bytes, int) and max_bytes > 0:
            size = len(normalized.encode("utf-8"))
            if size > max_bytes:
                raise ValueError(
                    f"bounded patch for {file_path} exceeds max_bytes ({size} > {max_bytes})"
                )

        required_substrings = [
            str(item).strip() for item in validation.get("must_contain", []) if str(item).strip()
        ]
        missing = [item for item in required_substrings if item not in normalized]
        if missing:
            raise ValueError(
                f"bounded patch for {file_path} is missing required substrings: {missing}"
            )

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
            classified = self._classify_output_artifact_exception(e)
            if classified is not None:
                logger.warning(
                    "Issue artifact unavailable for %s/%s (run %s): %s",
                    owner,
                    repo,
                    workflow_run_id,
                    classified["reason_code"],
                )
                return self._build_output_unavailable_result(
                    attempted_action=RemediationAction.CREATE_ISSUE,
                    classification=classified,
                )
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
