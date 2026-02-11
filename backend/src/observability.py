"""Observability configuration for PipelineHealer using Azure Monitor OpenTelemetry."""

import logging
from typing import TYPE_CHECKING, Any

from .config import get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


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
            "service.version": "0.1.0",
        }
    )

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    logger.info("Basic OpenTelemetry tracing configured")


def get_tracer(name: str = "pipelinehealer") -> "Tracer":
    """Get a tracer instance for creating spans.

    Args:
        name: Tracer name

    Returns:
        Tracer instance
    """
    from opentelemetry import trace

    return trace.get_tracer(name)


class TracingMiddleware:
    """Custom middleware for adding trace context to agent operations."""

    def __init__(self) -> None:
        """Initialize tracing middleware."""
        self._tracer = get_tracer("pipelinehealer.agents")

    def trace_agent_operation(
        self,
        operation_name: str,
        agent_name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """Create a span for an agent operation.

        Args:
            operation_name: Name of the operation
            agent_name: Name of the agent
            attributes: Additional span attributes

        Returns:
            Span context manager
        """
        span_attributes = {
            "agent.name": agent_name,
            "operation.name": operation_name,
        }

        if attributes:
            span_attributes.update(attributes)

        return self._tracer.start_as_current_span(
            f"{agent_name}.{operation_name}",
            attributes=span_attributes,
        )


# Global tracing middleware instance
tracing = TracingMiddleware()
