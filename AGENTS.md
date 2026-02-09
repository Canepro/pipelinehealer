# Agent Instructions (Repo-Specific)

This repository contains **PipelineHealer** — a multi-agent CI/CD self-healing system built for the [AI Dev Days Hackathon](https://github.com/Azure/AI-Dev-Days-Hackathon).

## Quick Commands

### Backend (Python + UV)

```bash
cd pipelinehealer/backend
cp .env.example .env           # first time only — fill in values
uv pip install -e ".[dev]"     # install with dev dependencies
uvicorn src.main:app --reload  # run API server on :8000
pytest                         # run tests
ruff check src/                # lint
mypy src/                      # typecheck
```

### Frontend (TypeScript + Bun/npm)

```bash
cd pipelinehealer/frontend
bun install                    # or npm install
bun run dev                    # Vite dev server on :5173
bun run build                  # tsc + vite build
bun run lint                   # eslint
bun run format                 # prettier
```

### Docker (local dev)

```bash
cd pipelinehealer
docker-compose up --build      # backend :8000, frontend :3000, Cosmos emulator :8081
```

### Azure Deployment

```bash
cd pipelinehealer
azd up                         # provision infra (Bicep) + deploy services
```

## Project Layout

```
ai-dev-days-hackathon-project/
├── PROJECT_STATUS.md              # Roadmap, weekly plan, session continuity
└── pipelinehealer/
    ├── azure.yaml                 # Azure Developer CLI config
    ├── docker-compose.yml         # Local dev stack
    ├── README.md                  # Project README (public-facing)
    ├── LICENSE                    # MIT
    ├── backend/                   # Python FastAPI backend
    │   ├── pyproject.toml         # Dependencies (UV/hatch)
    │   ├── .env.example           # Required env vars
    │   ├── Dockerfile
    │   ├── src/
    │   │   ├── main.py            # FastAPI app entry point
    │   │   ├── config.py          # Pydantic settings (env-driven)
    │   │   ├── models.py          # Data models
    │   │   ├── storage.py         # Cosmos DB + in-memory storage
    │   │   ├── observability.py   # OpenTelemetry / App Insights
    │   │   ├── agents/            # AI agents (one per file)
    │   │   │   ├── base.py        # Base agent class
    │   │   │   ├── log_analyzer.py
    │   │   │   ├── diagnosis.py
    │   │   │   ├── remediation.py
    │   │   │   └── orchestrator.py
    │   │   ├── api/               # FastAPI routers
    │   │   │   ├── webhook.py     # GitHub webhook handler
    │   │   │   └── dashboard.py   # Dashboard API endpoints
    │   │   ├── tools/             # Agent tools
    │   │   │   ├── github_tools.py    # GitHub REST API wrapper
    │   │   │   └── fix_generators.py  # Fix generation for 5 failure types
    │   │   └── workflows/
    │   │       └── pipeline_healer.py # Orchestration pipeline
    │   └── tests/
    │       ├── test_diagnosis.py
    │       └── test_webhook.py
    ├── frontend/                  # React dashboard
    │   ├── package.json
    │   ├── Dockerfile
    │   ├── vite.config.ts
    │   ├── tailwind.config.js
    │   └── src/
    │       ├── main.tsx
    │       ├── App.tsx
    │       ├── api/               # API client (TanStack Query)
    │       ├── components/        # UI components
    │       └── pages/
    │           ├── Dashboard.tsx   # Stats cards, charts
    │           ├── Activities.tsx  # Filterable activity table
    │           └── ActivityDetail.tsx
    ├── infra/                     # Azure Bicep templates
    │   ├── main.bicep
    │   └── main.bicepparam
    └── demo-repo/                 # Demo repo for triggering test failures
        ├── .github/               # GitHub Actions workflow with failure triggers
        ├── index.js
        ├── test.js
        └── package.json
```

## Architecture

Four agents form a sequential pipeline triggered by GitHub webhooks:

1. **Log Analyzer** (`agents/log_analyzer.py`) — Parses raw CI logs, extracts structured error patterns. Does not diagnose.
2. **Diagnosis Agent** (`agents/diagnosis.py`) — Maps patterns to failure categories. Does not fix.
3. **Remediation Agent** (`agents/remediation.py`) — Generates targeted fixes based on confirmed diagnosis. Does not guess from raw logs.
4. **Orchestrator** (`agents/orchestrator.py`) — Coordinates the pipeline, manages state, opens PR or issue.

Agents communicate through typed Pydantic models, not free-form text.

### Supported Failure Types

| Type | Auto-Fix |
|------|----------|
| Dependency issues | PR |
| Lint/format errors | PR |
| Test failures | Issue |
| Build config errors | Issue |
| Timeouts | Issue |

### CI Platform Extensibility

Currently GitHub Actions only. The architecture should support pluggable CI platforms via an adapter interface:

```python
class CIPlatformAdapter(ABC):
    async def get_run_info(self, event_data: dict) -> WorkflowRunInfo: ...
    async def get_logs(self, run_id: str) -> dict[str, str]: ...
    async def create_fix(self, repo: str, files: dict, message: str) -> str: ...
    async def create_issue(self, repo: str, title: str, body: str) -> str: ...
    async def retry_run(self, run_id: str) -> bool: ...
```

- `GitHubAdapter` wraps existing `GitHubTools` methods
- Webhook routes: `/webhook/github`, `/webhook/jenkins`, `/webhook/gitlab`
- Factory selects adapter based on incoming webhook source
- See `REVIEW.md` for full extensibility plan

### Data Flow

```
GitHub workflow_run.completed webhook
  → api/webhook.py (signature verification, event routing)
  → workflows/pipeline_healer.py (orchestration)
  → agents/log_analyzer.py → agents/diagnosis.py → agents/remediation.py
  → tools/github_tools.py (create PR or issue)
  → storage.py (persist activity to Cosmos DB)
```

## Engineering Rules

- Do not commit secrets. Use `.env` locally (see `.env.example`), Azure Key Vault in production.
- All configuration is env-driven via Pydantic `Settings` in `config.py`. Do not hardcode endpoints, keys, or deployment names.
- Agents must remain single-responsibility. If an agent is doing two jobs, split it.
- Agent inputs and outputs must use typed Pydantic models defined in `models.py`.
- Backend code must pass `ruff check` and `mypy --strict`.
- Frontend code must pass `eslint` and `tsc`.
- Keep the in-memory storage path (`InMemoryStorage`) working for local dev without Azure dependencies.

## Hackathon Context

### Target Categories

- **Grand Prize: Agentic DevOps** (primary) — Automating CI/CD incident response
- **Best Multi-Agent System** — Four-agent orchestration pipeline
- **Best Azure Integration** — Cosmos DB, OpenAI, Container Apps, Functions, Key Vault, App Insights

### Required Technologies (must use at least one)

- Microsoft Agent Framework ✅ (agent orchestration)
- Azure OpenAI ✅ (GPT-4o for agent reasoning)
- Azure services ✅ (Cosmos DB, Container Apps, Functions, Key Vault, App Insights)
- GitHub ✅ (public repo, webhooks, PR/issue creation)

### Submission Checklist

- [ ] Working project deployed to Azure (`azd up`)
- [ ] Public GitHub repository
- [ ] Project description (features, problem solved, technologies)
- [ ] Demo video (2 min max, YouTube/Vimeo, shows the product working)
- [ ] Architecture diagram (Mermaid or draw.io)
- [ ] Microsoft Learn usernames for all participants
- [ ] Microsoft Learn Skilling Plan completed

### Judging Criteria (20% each)

1. **Technological Implementation** — Code quality, effective use of hero technologies, documentation
2. **Agentic Design & Innovation** — Creative AI patterns, agent orchestration sophistication
3. **Real-World Impact** — Problem significance, production readiness, potential impact
4. **User Experience & Presentation** — Intuitive UX, clear demo video, balanced frontend/backend
5. **Adherence to Category** — Matches the Agentic DevOps category description

### Key Deadlines

| Phase | Dates |
|-------|-------|
| Registration | Jan 20 – Feb 22, 2026 |
| Hacking | Feb 10 – Mar 15, 2026 (11:59 PM PT) |
| Judging | Mar 16 – Mar 22, 2026 |
| Winners | Mar 25, 2026 |

### Official Rules Summary

- Project must be **newly created** after Feb 10, 2026 (start of hacking period).
- Open-source dependencies are allowed; the project itself must be the entrant's original work.
- Demo video must be under 2 minutes. Judges are not required to watch beyond that.
- Repository must be public.
- Up to 4 team members. Currently solo.
- Can win one Grand Prize + one Category Prize.
- Judges may reassign projects to a different category if it fits better.
- Stage 1 judging is pass/fail (does it fit the theme and use required tech). Stage 2 is scored.

## Azure Services Reference

| Service | Purpose | Config |
|---------|---------|--------|
| Azure OpenAI | GPT-4o for agent reasoning | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME` |
| Cosmos DB | Activity/healing record storage | `COSMOS_DB_ENDPOINT`, serverless tier |
| Container Apps | Backend + frontend hosting | Defined in `azure.yaml` |
| Functions | Webhook handler | Defined in `azure.yaml` |
| Key Vault | Secrets (GitHub App key, etc.) | `KEY_VAULT_URL` |
| Application Insights | Observability, tracing | `APPLICATIONINSIGHTS_CONNECTION_STRING` |

## Environment Variables

All variables are documented in `backend/.env.example`. Required for production:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI service endpoint |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes | GPT-4o deployment name |
| `COSMOS_DB_ENDPOINT` | Yes | Cosmos DB endpoint |
| `GITHUB_WEBHOOK_SECRET` | Prod | Webhook HMAC secret |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Dev | PAT for local development |
| `GITHUB_APP_ID` | Prod | GitHub App ID |
| `KEY_VAULT_URL` | Prod | Azure Key Vault for secrets |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional | App Insights telemetry |

For local dev, only `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, and `GITHUB_PERSONAL_ACCESS_TOKEN` are needed. Storage falls back to in-memory.

## Testing

```bash
# Unit tests
cd pipelinehealer/backend
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Run specific test
pytest tests/test_diagnosis.py -v
```

Integration and E2E tests require deployed Azure resources and a configured GitHub App.

## Demo Repo

`demo-repo/` contains a small Node.js project with a GitHub Actions workflow that can trigger various failure types via workflow dispatch. Use this to test PipelineHealer end-to-end:

1. Push `demo-repo/` to a new GitHub repository
2. Configure the webhook to point to PipelineHealer's deployed URL
3. Trigger workflow dispatch with different failure scenarios
4. Observe PipelineHealer's response in the dashboard

## Tracking & Continuity

- **Project status and weekly plan**: `PROJECT_STATUS.md` (root of repo)
- **Blog series**: Documented in portfolio repo at `content/blog/blog.md`
- **Session IDs**: Recorded in `PROJECT_STATUS.md` for agent continuity across sessions
