"""TTL-aware cache wrapper for research source responses."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from src.models import QueryResult
from src.storage.cache_store import CacheStore


class QueryCache:
    """Small cache service keyed by `(source, canonical_query)`."""

    def __init__(
        self,
        store: CacheStore | None = None,
        *,
        ttl_seconds: int = 86_400,
        logger: logging.Logger | None = None,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self._store = store or CacheStore()
        self._ttl_seconds = ttl_seconds
        self._logger = logger or logging.getLogger(__name__)

    @staticmethod
    def canonicalize_query(query: str) -> str:
        """Normalize a query into a stable cache key fragment."""

        return query.strip().lower()

    def _normalize_source(self, source: str) -> str:
        normalized = source.strip().lower()
        if not normalized:
            raise ValueError("source must be non-empty")
        return normalized

    def get(self, source: str, query: str) -> QueryResult | None:
        """Look up a cached response for the supplied query."""

        normalized_source = self._normalize_source(source)
        canonical_query = self.canonicalize_query(query)
        self._store.cleanup_expired(self._ttl_seconds)
        response_json = self._store.get(normalized_source, canonical_query)
        if response_json is None:
            self._logger.info(
                "cache_miss",
                extra={"source": normalized_source, "canonical_query": canonical_query},
            )
            return None

        now = datetime.now(UTC)
        result = QueryResult(
            source=normalized_source,
            query=query.strip(),
            canonical_query=canonical_query,
            response_json=response_json,
            retrieved_at=now,
            cached=True,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        self._logger.info(
            "cache_hit",
            extra={"source": normalized_source, "canonical_query": canonical_query},
        )
        return result

    def set(self, source: str, query: str, response_json: str) -> QueryResult:
        """Store a response and return the normalized cache entry."""

        normalized_source = self._normalize_source(source)
        canonical_query = self.canonicalize_query(query)
        self._store.set(normalized_source, canonical_query, response_json)
        now = datetime.now(UTC)
        result = QueryResult(
            source=normalized_source,
            query=query.strip(),
            canonical_query=canonical_query,
            response_json=response_json,
            retrieved_at=now,
            cached=False,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        self._logger.info(
            "cache_store",
            extra={"source": normalized_source, "canonical_query": canonical_query},
        )
        return result

    def cleanup_expired(self) -> int:
        """Remove expired entries using the configured TTL."""

        deleted = self._store.cleanup_expired(self._ttl_seconds)
        self._logger.info("cache_cleanup", extra={"deleted": deleted})
        return deleted
