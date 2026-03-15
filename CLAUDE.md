# DragonLens - Agent Context
DragonLens is a brand visibility tool specifically build for the Chinese Market. 
It queries Chinese LLMs with natural prompts, extracts brand mentions and rankings, analyzes sentiment, and calculates visibility metrics.
Think of a lighter version of Profound for the Chinese market. The goal is to make DragonLens work for any arbitrary vertical.
It uses a multi-model approach — running the same prompts across multiple Chinese LLMs (Qwen, DeepSeek, Kimi, ByteDance Seed, Baidu ERNIE, MiniMax) and comparing their outputs.

## Architecture
Data flows left to right:
  UI (Streamlit) → API (FastAPI) → Workers (Celery) → LLM Providers
  Workers → Extraction Pipeline → Knowledge DB → Metrics

## Key entry points
- `workers/tasks.py`: start_run() kicks off the pipeline via Celery chord
- `services/extraction/pipeline.py`: ExtractionPipeline is the canonical extraction path
- `services/brand_recognition/`: Legacy extraction modules, being replaced by extraction/
- `models/domain.py`: All SQLAlchemy models (source of truth for DB schema)
- `models/schemas.py`: All Pydantic API schemas

## Conventions
- Prompts live in src/prompts/ as Jinja2 markdown with YAML frontmatter
- Use commit_with_retry/flush_with_retry for all DB writes (SQLite compat)
- Feature flags in services/brand_recognition/config.py
- Translation goes through services/translater.py (async with sync wrappers)

## Testing
- Write test first and write testable functions and modules
- `make test` runs all tests
- Unit tests in tests/unit/, integration in tests/integration/
- Tests use SQLite; production uses PostgreSQL
- When an implementation is finished, run a smoke test using `make example-all-mini`. Watch the logs especially on celery using `make logs-celery` while running. Fix issue when finding them in the logs

## Don't do
- Don't add exports to brand_recognition/__init__.py without strong reason
- Don't add business logic to API routers — put it in services/
- Don't use raw asyncio.run() — use _run_async() helper for sync→async bridges
- Don't use relative imports

## Style and conventions
- function 10 line max
- follow PEP 8 and uncle Bob clean code practises
- clear naming for variables, function and classes
- no # comments and """ only for API that won't change. If you think you have to write a comment, write a function instead with a descriptive name