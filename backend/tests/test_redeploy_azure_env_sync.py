"""Regression tests for Azure deploy env-sync behavior."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from textwrap import dedent


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_fake_az(tmp_path: Path) -> Path:
    fake_az = tmp_path / "az"
    fake_az.write_text(
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail

            echo "$*" >> "${FAKE_AZ_LOG}"

            if [[ "${1:-}" == "containerapp" && "${2:-}" == "show" ]]; then
              app=""
              query=""
              while [[ $# -gt 0 ]]; do
                case "$1" in
                  -n)
                    app="${2:-}"
                    shift 2
                    ;;
                  --query)
                    query="${2:-}"
                    shift 2
                    ;;
                  *)
                    shift
                    ;;
                esac
              done

              if [[ "$query" == "properties.configuration.ingress.fqdn" ]]; then
                if [[ "$app" == "fe" ]]; then
                  echo "frontend.example.com"
                else
                  echo "backend.example.com"
                fi
                exit 0
              fi

              if [[ "$query" == "properties.template.containers[0].image" ]]; then
                if [[ "$app" == "fe" ]]; then
                  echo "frontend-image:tag"
                else
                  echo "backend-image:tag"
                fi
                exit 0
              fi
            fi

            if [[ "${1:-}" == "containerapp" && "${2:-}" == "update" ]]; then
              exit 0
            fi

            echo "unsupported az invocation: $*" >&2
            exit 1
            """
        ),
        encoding="utf-8",
    )
    fake_az.chmod(fake_az.stat().st_mode | stat.S_IEXEC)
    return fake_az


def _run_env_only_deploy(tmp_path: Path, env_file: Path) -> str:
    _write_fake_az(tmp_path)
    az_log = tmp_path / "az.log"
    script = _repo_root() / "scripts/deploy/redeploy_azure_containerapps.sh"
    env = os.environ.copy()
    env["FAKE_AZ_LOG"] = str(az_log)
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"

    subprocess.run(
        [
            "bash",
            str(script),
            "--env-only",
            "--no-verify",
            "--resource-group",
            "rg",
            "--backend-app",
            "be",
            "--frontend-app",
            "fe",
            "--env-file",
            str(env_file),
        ],
        cwd=_repo_root(),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    return az_log.read_text(encoding="utf-8")


def test_deploy_env_skips_missing_frontend_runtime_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        dedent(
            """\
            API_AUTH_KEY=api_key
            ADMIN_API_KEY=admin_key
            VITE_API_URL=https://api.override.example
            """
        ),
        encoding="utf-8",
    )

    az_log = _run_env_only_deploy(tmp_path, env_file)
    fe_update = next(
        line
        for line in az_log.splitlines()
        if line.startswith("containerapp update ") and " -n fe " in f" {line} "
    )

    assert "BACKEND_UPSTREAM=https://backend.example.com" in fe_update
    assert "API_AUTH_KEY=api_key" in fe_update
    assert "VITE_API_URL=https://api.override.example" in fe_update
    assert "VITE_AUTH_MODE=" not in fe_update
    assert "VITE_ENTRA_CLIENT_ID=" not in fe_update
    assert "VITE_API_TIMEOUT_MS=" not in fe_update


def test_deploy_env_applies_default_for_explicit_empty_auth_mode(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        dedent(
            """\
            API_AUTH_KEY=api_key
            ADMIN_API_KEY=admin_key
            VITE_AUTH_MODE=
            """
        ),
        encoding="utf-8",
    )

    az_log = _run_env_only_deploy(tmp_path, env_file)
    fe_update = next(
        line
        for line in az_log.splitlines()
        if line.startswith("containerapp update ") and " -n fe " in f" {line} "
    )

    assert "VITE_AUTH_MODE=none" in fe_update
