"""
SCIRM Distributed Tracing
OpenTelemetry integration for request tracing across all services.
"""

import os
from typing import Optional

from fastapi import FastAPI


OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "scirm")


def setup_tracing(app: FastAPI, service_name: Optional[str] = None) -> None:
    """
    Configure OpenTelemetry tracing for a FastAPI application.
    Only activates if OTEL_ENABLED=true and the OpenTelemetry packages are installed.
    """
    if not OTEL_ENABLED:
        return

    resolved_name = service_name or SERVICE_NAME

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create({"service.name": resolved_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)

        # Also instrument httpx for outbound calls (agent-to-agent)
        try:
            HTTPXClientInstrumentor().instrument()
        except Exception:
            pass

    except ImportError:
        import structlog
        structlog.get_logger().warning(
            "OpenTelemetry packages not installed — tracing disabled. "
            "Install: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp"
        )
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("Tracing setup failed", error=str(exc))
