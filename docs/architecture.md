# Architecture — Async Research Assistant

## Module map

```
User
 │
 ▼
src/cli.py  (Nicat)
 │  --sources wiki,arxiv,web
 │  --no-cache
 ▼
src/core/researcher.py
 │  validates question
 │  calls orchestrator
 │  calls synthesizer
 ▼
src/concurrency/orchestrator.py
 │  asyncio.gather (parallel)
 │  per-source asyncio.timeout()
 │  graceful degradation → []
 ├──────────────────┬──────────────────┐
 ▼                  ▼                  ▼
ai.fetch_wikipedia  ai.fetch_arxiv     ai.fetch_web
 │                  │                  │
 └──────────────────┴──────────────────┘
                    │
             list[Source]
                    │
                    ▼
         src/services/cache.py  (Raul)
         keyed by (source, query)
         TTL = CACHE_TTL_SECONDS
                    │
                    ▼
         ai.synthesize(question, sources)
                    │
             AnswerWithCitations
                    │
                    ▼
                CLI output
```

## Key design decisions

**Why asyncio.gather with per-source timeout?**
Each source (Wikipedia, arXiv, web) is independent. Running them in parallel reduces
wall-clock time from ~sum(latencies) to ~max(latency). Per-source `asyncio.timeout()`
ensures one slow source does not block the other two.

**Why graceful degradation?**
If arXiv times out, the answer is still produced from Wikipedia + web. The user gets
a result with a note about the missing source rather than a crash.

**Why a shared httpx.AsyncClient?**
Connection reuse across all three fetchers roughly doubles throughput by avoiding
repeated TLS handshakes.

**Why canonical cache keys?**
`"What is photosynthesis?"` and `"what is photosynthesis"` hit the same cache entry.
Implemented by lowercasing and stripping the query before hashing.

## Data flow

```
question (str)
  → orchestrator → 3x async fetch → list[Source]
  → cache check (Raul)
  → synthesize(question, sources) → AnswerWithCitations
  → CLI renders answer + numbered references
```

## Concurrency model

| Layer | Tool | Why |
|---|---|---|
| Source fetching | asyncio.gather | I/O bound, 3 independent HTTP calls |
| Semaphore | asyncio.Semaphore(MAX_PARALLEL) | Respect provider rate limits |
| Per-source timeout | asyncio.timeout() | Isolate slow sources |
| HTTP client | httpx.AsyncClient | Shared connection pool |

## Module ownership

| Module | Owner |
|---|---|
| src/config.py | Shahin |
| src/concurrency/orchestrator.py | Shahin |
| src/core/researcher.py | Shahin |
| scripts/bench.py | Shahin |
| src/services/ai_service.py | Raul |
| src/services/cache.py | Raul |
| src/storage/cache_store.py | Raul |
| src/models.py | Raul |
| src/cli.py | Nicat |
| tests/ | Nicat |
| Dockerfile | Nicat |
| README.md | Nicat |