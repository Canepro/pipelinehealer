"""Main FastAPI application for PipelineHealer."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import dashboard, webhook
from .config import get_settings
from .observability import configure_observability
from .workflows.pipeline_healer import PipelineHealerWorkflow, create_workflow

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


_BACKFILL_INTERVAL_SECONDS = 600  # 10 minutes


async def _backfill_sweep_loop(workflow: PipelineHealerWorkflow) -> None:
    """Periodic background loop that backfills ci-doctor diagnostics.

    Runs every ``_BACKFILL_INTERVAL_SECONDS`` and enriches completed activities
    whose original poll window was exhausted.
    """
    sweep_logger = logging.getLogger(__name__)
    # Wait an initial interval before the first sweep so the app can warm up.
    await asyncio.sleep(_BACKFILL_INTERVAL_SECONDS)
    while True:
        try:
            count = await workflow.run_backfill_sweep(max_age_hours=24.0)
            if count:
                sweep_logger.info("Backfill sweep enriched %d activity(ies)", count)
        except Exception:
            sweep_logger.debug("Backfill sweep iteration failed", exc_info=True)
        await asyncio.sleep(_BACKFILL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()

    # Configure logging level
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Suppress noisy Azure SDK HTTP loggers that flood container log retention
    for _noisy in ("azure.cosmos", "azure.identity", "azure.core"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    logger.info(
        "Starting PipelineHealer",
        environment=settings.environment,
        log_level=settings.log_level,
    )

    # Create and initialize workflow
    use_in_memory = settings.environment == "development"
    workflow = create_workflow(use_in_memory=use_in_memory)
    await workflow.initialize()

    # Store on app.state -- route handlers read via Depends(get_storage/get_workflow).
    app.state.workflow = workflow
    app.state.storage = workflow.storage
    await dashboard.apply_persisted_runtime_settings(workflow.storage, workflow)

    # Recover activities stuck in transient states from a previous crash/restart.
    recovered = await workflow.recover_stale_activities()
    if recovered:
        logger.info("Recovered %d stale activity(ies) from previous run", recovered)

    # Start background backfill sweep for ci-doctor diagnostics.
    backfill_task = asyncio.create_task(
        _backfill_sweep_loop(workflow),
        name="backfill-diagnostics-sweep",
    )

    logger.info("PipelineHealer initialized successfully")

    yield

    # Cleanup
    logger.info("Shutting down PipelineHealer")
    backfill_task.cancel()
    with suppress(asyncio.CancelledError):
        await backfill_task
    await workflow.close()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="PipelineHealer",
        description="Self-healing CI/CD agent system",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    # Optional: enable OpenTelemetry/App Insights when configured.
    configure_observability(app)

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request, call_next):  # type: ignore[no-untyped-def]
        """Attach/request a stable request ID and return it in response headers."""
        # Preserve caller-supplied IDs so operators can correlate curl/UI actions with logs.
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    # Include routers
    app.include_router(webhook.router)
    app.include_router(dashboard.router)

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "service": "PipelineHealer",
            "version": "0.1.0",
            "status": "running",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
