"""Main FastAPI application for PipelineHealer."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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

# Global workflow instance
_workflow: PipelineHealerWorkflow | None = None


def get_workflow() -> PipelineHealerWorkflow:
    """Get the workflow instance."""
    if _workflow is None:
        raise RuntimeError("Workflow not initialized")
    return _workflow


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    global _workflow

    settings = get_settings()

    # Configure logging level
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info(
        "Starting PipelineHealer",
        environment=settings.environment,
        log_level=settings.log_level,
    )

    # Create and initialize workflow
    use_in_memory = settings.environment == "development"
    _workflow = create_workflow(use_in_memory=use_in_memory)
    await _workflow.initialize()

    # Set workflow and storage for API routes
    webhook.set_workflow(_workflow)
    dashboard.set_storage(_workflow.storage)
    dashboard.set_workflow(_workflow)

    logger.info("PipelineHealer initialized successfully")

    yield

    # Cleanup
    logger.info("Shutting down PipelineHealer")
    if _workflow:
        await _workflow.close()


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
