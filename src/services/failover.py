"""Provider failover helpers for the service layer."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ai.providers.anthropic import AnthropicLLM
from ai.providers.base import LLMProvider, ProviderError
from ai.providers.google import GeminiLLM
from ai.providers.openai import OpenAILLM


ProviderBuilder = Callable[[], LLMProvider]


@dataclass(slots=True)
class _NamedProvider:
    name: str
    provider: LLMProvider


_LLM_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {
    "anthropic": AnthropicLLM,
    "openai": OpenAILLM,
    "google": GeminiLLM,
    "gemini": GeminiLLM,
}


def parse_provider_names(raw_value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated provider list into normalized names."""

    if raw_value is None or not raw_value.strip():
        return ()

    seen: set[str] = set()
    names: list[str] = []
    for piece in raw_value.split(","):
        name = piece.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return tuple(names)


def _provider_names_from_env() -> tuple[str, ...]:
    fallback_names = parse_provider_names(os.getenv("LLM_PROVIDER_FALLBACKS"))
    if fallback_names:
        return fallback_names

    provider_names = parse_provider_names(os.getenv("LLM_PROVIDER"))
    if provider_names:
        return provider_names

    return ("anthropic", "openai", "gemini")


class FailoverLLMProvider(LLMProvider):
    """Try a sequence of LLM providers until one succeeds."""

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        *,
        provider_names: Sequence[str] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not providers:
            raise ValueError("providers must be non-empty")
        if provider_names is not None and len(provider_names) != len(providers):
            raise ValueError("provider_names must match providers")
        self._providers = tuple(providers)
        self._provider_names = tuple(provider_names) if provider_names is not None else tuple(
            type(provider).__name__ for provider in providers
        )
        self._logger = logger or logging.getLogger(__name__)

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        failures: list[str] = []
        for name, provider in zip(self._provider_names, self._providers, strict=True):
            try:
                response = provider.complete(
                    prompt,
                    json_schema=json_schema,
                    max_tokens=max_tokens,
                ).strip()
                if not response:
                    raise ProviderError(f"{name} returned an empty response")
                if failures:
                    self._logger.info(
                        "llm_failover_success",
                        extra={"provider": name, "failures": failures},
                    )
                return response
            except (ProviderError, TimeoutError) as exc:
                message = f"{name}: {exc}"
                failures.append(message)
                self._logger.warning(
                    "llm_provider_failed",
                    extra={"provider": name, "error": type(exc).__name__, "detail": str(exc)},
                )

        raise ProviderError("All configured LLM providers failed: " + "; ".join(failures))


def _instantiate_provider(name: str) -> LLMProvider:
    builder = _LLM_PROVIDER_BUILDERS.get(name)
    if builder is None:
        raise ProviderError(f"Unknown LLM provider {name!r}")
    return builder()


def build_llm_provider_chain(
    provider_names: Sequence[str] | None = None,
    *,
    logger: logging.Logger | None = None,
) -> LLMProvider:
    """Build a failover-capable LLM provider from configured provider names."""

    names = tuple(provider_names) if provider_names is not None else _provider_names_from_env()
    if not names:
        raise ProviderError("No LLM providers configured for failover")

    providers: list[_NamedProvider] = []
    failures: list[str] = []
    for name in names:
        try:
            provider = _instantiate_provider(name)
        except ProviderError as exc:
            failures.append(f"{name}: {exc}")
            if logger is not None:
                logger.warning(
                    "llm_provider_unavailable",
                    extra={"provider": name, "error": type(exc).__name__, "detail": str(exc)},
                )
            continue
        providers.append(_NamedProvider(name=name, provider=provider))

    if not providers:
        raise ProviderError("Unable to initialize any configured LLM provider: " + "; ".join(failures))

    if len(providers) == 1:
        return providers[0].provider

    return FailoverLLMProvider(
        [item.provider for item in providers],
        provider_names=[item.name for item in providers],
        logger=logger,
    )