#!/usr/bin/env python3
"""Inventory or migrate PipelineHealer runtime secrets into Infisical."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


SECRET_ENV_KEYS = (
    "API_AUTH_KEY",
    "ADMIN_API_KEY",
    "SETTINGS_DB_ENCRYPTION_KEY",
    "AUDIT_SALT",
    "POSTGRES_DSN",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_OPENAI_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GITHUB_WEBHOOK_SECRET",
    "JENKINS_BRIDGE_SHARED_SECRET",
    "AGENT_HANDOFF_WEBHOOK_URL",
    "AGENT_HANDOFF_CALLBACK_SECRET",
    "CODEX_APP_SERVER_HANDOFF_URL",
    "OPENCLAW_HANDOFF_URL",
    "HERMES_HANDOFF_URL",
    "CODEX_APP_SERVER_WS_BEARER_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "INFISICAL_TOKEN",
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def infisical_scope_args(args: argparse.Namespace) -> list[str]:
    scope = ["--env", args.env, "--path", args.path]
    if args.project_id:
        scope.extend(["--projectId", args.project_id])
    if args.domain:
        scope.extend(["--domain", args.domain])
    if args.token:
        scope.extend(["--token", args.token])
    return scope


def run_infisical_set(args: argparse.Namespace, secrets: dict[str, str]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        os.chmod(temp_path, 0o600)
        for key, value in secrets.items():
            escaped = value.replace("\n", "\\n")
            handle.write(f"{key}={escaped}\n")
    try:
        command = [
            args.cli,
            "--silent",
            "secrets",
            "set",
            "--file",
            str(temp_path),
            "--type",
            "shared",
            *infisical_scope_args(args),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    finally:
        temp_path.unlink(missing_ok=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"Infisical migration failed: {detail or 'unknown error'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--env", default=os.getenv("INFISICAL_ENVIRONMENT", "dev"))
    parser.add_argument("--path", default=os.getenv("INFISICAL_SECRET_PATH", "/pipelinehealer/dev"))
    parser.add_argument("--project-id", default=os.getenv("INFISICAL_PROJECT_ID", ""))
    parser.add_argument("--domain", default=os.getenv("INFISICAL_API_URL", ""))
    parser.add_argument("--token", default=os.getenv("INFISICAL_TOKEN", ""))
    parser.add_argument("--cli", default=os.getenv("INFISICAL_CLI_PATH", "infisical"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    values = parse_env_file(env_path)
    candidates = {key: values[key] for key in SECRET_ENV_KEYS if values.get(key)}

    print(f"env_file={env_path}")
    print(f"target=env:{args.env} path:{args.path} project_id_configured={bool(args.project_id)}")
    print(f"candidate_secret_count={len(candidates)}")
    for key in sorted(candidates):
        print(f"candidate={key}")

    if not args.apply:
        print("mode=inventory_only")
        return 0

    if not candidates:
        print("mode=apply migrated=0")
        return 0

    run_infisical_set(args, candidates)
    print(f"mode=apply migrated={len(candidates)}")
    print("values_printed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
