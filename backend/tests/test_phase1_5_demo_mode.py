"""Phase 1.5 tests: demo-mode behavior and safer patch rendering."""

import base64

import httpx
import pytest

from src.agents.remediation import RemediationAgent
from src.models import Diagnosis, FailureType, RemediationAction
from src.tools.fix_generators import FixGenerators


class FakeGitHubToolsWithFiles:
    """Minimal fake GitHubTools that can return file contents."""

    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None):
        if path not in self._files:
            request = httpx.Request("GET", "https://api.github.com/fake")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

        raw = self._files[path].encode("utf-8")
        return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}


@pytest.mark.asyncio
async def test_demo_mode_flaky_test_retries_workflow() -> None:
    gen = FixGenerators(heal_mode="demo")
    plan = await gen.generate_fix(
        diagnosis=Diagnosis(
            failure_type=FailureType.TEST,
            confidence=0.9,
            root_cause="intermittent failure",
            is_auto_fixable=True,
            error_details={"is_flaky": True, "test_framework": "jest"},
        ),
        repository_info={},
    )
    assert plan.action == RemediationAction.RETRY_WORKFLOW


@pytest.mark.asyncio
async def test_demo_mode_timeout_generates_timeout_bump_pr_plan() -> None:
    gen = FixGenerators(heal_mode="demo")
    plan = await gen.generate_fix(
        diagnosis=Diagnosis(
            failure_type=FailureType.TIMEOUT,
            confidence=0.9,
            root_cause="Operation timed out",
            is_auto_fixable=True,
            error_details={"timeout_minutes": 1, "suggested_timeout": 5, "timed_out_step": "Long running task"},
        ),
        repository_info={},
    )
    assert plan.action == RemediationAction.CREATE_PR
    assert plan.file_changes
    assert plan.file_changes[0].get("type") == "line_update"
    assert isinstance(plan.file_changes[0].get("files"), list)


@pytest.mark.asyncio
async def test_build_config_permissions_error_generates_permissions_pr_plan() -> None:
    gen = FixGenerators(heal_mode="safe")
    plan = await gen.generate_fix(
        diagnosis=Diagnosis(
            failure_type=FailureType.BUILD_CONFIG,
            confidence=0.9,
            root_cause="Insufficient GitHub Actions token permissions",
            is_auto_fixable=True,
            error_details={
                "workflow_permissions_fix": True,
                "permissions": {
                    "contents": "write",
                    "pull-requests": "write",
                },
            },
        ),
        repository_info={},
    )
    assert plan.action == RemediationAction.CREATE_PR
    assert plan.branch_name == "fix/ci-workflow-permissions"
    assert plan.file_changes
    assert plan.file_changes[0].get("type") == "line_update"
    assert plan.file_changes[0].get("pattern") == r"^jobs:\s*$"


@pytest.mark.asyncio
async def test_render_line_update_supports_backrefs_and_file_selection() -> None:
    gh = FakeGitHubToolsWithFiles(
        files={
            ".github/workflows/ci.yml": "jobs:\n  build:\n    timeout-minutes: 1\n",
        }
    )
    agent = RemediationAgent(github_tools=gh)  # safe mode default is fine for rendering tests

    rendered = await agent._render_file_changes(
        owner="octo",
        repo="demo",
        base_ref="main",
        file_changes=[
            {
                "type": "line_update",
                "files": ["missing.yml", ".github/workflows/ci.yml"],
                "pattern": r"^(?P<indent>\s*)timeout-minutes:\s*\d+\s*$",
                "replacement": r"\g<indent>timeout-minutes: 5",
                "append_if_missing": False,
                "require_existing": True,
            }
        ],
    )

    assert rendered and rendered[0]["file"] == ".github/workflows/ci.yml"
    assert "timeout-minutes: 5" in rendered[0]["content"]


@pytest.mark.asyncio
async def test_render_line_updates_accumulate_for_same_file() -> None:
    gh = FakeGitHubToolsWithFiles(
        files={
            ".github/workflows/ci.yml": (
                "jobs:\n"
                "  build:\n"
                "    env:\n"
                "      REQUIRED_CONFIG: \"\"\n"
                "      OPTIONAL_CONFIG: \"\"\n"
            ),
        }
    )
    agent = RemediationAgent(github_tools=gh)

    rendered = await agent._render_file_changes(
        owner="octo",
        repo="demo",
        base_ref="main",
        file_changes=[
            {
                "type": "line_update",
                "file": ".github/workflows/ci.yml",
                "pattern": r"^(?P<indent>\s*)REQUIRED_CONFIG:\s*.*$",
                "replacement": r"\g<indent>REQUIRED_CONFIG: demo",
                "append_if_missing": False,
            },
            {
                "type": "line_update",
                "file": ".github/workflows/ci.yml",
                "pattern": r"^(?P<indent>\s*)OPTIONAL_CONFIG:\s*.*$",
                "replacement": r"\g<indent>OPTIONAL_CONFIG: demo",
                "append_if_missing": False,
            },
        ],
    )

    assert len(rendered) == 1
    content = rendered[0]["content"]
    assert "REQUIRED_CONFIG: demo" in content
    assert "OPTIONAL_CONFIG: demo" in content
