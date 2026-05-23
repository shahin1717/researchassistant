# Async Research Assistant

Async Research Assistant answers a research question by querying Wikipedia,
arXiv, and a web-search provider in parallel, caching source results in SQLite,
and synthesizing a cited answer with an LLM.

**Team:** Shahin, Raul, Nicat (Niijat)  
**Topic:** 4 — Async Research Assistant  
**Target tag:** `v1.0-final`

## Setup

```bash
git clone https://github.com/shahin1717/researchassistant
cd researchassistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with the provider keys you plan to use. Do not commit real keys.

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `LLM_PROVIDER` | yes | `gemini` | `gemini`, `openai`, or `anthropic` |
| `LLM_MODEL` | no | `gemini-2.0-flash` | Model used for synthesis |
| `GOOGLE_API_KEY` | provider-specific | empty | Gemini API key |
| `OPENAI_API_KEY` | provider-specific | empty | OpenAI API key |
| `ANTHROPIC_API_KEY` | provider-specific | empty | Anthropic API key |
| `WEB_SEARCH_PROVIDER` | no | `tavily` | `tavily`, `serper`, or `duckduckgo` |
| `TAVILY_API_KEY` | provider-specific | empty | Tavily search key |
| `SERPER_API_KEY` | provider-specific | empty | Serper search key |
| `CACHE_DIR` | no | `./.cache` | SQLite cache and telemetry directory |
| `CACHE_TTL_SECONDS` | no | `86400` | Cache entry lifetime |
| `PER_SOURCE_TIMEOUT_SECONDS` | no | `10` | Timeout per source fetch |
| `MAX_SOURCES_PER_QUERY` | no | `3` | Results fetched per source |
| `MAX_PARALLEL` | no | `10` | Async concurrency bound |
| `LOG_LEVEL` | no | `INFO` | Python logging level |

## CLI

Ask a question:

```bash
python -m src ask "What is photosynthesis and what are its main stages?"
```

Restrict sources and bypass cache:

```bash
python -m src ask "What is chlorophyll?" --sources wiki,arxiv --no-cache
```

Show cost telemetry from SQLite:

```bash
python -m src cost-report
```

The CLI rejects empty questions and questions longer than 500 characters before
calling any source or LLM provider.

## Streamlit Web UI

```bash
streamlit run src/app.py
```

The web UI includes a research tab and a developer dashboard with cache
hit/miss telemetry, cache entry counts, total spend, provider spend breakdowns,
and the most expensive queries.

## Docker

Build and run the Streamlit app:

```bash
docker build -t researchassistant:latest .
docker run --env-file .env -p 8501:8501 researchassistant:latest
```

Open `http://localhost:8501`.

Run the CLI inside the image:

```bash
docker run --env-file .env researchassistant:latest python -m src ask "What is photosynthesis?"
```

The Dockerfile uses a builder stage plus a slim runtime stage.

## Tests

Run the offline SE layer suite:

```bash
pytest tests/test_se_layer.py -q
```

Run the full suite:

```bash
pytest -q
```

The SE layer tests mock source fetchers and LLM synthesis, so they require no
network access and no real API keys.

## Sequential vs Parallel Benchmark

Shahin's integrated benchmark result:

| Workload | Sequential | Parallel | Speedup |
|---|---:|---:|---:|
| Wikipedia, arXiv, and web source fetching | 17.35s | 4.37s | 4.0x |

Reproduce with:

```bash
python scripts/bench.py
```

## Project Layout

```text
ai/                 Provided AI contract; do not modify
src/config.py       Pydantic settings and logging
src/models.py       Pydantic SE-layer models
src/concurrency/    Parallel source orchestrator
src/core/           Research pipeline coordinator
src/services/       Cache and AI wrappers
src/storage/        SQLite cache and telemetry
src/cli.py          argparse CLI
src/app.py          Streamlit UI
tests/              Offline and smoke tests
scripts/bench.py    Sequential vs parallel benchmark
```

## Notes

- Source and synthesis results depend on configured API keys and provider
  availability.
- SQLite cache and telemetry are stored under `CACHE_DIR`.
- The `ai/` package is treated as a locked contract for the coursework.
