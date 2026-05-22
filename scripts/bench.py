# scripts/bench.py
"""Sequential vs parallel benchmark — run this and paste the output into README."""

from __future__ import annotations

import asyncio
import time
import json
from pathlib import Path

import httpx

from ai import fetch_wikipedia, fetch_arxiv, fetch_web
from ai.sources import get_web_search_provider
from src.concurrency.orchestrator import fetch_all
from src.config import settings


QUESTIONS = json.loads(
    (Path(__file__).parent.parent / "data" / "research_questions.json").read_text()
)["questions"]


async def run_sequential(query: str) -> float:
    """Run all three fetchers one after another. Returns total seconds."""
    provider = get_web_search_provider()
    t0 = time.perf_counter()
    headers = {
        "User-Agent": "ResearchAssistantBot/1.0 (sultan.musayeva@aiacademy.az; ShahinAcademicTeam) httpx/0.27.2"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        await fetch_wikipedia(query, client=client)
        await fetch_arxiv(query, client=client)
        await fetch_web(query, provider=provider, client=client)
    return round(time.perf_counter() - t0, 2)


async def run_parallel(query: str) -> float:
    """Run all three fetchers in parallel. Returns wall-clock seconds."""
    t0 = time.perf_counter()
    await fetch_all(query)
    return round(time.perf_counter() - t0, 2)


async def main() -> None:
    print(f"\n{'Question':<45} {'Sequential':>12} {'Parallel':>10} {'Speedup':>9}")
    print("-" * 80)

    total_seq = 0.0
    total_par = 0.0

    for q in QUESTIONS:
        question = q["text"] if isinstance(q, dict) else q
        label = question[:43] + ".." if len(question) > 45 else question

        seq = await run_sequential(question)
        par = await run_parallel(question)
        speedup = round(seq / par, 1) if par > 0 else 0

        total_seq += seq
        total_par += par

        print(f"{label:<45} {seq:>11.2f}s {par:>9.2f}s {speedup:>8.1f}x")

    print("-" * 80)
    overall = round(total_seq / total_par, 1) if total_par > 0 else 0
    print(f"{'TOTAL':<45} {total_seq:>11.2f}s {total_par:>9.2f}s {overall:>8.1f}x")
    print(f"\nReproduce: python scripts/bench.py")


if __name__ == "__main__":
    asyncio.run(main())