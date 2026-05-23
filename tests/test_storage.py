"""Offline tests for src/storage/cache_store.py."""

from __future__ import annotations

import time

import pytest

from src.storage.cache_store import CacheStore


@pytest.fixture
def store() -> CacheStore:
    """In-memory SQLite store, discarded after each test."""
    s = CacheStore()
    yield s
    s.close()


# ── Basic get/set ──────────────────────────────────────────────────────────────

def test_set_and_get_returns_stored_value(store: CacheStore) -> None:
    store.set("wiki", "photosynthesis", '{"data": "ok"}')
    result = store.get("wiki", "photosynthesis")
    assert result == '{"data": "ok"}'


def test_get_missing_key_returns_none(store: CacheStore) -> None:
    assert store.get("wiki", "nonexistent") is None


def test_set_overwrites_existing_entry(store: CacheStore) -> None:
    store.set("wiki", "photosynthesis", '{"data": "old"}')
    store.set("wiki", "photosynthesis", '{"data": "new"}')
    assert store.get("wiki", "photosynthesis") == '{"data": "new"}'


# ── TTL / expiry ───────────────────────────────────────────────────────────────

def test_cleanup_expired_removes_old_entries(store: CacheStore) -> None:
    store.set("wiki", "old_query", '{"data": "stale"}')
    # TTL of 0 means everything already expired
    deleted = store.cleanup_expired(ttl_seconds=0)
    assert deleted >= 1
    assert store.get("wiki", "old_query") is None


def test_cleanup_expired_keeps_fresh_entries(store: CacheStore) -> None:
    store.set("wiki", "fresh_query", '{"data": "fresh"}')
    deleted = store.cleanup_expired(ttl_seconds=86400)
    assert deleted == 0
    assert store.get("wiki", "fresh_query") is not None


def test_cleanup_expired_rejects_negative_ttl(store: CacheStore) -> None:
    with pytest.raises(ValueError):
        store.cleanup_expired(ttl_seconds=-1)


# ── Spend log ─────────────────────────────────────────────────────────────────

def test_total_spend_empty_returns_zero(store: CacheStore) -> None:
    assert store.total_spend() == 0.0


def test_total_spend_sums_all_rows(store: CacheStore) -> None:
    store.record_spend("gemini", "photosynthesis", 0.25)
    store.record_spend("openai", "chlorophyll", 0.75)
    assert store.total_spend() == pytest.approx(1.0)


def test_spend_breakdown_groups_by_provider(store: CacheStore) -> None:
    store.record_spend("gemini", "q1", 0.10)
    store.record_spend("gemini", "q2", 0.20)
    store.record_spend("openai", "q3", 0.50)
    breakdown = store.spend_breakdown()
    sources = {row["source"]: row["cost"] for row in breakdown}
    assert sources["gemini"] == pytest.approx(0.30)
    assert sources["openai"] == pytest.approx(0.50)


def test_spend_breakdown_orders_by_cost_descending(store: CacheStore) -> None:
    store.record_spend("cheap", "q1", 0.01)
    store.record_spend("expensive", "q2", 0.99)
    breakdown = store.spend_breakdown()
    assert breakdown[0]["source"] == "expensive"


def test_most_expensive_queries_returns_sorted(store: CacheStore) -> None:
    store.record_spend("gemini", "cheap_query", 0.01)
    store.record_spend("gemini", "expensive_query", 0.99)
    store.record_spend("gemini", "medium_query", 0.50)
    results = store.most_expensive_queries(limit=2)
    assert len(results) == 2
    assert results[0]["canonical_query"] == "expensive_query"
    assert results[0]["cost_usd"] == pytest.approx(0.99)


def test_most_expensive_queries_respects_limit(store: CacheStore) -> None:
    for i in range(10):
        store.record_spend("gemini", f"query_{i}", float(i))
    results = store.most_expensive_queries(limit=3)
    assert len(results) == 3


# ── Cache hit/miss events ─────────────────────────────────────────────────────

def test_cache_hit_miss_counts_empty(store: CacheStore) -> None:
    counts = store.cache_hit_miss_counts()
    assert counts == {"hit": 0, "miss": 0}


def test_cache_hit_miss_counts_tracks_correctly(store: CacheStore) -> None:
    store.record_cache_event("wiki", "q1", "hit")
    store.record_cache_event("wiki", "q2", "hit")
    store.record_cache_event("arxiv", "q3", "miss")
    counts = store.cache_hit_miss_counts()
    assert counts["hit"] == 2
    assert counts["miss"] == 1


def test_record_cache_event_rejects_invalid_event(store: CacheStore) -> None:
    with pytest.raises(ValueError):
        store.record_cache_event("wiki", "q1", "invalid")


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_cache_metrics_returns_correct_counts(store: CacheStore) -> None:
    store.set("wiki", "q1", '{}')
    store.set("arxiv", "q2", '{}')
    store.record_spend("gemini", "q1", 0.01)
    store.record_cache_event("wiki", "q1", "hit")
    metrics = store.cache_metrics()
    assert metrics["cache_entries"] == 2
    assert metrics["spend_entries"] == 1
    assert metrics["cache_events"] == 1


# ── Context manager ───────────────────────────────────────────────────────────

def test_context_manager_closes_connection() -> None:
    with CacheStore() as s:
        s.set("wiki", "test", '{"ok": true}')
        assert s.get("wiki", "test") is not None
    # After __exit__, connection is closed — further calls should raise
    with pytest.raises(Exception):
        s.get("wiki", "test")