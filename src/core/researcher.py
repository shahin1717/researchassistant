"""Core research logic — orchestrates fetching and synthesis."""

from __future__ import annotations

import logging

from ai import synthesize, AnswerWithCitations, Source
from src.concurrency.orchestrator import fetch_all

logger = logging.getLogger(__name__)


async def research(
    question: str,
    *,
    sources: tuple[str, ...] = ("wiki", "arxiv", "web"),
    no_cache: bool = False,
) -> AnswerWithCitations:
    """Run the full research pipeline for a question."""
    if not question.strip():
        raise ValueError("question must be non-empty")

    logger.info("research_start", extra={"question": question, "sources": sources})

    all_sources, timings = await fetch_all(question, sources=sources)

    if not all_sources:
        raise RuntimeError("all sources failed or returned no results")

    logger.info("research_fetched", extra={"total_sources": len(all_sources),
                "timings": timings})

    answer = synthesize(question, all_sources)

    logger.info("research_done", extra={"citations": len(answer.citations)})

    return answer