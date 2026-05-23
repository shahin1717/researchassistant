"""OpenTelemetry helpers for the Async Research Assistant."""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter


def create_tracer_provider(
    *,
    service_name: str = "researchassistant",
    exporter: SpanExporter | None = None,
    resource_attributes: Mapping[str, str] | None = None,
) -> TracerProvider:
    """Create a standalone tracer provider for tests or app bootstrap."""

    attributes = {"service.name": service_name}
    if resource_attributes:
        attributes.update(resource_attributes)
    provider = TracerProvider(resource=Resource.create(attributes))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def get_tracer(name: str) -> trace.Tracer:
    """Return an OpenTelemetry tracer using the current global provider."""

    return trace.get_tracer(name)