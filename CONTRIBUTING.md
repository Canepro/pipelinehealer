# Contributing

<!-- LAST_VERIFIED: c78ae9b -->

Thanks for your interest in improving PipelineHealer.

## Scope

PipelineHealer is an OSS-first pipeline remediation platform with Azure as a supported reference deployment path. Contributions should prioritize:

- product portability over platform lock-in
- deterministic remediation behavior
- safety and auditability
- operator clarity
- docs accuracy

Contributions should avoid encoding Azure-only assumptions into the core product model. Deployment-specific behavior belongs in adapters, manifests, or runbooks, not in the product identity.

## Product Framing Rules

When changing operator surfaces, configuration, or provider boundaries:

- Treat PipelineHealer as a pipeline platform, not only a GitHub Actions or CI-only tool.
- Keep a clear distinction between:
  - configured intent
  - effective runtime behavior
  - external dependency status
  - configuration source/provenance
- Prefer one declared source-of-truth model over split-brain configuration flows.
- If a capability is meant to be operator-managed, avoid requiring hidden deployment-only toggles for normal use.
- Track serious behavior/surface changes against a version in `docs/FUTURE_PLAN.md` before implementation.

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
- For control-plane/configuration changes, update the governing docs before or alongside code:
  1. `README.md`
  2. `docs/architecture/OPERATOR_CONTROL_PLANE.md`
  3. `docs/reference/API.md`
  4. `docs/reference/CLI.md`
- Update docs when behavior changes:
  1. `README.md`
  2. `docs/reference/API.md`
  3. `docs/runbooks/LOCAL_DEMO_RUNBOOK.md`
  4. `docs/reference/CLI.md`

## Quality Gates

Before opening a PR, run:

```bash
cd backend && pytest -q && mypy src
cd ../frontend && bun run lint && bun run build
bash scripts/release_scope_check.sh
```
