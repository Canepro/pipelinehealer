"""GitHub Tools for PipelineHealer agents using GitHub MCP Server."""

import logging
import os
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class GitHubTools:
    """Tools for interacting with GitHub via the GitHub MCP Server or REST API.
    
    This class provides methods that can be used as agent tools for:
    - Fetching workflow run information
    - Getting job logs
    - Creating pull requests
    - Creating issues
    - Managing repository files
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ):
        """Initialize GitHub tools.
        
        Args:
            token: GitHub personal access token or app token
            base_url: GitHub API base URL
        """
        self._token = token or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # Workflow Run Tools
    # =========================================================================

    async def get_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, Any]:
        """Get details of a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Workflow run details
        """
        client = await self._get_client()
        response = await client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    async def get_workflow_jobs(
        self,
        owner: str,
        repo: str,
        run_id: int,
        filter: str = "all",
    ) -> list[dict[str, Any]]:
        """Get jobs for a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            filter: Filter jobs (latest, all)
            
        Returns:
            List of workflow jobs
        """
        client = await self._get_client()
        response = await client.get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            params={"filter": filter},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("jobs", [])

    async def get_job_logs(
        self,
        owner: str,
        repo: str,
        job_id: int,
    ) -> str:
        """Get logs for a specific job.
        
        Args:
            owner: Repository owner
            repo: Repository name
            job_id: Job ID
            
        Returns:
            Job logs as text
        """
        client = await self._get_client()
        response = await client.get(
            f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    async def get_failed_jobs_logs(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, str]:
        """Get logs for all failed jobs in a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Dictionary mapping job name to logs
        """
        jobs = await self.get_workflow_jobs(owner, repo, run_id)
        failed_jobs = [j for j in jobs if j.get("conclusion") == "failure"]
        
        logs: dict[str, str] = {}
        for job in failed_jobs:
            job_id = job["id"]
            job_name = job["name"]
            try:
                job_logs = await self.get_job_logs(owner, repo, job_id)
                logs[job_name] = job_logs
            except Exception as e:
                logger.error(f"Failed to get logs for job {job_name}: {e}")
                logs[job_name] = f"Error fetching logs: {e}"
        
        return logs

    # =========================================================================
    # Repository Content Tools
    # =========================================================================

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Get contents of a file from a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to the file
            ref: Git reference (branch, tag, commit)
            
        Returns:
            File contents and metadata
        """
        client = await self._get_client()
        params = {}
        if ref:
            params["ref"] = ref
        
        response = await client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_repository_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """Get the file tree of a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            tree_sha: Tree SHA or ref
            recursive: Whether to get recursive tree
            
        Returns:
            List of tree entries
        """
        client = await self._get_client()
        params = {"recursive": "1"} if recursive else {}
        
        response = await client.get(
            f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("tree", [])

    # =========================================================================
    # Branch and PR Tools
    # =========================================================================

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        from_ref: str = "HEAD",
    ) -> dict[str, Any]:
        """Create a new branch.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch_name: Name for the new branch
            from_ref: Reference to branch from
            
        Returns:
            Created reference info
        """
        client = await self._get_client()
        
        # Get the SHA of the source ref
        ref_response = await client.get(f"/repos/{owner}/{repo}/git/ref/heads/{from_ref}")
        if ref_response.status_code == 404:
            # Try as a commit SHA
            commit_response = await client.get(f"/repos/{owner}/{repo}/commits/{from_ref}")
            commit_response.raise_for_status()
            sha = commit_response.json()["sha"]
        else:
            ref_response.raise_for_status()
            sha = ref_response.json()["object"]["sha"]
        
        # Create the new branch
        response = await client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha,
            },
        )
        response.raise_for_status()
        return response.json()

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to the file
            content: File content (will be base64 encoded)
            message: Commit message
            branch: Branch to commit to
            sha: SHA of the file to update (required for updates)
            
        Returns:
            Commit info
        """
        import base64
        
        client = await self._get_client()
        
        # If sha not provided, try to get it
        if sha is None:
            try:
                existing = await self.get_file_contents(owner, repo, path, ref=branch)
                sha = existing.get("sha")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise
        
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        
        response = await client.put(
            f"/repos/{owner}/{repo}/contents/{path}",
            json=body,
        )
        response.raise_for_status()
        return response.json()

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            body: PR description
            head: Head branch
            base: Base branch
            draft: Whether to create as draft
            
        Returns:
            Created PR info
        """
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            },
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Issue Tools
    # =========================================================================

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an issue.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body
            labels: Labels to apply
            assignees: Users to assign
            
        Returns:
            Created issue info
        """
        client = await self._get_client()
        
        json_body: dict[str, Any] = {
            "title": title,
            "body": body,
        }
        if labels:
            json_body["labels"] = labels
        if assignees:
            json_body["assignees"] = assignees
        
        response = await client.post(
            f"/repos/{owner}/{repo}/issues",
            json=json_body,
        )
        response.raise_for_status()
        return response.json()

    async def add_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue or PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue or PR number
            body: Comment body
            
        Returns:
            Created comment info
        """
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Workflow Re-run Tools
    # =========================================================================

    async def rerun_workflow(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, Any]:
        """Re-run a workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Empty dict on success
        """
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun",
        )
        response.raise_for_status()
        return {}

    async def rerun_failed_jobs(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> dict[str, Any]:
        """Re-run only failed jobs in a workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Empty dict on success
        """
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
        )
        response.raise_for_status()
        return {}


# Tool function wrappers for agent framework integration
def create_github_tool_functions(github_tools: GitHubTools) -> dict[str, Any]:
    """Create tool functions for use with agent framework.
    
    Args:
        github_tools: GitHubTools instance
        
    Returns:
        Dictionary of tool functions
    """
    return {
        "get_workflow_run": github_tools.get_workflow_run,
        "get_workflow_jobs": github_tools.get_workflow_jobs,
        "get_job_logs": github_tools.get_job_logs,
        "get_failed_jobs_logs": github_tools.get_failed_jobs_logs,
        "get_file_contents": github_tools.get_file_contents,
        "get_repository_tree": github_tools.get_repository_tree,
        "create_branch": github_tools.create_branch,
        "create_or_update_file": github_tools.create_or_update_file,
        "create_pull_request": github_tools.create_pull_request,
        "create_issue": github_tools.create_issue,
        "add_issue_comment": github_tools.add_issue_comment,
        "rerun_workflow": github_tools.rerun_workflow,
        "rerun_failed_jobs": github_tools.rerun_failed_jobs,
    }
