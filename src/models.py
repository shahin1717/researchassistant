"""Shared Pydantic models for the Async Research Assistant SE layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchSession(BaseModel):
    """Typed request metadata passed across the SE layer."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    session_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    sources: tuple[str, ...] = Field(default_factory=tuple, alias="allowed_sources")
    use_cache: bool = True
    cache_ttl_seconds: int = Field(default=86_400, ge=0)
    max_parallel: int = Field(default=10, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("session_id", "question")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must be non-empty")
        return cleaned

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value if item.strip())
        return cleaned

    @property
    def allowed_sources(self) -> tuple[str, ...]:
        """Backward-compatible name for callers that prefer `allowed_sources`."""

        return self.sources


class QueryResult(BaseModel):
    """Normalized result from a single source query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1)
    query: str = Field(min_length=1)
    canonical_query: str = Field(min_length=1)
    response_json: str = Field(min_length=1)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cached: bool = False
    expires_at: datetime | None = None

    @field_validator("source", "query", "canonical_query", "response_json")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must be non-empty")
        return cleaned

    @property
    def cache_key(self) -> str:
        """Return the stable cache key used by storage and cache wrappers."""

        return f"{self.source}:{self.canonical_query}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for CLI and logging."""

        return {
            "source": self.source,
            "query": self.query,
            "canonical_query": self.canonical_query,
            "response_json": self.response_json,
            "retrieved_at": self.retrieved_at.isoformat(),
            "cached": self.cached,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
