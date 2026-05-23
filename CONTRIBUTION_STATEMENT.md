# Contribution Statement

**Team:** Paputu 
**Topic:** Topic 4 — Async Research Assistant  
**Repository:** https://github.com/shahin1717/researchassistant  
**Final tag:** `v1.0-final`  
**Submission date:** 2026-05-23

---

## Member A — Shahin Alakparov (`@shahin1717`)

**Owned (sole author):**
- `src/config.py` — Pydantic settings, logging setup, env forwarding
- `src/concurrency/orchestrator.py` — `fetch_all()`, `asyncio.gather`, per-source `_timed()` wrapper, `asyncio.timeout` per task
- `src/core/researcher.py` — full pipeline: cache check → parallel fetch → cache store → LLM synthesis → cost telemetry
- `scripts/bench.py` — sequential vs parallel benchmark (measured 4.0× speedup)
- `scripts/demo.py` — runs all 5 research questions, saves to `artefacts/`
- `docs/architecture.md` — architecture diagram and design decisions
- `.github/workflows/ci.yml` — GitHub Actions CI (lint, typecheck, test, docker)
- `tests/test_storage.py` — 17 storage tests (100% coverage on `cache_store.py`)
- `tests/test_researcher.py` — 5 researcher error-path tests
- PRs: #1 (orchestrator), #2 (GitHub Actions), #4 (integrate services), #7 (fix paths), #8 (fix orchestrator timings), #9 (more tests)

**Co-owned:**
- `src/models.py` — reviewed and integrated with Raul's services layer
- `src/services/ai_service.py` — integrated token budget limiter written by Raul; added logging formatter fix

**Reviewed:**
- PRs #3 (Raul/services), #5 (Raul/services v2), #6 (Nicat/cli)

**Approximate share of commits:** 82% (30 commits combining `shahin1717` and `Shahin Alakparov` identities — both are the same person due to different git configs on different machines)

---

## Member B — Raul Aghayev (`@Raghayev17889`)

**Owned (sole author):**
- `src/services/ai_service.py` — `AIService` class, Tenacity retry logic, `asyncio.Semaphore` concurrency bound, `asyncio.wait_for` per-call timeout, `TokenBudgetLimiter` sliding-window TPM rate limiter
- `src/services/cache.py` — `QueryCache`, `canonicalize_query()`, TTL cleanup, hit/miss event logging
- `src/storage/cache_store.py` — SQLite backend, 3 tables (`cache_entries`, `spend_log`, `cache_events`), thread-safe `RLock`, telemetry helpers
- `src/models.py` — `ResearchSession` and `QueryResult` frozen Pydantic models
- PRs: #3 (services initial), #5 (services v2 — User-Agent fix, arXiv HTTPS, guard dev snippet)

**Co-owned:**
- `src/core/researcher.py` — cache integration patterns used by Shahin

**Reviewed:**
- PRs #1 (orchestrator), #4 (integrate services)

**Approximate share of commits:** 5% (2 commits — Raul worked heavily on the services layer but most integration commits were made by Shahin after review sessions)

> **Note on low commit count:** Raul owned `ai_service.py`, `cache.py`, `cache_store.py`, and `models.py` — verified by PR #3 and #5 which he authored. The low commit count reflects that integration was done by the lead developer (Shahin) after code review sessions, not that Raul contributed less code. The token budget limiter (`TokenBudgetLimiter`) and the full SQLite telemetry layer are Raul's work.

---

## Member C — Nicat (Nijat) Alaskarli (`@NicatAlaskarli`)

**Owned (sole author):**
- `src/cli.py` — full `argparse` CLI: `ask` and `cost-report` subcommands, input validation (empty/500-char limit), `parse_sources()`, `format_answer()`
- `src/app.py` — Streamlit web UI with Research tab and Developer Dashboard (cache hit/miss telemetry, spend breakdown, expensive queries)
- `Dockerfile` — multi-stage build (`python:3.11-slim` builder → runtime), non-root `appuser`, exposes port 8501
- `tests/test_se_layer.py` — 10 offline SE tests (orchestrator, cache, CLI, end-to-end)
- `tests/test_ai_service.py` — 3 token budget limiter tests
- `tests/conftest.py` — shared fixtures (`wiki_source`, `arxiv_source`, `mock_answer`)
- PR: #6 (nicat/cli)

**Co-owned:**
- `src/cli_demo.py` — demo CLI shared with Shahin
- `requirements.txt` — added `streamlit>=1.0`

**Reviewed:**
- PRs #4 (integrate services), #8 (fix orchestrator)

**Approximate share of commits:** 13% (6 commits combining `NicatAlaskarli` and `Nijat Alaskarli` identities — same person, different git configs)

---

## AI tool disclosure

| Module / file | Assistant | What we did with it |
|---|---|---|
| `src/concurrency/orchestrator.py` | Claude (Anthropic) | Claude suggested the `_timed()` coroutine wrapper and `asyncio.timeout()` per-task placement. Team reviewed and confirmed correctness — specifically that `_timed` catches exceptions so `asyncio.gather` needs no `return_exceptions=True`. |
| `tests/test_storage.py` | Claude (Anthropic) | Claude scaffolded the test structure and fixture setup. Team reviewed all 17 tests, corrected the `CacheStore` constructor calls, and verified against the actual SQLite schema. |
| `tests/test_researcher.py` | Claude (Anthropic) | Claude suggested error-path test cases. Team adjusted the `monkeypatch` targets to match actual module import paths. |
| `scripts/demo.py` | None | --- |
| `src/config.py` (`_ExtraFormatter`) | None | --- |
| `report.tex` | Claude (Anthropic) | Claude drafted the full report based on actual source code. Team will review every section before submission and is prepared to defend all technical claims during oral defense. |

We affirm that we **can defend every line of code** in this repository during the oral defense.

---

## Signatures

By signing below, we affirm that:
- The contributions described above are accurate.
- The commit percentages reflect actual work, not artificially split commits.
- Every line of code in the repository can be defended by at least one team member.
- AI assistant usage has been disclosed as described above.

| Member | Signature | Date |
|---|---|---|
| Shahin Alakparov | __________________________ | 2026-05-23 |
| Raul Aghayev | __________________________ | 2026-05-23 |
| Nicat (Nijat) Alaskarli | __________________________ | 2026-05-23 |