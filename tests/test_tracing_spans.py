from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai
import ai.synthesizer as ai_synthesizer
from ai.providers.base import LLMProvider
from ai.schemas import AnswerWithCitations, Citation, Source
from src.core import researcher
from src.services.ai_service import AIService
from src.services.tracing import create_tracer_provider


class FakeLLM(LLMProvider):
    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        return "A traced answer [1]"


def _source(origin: str, title: str) -> Source:
    return Source(
        title=title,
        url=f"https://example.test/{origin}/{title.lower().replace(' ', '-')}",
        snippet=f"{title} summary.",
        origin=origin,
    )


@pytest.mark.asyncio
async def test_research_emits_core_request_spans(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider(exporter=exporter)
    tracer = provider.get_tracer("tests.tracing")

    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr("src.concurrency.orchestrator.get_web_search_provider", lambda: object())
    monkeypatch.setattr(ai_synthesizer, "get_llm", lambda: FakeLLM())

    async def fake_fetch_wikipedia(query: str, *, max_results: int = 3, client=None) -> list[Source]:
        return [_source("wikipedia", "Photosynthesis")]

    async def fake_fetch_arxiv(query: str, *, max_results: int = 3, client=None) -> list[Source]:
        return [_source("arxiv", "Photosynthesis Paper")]

    async def fake_fetch_web(query: str, *, max_results: int = 3, provider=None, client=None) -> list[Source]:
        return [_source("web", "Plants and Light")]

    monkeypatch.setattr(ai, "fetch_wikipedia", fake_fetch_wikipedia)
    monkeypatch.setattr(ai, "fetch_arxiv", fake_fetch_arxiv)
    monkeypatch.setattr(ai, "fetch_web", fake_fetch_web)

    answer = await researcher.research(
        "What is photosynthesis?",
        sources=("wiki", "arxiv", "web"),
        no_cache=True,
        tracer=tracer,
    )

    assert isinstance(answer, AnswerWithCitations)

    provider.force_flush()
    span_names = {span.name for span in exporter.get_finished_spans()}

    assert "research.request" in span_names
    assert "research.fetch_all" in span_names
    assert "research.fetch.wiki" in span_names
    assert "research.fetch.arxiv" in span_names
    assert "research.fetch.web" in span_names
    assert "ai.fetch_wikipedia" in span_names
    assert "ai.fetch_arxiv" in span_names
    assert "ai.fetch_web" in span_names
    assert "ai.synthesize" in span_names


def test_ai_service_synthesize_emits_span(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider(exporter=exporter)
    tracer = provider.get_tracer("tests.tracing")

    service = AIService(tracer=tracer, max_attempts=1)
    sources = [_source("wikipedia", "Photosynthesis")]
    result = asyncio.run(service.synthesize("What is photosynthesis?", sources, llm=FakeLLM()))

    assert result.answer == "A traced answer [1]"

    provider.force_flush()
    span_names = [span.name for span in exporter.get_finished_spans()]
    assert "ai.synthesize" in span_names
