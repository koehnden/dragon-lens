# DragonLens - Agent Context

DragonLens is a brand visibility tool for the Chinese market.
It queries Chinese LLMs with natural prompts, extracts brand mentions and rankings, analyzes sentiment, and calculates visibility metrics.
Multi-model approach: same prompts across Qwen, DeepSeek, Kimi, ByteDance Seed, Baidu ERNIE, MiniMax — comparing outputs.

## Architecture

Data flows left to right:
  UI (Streamlit) → API (FastAPI) → Workers (Celery + Redis) → LLM Providers
  Workers → Extraction Pipeline → Knowledge DB → Metrics

Two ORM bases share one PostgreSQL engine:
- `models.database.Base` — main app tables (runs, brands, mentions, metrics)
- `models.knowledge_database.KnowledgeBase` — knowledge tables (validated brands/products, aliases, rejected entities, feedback)

Sentiment analysis runs as a separate microservice (`services/sentiment_server.py` on port 8100) using Erlangshen-RoBERTa-110M, with Qwen fallback.

## Key Entry Points

- `workers/tasks.py`: `start_run()` — chord-based pipeline: `ensure_llm_answer` → `ensure_extraction` → `finalize_run`
- `services/extraction/pipeline.py`: `ExtractionPipeline` — the canonical extraction path (3-step: KB match → Qwen batch → OpenRouter consolidation/validation)
- `models/domain.py`: All SQLAlchemy models for main DB (source of truth for DB schema)
- `models/knowledge_domain.py`: All SQLAlchemy models for knowledge DB
- `models/schemas.py`: All Pydantic API schemas
- `services/remote_llms.py`: `LLMRouter` resolves provider/model to service+route; `OpenRouterService`, `DeepSeekService`, `KimiService` extend `OpenAICompatibleService`
- `services/base_llm.py`: `OpenAICompatibleService` — base class for all remote LLM adapters
- `config.py`: Single `Settings` class (pydantic-settings), reads from `.env`

## Known Debt / Migration State

- `services/brand_recognition/` is LEGACY — being replaced by `services/extraction/`.
  Do not build new features on brand_recognition. Do not add exports to `brand_recognition/__init__.py` (already 80+ symbols).
- `workers/tasks.py` contains three execution paths: chord-based `start_run` (current), legacy `run_vertical_analysis` (deprecated), and `_process_run_inline` (test-only). Only extend `start_run`.
- `constants/__init__.py` has a large re-export block — avoid adding to it.

## Environment Setup

```bash
make setup    # Poetry, Ollama, Qwen model, dependencies
make run      # PostgreSQL, Redis, Ollama, API, Celery, sentiment service, Streamlit
make stop     # Stop all services
```

Requires: Docker (PostgreSQL + Redis), Ollama with `qwen2.5:7b-instruct-q4_0`, Python 3.11+.
Optional: OpenRouter API key for extraction consolidation and vertical seeding.

## Repo Conventions

- Prompts live in `src/prompts/` as Jinja2 markdown with YAML frontmatter. Load via `prompts.loader.load_prompt()` or `services/brand_recognition/prompts.py`.
- Use `commit_with_retry` / `flush_with_retry` for all DB writes (SQLite compat in tests).
- Feature flags in `services/brand_recognition/config.py` (env vars like `ENABLE_QWEN_EXTRACTION`).
- Translation goes through `services/translater.py` (async with sync wrappers).
- Don't use raw `asyncio.run()` — use `_run_async()` helper for sync→async bridges (defined in `workers/tasks.py` and `services/brand_recognition/async_utils.py`).
- Don't add business logic to API routers — put it in `services/`.
- Alembic manages PostgreSQL migrations (`models/migrations.py`). SQLite uses inline migration functions in `models/database.py`.

## Adding a New LLM Provider

1. Create a new class in `services/remote_llms.py` extending `OpenAICompatibleService` from `services/base_llm.py`.
2. Add the provider to `LLMProvider` enum in `models/domain.py`.
3. Add API key config to `config.py` Settings and `services/base_llm.py` `ENV_API_KEYS`.
4. Register in `LLMRouter._create_service()`.
5. Add pricing in `services/pricing.py` if available.

## Extraction Pipeline (canonical path)
Note: The goal is to make DragonLens work for any arbitrary vertical. No hardcoding rule for specific verticals!

`services/extraction/pipeline.py` → `ExtractionPipeline`:
1. **Seed** — `VerticalSeeder` cold-starts knowledge base from user brands + OpenRouter LLM call
2. **Per-response**: parse items → `KnowledgeBaseMatcher` (KB match) → `QwenBatchExtractor` (Qwen 7B for unmatched items) → Latin token enrichment
3. **Finalize** (run-level): `ExtractionConsultant` normalizes aliases, consolidates product variants, validates relevance via OpenRouter → persists to knowledge DB

## Available Make Commands

Run `make help` to see all available commands (setup, services, examples, evaluation, logs).

## Testing

- `make test` runs all tests.
- Unit tests in `tests/unit/`, integration in `tests/integration/`, smoke in `tests/smoke/`.
- Tests use SQLite; production uses PostgreSQL.
- After any pipeline change, run `make example-all-mini` as end-to-end smoke test. Watch celery logs via `make logs-celery` while running. Fix issues found in logs.