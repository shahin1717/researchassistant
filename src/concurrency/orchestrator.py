"""Concurrent orchestration of the three research sources."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Sequence

import httpx

from ai import fetch_wikipedia, fetch_arxiv, fetch_web, Source
from ai.sources import get_web_search_provider
from src.config import settings

logger = logging.getLogger(__name__)


async def _fetch_safe(name: str, coro, timeout: float) -> list[Source]:
    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            result = await coro
        logger.info("source_ok", extra={"source": name, "count": len(result),
                    "seconds": round(time.perf_counter() - t0, 2)})
        return result
    except TimeoutError:
        logger.warning("source_timeout", extra={"source": name,
                       "seconds": round(time.perf_counter() - t0, 2)})
        return []
    except Exception as exc:
        logger.warning("source_error", extra={"source": name, "error": str(exc),
                       "seconds": round(time.perf_counter() - t0, 2)})
        return []

async def fetch_all(
    query: str,
    *,
    sources: Sequence[str] = ("wiki", "arxiv", "web"),
) -> tuple[list[Source], dict[str, float]]:
    timeout = settings.per_source_timeout_seconds
    max_results = settings.max_sources_per_query
    timings: dict[str, float] = {}

    async with httpx.AsyncClient() as client:
        tasks = []
        names = []

        if "wiki" in sources:
            names.append("wiki")
            tasks.append(_fetch_safe("wiki",
                fetch_wikipedia(query, max_results=max_results, client=client), timeout))
        if "arxiv" in sources:
            names.append("arxiv")
            tasks.append(_fetch_safe("arxiv",
                fetch_arxiv(query, max_results=max_results, client=client), timeout))
        if "web" in sources:
            provider = get_web_search_provider()
            names.append("web")
            tasks.append(_fetch_safe("web",
                fetch_web(query, max_results=max_results, provider=provider, client=client), timeout))

        t0 = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        timings["total_parallel"] = round(time.perf_counter() - t0, 2)

    all_sources: list[Source] = []
    for r in results:
        if isinstance(r, list):
            all_sources.extend(r)

    return all_sources, timings