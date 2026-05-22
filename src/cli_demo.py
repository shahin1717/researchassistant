"""Minimal demo CLI showing `AIService` + `QueryCache` usage.

Run:
    python src/cli_demo.py --offline "What is photosynthesis?"

This demo uses an internal fake LLM when `--offline` is set so it runs
without network or API keys.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import List

from ai.schemas import Source, AnswerWithCitations
from src.services.ai_service import AIService
from src.services.cache import QueryCache
from src.storage.cache_store import CacheStore


class _FakeLLM:
    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "Photosynthesis is the process by which plants convert light energy into chemical energy [1]. "
            "The reaction takes place in chloroplasts and produces oxygen as a byproduct [2]."
        )

    def complete(self, prompt: str, *, json_schema: dict | None = None, max_tokens: int = 1024) -> str:
        return self.response


_OFFLINE_DB = {
    "photosynthesis": [
        Source(
            title="Photosynthesis",
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            snippet="Photosynthesis is a process used by plants and other organisms to convert light energy into chemical energy.",
            origin="wikipedia",
        ),
        Source(
            title="Light-Dependent Reactions",
            url="https://arxiv.org/abs/1706.03762",
            snippet="A review of the light-dependent reactions of photosynthesis.",
            origin="arxiv",
        ),
    ]
}


async def run_demo(question: str, offline: bool) -> AnswerWithCitations:
    logger = logging.getLogger("demo")
    logger.setLevel(logging.INFO)

    store = CacheStore()  # in-memory by default
    cache = QueryCache(store=store, ttl_seconds=60, logger=logger)
    svc = AIService(max_parallel=4, max_attempts=2, logger=logger)

    # Try cache first
    cached = cache.get("web", question)
    if cached:
        logger.info("Using cached result")
        # synthesize would normally operate on sources; here we just return
        # a small AnswerWithCitations wrapper around the cached JSON.
        return AnswerWithCitations(question=question, answer=cached.response_json, citations=[])

    # offline: use canned sources + fake LLM
    if offline:
        srcs: List[Source] = []
        for key, val in _OFFLINE_DB.items():
            if key in question.lower():
                srcs = val
                break
        if not srcs:
            srcs = [
                Source(title="Generic", url="https://example.com/generic", snippet=f"Overview: {question}", origin="web")
            ]
        llm = _FakeLLM()
    else:
        # In live mode, callers should pass a real LLM via env/config.
        llm = None
        srcs = []  # placeholder; real code would call svc.fetch_*

    answer = await svc.synthesize(question, srcs, llm=llm)

    # Persist a simple cache entry for demonstration.
    cache.set("web", question, answer.answer)

    return answer


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("question", nargs="+", help="Question to research")
    p.add_argument("--offline", action="store_true", help="Run with fake LLM and canned sources")
    args = p.parse_args()
    q = " ".join(args.question)

    ans = asyncio.run(run_demo(q, offline=args.offline))

    print(f"Q: {ans.question}\n")
    print(f"A: {ans.answer}\n")
    if ans.citations:
        print("References:")
        for c in ans.citations:
            print(f"  [{c.index}] ({c.source.origin}) {c.source.title}\n      {c.source.url}")


if __name__ == "__main__":
    main()
