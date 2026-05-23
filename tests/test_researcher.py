"""Offline tests for src/core/researcher.py error paths."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from ai.schemas import AnswerWithCitations, Citation, Source
from src.core import researcher


@pytest.fixture
def wiki_source() -> Source:
    return Source(
        title="Photosynthesis",
        url="https://example.test/photosynthesis",
        snippet="Plants convert light energy into chemical energy.",
        origin="wikipedia",
    )


@pytest.fixture
def mock_answer(wiki_source: Source) -> AnswerWithCitations:
    return AnswerWithCitations(
        question="What is photosynthesis?",
        answer="Photosynthesis converts light into chemical energy [1].",
        citations=[Citation(index=1, source=wiki_source)],
    )


# ── Input validation ──────────────────────────────────────────────────────────

def test_research_rejects_empty_question(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    with pytest.raises(ValueError, match="non-empty"):
        asyncio.run(researcher.research("   "))


# ── All sources empty ─────────────────────────────────────────────────────────

def test_research_raises_when_all_sources_return_empty(
    tmp_path, monkeypatch, mock_answer
) -> None:
    """If every source returns [] and cache is empty, RuntimeError is raised."""
    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    async def fake_fetch_all(question, *, sources, ai_service):
        return [], {"total_parallel": 0.0}

    monkeypatch.setattr(researcher, "fetch_all", fake_fetch_all)

    with pytest.raises(RuntimeError, match="All sources failed"):
        asyncio.run(researcher.research("What is photosynthesis?", no_cache=True))


# ── Corrupted cache entry falls back to fetch ─────────────────────────────────

def test_research_corrupted_cache_falls_back_to_fetch(
    tmp_path, monkeypatch, wiki_source, mock_answer
) -> None:
    """A corrupted cache entry (bad JSON) should trigger a fresh fetch."""
    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    # Pre-populate cache with invalid JSON
    from src.storage.cache_store import CacheStore
    from pathlib import Path
    db_path = Path(tmp_path) / "cache.db"
    store = CacheStore(db_path)
    store.set("wiki", "what is photosynthesis?", "NOT_VALID_JSON{{{{")
    store.close()

    fetch_called = {"count": 0}

    async def fake_fetch_all(question, *, sources, ai_service):
        fetch_called["count"] += 1
        return [wiki_source], {"total_parallel": 0.01}

    fake_synthesize = AsyncMock(return_value=mock_answer)
    monkeypatch.setattr(researcher, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(researcher.AIService, "synthesize", fake_synthesize)

    result = asyncio.run(
        researcher.research("What is photosynthesis?", sources=("wiki",))
    )

    assert result.answer.startswith("Photosynthesis")
    assert fetch_called["count"] == 1  # fell back to fetch


# ── No-cache bypasses SQLite entirely ────────────────────────────────────────

def test_research_no_cache_skips_cache_lookup(
    tmp_path, monkeypatch, wiki_source, mock_answer
) -> None:
    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    fetch_called = {"count": 0}

    async def fake_fetch_all(question, *, sources, ai_service):
        fetch_called["count"] += 1
        return [wiki_source], {"total_parallel": 0.01}

    fake_synthesize = AsyncMock(return_value=mock_answer)
    monkeypatch.setattr(researcher, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(researcher.AIService, "synthesize", fake_synthesize)

    asyncio.run(
        researcher.research("What is photosynthesis?", sources=("wiki",), no_cache=True)
    )

    # fetch must have been called — cache was bypassed
    assert fetch_called["count"] == 1


# ── Sources are cached after a fresh fetch ───────────────────────────────────

def test_research_caches_results_after_fetch(
    tmp_path, monkeypatch, wiki_source, mock_answer
) -> None:
    monkeypatch.setattr(researcher.settings, "cache_dir", str(tmp_path))

    fetch_calls = {"count": 0}

    async def fake_fetch_all(question, *, sources, ai_service):
        fetch_calls["count"] += 1
        return [wiki_source], {"total_parallel": 0.01}

    fake_synthesize = AsyncMock(return_value=mock_answer)
    monkeypatch.setattr(researcher, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(researcher.AIService, "synthesize", fake_synthesize)

    # First call — fetches and caches
    asyncio.run(researcher.research("What is photosynthesis?", sources=("wiki",)))
    # Second call — should hit cache, not call fetch_all again
    asyncio.run(researcher.research("What is photosynthesis?", sources=("wiki",)))

    assert fetch_calls["count"] == 1