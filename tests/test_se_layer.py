"""Offline pytest suite for the SE layer."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from ai.schemas import AnswerWithCitations, Citation, Source
from src.cli import main, parse_sources, validate_question
from src.concurrency.orchestrator import fetch_all
from src.core import researcher
from src.models import ResearchSession
from src.services.cache import QueryCache
from src.storage.cache_store import CacheStore


@pytest.fixture
def dummy_sources() -> list[Source]:
    return [
        Source(
            title="Photosynthesis",
            url="https://example.test/photosynthesis",
            snippet="Plants convert light energy into chemical energy.",
            origin="wikipedia",
        )
    ]


@pytest.fixture
def wiki_source() -> Source:
    return Source(
        title="Photosynthesis",
        url="https://example.test/photosynthesis",
        snippet="Plants convert light energy into chemical energy.",
        origin="wikipedia",
    )


@pytest.fixture
def arxiv_source() -> Source:
    return Source(
        title="Photosynthesis Paper",
        url="https://arxiv.org/abs/1234.5678",
        snippet="A paper discussing photosynthetic stages.",
        origin="arxiv",
    )


@pytest.fixture
def mock_answer(wiki_source: Source) -> AnswerWithCitations:
    return AnswerWithCitations(
        question="What is photosynthesis?",
        answer="Photosynthesis converts light into chemical energy [1].",
        citations=[Citation(index=1, source=wiki_source)],
    )


def test_research_session_rejects_empty_question() -> None:
    """ResearchSession prevents empty questions crossing module boundaries."""

    with pytest.raises(ValidationError):
        ResearchSession(session_id="123", question="   ")


def test_cli_question_validation() -> None:
    assert validate_question("  What is photosynthesis? ") == "What is photosynthesis?"

    with pytest.raises(ValueError, match="empty"):
        validate_question("   ")

    with pytest.raises(ValueError, match="500"):
        validate_question("a" * 501)


def test_cli_source_parsing() -> None:
    assert parse_sources("wiki,arxiv,web,wikipedia") == ("wiki", "arxiv", "web")

    with pytest.raises(ValueError, match="Unknown source"):
        parse_sources("wiki,books")


def test_orchestrator_degrades_when_one_source_fails(
    monkeypatch: pytest.MonkeyPatch,
    wiki_source: Source,
    arxiv_source: Source,
) -> None:
    """If one provider fails, fetch_all still returns successful sources."""

    class FakeAIService:
        async def fetch_wikipedia(self, query: str, **kwargs: object) -> list[Source]:
            return [wiki_source]

        async def fetch_arxiv(self, query: str, **kwargs: object) -> list[Source]:
            return [arxiv_source]

        async def fetch_web(self, query: str, **kwargs: object) -> list[Source]:
            raise TimeoutError("web timeout")

    monkeypatch.setattr("src.concurrency.orchestrator.get_web_search_provider", lambda: object())

    async def run_fetch() -> tuple[list[Source], dict[str, float]]:
        return await fetch_all(
            "What is photosynthesis?",
            sources=("wiki", "arxiv", "web"),
            ai_service=FakeAIService(),
        )

    sources, timings = asyncio.run(run_fetch())

    assert [source.origin for source in sources] == ["wikipedia", "arxiv"]
    assert "total_parallel" in timings


def test_research_uses_cache_and_synthesizes_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    wiki_source: Source,
    mock_answer: AnswerWithCitations,
) -> None:
    """The integrated researcher can run without network when fetch and LLM are mocked."""

    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    async def fake_fetch_all(question: str, *, sources, ai_service):
        return [wiki_source], {"total_parallel": 0.01}

    fake_synthesize = AsyncMock(return_value=mock_answer)
    monkeypatch.setattr(researcher, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(researcher.AIService, "synthesize", fake_synthesize)

    async def run_research() -> AnswerWithCitations:
        return await researcher.research(
            "What is photosynthesis?",
            sources=("wiki",),
            no_cache=True,
        )

    answer = asyncio.run(run_research())

    assert answer.answer.startswith("Photosynthesis converts")
    fake_synthesize.assert_awaited_once()


def test_cli_ask_calls_researcher_without_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_answer: AnswerWithCitations,
) -> None:
    called: dict[str, object] = {}

    async def fake_research(question: str, *, sources, no_cache: bool):
        called["question"] = question
        called["sources"] = sources
        called["no_cache"] = no_cache
        return mock_answer

    monkeypatch.setattr("src.cli.research", fake_research)

    result = main(["ask", "  What is photosynthesis?  ", "--sources", "wiki,arxiv", "--no-cache"])

    assert result == 0
    assert called == {
        "question": "What is photosynthesis?",
        "sources": ("wiki", "arxiv"),
        "no_cache": True,
    }
    assert "References:" in capsys.readouterr().out


def test_caching_behavior() -> None:
    """Verify that QueryCache stores and retrieves correctly."""

    store = CacheStore()
    cache = QueryCache(store=store)

    source = "wikipedia"
    query = "photosynthesis"
    response_json = '{"data": "test"}'

    assert cache.get(source, query) is None

    cache.set(source, query, response_json)

    cached = cache.get(source, query)
    assert cached is not None
    assert cached.response_json == response_json


def test_cli_cost_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify cost-report subcommand."""

    monkeypatch.setattr("src.cli.settings.cache_dir", str(tmp_path))
    store = CacheStore(tmp_path / "cache.db")
    store.record_spend("gemini", "photosynthesis", 0.25)
    store.record_spend("openai", "chlorophyll", 0.75)
    store.close()

    result = main(["cost-report"])

    assert result == 0
    captured = capsys.readouterr()
    assert "Total spend: $1.000000" in captured.out
    assert "openai: $0.750000" in captured.out
