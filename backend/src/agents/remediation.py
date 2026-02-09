"""Remediation Agent for generating fixes for CI/CD failures."""

import logging
from typing import Any

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import (
    Diagnosis,
    FailureType,
    RemediationAction,
    RemediationPlan,
    RemediationResult,
)
from ..tools.fix_generators import FixGenerators
from ..tools.github_tools import GitHubTools
from .base import get_agent_prompt

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
        self._fix_generators = fix_generators or FixGenerators()
        self._credential = azure_credential or DefaultAzureCredential()
        self._settings = get_settings()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the agent instance."""
        if self._agent is None:
            client = AzureOpenAIResponsesClient(
                endpoint=self._settings.azure_openai_endpoint,
                deployment_name=self._settings.azure_openai_deployment_name,
                api_version=self._settings.azure_openai_api_version,
                credential=self._credential,
            )
            
            self._agent = client.create_agent(
                name="Remediation",
                instructions=get_agent_prompt("remediation"),
            )
        
        return self._agent

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
        
        # Check if we should skip remediation
        if diagnosis.confidence < 0.5:
            logger.info(f"Skipping remediation due to low confidence: {diagnosis.confidence}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.SKIP,
                error_message=f"Confidence too low ({diagnosis.confidence:.0%}) for automatic remediation",
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
            return await self._create_pull_request(plan, owner, repo, default_branch)
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

    async def _create_pull_request(
        self,
        plan: RemediationPlan,
        owner: str,
        repo: str,
        base_branch: str,
    ) -> RemediationResult:
        """Create a pull request with the fix.
        
        Args:
            plan: The remediation plan
            owner: Repository owner
            repo: Repository name
            base_branch: Base branch for the PR
            
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
            # Create a new branch
            await self._github_tools.create_branch(
                owner=owner,
                repo=repo,
                branch_name=plan.branch_name,
                from_ref=base_branch,
            )
            logger.info(f"Created branch: {plan.branch_name}")
            
            # Apply file changes
            for change in plan.file_changes:
                file_path = change.get("file", "")
                content = change.get("content", "")
                
                if file_path and content:
                    await self._github_tools.create_or_update_file(
                        owner=owner,
                        repo=repo,
                        path=file_path,
                        content=content,
                        message=f"fix: {plan.description}",
                        branch=plan.branch_name,
                    )
                    logger.info(f"Updated file: {file_path}")
            
            # Create the pull request
            pr_result = await self._github_tools.create_pull_request(
                owner=owner,
                repo=repo,
                title=plan.pr_title or f"[PipelineHealer] {plan.description}",
                body=plan.pr_body or "Automated fix by PipelineHealer",
                head=plan.branch_name,
                base=base_branch,
            )
            
            pr_url = pr_result.get("html_url", "")
            logger.info(f"Created PR: {pr_url}")
            
            return RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_PR,
                pr_url=pr_url,
                details={"pr_number": pr_result.get("number")},
            )
            
        except Exception as e:
            logger.exception(f"Failed to create PR: {e}")
            return RemediationResult(
                success=False,
                action_taken=RemediationAction.CREATE_PR,
                error_message=str(e),
            )

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
            
            issue_result = await self._github_tools.create_issue(
                owner=owner,
                repo=repo,
                title=plan.issue_title or f"[PipelineHealer] CI Failure Analysis",
                body=body,
                labels=["ci-failure", "pipelinehealer"],
            )
            
            issue_url = issue_result.get("html_url", "")
            logger.info(f"Created issue: {issue_url}")
            
            return RemediationResult(
                success=True,
                action_taken=RemediationAction.CREATE_ISSUE,
                issue_url=issue_url,
                details={"issue_number": issue_result.get("number")},
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
