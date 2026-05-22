"""Retrying service wrapper around the provided `ai` module."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import ai
from ai.providers.base import LLMProvider, ProviderError
from ai.schemas import AnswerWithCitations, Source
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt, wait_exponential


T = TypeVar("T")


class AIService:
    """Thin provider-agnostic wrapper around the `ai.*` functions."""

    def __init__(
        self,
        *,
        max_parallel: int | None = None,
        source_timeout_seconds: float | None = None,
        synthesize_timeout_seconds: float | None = None,
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
                        return result
        except retry_exceptions as error:
            duration_ms = (time.monotonic() - start) * 1000.0
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

    print(session)
    print(hit.response_json if hit else "cache miss")
