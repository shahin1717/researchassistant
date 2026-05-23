from __future__ import annotations

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.services.tracing import create_tracer_provider


def test_create_tracer_provider_records_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider(exporter=exporter)
    tracer = provider.get_tracer("researchassistant.tests")

    with tracer.start_as_current_span("setup-span"):
        pass

    provider.force_flush()
    spans = exporter.get_finished_spans()

    assert len(spans) == 1
    assert spans[0].name == "setup-span"
    assert spans[0].resource.attributes["service.name"] == "researchassistant"