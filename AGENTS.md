# Repository Guidelines
This repo is a **prototype for tracking brand visibility in Chinese LLMs**, starting with **local Qwen models** and later adding **remote Kimi2 / DeepSeek** with (optional) web search.
You are the coding agent helping build and maintain this project.

## Project Structure & Module Organization
- `src/`: application code
  - `src/api/`: FastAPI app and routers
  - `src/services/`: LLM clients and pipeline services
    - `src/services/brand_recognition/`: Brand and product extraction from prompt responses
  - `src/workers/`: Celery tasks and worker setup
  - `src/models/`: SQLAlchemy models and Pydantic schemas
  - `src/ui/`: Streamlit UI pages and app entrypoint
- `tests/`: automated tests (`unit/`, `integration/`, `smoke/`)
- `scripts/`: one-off utilities (DB init, Swagger generation, data loading)
- `docs/`: API design, swagger, and test summaries
- `data/`: local caches (e.g., Wikidata)

## Build, Test, and Development Commands
- `source /Users/denniskoehn/Library/Caches/pypoetry/virtualenvs/dragonlens-jMPIaC1x-py3.11/bin/activate` to activate the virtualenv with all dependencies installed
- `make setup`: installs Poetry, dependencies, and the local model.
- `make run`: starts Redis, Ollama, FastAPI, and Celery.
- `make dev`: starts services with API auto-reload.
- `make stop`: stops all services.
- `make test`, `make test-unit`, `make test-integration`, `make test-smoke`: run test suites.
- `make test-coverage`: pytest with coverage reports.
- `poetry run black src/ tests/`, `poetry run ruff check src/`, `poetry run mypy src/`: format, lint, type-check.

## Coding Style & Naming Conventions
- Python 3.11, 4-space indentation, PEP 8.
- Follow TDD! Always write unit and integration tests first and them implement the feature. Run all tests after a new implementation and reiterate if any test fails.
- Document driven development (DDD) when writing API endpoints. Write the endpoint requirements first in `docs/swagger.yaml`
- avoid relative imports.
- Prefer **small, composable modules** over a big monolith.
- Write small functions with maximum 10 lines of code!
- Never any # comment. Docs string only for API function! If you think you need a comment, write function with a descriptive name instead
- Where possible, provide **type hints** and basic tests (pytest) for core logic (parsing, extraction).
- Keep local-mode as the default:
  - The project should be usable on an M1 laptop with only **Ollama, Redis, SQLite** and `poetry install`.
- All secrets (API keys) must be read from env variables or a local `.env` file (ignored by git).
- Avoid vendor lock-in and keep code open for extension: wrap LLM calls in simple adapter classes (`QwenLocalClient`, `DeepSeekClient`, `KimiClient`).
- For Celery tasks, keep them:
  - Idempotent where possible.
  - Logged (start/end, prompt counts, errors).
- Tests follow `test_*.py` naming with `test_` functions.

## Testing Guidelines
- Frameworks: pytest, pytest-asyncio, pytest-cov.
- Prefer unit tests in `tests/unit/`, integration tests in `tests/integration/`, and smoke tests in `tests/smoke/`.
- Run focused tests with `poetry run pytest tests/unit/test_file.py -v` before the full suite.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and usually lower-case (e.g., "add knowledge graph", "fix make example re-run logic").
- PRs should include: a clear summary, tests run, linked issues, and screenshots for UI changes.
- If API behavior changes, regenerate Swagger with `poetry run python scripts/generate_swagger.py` and update `docs/swagger.yaml`.

## Security & Configuration Tips
- Use `.env` for local secrets; never commit API keys.
- Redis is required for Celery; Ollama is required for local Qwen.

## Agent-Specific Instructions
- See `CLAUDE.md` for architecture goals and additional constraints (TDD emphasis, small functions, no relative imports).
