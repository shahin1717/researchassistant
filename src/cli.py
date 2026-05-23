"""Command-line interface for the Async Research Assistant."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Sequence

from ai.schemas import AnswerWithCitations
from src.config import settings
from src.core.researcher import research
from src.storage.cache_store import CacheStore

MAX_QUESTION_CHARS = 500
SOURCE_ALIASES = {
    "wiki": "wiki",
    "wikipedia": "wiki",
    "arxiv": "arxiv",
    "web": "web",
}


def setup_logging() -> logging.Logger:
    """Return the CLI logger configured by src.config."""

    return logging.getLogger("cli")


def validate_question(question: str) -> str:
    """Normalize and validate a user question before network or LLM calls."""

    cleaned = question.strip()
    if not cleaned:
        raise ValueError("Question cannot be empty.")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise ValueError(f"Question must be {MAX_QUESTION_CHARS} characters or fewer.")
    return cleaned


def parse_sources(value: str) -> tuple[str, ...]:
    """Parse CLI source flags into canonical source identifiers."""

    selected: list[str] = []
    for raw_source in value.split(","):
        raw_source = raw_source.strip().lower()
        if not raw_source:
            continue
        canonical = SOURCE_ALIASES.get(raw_source)
        if canonical is None:
            allowed = ", ".join(sorted(SOURCE_ALIASES))
            raise ValueError(f"Unknown source {raw_source!r}. Choose from: {allowed}.")
        if canonical not in selected:
            selected.append(canonical)

    if not selected:
        raise ValueError("At least one source must be selected.")
    return tuple(selected)


def format_answer(answer: AnswerWithCitations) -> str:
    """Format a synthesized answer with clean numbered references."""

    lines = [
        "",
        "=" * 72,
        f"Question: {answer.question}",
        "",
        answer.answer,
    ]

    if not answer.citations:
        lines.extend(["", "References: none returned"])
    else:
        lines.extend(["", "References:"])
        for citation in answer.citations:
            source = citation.source
            lines.append(f"[{citation.index}] {source.title} ({source.origin})")
            lines.append(f"    {source.url}")

    lines.extend(["=" * 72, ""])
    return "\n".join(lines)


async def run_ask(
    question: str,
    sources: tuple[str, ...],
    no_cache: bool,
    logger: logging.Logger,
) -> int:
    """Execute the async research pipeline."""

    try:
        cleaned_question = validate_question(question)
    except ValueError as exc:
        logger.error("invalid_question", extra={"error": str(exc)})
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    try:
        logger.info("cli_research_start", extra={"sources": sources, "no_cache": no_cache})
        answer = await research(cleaned_question, sources=sources, no_cache=no_cache)
    except (RuntimeError, ValueError, TimeoutError) as exc:
        logger.error("research_failed", extra={"error": str(exc)})
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    sys.stdout.write(format_answer(answer))
    return 0


def run_cost_report(logger: logging.Logger) -> int:
    """Print a cost report from the spend_log table."""

    db_path = Path(settings.cache_dir) / "cache.db"
    try:
        store = CacheStore(db_path)
        total = store.total_spend()
        breakdown = store.spend_breakdown()
        expensive = store.most_expensive_queries(limit=5)
    except OSError as exc:
        logger.error("cost_report_failed", extra={"error": str(exc)})
        sys.stderr.write(f"Error: could not read telemetry database: {exc}\n")
        return 1
    finally:
        if "store" in locals():
            store.close()

    lines = [
        "",
        "=" * 48,
        "Cost Report",
        "=" * 48,
        f"Total spend: ${total:.6f}",
        "",
    ]

    if breakdown:
        lines.append("Breakdown by provider:")
        for row in breakdown:
            lines.append(f"- {row['source']}: ${row['cost']:.6f}")
    else:
        lines.append("No spend recorded yet.")

    if expensive:
        lines.extend(["", "Most expensive queries:"])
        for row in expensive:
            lines.append(f"- ${row['cost_usd']:.6f}: {row['canonical_query']}")

    lines.extend(["=" * 48, ""])
    sys.stdout.write("\n".join(lines))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Async Research Assistant CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_p = subparsers.add_parser("ask", help="Ask a research question")
    ask_p.add_argument("question", help="The question to ask")
    ask_p.add_argument(
        "--sources",
        type=str,
        default="wiki,arxiv,web",
        help="Comma-separated list of sources (e.g., wiki,arxiv,web)",
    )
    ask_p.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache for this query",
    )

    subparsers.add_parser("cost-report", help="View spend report")

    args = parser.parse_args(argv)
    logger = setup_logging()

    if args.command == "ask":
        try:
            sources = parse_sources(args.sources)
        except ValueError as exc:
            logger.error("invalid_sources", extra={"error": str(exc)})
            sys.stderr.write(f"Error: {exc}\n")
            return 1
        return asyncio.run(run_ask(args.question, sources, args.no_cache, logger))
    if args.command == "cost-report":
        return run_cost_report(logger)

    return 1


if __name__ == "__main__":
    sys.exit(main())
