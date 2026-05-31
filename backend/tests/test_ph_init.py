"""Regression tests for the ph.sh init bootstrap command."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_init(env_file: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PH_ENV_FILE"] = str(env_file)
    return subprocess.run(
        ["bash", "scripts/ph.sh", "init", *args],
        cwd=_repo_root(),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_ph(*args: str, env_file: Path | None = None, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in (
        "PH_RG",
        "PH_BACKEND_APP",
        "PH_FRONTEND_APP",
        "PH_ACR_NAME",
        "ACR_NAME",
        "PH_BACKEND_URL",
        "DEMO_REPO",
        "PH_FRONTEND_URL",
    ):
        env.pop(key, None)
    if env_file is not None:
        env["PH_ENV_FILE"] = str(env_file)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "scripts/ph.sh", *args],
        cwd=_repo_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _env_map(env_file: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        result[key] = value
    return result


def test_init_creates_codex_app_server_env_without_printing_generated_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"

    result = _run_init(
        env_file,
        "--auto-fix",
        "--repos",
        "owner/demo-repo",
        "--infisical-project-id",
        "project-123",
        "--infisical-env",
        "prod",
        "--infisical-path",
        "/pipelinehealer/prod",
    )

    values = _env_map(env_file)
    mode = stat.S_IMODE(env_file.stat().st_mode)

    assert mode == 0o600
    assert values["LLM_PROVIDER"] == "codex_app_server"
    assert values["CODEX_APP_SERVER_MODEL"] == "gpt-5.4"
    assert values["STORAGE_MODE"] == "memory"
    assert values["AUTH_MODE"] == "api_key"
    assert values["AUTO_CREATE_PR"] == "true"
    assert values["AUTO_MERGE_REMEDIATION_PRS"] == "true"
    assert values["AUTO_MERGE_STRATEGY"] == "merge_when_clean"
    assert values["PH_ALLOWED_REPOS"] == "owner/demo-repo"
    assert values["SETTINGS_SECRET_BACKEND"] == "infisical"
    assert values["INFISICAL_PROJECT_ID"] == "project-123"
    assert values["INFISICAL_ENVIRONMENT"] == "prod"
    assert values["INFISICAL_SECRET_PATH"] == "/pipelinehealer/prod"

    generated_secret_keys = (
        "API_AUTH_KEY",
        "ADMIN_API_KEY",
        "AUDIT_SALT",
        "GITHUB_WEBHOOK_SECRET",
        "SETTINGS_DB_ENCRYPTION_KEY",
    )
    for key in generated_secret_keys:
        assert values[key]
        assert "CHANGE_ME" not in values[key]
        assert "YOUR_" not in values[key]
        assert values[key] not in result.stdout

    assert "Created env scaffold with generated local secrets. Values were not printed." in result.stdout
    assert "UI-first fields already supported" in result.stdout
    assert "pipelinehealer.canepro.me" not in result.stdout
    assert "rg-canepro" not in result.stdout
    assert "ca-canepro" not in result.stdout
    assert "Canepro/pipelinehealer-demo" not in result.stdout


def test_init_leaves_existing_env_unchanged_without_force(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        "API_AUTH_KEY=keep-me\nLLM_PROVIDER=azure_openai\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    result = _run_init(env_file, "--auto-fix", "--repos", "owner/repo")

    assert env_file.read_text(encoding="utf-8") == "API_AUTH_KEY=keep-me\nLLM_PROVIDER=azure_openai\n"
    assert "Env file already exists. Leaving values unchanged." in result.stdout


def test_demo_proof_requires_explicit_repo_when_no_env_default() -> None:
    result = _run_ph("demo:proof")

    assert result.returncode == 2
    assert "Usage: bash scripts/ph.sh demo:proof --repo owner/repo" in result.stderr
    assert "Canepro/pipelinehealer-demo" not in result.stderr


def test_azure_status_requires_operator_supplied_app_names() -> None:
    result = _run_ph("status")

    assert result.returncode == 2
    assert "needs Azure Container Apps target env vars" in result.stderr
    assert "PH_RG" in result.stderr
    assert "PH_BACKEND_APP" in result.stderr
    assert "PH_FRONTEND_APP" in result.stderr
    assert "rg-canepro" not in result.stderr
    assert "ca-canepro" not in result.stderr


def test_deploy_env_requires_operator_supplied_app_names() -> None:
    result = _run_ph("deploy:env", "--no-verify")

    assert result.returncode == 2
    assert "Missing Azure deployment target configuration" in result.stderr
    assert "--resource-group or PH_RG" in result.stderr
    assert "--backend-app or PH_BACKEND_APP" in result.stderr
    assert "--frontend-app or PH_FRONTEND_APP" in result.stderr
    assert "rg-canepro" not in result.stderr
    assert "ca-canepro" not in result.stderr


def test_demo_e2e_requires_operator_supplied_repo_and_backend_names() -> None:
    result = _run_ph("demo:e2e", "--skip-trigger", "--skip-webhook-sync", "--skip-reset")

    assert result.returncode == 2
    assert "Missing Azure demo target configuration" in result.stderr
    assert "--repo or DEMO_REPO" in result.stderr
    assert "--resource-group or PH_RG" in result.stderr
    assert "--backend-app or PH_BACKEND_APP" in result.stderr
    assert "Canepro/pipelinehealer-demo" not in result.stderr
    assert "rg-canepro" not in result.stderr
    assert "ca-canepro" not in result.stderr


def test_azure_logs_require_operator_supplied_backend_names() -> None:
    for command in ("logs", "logs:raw"):
        result = _run_ph(command)
        assert result.returncode == 2
        assert "needs Azure backend target env vars" in result.stderr
        assert "PH_RG" in result.stderr
        assert "PH_BACKEND_APP" in result.stderr
        assert "rg-canepro" not in result.stderr
        assert "ca-canepro" not in result.stderr

    grep_result = _run_ph("logs:grep", "--pattern", "error")
    assert grep_result.returncode == 2
    assert "needs Azure backend target env vars" in grep_result.stderr


def test_deploy_state_commands_require_resource_group() -> None:
    for command in ("deploy:bg", "deploy:logs", "deploy:status"):
        result = _run_ph(command)
        assert result.returncode == 2
        assert "needs --resource-group or PH_RG for deploy state files" in result.stderr
        assert "/tmp/ph-deploy-/" not in result.stderr
        assert "/tmp/ph-deploy-/" not in result.stdout


def test_rollout_canary_validates_azure_target_before_env_mutation(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"
    original = "PH_ALLOWED_REPOS=keep/repo\nHEAL_MODE=observe\n"
    env_file.write_text(original, encoding="utf-8")
    env_file.chmod(0o600)

    result = _run_ph("rollout:canary", "--repos", "owner/repo", env_file=env_file)

    assert result.returncode == 2
    assert "needs Azure Container Apps target env vars" in result.stderr
    assert env_file.read_text(encoding="utf-8") == original
