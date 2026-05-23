"""Concurrent orchestration of the three research sources delegating to AIService."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Sequence

import httpx

from ai.schemas import Source
from ai.sources import get_web_search_provider
from src.config import settings
from src.services.ai_service import AIService

logger = logging.getLogger(__name__)


async def fetch_all(
    query: str,
    *,
    sources: Sequence[str] = ("wiki", "arxiv", "web"),
    ai_service: AIService | None = None,
) -> tuple[list[Source], dict[str, float]]:
    """Fetch from Wikipedia, arXiv, and web sources in parallel.

    Uses the retry and rate-limiting wrapper from AIService.
    """
    svc = ai_service or AIService()
    max_results = settings.max_sources_per_query
    timings: dict[str, float] = {}

    tasks = []
    names = []

    # Prepare async client with standard User-Agent to avoid Wikipedia API 403 blocks
    headers = {
        "User-Agent": "ResearchAssistantBot/1.0 (sultan.musayeva@aiacademy.az; ShahinAcademicTeam) httpx/0.27.2"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        if "wiki" in sources:
            names.append("wiki")
            tasks.append(svc.fetch_wikipedia(query, max_results=max_results, client=client))
        if "arxiv" in sources:
            names.append("arxiv")
            tasks.append(svc.fetch_arxiv(query, max_results=max_results, client=client))
        if "web" in sources:
            provider = get_web_search_provider()
            names.append("web")
            tasks.append(svc.fetch_web(query, max_results=max_results, provider=provider, client=client))

        if not tasks:
            return [], {"total_parallel": 0.0}

        t0 = time.perf_counter()
        # Concurrently await tasks, catching timeouts or errors safely
        results = await asyncio.gather(*tasks, return_exceptions=True)
        timings["total_parallel"] = round(time.perf_counter() - t0, 2)

    all_sources: list[Source] = []
    for name, r in zip(names, results):
        if isinstance(r, Exception):
            logger.warning(
                "source_failed_in_orchestrator",
                extra={"source": name, "error": type(r).__name__, "message": str(r)},
            )
            continue
        all_sources.extend(r)

    return all_sources, timings