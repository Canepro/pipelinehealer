"""GitHub Tools for PipelineHealer agents using GitHub MCP Server."""

import asyncio
import logging
import os
import random
from typing import Any, cast

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
        settings = get_settings()
        self._settings = settings
        self._token = (
            token
            or settings.github_personal_access_token
            or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        )
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None
        self._max_retries = max(0, settings.github_api_max_retries)
        self._retry_base_seconds = max(0.0, settings.github_api_retry_base_seconds)
        self._retry_max_seconds = max(0.0, settings.github_api_retry_max_seconds)

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

    def _retry_delay_seconds(self, attempt: int, retry_after: str | None) -> float:
        """Calculate retry delay with optional Retry-After support."""
        if retry_after:
            try:
                parsed: float = float(retry_after)
                if parsed >= 0:
                    if self._retry_max_seconds > 0:
                        max_delay: float = float(self._retry_max_seconds)
                        return parsed if parsed <= max_delay else max_delay
                    return parsed
            except ValueError:
                pass

        base = self._retry_base_seconds * (2**attempt)
        jitter = random.uniform(0.0, max(0.05, base * 0.2))
        delay: float = base + jitter
        if self._retry_max_seconds > 0:
            backoff_cap: float = float(self._retry_max_seconds)
            return delay if delay <= backoff_cap else backoff_cap
        return delay

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make an HTTP request with retry/backoff for transient GitHub errors."""
        client = await self._get_client()

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise

                delay = self._retry_delay_seconds(attempt, None)
                logger.warning(
                    "GitHub API %s %s failed (%s). Retrying in %.2fs (%d/%d)...",
                    method,
                    url,
                    type(exc).__name__,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay_seconds(attempt, response.headers.get("Retry-After"))
                logger.warning(
                    "GitHub API %s %s returned %s. Retrying in %.2fs (%d/%d)...",
                    method,
                    url,
                    response.status_code,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response

        # The loop always returns or raises above.
        raise RuntimeError("unreachable")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def refresh_runtime_settings(self) -> None:
        """Refresh runtime retry policy from the cached settings object."""
        settings = get_settings()
        self._settings = settings
        self._max_retries = max(0, settings.github_api_max_retries)
        self._retry_base_seconds = max(0.0, settings.github_api_retry_base_seconds)
        self._retry_max_seconds = max(0.0, settings.github_api_retry_max_seconds)

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
        response = await self._request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        return cast(dict[str, Any], response.json())

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
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            params={"filter": filter},
        )
        data = cast(dict[str, Any], response.json())
        return cast(list[dict[str, Any]], data.get("jobs", []))

    async def list_repo_workflows(
        self,
        owner: str,
        repo: str,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List workflows configured for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            per_page: Maximum workflows to fetch

        Returns:
            List of workflow descriptor objects
        """
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/workflows",
            params={"per_page": max(1, min(per_page, 100))},
        )
        payload = cast(dict[str, Any], response.json())
        return cast(list[dict[str, Any]], payload.get("workflows", []))

    async def get_recent_commits(
        self,
        owner: str,
        repo: str,
        since: str | None = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent commits for repository context correlation.

        Args:
            owner: Repository owner
            repo: Repository name
            since: ISO-8601 timestamp string for lower bound filtering
            per_page: Maximum commits to fetch

        Returns:
            List of commit objects
        """
        params: dict[str, Any] = {"per_page": max(1, min(per_page, 100))}
        if since:
            params["since"] = since

        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params=params,
        )
        return cast(list[dict[str, Any]], response.json())

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
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            follow_redirects=True,
        )
        return response.text

    async def get_check_run_annotations(
        self,
        owner: str,
        repo: str,
        check_run_id: int,
    ) -> list[dict[str, Any]]:
        """Get annotations for a specific check run.

        Args:
            owner: Repository owner
            repo: Repository name
            check_run_id: GitHub check run ID

        Returns:
            List of check-run annotation objects
        """
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}/annotations",
        )
        return cast(list[dict[str, Any]], response.json())

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
        failed_jobs = [
            j for j in jobs if j.get("conclusion") in ("failure", "timed_out")
        ]

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
        params = {}
        if ref:
            params["ref"] = ref

        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params=params,
        )
        return cast(dict[str, Any], response.json())

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
        params = {"recursive": "1"} if recursive else {}

        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params=params,
        )
        data = cast(dict[str, Any], response.json())
        return cast(list[dict[str, Any]], data.get("tree", []))

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
        # Get the SHA of the source ref
        try:
            ref_response = await self._request(
                "GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_ref}"
            )
            ref_data = cast(dict[str, Any], ref_response.json())
            obj = cast(dict[str, Any], ref_data["object"])
            sha = cast(str, obj["sha"])
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            # Try as a commit SHA
            commit_response = await self._request(
                "GET", f"/repos/{owner}/{repo}/commits/{from_ref}"
            )
            commit_data = cast(dict[str, Any], commit_response.json())
            sha = cast(str, commit_data["sha"])

        # Create the new branch
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha,
            },
        )
        return cast(dict[str, Any], response.json())

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

        response = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json=body,
        )
        return cast(dict[str, Any], response.json())

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
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            },
        )
        return cast(dict[str, Any], response.json())

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Fetch one pull request."""
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
        )
        return cast(dict[str, Any], response.json())

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        """Update mutable pull request fields."""
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        response = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            json=payload,
        )
        return cast(dict[str, Any], response.json())

    async def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get files changed by a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            per_page: Maximum files to fetch

        Returns:
            List of file objects from the PR files API
        """
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
            params={"per_page": max(1, min(per_page, 100))},
        )
        return cast(list[dict[str, Any]], response.json())

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        head: str | None = None,
        base: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List pull requests for a repository."""
        normalized_state = state.strip().lower()
        if normalized_state not in {"open", "closed", "all"}:
            normalized_state = "open"

        params: dict[str, Any] = {
            "state": normalized_state,
            "sort": sort,
            "direction": direction,
            "per_page": max(1, min(per_page, 100)),
        }
        if head:
            params["head"] = head
        if base:
            params["base"] = base

        response = await self._request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
        return cast(list[dict[str, Any]], response.json())

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
        json_body: dict[str, Any] = {
            "title": title,
            "body": body,
        }
        if labels:
            json_body["labels"] = labels
        if assignees:
            json_body["assignees"] = assignees

        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json=json_body,
        )
        return cast(dict[str, Any], response.json())

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
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        return cast(dict[str, Any], response.json())

    async def list_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List comments for an issue."""
        response = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            params={"per_page": max(1, min(per_page, 100)), "sort": "created", "direction": "desc"},
        )
        return cast(list[dict[str, Any]], response.json())

    async def search_issues(
        self,
        owner: str,
        repo: str,
        query: str,
        state: str = "all",
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search issues in a repository for historical failure correlation.

        Args:
            owner: Repository owner
            repo: Repository name
            query: Additional search terms
            state: Issue state filter (open, closed, all)
            per_page: Maximum issues to fetch

        Returns:
            List of issue objects from the search API
        """
        normalized_state = state.strip().lower()
        if normalized_state not in {"open", "closed", "all"}:
            normalized_state = "all"

        clauses = [
            f"repo:{owner}/{repo}",
            "is:issue",
            f"state:{normalized_state}",
        ]
        if query.strip():
            clauses.append(query.strip())

        response = await self._request(
            "GET",
            "/search/issues",
            params={
                "q": " ".join(clauses),
                "sort": "updated",
                "order": "desc",
                "per_page": max(1, min(per_page, 100)),
            },
        )
        payload = cast(dict[str, Any], response.json())
        items = cast(list[dict[str, Any]], payload.get("items", []))
        # Guard against PR objects appearing in issue search results.
        return [item for item in items if "pull_request" not in item]

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        labels: str | None = None,
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List repository issues (non-search API; lower indexing latency)."""
        normalized_state = state.strip().lower()
        if normalized_state not in {"open", "closed", "all"}:
            normalized_state = "all"
        params: dict[str, Any] = {
            "state": normalized_state,
            "sort": sort,
            "direction": direction,
            "per_page": max(1, min(per_page, 100)),
        }
        if labels:
            params["labels"] = labels
        response = await self._request("GET", f"/repos/{owner}/{repo}/issues", params=params)
        items = cast(list[dict[str, Any]], response.json())
        return [item for item in items if "pull_request" not in item]

    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        state_reason: str | None = None,
    ) -> dict[str, Any]:
        """Update mutable issue fields including open/closed state."""
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if state_reason is not None:
            payload["state_reason"] = state_reason
        response = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json=payload,
        )
        return cast(dict[str, Any], response.json())

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
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun",
        )
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
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
        )
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
        "list_repo_workflows": github_tools.list_repo_workflows,
        "get_recent_commits": github_tools.get_recent_commits,
        "get_job_logs": github_tools.get_job_logs,
        "get_failed_jobs_logs": github_tools.get_failed_jobs_logs,
        "get_file_contents": github_tools.get_file_contents,
        "get_repository_tree": github_tools.get_repository_tree,
        "create_branch": github_tools.create_branch,
        "create_or_update_file": github_tools.create_or_update_file,
        "create_pull_request": github_tools.create_pull_request,
        "get_pull_request": github_tools.get_pull_request,
        "update_pull_request": github_tools.update_pull_request,
        "list_pull_requests": github_tools.list_pull_requests,
        "get_pull_request_files": github_tools.get_pull_request_files,
        "create_issue": github_tools.create_issue,
        "add_issue_comment": github_tools.add_issue_comment,
        "list_issue_comments": github_tools.list_issue_comments,
        "list_issues": github_tools.list_issues,
        "update_issue": github_tools.update_issue,
        "search_issues": github_tools.search_issues,
        "rerun_workflow": github_tools.rerun_workflow,
        "rerun_failed_jobs": github_tools.rerun_failed_jobs,
    }
