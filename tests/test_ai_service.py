from __future__ import annotations

import pytest

import src.services.ai_service as ai_service
from ai.schemas import AnswerWithCitations, Citation, Source


@pytest.mark.asyncio
async def test_token_budget_limiter_waits_for_window_rollover():
    clock = [0.0]
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock[0] += seconds

    limiter = ai_service.TokenBudgetLimiter(
        5,
        window_seconds=60.0,
        sleeper=fake_sleep,
        clock=lambda: clock[0],
    )

    first_wait = await limiter.acquire(3)
    second_wait = await limiter.acquire(4)

    assert first_wait == 0.0
    assert second_wait == pytest.approx(60.0)
    assert sleep_calls == [pytest.approx(60.0)]


@pytest.mark.asyncio
async def test_ai_service_rate_limits_repeated_synthesize_calls(monkeypatch):
    clock = [0.0]
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock[0] += seconds

    sources = [
        Source(
            title="Photosynthesis",
            url="https://example.com/photosynthesis",
            snippet="Plants convert light into chemical energy.",
            origin="web",
        )
    ]

    def fake_synthesize(question: str, sources: list[Source], *, llm=None) -> AnswerWithCitations:
        return AnswerWithCitations(
            question=question,
            answer="A cited answer [1]",
            citations=[Citation(index=1, source=sources[0])],
        )

    monkeypatch.setattr(ai_service.ai, "synthesize", fake_synthesize)
    monkeypatch.setattr(
        ai_service.AIService,
        "_estimate_tokens",
        staticmethod(lambda operation, args, kwargs: 1),
    )

    service = ai_service.AIService(
        token_budget_tpm=1,
        token_budget_window_seconds=60.0,
        rate_limit_sleep=fake_sleep,
        rate_limit_clock=lambda: clock[0],
        max_attempts=1,
    )

    first = await service.synthesize("What is photosynthesis?", sources, llm=None)
    second = await service.synthesize("What is photosynthesis?", sources, llm=None)

    assert first.answer == "A cited answer [1]"
    assert second.answer == "A cited answer [1]"
    assert sleep_calls == [pytest.approx(60.0)]


@pytest.mark.asyncio
async def test_ai_service_fetch_wikipedia_delegates(monkeypatch):
    async def fake_fetch_wikipedia(query: str, *, max_results: int = 3, client=None):
        return [
            Source(
                title=f"{query} article",
                url="https://example.com/wiki",
                snippet="Summary text.",
                origin="wikipedia",
            )
        ][:max_results]

    monkeypatch.setattr(ai_service.ai, "fetch_wikipedia", fake_fetch_wikipedia)

    service = ai_service.AIService(max_attempts=1)
    out = await service.fetch_wikipedia("photosynthesis", max_results=1)

    assert len(out) == 1
    assert out[0].origin == "wikipedia"
    assert out[0].title == "photosynthesis article"