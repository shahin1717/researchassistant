"""Retrying service wrapper around the provided `ai` module."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import ai
from ai.providers.base import LLMProvider, ProviderError
from ai.schemas import AnswerWithCitations, Source
from opentelemetry.trace import Tracer
from src.services.tracing import get_tracer
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt, wait_exponential


T = TypeVar("T")


@dataclass(slots=True)
class _TokenUsage:
    timestamp: float
    tokens: int


class TokenBudgetLimiter:
    """Sliding-window token budget limiter for approximate TPM enforcement."""

    def __init__(
        self,
        tokens_per_window: int,
        *,
        window_seconds: float = 60.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if tokens_per_window <= 0:
            raise ValueError("tokens_per_window must be > 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._tokens_per_window = tokens_per_window
        self._window_seconds = window_seconds
        self._sleep = sleeper
        self._clock = clock
        self._lock = asyncio.Lock()
        self._events: deque[_TokenUsage] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._events and self._events[0].timestamp <= cutoff:
            self._events.popleft()

    def _used_tokens(self) -> int:
        return sum(event.tokens for event in self._events)

    def _seconds_until_available(self, now: float, requested_tokens: int) -> float:
        overflow = self._used_tokens() + requested_tokens - self._tokens_per_window
        if overflow <= 0:
            return 0.0

        reclaimed = 0
        for event in self._events:
            reclaimed += event.tokens
            if reclaimed >= overflow:
                return max(0.0, (event.timestamp + self._window_seconds) - now)

        return self._window_seconds

    async def acquire(self, tokens: int) -> float:
        if tokens <= 0:
            return 0.0

        waited = 0.0
        while True:
            async with self._lock:
                now = self._clock()
                self._prune(now)
                if self._used_tokens() + tokens <= self._tokens_per_window:
                    self._events.append(_TokenUsage(timestamp=now, tokens=tokens))
                    return waited
                wait_seconds = self._seconds_until_available(now, tokens)

            await self._sleep(wait_seconds)
            waited += wait_seconds


class AIService:
    """Thin provider-agnostic wrapper around the `ai.*` functions."""

    def __init__(
        self,
        *,
        max_parallel: int | None = None,
        source_timeout_seconds: float | None = None,
        synthesize_timeout_seconds: float | None = None,
        token_budget_tpm: int | None = None,
        token_budget_window_seconds: float | None = None,
        rate_limit_sleep: Callable[[float], Awaitable[None]] | None = None,
        rate_limit_clock: Callable[[], float] | None = None,
        tracer: Tracer | None = None,
        max_attempts: int = 3,
        logger: logging.Logger | None = None,
    ) -> None:
        self._max_parallel = max_parallel or _read_int_env("MAX_PARALLEL", 10)
        self._source_timeout_seconds = (
            source_timeout_seconds
            if source_timeout_seconds is not None
            else _read_float_env("PER_SOURCE_TIMEOUT_SECONDS", 10.0)
        )
        self._synthesize_timeout_seconds = (
            synthesize_timeout_seconds
            if synthesize_timeout_seconds is not None
            else _read_float_env("SYNTHESIZE_TIMEOUT_SECONDS", 30.0)
        )
        self._token_budget_tpm = (
            token_budget_tpm
            if token_budget_tpm is not None
            else _read_int_env("TOKEN_BUDGET_TPM", 0)
        )
        self._token_budget_window_seconds = (
            token_budget_window_seconds
            if token_budget_window_seconds is not None
            else _read_float_env("TOKEN_BUDGET_WINDOW_SECONDS", 60.0)
        )
        self._rate_limiter = (
            None
            if self._token_budget_tpm <= 0
            else TokenBudgetLimiter(
                self._token_budget_tpm,
                window_seconds=self._token_budget_window_seconds,
                sleeper=rate_limit_sleep or asyncio.sleep,
                clock=rate_limit_clock or time.monotonic,
            )
        )
        self._tracer = tracer or get_tracer(__name__)
        self._max_attempts = max_attempts
        self._semaphore = asyncio.Semaphore(self._max_parallel)
        self._logger = logger or logging.getLogger(__name__)

    @property
    def max_parallel(self) -> int:
        return self._max_parallel

    @property
    def source_timeout_seconds(self) -> float:
        return self._source_timeout_seconds

    @property
    def synthesize_timeout_seconds(self) -> float:
        return self._synthesize_timeout_seconds

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    @staticmethod
    def _estimate_value_chars(value: object, *, depth: int = 0) -> int:
        if depth >= 2:
            return 8
        if value is None:
            return 4
        if isinstance(value, bool):
            return 5
        if isinstance(value, (int, float)):
            return 8
        if isinstance(value, str):
            return min(len(value), 4096)
        if isinstance(value, (bytes, bytearray)):
            return min(len(value), 4096)
        if isinstance(value, dict):
            estimated = 2
            for key, item in list(value.items())[:5]:
                estimated += len(str(key))
                estimated += AIService._estimate_value_chars(item, depth=depth + 1)
            estimated += max(0, len(value) - 5) * 8
            return min(estimated, 4096)
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)[:5]
            estimated = 2 + max(0, len(value) - 5) * 8
            estimated += sum(AIService._estimate_value_chars(item, depth=depth + 1) for item in items)
            return min(estimated, 4096)
        return len(type(value).__name__)

    @staticmethod
    def _estimate_tokens(operation: str, args: tuple[object, ...], kwargs: dict[str, object]) -> int:
        estimated_chars = len(operation)
        estimated_chars += sum(AIService._estimate_value_chars(value) for value in args)
        estimated_chars += sum(
            len(key) + 1 + AIService._estimate_value_chars(value)
            for key, value in sorted(kwargs.items())
            if key not in {"client", "provider", "llm"}
        )
        estimated_chars = min(estimated_chars, 16384)
        estimated = max(1, math.ceil(estimated_chars / 4))
        return estimated

    def _retry_exceptions(self) -> tuple[type[BaseException], ...]:
        return (ProviderError, TimeoutError)

    def _log_retry(self, retry_state: RetryCallState) -> None:
        error = retry_state.outcome.exception() if retry_state.outcome else None
        self._logger.warning(
            "ai_call_retry",
            extra={
                "operation": retry_state.fn.__name__ if retry_state.fn else "unknown",
                "attempt": retry_state.attempt_number,
                "error": type(error).__name__ if error is not None else None,
            },
        )

    async def _run_async_call(
        self,
        operation: str,
        func: Callable[..., Awaitable[T]],
        *args: object,
        timeout_seconds: float,
        **kwargs: object,
    ) -> T:
        start = time.monotonic()
        retry_exceptions = self._retry_exceptions()
        estimated_tokens = self._estimate_tokens(operation, args, kwargs)
        span_name = f"ai.{operation}"
        with self._tracer.start_as_current_span(span_name) as span:
            span.set_attribute("ai.operation", operation)
            span.set_attribute("ai.timeout_seconds", timeout_seconds)
            span.set_attribute("ai.estimated_tokens", estimated_tokens)
            if self._rate_limiter is not None:
                waited_seconds = await self._rate_limiter.acquire(estimated_tokens)
                if waited_seconds > 0:
                    self._logger.info(
                        "ai_rate_limit_wait",
                        extra={
                            "operation": operation,
                            "tokens": estimated_tokens,
                            "waited_seconds": round(waited_seconds, 2),
                        },
                    )
                    span.set_attribute("ai.rate_limit_wait_seconds", round(waited_seconds, 2))
            self._logger.info(
                "ai_call_start",
                extra={"operation": operation, "timeout_seconds": timeout_seconds},
            )
            retry = AsyncRetrying(
                retry=retry_if_exception_type(retry_exceptions),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
                stop=stop_after_attempt(self._max_attempts),
                reraise=True,
                before_sleep=self._log_retry,
            )
            try:
                async for attempt in retry:
                    with attempt:
                        async with self._semaphore:
                            result = await asyncio.wait_for(
                                func(*args, **kwargs),
                                timeout=timeout_seconds,
                            )
                            duration_ms = (time.monotonic() - start) * 1000.0
                            self._logger.info(
                                "ai_call_success",
                                extra={
                                    "operation": operation,
                                    "duration_ms": round(duration_ms, 2),
                                },
                            )
                            span.set_attribute("ai.duration_ms", round(duration_ms, 2))
                            return result
            except retry_exceptions as error:
                duration_ms = (time.monotonic() - start) * 1000.0
                span.record_exception(error)
                self._logger.error(
                    "ai_call_failed",
                    extra={
                        "operation": operation,
                        "duration_ms": round(duration_ms, 2),
                        "error": type(error).__name__,
                    },
                )
                raise
        raise RuntimeError(f"unreachable retry state for {operation}")

    async def _run_sync_call(
        self,
        operation: str,
        func: Callable[..., T],
        *args: object,
        timeout_seconds: float,
        **kwargs: object,
    ) -> T:
        async def _invoke() -> T:
            return await asyncio.to_thread(func, *args, **kwargs)

        return await self._run_async_call(
            operation,
            _invoke,
            timeout_seconds=timeout_seconds,
        )

    async def fetch_wikipedia(
        self,
        query: str,
        *,
        max_results: int = 3,
        client: object | None = None,
    ) -> list[Source]:
        return await self._run_async_call(
            "fetch_wikipedia",
            ai.fetch_wikipedia,
            query,
            max_results=max_results,
            client=client,
            timeout_seconds=self._source_timeout_seconds,
        )

    async def fetch_arxiv(
        self,
        query: str,
        *,
        max_results: int = 3,
        client: object | None = None,
    ) -> list[Source]:
        return await self._run_async_call(
            "fetch_arxiv",
            ai.fetch_arxiv,
            query,
            max_results=max_results,
            client=client,
            timeout_seconds=self._source_timeout_seconds,
        )

    async def fetch_web(
        self,
        query: str,
        *,
        max_results: int = 3,
        provider: object | None = None,
        client: object | None = None,
    ) -> list[Source]:
        return await self._run_async_call(
            "fetch_web",
            ai.fetch_web,
            query,
            max_results=max_results,
            provider=provider,
            client=client,
            timeout_seconds=self._source_timeout_seconds,
        )

    async def synthesize(
        self,
        question: str,
        sources: list[Source],
        *,
        llm: LLMProvider | None = None,
    ) -> AnswerWithCitations:
        return await self._run_sync_call(
            "synthesize",
            ai.synthesize,
            question,
            sources,
            llm=llm,
            timeout_seconds=self._synthesize_timeout_seconds,
        )


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _read_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


if __name__ == "__main__":
    from src.models import ResearchSession
    from src.storage.cache_store import CacheStore
    from src.services.cache import QueryCache

    session = ResearchSession(session_id="abc123", question="What is photosynthesis?")
    store = CacheStore()
    cache = QueryCache(store=store, ttl_seconds=60)

    cache.set("web", "  Photosynthesis  ", '{"answer": "ok"}')
    hit = cache.get("web", "photosynthesis")
