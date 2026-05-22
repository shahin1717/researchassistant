"""SQLite-backed cache storage for research queries."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from time import time
from typing import Any


class CacheStore:
    """Small SQLite store for `(source, canonical_query)` cache entries."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._in_memory = db_path is None
        self._db_path = ":memory:" if db_path is None else str(db_path)
        if db_path is not None:
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.create_tables()

    def create_tables(self) -> None:
        """Create the cache and spend-log tables if they do not exist."""

        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    source TEXT NOT NULL,
                    canonical_query TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (source, canonical_query)
                );

                CREATE TABLE IF NOT EXISTS spend_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    canonical_query TEXT NOT NULL,
                    cost_usd REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()

    def get(self, source: str, canonical_query: str) -> str | None:
        """Return a cached JSON payload if one exists."""

        with self._lock:
            row = self._conn.execute(
                """
                SELECT response_json
                FROM cache_entries
                WHERE source = ? AND canonical_query = ?
                """,
                (source, canonical_query),
            ).fetchone()
        if row is None:
            return None
        return str(row["response_json"])

    def set(self, source: str, canonical_query: str, response_json: str) -> None:
        """Insert or replace a cache entry."""

        created_at = time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cache_entries (source, canonical_query, response_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source, canonical_query) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (source, canonical_query, response_json, created_at),
            )
            self._conn.commit()

    def cleanup_expired(self, ttl_seconds: int) -> int:
        """Delete rows older than the supplied TTL and return the row count."""

        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        cutoff = time() - ttl_seconds
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM cache_entries WHERE created_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount if cursor.rowcount is not None else 0
            self._conn.commit()
        return int(deleted)

    def record_spend(self, source: str, canonical_query: str, cost_usd: float) -> None:
        """Persist a cost telemetry row for a source call."""

        created_at = time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO spend_log (source, canonical_query, cost_usd, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source, canonical_query, cost_usd, created_at),
            )
            self._conn.commit()

    def total_spend(self) -> float:
        """Return the total recorded spend across all rows."""

        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total_cost FROM spend_log"
            ).fetchone()
        return float(row["total_cost"] if row is not None else 0.0)

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        with self._lock:
            self._conn.close()

    def __enter__(self) -> CacheStore:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
