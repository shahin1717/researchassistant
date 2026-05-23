"""Streamlit web interface for the Async Research Assistant."""

from __future__ import annotations
import sys
import os
import asyncio
from pathlib import Path
import streamlit as st

root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_path not in sys.path:
    sys.path.insert(0, root_path)
    
from src.cli import MAX_QUESTION_CHARS, format_answer, validate_question
from src.config import settings
from src.core.researcher import research
from src.storage.cache_store import CacheStore

SOURCE_OPTIONS = {
    "Wikipedia": "wiki",
    "arXiv": "arxiv",
    "Web": "web",
}


def _run_research(question: str, sources: tuple[str, ...], no_cache: bool):
    return asyncio.run(research(question, sources=sources, no_cache=no_cache))


def _open_store() -> CacheStore:
    return CacheStore(Path(settings.cache_dir) / "cache.db")


def _render_answer() -> None:
    st.subheader("Research")
    question = st.text_area(
        "Question",
        max_chars=MAX_QUESTION_CHARS,
        placeholder="What is photosynthesis and what are its main stages?",
        height=120,
    )

    selected_labels = st.multiselect(
        "Sources",
        options=list(SOURCE_OPTIONS),
        default=list(SOURCE_OPTIONS),
    )
    no_cache = st.toggle("Bypass cache", value=False)

    if st.button("Run research", type="primary"):
        try:
            cleaned_question = validate_question(question)
        except ValueError as exc:
            st.error(str(exc))
            return

        selected_sources = tuple(SOURCE_OPTIONS[label] for label in selected_labels)
        if not selected_sources:
            st.error("Select at least one source.")
            return

        with st.spinner("Searching sources and synthesizing answer..."):
            try:
                answer = _run_research(cleaned_question, selected_sources, no_cache)
            except (RuntimeError, ValueError, TimeoutError) as exc:
                st.error(str(exc))
                return

        st.markdown("### Answer")
        st.write(answer.answer)

        st.markdown("### References")
        if not answer.citations:
            st.info("No citations were returned.")
            return

        for citation in answer.citations:
            source = citation.source
            st.markdown(f"**[{citation.index}] {source.title}**")
            st.caption(f"{source.origin} | {source.url}")

        with st.expander("Terminal format"):
            st.code(format_answer(answer), language="text")


def _render_dashboard() -> None:
    st.subheader("Developer Dashboard")
    store = _open_store()
    try:
        metrics = store.cache_metrics()
        cache_counts = store.cache_hit_miss_counts()
        total_spend = store.total_spend()
        breakdown = store.spend_breakdown()
        expensive = store.most_expensive_queries(limit=10)
    finally:
        store.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Cache entries", metrics["cache_entries"])
    col2.metric("Cache events", metrics["cache_events"])
    col3.metric("Total spend", f"${total_spend:.6f}")

    st.markdown("### Cache hits vs misses")
    st.bar_chart({"hits": cache_counts["hit"], "misses": cache_counts["miss"]})

    st.markdown("### Spend by provider")
    if breakdown:
        st.bar_chart({row["source"]: row["cost"] for row in breakdown})
        st.table(breakdown)
    else:
        st.info("No spend telemetry has been recorded yet.")

    st.markdown("### Most expensive queries")
    if expensive:
        st.table(expensive)
    else:
        st.info("Run a research query to populate cost telemetry.")


def main() -> None:
    st.set_page_config(page_title="Async Research Assistant", layout="wide")
    st.title("Async Research Assistant")

    research_tab, dashboard_tab = st.tabs(["Research", "Developer Dashboard"])
    with research_tab:
        _render_answer()
    with dashboard_tab:
        _render_dashboard()


if __name__ == "__main__":
    main()
