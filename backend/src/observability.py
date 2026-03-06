"""Observability configuration for PipelineHealer using Azure Monitor OpenTelemetry."""

import logging
from typing import Any

from . import __version__
from .config import get_settings

logger = logging.getLogger(__name__)


def configure_observability(app: Any) -> None:
    """Configure observability with Azure Application Insights.

    Args:
        app: FastAPI application instance
    """
    settings = get_settings()

    if not settings.applicationinsights_connection_string:
        logger.info("Application Insights not configured, skipping observability setup")
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Configure Azure Monitor
        configure_azure_monitor(
            connection_string=settings.applicationinsights_connection_string,
        )

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        logger.info("Application Insights observability configured successfully")

    except ImportError:
        logger.warning("azure-monitor-opentelemetry not installed, falling back to basic tracing")
        _configure_basic_tracing()
    except Exception as e:
        logger.error(f"Failed to configure Application Insights: {e}")
        _configure_basic_tracing()


def _configure_basic_tracing() -> None:
    """Configure basic OpenTelemetry tracing without Azure Monitor."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    resource = Resource.create(
        {
            "service.name": "pipelinehealer",
            "service.version": __version__,
        }
    )

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    logger.info("Basic OpenTelemetry tracing configured")
