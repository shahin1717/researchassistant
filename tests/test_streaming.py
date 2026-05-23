from __future__ import annotations

import pytest

from ai.schemas import Source
from src.services import ai_service


class StreamingLLM:
    def __init__(self, parts: list[str]) -> None:
        self._parts = parts

    def stream_complete(self, prompt: str):
        for p in self._parts:
            yield p


class SimpleLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, prompt: str) -> str:
        return self._text


def _sample_sources() -> list[Source]:
    return [
        Source(
            title="Photosynthesis",
            url="https://example.test/photosynthesis",
            snippet="Plants convert light energy into chemical energy.",
            origin="wikipedia",
        )
    ]


@pytest.mark.asyncio
async def test_synthesize_stream_yields_parts() -> None:
    parts = ["Hello", " ", "World", "!"]
    llm = StreamingLLM(parts)
    svc = ai_service.AIService()

    received: list[str] = []
    async for chunk in svc.synthesize_stream("Q", _sample_sources(), llm=llm):
        received.append(chunk)

    assert received == parts


@pytest.mark.asyncio
async def test_synthesize_stream_fallbacks_to_full() -> None:
    llm = SimpleLLM("Complete answer")
    svc = ai_service.AIService()

    received: list[str] = []
    async for chunk in svc.synthesize_stream("Q", _sample_sources(), llm=llm):
        received.append(chunk)

    assert received == ["Complete answer"]
