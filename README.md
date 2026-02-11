# PipelineHealer

> Self-Healing CI/CD Agent System powered by Microsoft Agent Framework

[![Azure](https://img.shields.io/badge/Azure-Deployed-blue)](https://azure.microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

PipelineHealer is an AI-powered multi-agent system that automatically detects, diagnoses, and remediates CI/CD pipeline failures in GitHub Actions workflows.

## What Uses AI vs Pure Logic

PipelineHealer intentionally mixes deterministic logic with LLM calls.

AI (Azure OpenAI via Microsoft Agent Framework):

- Log summarization: condense raw job logs into a short, structured summary.
- Diagnosis fallback: when pattern rules do not confidently match, the model produces a structured `Diagnosis` JSON.
- Remediation narrative: write high-quality PR/issue bodies and root-cause descriptions (the actual file edits are still deterministic).

Pure logic:

- Webhook ingestion, event routing, idempotency checks.
- Log extraction (fetch jobs + logs), error/warning line heuristics.
- Pattern-based diagnosis for common cases (dependency/lint/test/timeout/build-config patterns).
- Remediation execution (create branch, commit file content, create PR/issue, rerun failed jobs).

## Healing Modes

`HEAL_MODE` controls how aggressive the system is:

- `safe` (Recommended): conservative, demo-stable behavior.
- `demo`: more aggressive hackathon-friendly behavior (for example retry flaky test runs, open PRs that bump workflow timeouts when it can patch a known workflow file).

See `backend/.env.example`.

## Overview

When a GitHub Actions workflow fails, PipelineHealer:

1. **Detects** the failure via webhook
2. **Analyzes** the build logs using AI
3. **Diagnoses** the root cause (dependency issues, test failures, lint errors, etc.)
4. **Remediates** by creating a fix PR or detailed issue

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│  GitHub Actions │     │              PipelineHealer               │
│                 │     │                                          │
│  ┌───────────┐  │     │  ┌─────────┐    ┌───────────────────┐   │
│  │ Workflow  │──┼─────┼─▶│ Webhook │───▶│   Orchestrator    │   │
│  │  Failed   │  │     │  │ Handler │    │      Agent        │   │
│  └───────────┘  │     │  └─────────┘    └─────────┬─────────┘   │
│                 │     │                           │             │
│  ┌───────────┐  │     │                 ┌─────────▼─────────┐   │
│  │    PR     │◀─┼─────┼─────────────────│   Log Analyzer    │   │
│  │ Created   │  │     │                 │      Agent        │   │
│  └───────────┘  │     │                 └─────────┬─────────┘   │
│                 │     │                           │             │
│  ┌───────────┐  │     │                 ┌─────────▼─────────┐   │
│  │  Issue    │◀─┼─────┼─────────────────│    Diagnosis      │   │
│  │ Created   │  │     │                 │      Agent        │   │
│  └───────────┘  │     │                 └─────────┬─────────┘   │
│                 │     │                           │             │
└─────────────────┘     │                 ┌─────────▼─────────┐   │
                        │                 │   Remediation     │   │
                        │                 │      Agent        │   │
                        │                 └───────────────────┘   │
                        └──────────────────────────────────────────┘
```

## Features

- **Multi-Agent Architecture**: Specialized agents for log analysis, diagnosis, and remediation
- **Intelligent Diagnosis**: Pattern-based and AI-powered root cause analysis
- **Automated Remediation**: Creates PRs for auto-fixable issues, detailed issues for others
- **Beautiful Dashboard**: Real-time monitoring of healing activities
- **Enterprise Ready**: Azure-native with full observability and security

## Failure Types Supported

| Type | Detection | Auto-Fix |
|------|-----------|----------|
| Dependency Issues | ✅ | ✅ |
| Lint/Format Errors | ✅ | ✅ |
| Test Failures | ✅ | ❌ (creates issue) |
| Build Config Errors | ✅ | ❌ (creates issue) |
| Timeouts | ✅ | ❌ (creates issue) |

In `HEAL_MODE=demo`, PipelineHealer may:

- Retry flaky test runs once (`retry_workflow`)
- Open a PR to bump `timeout-minutes` in a known workflow file

## Technology Stack

### Backend (Python + UV)
- **Microsoft Agent Framework** - Multi-agent orchestration
- **Azure OpenAI** - GPT-4o for agent reasoning
- **FastAPI** - API framework
- **Azure Cosmos DB** - Activity storage

### Frontend (TypeScript + Bun)
- **React 18** - UI framework
- **TanStack Query** - Data fetching
- **Recharts** - Visualization
- **Tailwind CSS** - Styling

### Infrastructure
- **Azure Container Apps** - Hosting
- **Azure Functions** - Webhook handling
- **Azure Application Insights** - Observability
- **GitHub MCP Server** - GitHub integration

## Quick Start

### Prerequisites

- Python 3.11+
- Bun (for frontend)
- Azure subscription (for deployment)
- GitHub App or Personal Access Token

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/pipelinehealer.git
   cd pipelinehealer
   ```

2. **Set up the backend**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your configuration
   
   # Install dependencies with UV
   uv pip install -e ".[dev]"
   
   # Run the backend
   uvicorn src.main:app --reload
   ```

3. **Set up the frontend**
   ```bash
   cd frontend
   bun install
   bun run dev
   ```

4. **Access the dashboard**
   Open the URL printed by Vite (usually http://127.0.0.1:5173)

### Local Development (Containerized Backend with Podman/Docker)

If you prefer running only the backend in a container:

```bash
cd /mnt/d/repos/pipelinehealer
cp backend/.env.example backend/.env
# edit backend/.env

podman compose --env-file backend/.env build backend
podman compose --env-file backend/.env up -d backend
podman compose --env-file backend/.env ps
curl -sS http://127.0.0.1:8000/health
```

Use `--env-file backend/.env` with compose commands to avoid empty-env warnings.

### End-to-End Demo Runbook

For the exact commands to reproduce the full demo flow (backend + smee.io + `gh workflow run` triggers), see:

- `docs/LOCAL_DEMO_RUNBOOK.md`

### Future Plan

Roadmap and next AI expansions:

- `docs/FUTURE_PLAN.md`

### Deploy to Azure

```bash
# Using Azure Developer CLI
azd up
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | Yes |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | GPT-4o deployment name | Yes |
| `COSMOS_DB_ENDPOINT` | Cosmos DB endpoint | Yes |
| `GITHUB_WEBHOOK_SECRET` | Webhook signature secret | Yes (prod) |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub PAT for API access | Yes |
| `API_AUTH_KEY` | Required `X-API-Key` value for `/api/*` in non-development envs | Yes (non-dev) |
| `VERIFY_WEBHOOK_SIGNATURE` | Enable webhook signature verification | Recommended `true` |
| `VERIFY_WEBHOOK_SIGNATURE_IN_DEVELOPMENT` | Enforce signature checks in development too | Optional |
| `CORS_ALLOWED_ORIGINS` | Exact CORS origins (CSV or JSON array) | Optional |
| `CORS_ALLOW_ORIGIN_REGEX` | Regex for dynamic hosts (for example Azure Container Apps) | Optional |

### API Security

- `/api/*` endpoints require `X-API-Key` when `ENVIRONMENT` is not `development`.
- In `development`, API key auth is bypassed for local iteration.
- In `production`, keep `VERIFY_WEBHOOK_SIGNATURE=true` and set `GITHUB_WEBHOOK_SECRET`.

Example:

```bash
curl -H "X-API-Key: $API_AUTH_KEY" "http://127.0.0.1:8000/api/activities?limit=20"
```

### GitHub Webhook Setup

1. Create a GitHub App or use a webhook on your repository
2. Set the webhook URL to `https://your-app.azurecontainerapps.io/webhook/github`
3. Select the `workflow_run` event
4. Set the webhook secret (match `GITHUB_WEBHOOK_SECRET`)
5. Keep `VERIFY_WEBHOOK_SIGNATURE=true` in non-development environments

## Project Structure

```
pipelinehealer/
├── backend/                 # Python backend
│   ├── src/
│   │   ├── agents/         # AI agents
│   │   ├── api/            # FastAPI routes
│   │   ├── tools/          # GitHub tools, fix generators
│   │   ├── workflows/      # Agent workflow orchestration
│   │   └── main.py         # Application entry point
│   └── pyproject.toml      # Python dependencies
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # UI components
│   │   ├── pages/          # Page components
│   │   └── api/            # API client
│   └── package.json        # Node dependencies
├── infra/                  # Azure Bicep templates
├── demo-repo/              # Demo repository for testing
└── README.md
```

## Hackathon Categories

This project targets:

- **Agentic DevOps Grand Prize** - Automating CI/CD incident response
- **Best Multi-Agent System** - Sophisticated agent orchestration
- **Best Azure Integration** - Native Azure services integration

## Demo

The `demo-repo/` directory contains a sample repository with a workflow that can trigger various failure types for testing:

1. Push the demo-repo to a new GitHub repository
2. Configure the webhook to point to PipelineHealer
3. Use workflow dispatch to trigger different failure scenarios
4. Watch PipelineHealer automatically respond

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Microsoft Agent Framework team
- Azure AI team
- GitHub MCP Server team

---

Built with ❤️ for the AI Dev Days Hackathon 2026
