from __future__ import annotations

import logging

import pytest

from ai.providers.base import LLMProvider, ProviderError
from ai.schemas import AnswerWithCitations, Citation, Source
from src.services import ai_service
from src.services.failover import FailoverLLMProvider, build_llm_provider_chain, parse_provider_names


class FailingProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.calls += 1
        raise ProviderError("provider is unavailable")


class SuccessProvider(LLMProvider):
    def __init__(self, response: str = "Fallback answer [1]") -> None:
        self.calls = 0
        self.response = response

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.calls += 1
        return self.response


def _sample_sources() -> list[Source]:
    return [
        Source(
            title="Photosynthesis",
            url="https://example.test/photosynthesis",
            snippet="Plants convert light energy into chemical energy.",
            origin="wikipedia",
        )
    ]


def test_parse_provider_names_dedupes_and_trims() -> None:
    assert parse_provider_names(" anthropic, openai , gemini,openai ") == (
        "anthropic",
        "openai",
        "gemini",
    )


def test_failover_provider_uses_second_provider_after_failure() -> None:
    primary = FailingProvider()
    fallback = SuccessProvider()
    provider = FailoverLLMProvider(
        [primary, fallback],
        provider_names=["anthropic", "openai"],
        logger=logging.getLogger("test.failover"),
    )

    out = provider.complete("Tell me about photosynthesis")

    assert out == "Fallback answer [1]"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_build_llm_provider_chain_skips_unavailable_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_builder() -> LLMProvider:
        raise ProviderError("missing key")

    fallback = SuccessProvider("OpenAI fallback [1]")

    monkeypatch.setattr(
        "src.services.failover._LLM_PROVIDER_BUILDERS",
        {
            "anthropic": failing_builder,
            "openai": lambda: fallback,
        },
    )

    provider = build_llm_provider_chain(["anthropic", "openai"])

    assert provider.complete("Tell me about photosynthesis") == "OpenAI fallback [1]"
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_ai_service_synthesize_uses_failover_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FailoverLLMProvider(
        [FailingProvider(), SuccessProvider("Synthesized answer [1]")],
        provider_names=["anthropic", "openai"],
        logger=logging.getLogger("test.ai_service"),
    )

    monkeypatch.setattr(ai_service, "build_llm_provider_chain", lambda logger=None: provider)

    service = ai_service.AIService(max_attempts=1)
    result = await service.synthesize("What is photosynthesis?", _sample_sources())

    assert result.answer == "Synthesized answer [1]"
    assert [citation.index for citation in result.citations] == [1]
