"""Remediation Agent for generating fixes for CI/CD failures."""

import asyncio
import base64
import hashlib
import json
import logging
import re
import time
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    Diagnosis,
    LearningContextMatch,
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
        learning_context: list[LearningContextMatch] | None = None,
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

        applied_learning_match = self._select_applied_learning_match(
            diagnosis,
            plan,
            learning_context,
        )
        if applied_learning_match is not None:
            plan = self._augment_plan_with_applied_learning_guidance(plan, applied_learning_match)
        if learning_context:
            plan = self._augment_plan_with_learning_context(plan, learning_context)

        applied_learning_details = (
            {
                "id": applied_learning_match.id,
                "title": applied_learning_match.title,
                "reason_code": applied_learning_match.reason_code,
                "match_rank": applied_learning_match.match_rank,
                "match_score": applied_learning_match.match_score,
                "verification_pass_rate": applied_learning_match.verification_pass_rate,
                "application_mode": "guidance_section",
                "action_changed": False,
            }
            if applied_learning_match is not None and self._plan_contains_applied_learning_guidance(plan)
            else None
        )

        logger.info(f"Generated remediation plan: {plan.action.value} - {plan.description}")

        if dry_run:
            details: dict[str, Any] = {
                "plan": plan.model_dump(),
                "dry_run": True,
            }
            if applied_learning_details is not None:
                details["applied_learning_context"] = applied_learning_details
            return RemediationResult(
                success=True,
                action_taken=plan.action,
                details=details,
            )

        # Apply the remediation
        try:
            result = await self._apply_remediation(
                plan,
                repository_info,
                workflow_run_id,
            )
            if (
                applied_learning_details is not None
                and self._result_published_applied_learning_guidance(result)
            ):
                result.details["applied_learning_context"] = applied_learning_details
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
                repository_info=repository_info,
            )
        elif plan.action == RemediationAction.CREATE_ISSUE:
            return await self._create_issue(
                plan,
                owner,
                repo,
                workflow_run_id,
                repository_info=repository_info,
            )
        elif plan.action == RemediationAction.RETRY_WORKFLOW:
            return await self._retry_workflow(owner, repo, workflow_run_id)
        elif plan.action == RemediationAction.NOTIFY:
            return await self._create_issue(
                plan,
                owner,
                repo,
                workflow_run_id,
                repository_info=repository_info,
            )
        else:
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.SKIP,
                error_message=f"Unknown action: {plan.action}",
            )

    @staticmethod
    def _render_learning_context_section(matches: list[LearningContextMatch]) -> str:
        """Render a compact advisory section for related active learning artifacts."""
        if not matches:
            return ""
        lines = ["## Related Active Playbooks", ""]
        for match in matches[:3]:
            basis = ", ".join(match.match_basis[:4]) if match.match_basis else "ranked retrieval"
            headline = (
                f"- `{match.id}` {match.title} "
                f"(score {match.match_score:.2f}, rank {match.match_rank})"
            )
            lines.append(headline)
            if match.reason_code:
                lines.append(f"  Reason code: `{match.reason_code}`")
            lines.append(f"  Match basis: {basis}")
            if match.suggested_playbook:
                lines.append(f"  Suggested playbook: {match.suggested_playbook}")
        return "\n".join(lines)

    def _augment_plan_with_learning_context(
        self,
        plan: RemediationPlan,
        learning_context: list[LearningContextMatch],
    ) -> RemediationPlan:
        """Append related active playbooks to operator-facing remediation artifacts."""
        rendered = self._render_learning_context_section(learning_context)
        if not rendered:
            return plan

        updates: dict[str, Any] = {}
        if plan.pr_body:
            updates["pr_body"] = f"{plan.pr_body.rstrip()}\n\n{rendered}\n"
        if plan.issue_body:
            updates["issue_body"] = f"{plan.issue_body.rstrip()}\n\n{rendered}\n"
        if not updates:
            return plan
        return plan.model_copy(update=updates)

    @staticmethod
    def _normalize_learning_reason_code(value: str | None) -> str:
        """Normalize reason codes before comparing diagnosis and learning matches."""
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    def _diagnosis_reason_code(self, diagnosis: Diagnosis) -> str:
        """Extract a stable reason code from diagnosis details when available."""
        details = diagnosis.error_details if isinstance(diagnosis.error_details, dict) else {}
        for raw in (
            details.get("reason_code"),
            details.get("classification_pattern"),
            details.get("classification_signal"),
            details.get("misconfiguration_kind"),
            details.get("resolution_kind"),
            details.get("failure_scope"),
        ):
            normalized = self._normalize_learning_reason_code(
                raw if isinstance(raw, str) else None
            )
            if normalized:
                return normalized
        return ""

    def _select_applied_learning_match(
        self,
        diagnosis: Diagnosis,
        plan: RemediationPlan,
        learning_context: list[LearningContextMatch] | None,
    ) -> LearningContextMatch | None:
        """Promote one strong learning match into bounded remediation guidance."""
        if not learning_context or diagnosis.confidence < 0.5:
            return None
        if not (plan.pr_body or plan.issue_body):
            return None

        top_match = learning_context[0]
        if not str(top_match.suggested_playbook or "").strip():
            return None
        if top_match.match_rank not in {0, 1}:
            return None
        if top_match.match_score < 0.88:
            return None
        if top_match.verification_pass_rate < 0.6:
            return None
        if top_match.failure_type and top_match.failure_type != diagnosis.failure_type:
            return None

        diagnosis_reason_code = self._diagnosis_reason_code(diagnosis)
        match_reason_code = self._normalize_learning_reason_code(top_match.reason_code)
        if diagnosis_reason_code and match_reason_code and diagnosis_reason_code != match_reason_code:
            return None

        return top_match

    @staticmethod
    def _render_applied_learning_guidance(match: LearningContextMatch) -> str:
        """Render the bounded guidance section when one active playbook is promoted."""
        basis = ", ".join(match.match_basis[:4]) if match.match_basis else "ranked retrieval"
        verification_pct = int(round(match.verification_pass_rate * 100))
        lines = [
            "## Applied Learning Guidance",
            "",
            (
                "This remediation plan was refined using one active playbook that matched the "
                "current failure evidence."
            ),
            "",
            f"- Playbook: `{match.id}` {match.title}",
            f"- Match basis: {basis}",
            f"- Match score: {match.match_score:.2f} (rank {match.match_rank})",
            f"- Verification pass rate: {verification_pct}%",
            f"- Observed recurrence count: {match.occurrence_count}",
        ]
        if match.reason_code:
            lines.append(f"- Reason code: `{match.reason_code}`")
        lines.extend(
            [
                "",
                "### Playbook Guidance",
                match.suggested_playbook.strip(),
                "",
                (
                    "This guidance supplements deterministic evidence and did not change the "
                    "selected remediation action on its own."
                ),
            ]
        )
        return "\n".join(lines)

    def _augment_plan_with_applied_learning_guidance(
        self,
        plan: RemediationPlan,
        match: LearningContextMatch,
    ) -> RemediationPlan:
        """Append the promoted learning guidance section to operator-facing artifacts."""
        rendered = self._render_applied_learning_guidance(match)
        updates: dict[str, Any] = {}
        if plan.pr_body:
            updates["pr_body"] = f"{plan.pr_body.rstrip()}\n\n{rendered}\n"
        if plan.issue_body:
            updates["issue_body"] = f"{plan.issue_body.rstrip()}\n\n{rendered}\n"
        if not updates:
            return plan
        return plan.model_copy(update=updates)

    @staticmethod
    def _plan_contains_applied_learning_guidance(plan: RemediationPlan) -> bool:
        """Return whether the rendered plan body includes applied learning guidance."""
        marker = "## Applied Learning Guidance"
        return marker in str(plan.pr_body or "") or marker in str(plan.issue_body or "")

    @staticmethod
    def _result_published_applied_learning_guidance(result: RemediationResult) -> bool:
        """Return whether the final remediation result published a fresh guided artifact."""
        if not result.success:
            return False
        if result.action_taken == RemediationAction.CREATE_PR:
            return result.details.get("reused_existing_pr") is False
        if result.action_taken in {RemediationAction.CREATE_ISSUE, RemediationAction.NOTIFY}:
            return result.details.get("reused_existing_issue") is False
        return False

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
    def _normalize_title_for_signature(title: str) -> str:
        """Normalize issue titles so cross-run dedup ignores noisy counters."""
        normalized = re.sub(r"\s+", " ", str(title or "").strip().lower())
        normalized = re.sub(r"\d+\s+test\(s\)\s+failed", "n tests failed", normalized)
        normalized = re.sub(r"\(\d+\s+issues\)", "(n issues)", normalized)
        normalized = re.sub(r":\s*\d+\s+violation", ": n violation", normalized)
        return normalized

    @staticmethod
    def _signature_for_plan(
        plan: RemediationPlan,
        *,
        workflow_name: str = "",
        head_branch: str = "",
        head_repository: str = "",
    ) -> str:
        """Return a cross-run failure signature (excludes workflow run id)."""
        normalized_workflow_name = (
            re.sub(r"[^a-z0-9_-]+", "-", str(workflow_name or "").strip().lower()) or ""
        )
        normalized_head_branch = (
            re.sub(r"[^a-z0-9_-]+", "-", str(head_branch or "").strip().lower()) or ""
        )
        normalized_head_repository = (
            re.sub(r"[^a-z0-9_./-]+", "-", str(head_repository or "").strip().lower()) or ""
        )
        payload = {
            "action": plan.action.value,
            "branch_name": plan.branch_name or "",
            "workflow_name": normalized_workflow_name,
            "head_branch": normalized_head_branch,
            "head_repository": normalized_head_repository,
            "issue_title": RemediationAgent._normalize_title_for_signature(plan.issue_title or ""),
            "description": plan.description,
            "files": sorted(
                str(change.get("file", "")) for change in plan.file_changes if change.get("file")
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _fingerprint_marker(fingerprint: str) -> str:
        return f"<!-- pipelinehealer:fingerprint:{fingerprint} -->"

    @staticmethod
    def _signature_marker(signature: str) -> str:
        return f"<!-- pipelinehealer:signature:{signature} -->"

    @staticmethod
    def _workflow_run_marker(workflow_run_id: int) -> str:
        return f"<!-- pipelinehealer:workflow-run:{workflow_run_id} -->"

    @staticmethod
    def _workflow_name_marker(workflow_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(workflow_name or "").strip().lower()) or "workflow"
        return f"<!-- pipelinehealer:workflow-name:{normalized} -->"

    @staticmethod
    def _head_branch_marker(head_branch: str) -> str:
        normalized = re.sub(r"[^a-z0-9_./-]+", "-", str(head_branch or "").strip().lower()) or "unknown"
        return f"<!-- pipelinehealer:head-branch:{normalized} -->"

    @staticmethod
    def _head_repository_marker(head_repository: str) -> str:
        normalized = re.sub(r"[^a-z0-9_./-]+", "-", str(head_repository or "").strip().lower()) or "unknown"
        return f"<!-- pipelinehealer:head-repository:{normalized} -->"

    @staticmethod
    def _generated_issue_kind_marker(kind: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(kind).strip().lower()) or "issue"
        return f"<!-- pipelinehealer:generated-issue:{normalized} -->"

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

    async def _find_existing_generated_issue(
        self,
        *,
        owner: str,
        repo: str,
        marker: str,
        workflow_run_id: int,
        kind: str,
        title: str,
        signature_marker: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an existing open generated issue for this workflow run and artifact kind."""
        run_marker = self._workflow_run_marker(workflow_run_id)
        kind_marker = self._generated_issue_kind_marker(kind)
        normalized_title = self._normalize_title_for_signature(title)
        issues = await self._github_tools.list_issues(
            owner=owner,
            repo=repo,
            state="open",
            labels="pipelinehealer",
            per_page=100,
        )
        for issue in issues:
            body = str(issue.get("body", "") or "")
            if marker in body:
                return issue
            if signature_marker and signature_marker in body:
                return issue
            issue_title = self._normalize_title_for_signature(str(issue.get("title", "") or ""))
            if run_marker in body and kind_marker in body and issue_title == normalized_title:
                return issue
        return None

    async def _find_superseded_review_issues(
        self,
        *,
        owner: str,
        repo: str,
        workflow_run_id: int,
        signature: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find open review-only generated issues superseded by a concrete PR."""
        run_marker = self._workflow_run_marker(workflow_run_id)
        kind_marker = self._generated_issue_kind_marker("review")
        signature_marker = self._signature_marker(signature) if signature else None
        issues = await self._github_tools.list_issues(
            owner=owner,
            repo=repo,
            state="open",
            labels="pipelinehealer",
            per_page=100,
        )
        superseded: list[dict[str, Any]] = []
        for issue in issues:
            body = str(issue.get("body", "") or "")
            title = str(issue.get("title", "") or "").lower()
            if "auto-fix tracking" in title:
                continue
            if kind_marker not in body:
                continue
            if run_marker in body:
                superseded.append(issue)
                continue
            if signature_marker and signature_marker in body:
                superseded.append(issue)
        return superseded

    async def _link_generated_issue_to_pull_requests(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        issue_url: str,
        pull_request_numbers: list[int],
    ) -> list[int]:
        """Append deterministic closure references to active PRs for this generated issue."""
        linked: list[int] = []
        marker = f"<!-- pipelinehealer:linked-issue:{issue_number} -->"
        for pr_number in pull_request_numbers:
            try:
                pr = await self._github_tools.get_pull_request(owner, repo, pr_number)
                current_body = str(pr.get("body", "") or "").rstrip()
                if marker in current_body or f"Closes #{issue_number}" in current_body:
                    linked.append(pr_number)
                    continue

                appended = (
                    ("\n\n" if current_body else "")
                    + "PipelineHealer linked issue:\n"
                    + f"Closes #{issue_number}\n"
                    + f"{marker}\n"
                )
                updated_body = f"{current_body}{appended}" if current_body else appended.lstrip()
                await self._github_tools.update_pull_request(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    body=updated_body,
                )
                linked.append(pr_number)
            except Exception as exc:
                logger.warning(
                    "Failed to link generated issue #%s to PR #%s in %s/%s: %s",
                    issue_number,
                    pr_number,
                    owner,
                    repo,
                    exc,
                )

        if linked:
            try:
                rendered = ", ".join(f"#{number}" for number in linked)
                await self._github_tools.add_issue_comment(
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    body=(
                        "PipelineHealer linked this generated issue to active pull request(s): "
                        f"{rendered}.\n\n"
                        f"Issue URL: {issue_url}"
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to comment on linked generated issue #%s in %s/%s: %s",
                    issue_number,
                    owner,
                    repo,
                    exc,
                )

        return linked

    async def _close_superseded_generated_issue(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        pr_number: int,
        pr_url: str,
    ) -> None:
        """Close a stale generated review issue once a concrete PR supersedes it."""
        await self._github_tools.add_issue_comment(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            body=(
                "Superseded by a concrete remediation PR.\n\n"
                f"- PR: #{pr_number} ({pr_url})\n"
                "- Reason: PipelineHealer opened a PR-based fix for the same workflow run."
            ),
        )
        await self._github_tools.update_issue(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            state="closed",
            state_reason="completed",
        )

    async def _close_generated_issue_with_reason(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        reason: str,
    ) -> None:
        """Close a generated issue after writing an operator-visible audit comment."""
        await self._github_tools.add_issue_comment(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            body=reason,
        )
        await self._github_tools.update_issue(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            state="closed",
            state_reason="completed",
        )

    def _artifact_trace_markers(
        self,
        *,
        plan: RemediationPlan,
        workflow_run_id: int,
        repository_info: dict[str, Any] | None,
        kind: str = "review",
    ) -> str:
        """Return HTML markers used for dedup, lifecycle close, and audit traceability."""
        remediation_fp = self._fingerprint_for_plan(plan, workflow_run_id)
        workflow_name = str((repository_info or {}).get("workflow_name") or "").strip()
        head_branch = str((repository_info or {}).get("head_branch") or "").strip()
        head_repository = str(
            (repository_info or {}).get("head_repository_full_name") or ""
        ).strip()
        signature = self._signature_for_plan(
            plan,
            workflow_name=workflow_name,
            head_branch=head_branch,
            head_repository=head_repository,
        )
        markers = [
            self._generated_issue_kind_marker(kind),
            self._workflow_run_marker(workflow_run_id),
            self._fingerprint_marker(remediation_fp),
            self._signature_marker(signature),
        ]
        if workflow_name:
            markers.append(self._workflow_name_marker(workflow_name))
        if head_branch:
            markers.append(self._head_branch_marker(head_branch))
        if head_repository:
            markers.append(self._head_repository_marker(head_repository))
        return "\n".join(markers)

    async def close_issues_on_workflow_success(
        self,
        *,
        owner: str,
        repo: str,
        workflow_name: str,
        head_branch: str | None,
        workflow_run_id: int,
        head_sha: str,
    ) -> dict[str, Any]:
        """Close open review issues when a tracked workflow succeeds."""
        if not self._settings.auto_close_on_workflow_success:
            return {"status": "skipped", "reason": "auto_close_on_workflow_success disabled"}
        if not self._settings.auto_apply_remediation:
            return {"status": "skipped", "reason": "auto_apply_remediation disabled"}

        workflow_marker = self._workflow_name_marker(workflow_name)
        branch_marker = self._head_branch_marker(head_branch) if head_branch else None
        review_kind_marker = self._generated_issue_kind_marker("review")
        closed_issue_numbers: list[int] = []

        issues = await self._github_tools.list_issues(
            owner=owner,
            repo=repo,
            state="open",
            labels="pipelinehealer",
            per_page=100,
        )
        for issue in issues:
            issue_number = issue.get("number")
            if not isinstance(issue_number, int):
                continue
            title = str(issue.get("title", "") or "")
            if "auto-fix tracking" in title.lower():
                continue
            body = str(issue.get("body", "") or "")
            if review_kind_marker not in body:
                continue
            if workflow_marker not in body:
                continue
            if branch_marker and branch_marker not in body:
                continue
            try:
                await self._close_generated_issue_with_reason(
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    reason=(
                        "Closed automatically because the tracked workflow succeeded.\n\n"
                        f"- Workflow: `{workflow_name}`\n"
                        f"- Successful run: #{workflow_run_id}\n"
                        f"- Commit: `{head_sha or 'unknown'}`\n"
                        f"- Branch: `{head_branch or 'unknown'}`"
                    ),
                )
                closed_issue_numbers.append(issue_number)
            except Exception as exc:
                logger.warning(
                    "Failed to auto-close generated issue #%s in %s/%s after success: %s",
                    issue_number,
                    owner,
                    repo,
                    exc,
                )

        return {
            "status": "completed",
            "closed_issue_numbers": closed_issue_numbers,
            "workflow_run_id": workflow_run_id,
        }

    @staticmethod
    def _extract_pr_number(pr: dict[str, Any]) -> int | None:
        raw = pr.get("number")
        return raw if isinstance(raw, int) else None

    @staticmethod
    def _extract_pr_head_sha(pr: dict[str, Any]) -> str:
        head = pr.get("head")
        if isinstance(head, dict):
            return str(head.get("sha") or "").strip()
        return ""

    @staticmethod
    def _extract_pr_node_id(pr: dict[str, Any]) -> str:
        return str(pr.get("node_id") or "").strip()

    def _auto_merge_client_mutation_id(self, workflow_run_id: int, pr_number: int, head_sha: str) -> str:
        """Return a stable GitHub GraphQL mutation id for this remediation PR."""
        suffix = head_sha[:12] if head_sha else "unknown"
        return f"pipelinehealer-run-{workflow_run_id}-pr-{pr_number}-{suffix}"

    async def _comment_auto_merge_status(
        self,
        *,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> None:
        """Best-effort PR comment for visible GitHub-side auto-merge audit."""
        try:
            await self._github_tools.add_issue_comment(
                owner=owner,
                repo=repo,
                issue_number=pr_number,
                body=body,
            )
        except Exception as exc:
            logger.warning(
                "Failed to comment on auto-merge status for PR #%s in %s/%s: %s",
                pr_number,
                owner,
                repo,
                exc,
            )

    async def _refresh_pr_for_auto_merge(
        self,
        *,
        owner: str,
        repo: str,
        pr: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch full PR details when list/create payloads omit merge metadata."""
        pr_number = self._extract_pr_number(pr)
        if pr_number is None:
            return pr
        if self._extract_pr_head_sha(pr) and self._extract_pr_node_id(pr) and "mergeable" in pr:
            return pr
        try:
            return await self._github_tools.get_pull_request(owner, repo, pr_number)
        except Exception as exc:
            logger.warning(
                "Failed to refresh PR #%s before auto-merge in %s/%s: %s",
                pr_number,
                owner,
                repo,
                exc,
            )
            return pr

    async def _enable_github_native_auto_merge(
        self,
        *,
        owner: str,
        repo: str,
        pr: dict[str, Any],
        workflow_run_id: int,
    ) -> dict[str, Any]:
        """Request GitHub native auto-merge for a generated remediation PR."""
        pr_number = self._extract_pr_number(pr)
        head_sha = self._extract_pr_head_sha(pr)
        node_id = self._extract_pr_node_id(pr)
        client_mutation_id = (
            self._auto_merge_client_mutation_id(workflow_run_id, pr_number, head_sha)
            if pr_number is not None
            else ""
        )
        details: dict[str, Any] = {
            "requested": True,
            "strategy": "github_auto_merge",
            "enabled": False,
            "merged": False,
            "pr_number": pr_number,
            "expected_head_oid": head_sha or None,
            "client_mutation_id": client_mutation_id or None,
        }
        if pr_number is None or not node_id:
            details["error"] = "GitHub PR payload did not include a PR number/node id"
            return details

        try:
            result = await self._github_tools.enable_pull_request_auto_merge(
                pull_request_id=node_id,
                expected_head_oid=head_sha or None,
                merge_method="SQUASH",
                client_mutation_id=client_mutation_id,
            )
            details["enabled"] = True
            details["github_result"] = result
            await self._comment_auto_merge_status(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                body=(
                    "PipelineHealer requested GitHub native auto-merge for this remediation PR.\n\n"
                    f"- Source workflow run: https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n"
                    f"- Expected head SHA: `{head_sha or 'unknown'}`\n"
                    f"- Client mutation id: `{client_mutation_id}`"
                ),
            )
        except Exception as exc:
            details["error"] = str(exc)
            logger.warning(
                "Failed to request GitHub native auto-merge for PR #%s in %s/%s: %s",
                pr_number,
                owner,
                repo,
                exc,
            )
        return details

    async def _merge_when_clean(
        self,
        *,
        owner: str,
        repo: str,
        pr: dict[str, Any],
        workflow_run_id: int,
        remediation_fingerprint: str,
    ) -> dict[str, Any]:
        """Poll GitHub until a remediation PR is mergeable and checks are clean, then merge."""
        pr_number = self._extract_pr_number(pr)
        poll_budget = max(0.0, float(getattr(self._settings, "auto_merge_poll_seconds", 0.0) or 0.0))
        require_clean_checks = bool(
            getattr(self._settings, "auto_merge_require_clean_checks", True)
        )
        details: dict[str, Any] = {
            "requested": True,
            "strategy": "merge_when_clean",
            "enabled": False,
            "merged": False,
            "pr_number": pr_number,
            "poll_budget_seconds": poll_budget,
            "require_clean_checks": require_clean_checks,
            "attempts": 0,
        }
        if pr_number is None:
            details["error"] = "GitHub PR payload did not include a PR number"
            return details

        deadline = time.monotonic() + poll_budget
        poll_interval = min(10.0, max(2.0, poll_budget / 12.0)) if poll_budget else 0.0
        last_state: dict[str, Any] = {}

        while True:
            details["attempts"] = int(details["attempts"]) + 1
            current_pr = await self._github_tools.get_pull_request(owner, repo, pr_number)
            head_sha = self._extract_pr_head_sha(current_pr)
            mergeable = current_pr.get("mergeable")
            mergeable_state = str(current_pr.get("mergeable_state") or "").lower()
            is_draft = bool(current_pr.get("draft"))
            state = str(current_pr.get("state") or "").lower()

            check_summary: dict[str, Any] = {
                "state": "not_required",
                "has_checks": False,
            }
            checks_ready = True
            if require_clean_checks:
                if not head_sha:
                    checks_ready = False
                    check_summary = {"state": "missing_head_sha", "has_checks": False}
                else:
                    check_summary = await self._github_tools.get_commit_check_summary(
                        owner,
                        repo,
                        head_sha,
                    )
                    has_checks = bool(check_summary.get("has_checks"))
                    has_successful_check = bool(check_summary.get("successful") or [])
                    if check_summary.get("state") == "success" and has_checks:
                        checks_ready = True
                        check_summary["merge_gate"] = "all_checks_clean"
                    elif mergeable_state == "clean" and has_checks and has_successful_check:
                        checks_ready = True
                        check_summary["merge_gate"] = "github_required_checks_clean"
                        check_summary["optional_failures_ignored"] = list(
                            check_summary.get("failing") or []
                        )
                    else:
                        checks_ready = False

            ready = (
                state == "open"
                and not is_draft
                and mergeable is True
                and mergeable_state in {"clean", "unstable", "has_hooks"}
                and checks_ready
            )
            last_state = {
                "state": state,
                "draft": is_draft,
                "mergeable": mergeable,
                "mergeable_state": mergeable_state,
                "head_sha": head_sha or None,
                "checks": check_summary,
            }
            details["last_state"] = last_state

            if ready:
                merge_result = await self._github_tools.merge_pull_request(
                    owner,
                    repo,
                    pr_number,
                    commit_title=f"fix: merge PipelineHealer remediation #{pr_number}",
                    commit_message=(
                        "Merged automatically by PipelineHealer after GitHub reported "
                        "the remediation PR mergeable and checks clean.\n\n"
                        f"Source workflow run: https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n"
                        f"Remediation fingerprint: {remediation_fingerprint}"
                    ),
                    sha=head_sha or None,
                    merge_method="squash",
                )
                details["merged"] = True
                details["enabled"] = True
                details["merge_result"] = merge_result
                await self._comment_auto_merge_status(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    body=(
                        "PipelineHealer merged this remediation PR after required checks passed.\n\n"
                        f"- Source workflow run: https://github.com/{owner}/{repo}/actions/runs/{workflow_run_id}\n"
                        f"- Head SHA: `{head_sha or 'unknown'}`\n"
                        f"- Remediation fingerprint: `{remediation_fingerprint}`"
                    ),
                )
                return details

            if poll_budget <= 0 or time.monotonic() >= deadline:
                details["error"] = "Timed out waiting for mergeable PR with clean checks"
                logger.info(
                    "Auto-merge wait ended for PR #%s in %s/%s: %s",
                    pr_number,
                    owner,
                    repo,
                    last_state,
                )
                return details

            await asyncio.sleep(poll_interval)

    async def _maybe_auto_merge_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        pr: dict[str, Any],
        workflow_run_id: int,
        remediation_fingerprint: str,
    ) -> dict[str, Any]:
        """Apply the configured auto-merge policy to a PipelineHealer-generated PR."""
        strategy = str(getattr(self._settings, "auto_merge_strategy", "merge_when_clean")).strip().lower()
        if strategy not in {"github_auto_merge", "merge_when_clean"}:
            strategy = "merge_when_clean"
        details: dict[str, Any] = {
            "requested": False,
            "strategy": strategy,
            "enabled": False,
            "merged": False,
        }
        if not bool(getattr(self._settings, "auto_merge_remediation_prs", False)):
            details["reason"] = "auto_merge_remediation_prs=false"
            return details

        try:
            refreshed_pr = await self._refresh_pr_for_auto_merge(owner=owner, repo=repo, pr=pr)
            if strategy == "github_auto_merge":
                return await self._enable_github_native_auto_merge(
                    owner=owner,
                    repo=repo,
                    pr=refreshed_pr,
                    workflow_run_id=workflow_run_id,
                )

            return await self._merge_when_clean(
                owner=owner,
                repo=repo,
                pr=refreshed_pr,
                workflow_run_id=workflow_run_id,
                remediation_fingerprint=remediation_fingerprint,
            )
        except Exception as exc:
            logger.warning(
                "Auto-merge policy failed for remediation PR in %s/%s (run %s): %s",
                owner,
                repo,
                workflow_run_id,
                exc,
            )
            details["requested"] = True
            details["error"] = str(exc)
            return details

    async def _create_pull_request(
        self,
        plan: RemediationPlan,
        owner: str,
        repo: str,
        base_branch: str,
        workflow_run_id: int,
        repository_info: dict[str, Any] | None = None,
    ) -> RemediationResult:
        """Create a pull request with the fix.

        Args:
            plan: The remediation plan
            owner: Repository owner
            repo: Repository name
            base_branch: Base branch for the PR
            workflow_run_id: ID of the workflow run
            repository_info: Optional repository context used for cross-run signatures

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
            workflow_name = str((repository_info or {}).get("workflow_name") or "").strip()
            head_branch = str((repository_info or {}).get("head_branch") or "").strip()
            head_repository = str(
                (repository_info or {}).get("head_repository_full_name") or ""
            ).strip()
            signature = self._signature_for_plan(
                plan,
                workflow_name=workflow_name,
                head_branch=head_branch,
                head_repository=head_repository,
            )
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
                auto_merge = await self._maybe_auto_merge_pull_request(
                    owner=owner,
                    repo=repo,
                    pr=existing_pr,
                    workflow_run_id=workflow_run_id,
                    remediation_fingerprint=remediation_fp,
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
                        "auto_merge": auto_merge,
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
                        auto_merge = await self._maybe_auto_merge_pull_request(
                            owner=owner,
                            repo=repo,
                            pr=existing_pr,
                            workflow_run_id=workflow_run_id,
                            remediation_fingerprint=remediation_fp,
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
                                "auto_merge": auto_merge,
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
            auto_merge = await self._maybe_auto_merge_pull_request(
                owner=owner,
                repo=repo,
                pr=pr_result,
                workflow_run_id=workflow_run_id,
                remediation_fingerprint=remediation_fp,
            )

            superseded_issues = await self._find_superseded_review_issues(
                owner=owner,
                repo=repo,
                workflow_run_id=workflow_run_id,
                signature=signature,
            )
            closed_superseded_issue_numbers: list[int] = []
            for issue in superseded_issues:
                issue_number = issue.get("number")
                if not isinstance(issue_number, int):
                    continue
                if tracking_issue_number is not None and issue_number == tracking_issue_number:
                    continue
                try:
                    await self._close_superseded_generated_issue(
                        owner=owner,
                        repo=repo,
                        issue_number=issue_number,
                        pr_number=int(pr_result.get("number") or 0),
                        pr_url=pr_url,
                    )
                    closed_superseded_issue_numbers.append(issue_number)
                except Exception as exc:
                    logger.warning(
                        "Failed to close superseded generated issue #%s in %s/%s: %s",
                        issue_number,
                        owner,
                        repo,
                        exc,
                    )

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
                    "closed_superseded_issue_numbers": closed_superseded_issue_numbers,
                    "auto_merge": auto_merge,
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
            patch_trace: dict[str, Any] | None = trace_by_file.get(path)
            if patch_trace is not None:
                item["patch_drafting_trace"] = patch_trace
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
        validation_raw = change.get("validation")
        if not isinstance(validation_raw, dict):
            raise ValueError(f"bounded_patch missing validation metadata for {file_path}")
        validation: dict[str, Any] = validation_raw

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
                draft_kind=draft_kind,
                validation=validation,
            )
            trace["outcome"] = "drafted"
            trace["used_fallback"] = False
            return drafted_text if drafted_text.endswith("\n") else f"{drafted_text}\n", trace
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            trace["draft_error"] = str(exc)
            if fallback_content:
                self._validate_bounded_patch_content(
                    file_path=file_path,
                    content=fallback_content,
                    draft_kind=draft_kind,
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
                raise ValueError(
                    "patch draft response is not valid JSON and no JSON object could be extracted"
                ) from None

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
        draft_kind: str,
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
        RemediationAgent._validate_bounded_patch_structure(
            file_path=file_path,
            content=normalized,
            draft_kind=draft_kind,
        )

    @staticmethod
    def _validate_bounded_patch_structure(
        *,
        file_path: str,
        content: str,
        draft_kind: str,
    ) -> None:
        """Apply lightweight structure checks for known bounded draft kinds."""
        if draft_kind != "eslint_flat_config":
            return

        checks = [
            ("export default", "missing `export default`"),
            ("files: [", "missing `files` array"),
            ("languageOptions: {", "missing `languageOptions` block"),
            ('ecmaVersion: "latest"', "missing quoted `ecmaVersion: \"latest\"`"),
            ('sourceType: "module"', "missing quoted `sourceType: \"module\"`"),
            ("rules: {}", "missing empty `rules` object"),
            ("];", "missing config terminator"),
        ]
        missing_reasons = [reason for needle, reason in checks if needle not in content]
        if missing_reasons:
            raise ValueError(
                f"bounded patch for {file_path} failed eslint_flat_config checks: {missing_reasons}"
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
        repository_info: dict[str, Any] | None = None,
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
            remediation_fp = self._fingerprint_for_plan(plan, workflow_run_id)
            fp_marker = self._fingerprint_marker(remediation_fp)
            workflow_name = str((repository_info or {}).get("workflow_name") or "").strip()
            head_branch = str((repository_info or {}).get("head_branch") or "").strip()
            head_repository = str(
                (repository_info or {}).get("head_repository_full_name") or ""
            ).strip()
            signature = self._signature_for_plan(
                plan,
                workflow_name=workflow_name,
                head_branch=head_branch,
                head_repository=head_repository,
            )
            sig_marker = self._signature_marker(signature)
            existing_issue = await self._find_existing_generated_issue(
                owner=owner,
                repo=repo,
                marker=fp_marker,
                workflow_run_id=workflow_run_id,
                kind="review",
                title=plan.issue_title or "[PipelineHealer] CI Failure Analysis",
                signature_marker=sig_marker,
            )
            pull_request_numbers = [
                int(number)
                for number in ((repository_info or {}).get("pull_request_numbers") or [])
                if isinstance(number, int)
            ]
            if existing_issue is not None:
                issue_number = existing_issue.get("number")
                issue_url = str(existing_issue.get("html_url", "") or "")
                reused_issue_linked_pr_numbers: list[int] = []
                if isinstance(issue_number, int) and pull_request_numbers:
                    reused_issue_linked_pr_numbers = await self._link_generated_issue_to_pull_requests(
                        owner=owner,
                        repo=repo,
                        issue_number=issue_number,
                        issue_url=issue_url,
                        pull_request_numbers=pull_request_numbers,
                    )
                return RemediationResult(
                    success=True,
                    action_taken=RemediationAction.CREATE_ISSUE,
                    issue_url=issue_url,
                    details={
                        "issue_number": issue_number,
                        "reused_existing_issue": True,
                        "remediation_fingerprint": remediation_fp,
                        "remediation_signature": signature,
                        "linked_pull_request_numbers": reused_issue_linked_pr_numbers,
                    },
                )

            # Add workflow run link to the issue body
            body = (plan.issue_body or "").rstrip()
            body += (
                "\n\n"
                + self._artifact_trace_markers(
                    plan=plan,
                    workflow_run_id=workflow_run_id,
                    repository_info=repository_info,
                    kind="review",
                )
            )
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
            issue_number = issue_result.get("number")
            linked_pr_numbers: list[int] = []
            if isinstance(issue_number, int) and pull_request_numbers:
                linked_pr_numbers = await self._link_generated_issue_to_pull_requests(
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    issue_url=issue_url,
                    pull_request_numbers=pull_request_numbers,
                )

            return RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                issue_url=issue_url,
                details={
                    "issue_number": issue_number,
                    "includes_proposed_fix": includes_proposed_fix,
                    "not_auto_reason_code": not_auto_reason_code,
                    "not_auto_reason_detail": not_auto_reason_detail,
                    "remediation_fingerprint": remediation_fp,
                    "remediation_signature": signature,
                    "linked_pull_request_numbers": linked_pr_numbers,
                    "reused_existing_issue": False,
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
