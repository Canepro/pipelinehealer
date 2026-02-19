# Contributing

Thanks for your interest in improving PipelineHealer.

## Scope

PipelineHealer is a hackathon-focused project with Azure-first deployment goals. Contributions should prioritize:

- deterministic remediation behavior
- safety and auditability
- docs accuracy

## Local Setup

Backend:

```bash
cd backend
uv pip install -e ".[dev]"
pytest -q
mypy src
```

Frontend:

```bash
cd frontend
bun install
bun run lint
bun run build
```

## One-Command Ops (Repo Root)

```bash
bash scripts/ph.sh help
```

Common flows:

- full deploy: `bash scripts/ph.sh deploy`
- env-only deploy: `bash scripts/ph.sh deploy:env`
- e2e demo: `bash scripts/ph.sh demo:e2e`
- reset demo fixtures: `bash scripts/ph.sh demo:reset`

Always execute scripts with `bash scripts/...`. Do not use `source` or `. scripts/...`.

## Pull Request Guidelines

- Keep changes small and reviewable.
- Do not commit secrets.
- Add concise comments for non-obvious logic (focus on intent/why, not line-by-line narration).
- Update or remove stale comments in files you touch.
- Add/update `CHANGELOG.md` `## [Unreleased]` entries for user-visible changes and include short commit hash references.
- Update docs when behavior changes:
  1. `README.md`
  2. `docs/API.md`
  3. `docs/LOCAL_DEMO_RUNBOOK.md`
  4. `docs/CLI.md`

## Quality Gates

Before opening a PR, run:

```bash
cd backend && pytest -q && mypy src
cd ../frontend && bun run lint && bun run build
bash scripts/release_scope_check.sh
```
