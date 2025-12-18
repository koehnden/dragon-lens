# CLAUDE.md – DragonLens

This repo is a **prototype for tracking brand visibility in Chinese LLMs**, starting with **local Qwen models** and later adding **remote Kimi2 / DeepSeek** with (optional) web search.

You are the coding agent helping build and maintain this project.

---

## Development Commands

### Setup

```bash
# Install dependencies
poetry install

# Copy environment template and configure
cp .env.example .env
# Edit .env to add your API keys (if using remote LLMs)

# Install Ollama (if not already installed)
# Visit https://ollama.ai or use: brew install ollama

# Pull Qwen model for Ollama
ollama pull qwen2.5:7b

# Start Redis (required for Celery)
# macOS with Homebrew:
brew services start redis
# Or using Docker:
docker run -d -p 6379:6379 redis:alpine
```

### Running the Application

```bash
# Terminal 1: Start FastAPI server
poetry run python -m src
# Or with hot reload for development:
poetry run uvicorn src.api:app --reload --port 8000

# Terminal 2: Start Celery worker
poetry run celery -A src.workers.celery_app worker --loglevel=info

# Terminal 3: Start Streamlit UI
poetry run streamlit run src/ui/app.py --server.port 8501

# Access the application:
# - Streamlit UI: http://localhost:8501
# - FastAPI docs: http://localhost:8000/docs
# - API: http://localhost:8000
```

### Development Tasks

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test file
poetry run pytest tests/unit/test_config.py

# Format code with Black
poetry run black src/ tests/

# Lint with Ruff
poetry run ruff check src/ tests/

# Type checking with MyPy
poetry run mypy src/

# Initialize/migrate database (creates tables)
poetry run python scripts/init_db.py

# Generate API documentation (Swagger/OpenAPI)
poetry run python scripts/generate_swagger.py
```

### Project Structure

```
src/
├── api/                  # FastAPI routers and app
│   ├── app.py           # Main FastAPI application
│   └── routers/         # API route handlers
│       ├── verticals.py
│       ├── tracking.py
│       └── metrics.py
├── models/              # Database models and schemas
│   ├── database.py      # SQLAlchemy setup
│   ├── domain.py        # Database models
│   └── schemas.py       # Pydantic schemas
├── services/            # LLM and external service clients
│   ├── ollama.py        # Ollama/Qwen wrapper
│   └── remote_llms.py   # DeepSeek, Kimi clients
├── workers/             # Celery tasks
│   ├── celery_app.py    # Celery configuration
│   └── tasks.py         # Background task definitions
├── ui/                  # Streamlit UI
│   ├── app.py           # Main Streamlit app
│   └── pages/           # UI pages
│       ├── setup.py
│       ├── results.py
│       └── history.py
└── config.py            # Application configuration

tests/
├── unit/                # Unit tests
└── integration/         # Integration tests
```

---

## High-level goal

Build an end-to-end system that:

- Takes a **vertical** (e.g. “SUV cars”), a list of **brands** (with competitors), and a list of **prompts** as input.
- Asks **Chinese LLMs** those prompts on a schedule.
- Extracts how often and how positively each brand is mentioned (“visibility metrics”).
- Tracks these metrics **over time** and visualizes them in a small **Streamlit UI**.

Start with **one local model (Qwen via Ollama)** and a simple pipeline; then generalize to more models and web-search variants.

---

## Versions / scope

### V1 (MVP – must have)

Focus: **single local model, end-to-end working loop**.

- Models:
  - Use **Qwen variants via Ollama** locally.
  - Use Qwen both for:
    - Answering prompts (Chinese output)
    - Utility NLP: translation, sentiment, and brand NER.
- Features:
  - Input in Streamlit: **vertical, brand list, prompt list** (English or Chinese).
  - For English prompts:
    - Translate to **Chinese** for querying the LLM.
    - Store **both** EN + ZH versions.
  - LLM answers **in Chinese**.
    - Translate back to **English** for debugging / UI.
    - Store both CH + EN answers.
  - Extract for each (prompt, answer, brand):
    - Which brands and products are mentioned.
    - Evidence snippets (in Chinese, with EN translation).
    - Basic sentiment (positive / neutral / negative) for each product
    - Basic rank for products (if the answer lists options).
  - Store results in a **local relational DB** (start with SQLite).
  - Track runs over time (timestamped, model version), but:
- Backend:
  - **FastAPI** with a small REST API for:
    - Managing verticals / brands / products / prompts.
    - Triggering a “tracking run” for a given (vertical, brand set, prompts).
    - Reading metrics for visualization.
  - Long-running tasks:
    - Use **Celery + Redis** for background jobs (running LLM calls + extraction).
    - Queue prompt of a given input and process them one by one for now.
- Frontend:
  - **Streamlit** app with:
    - Input form: vertical + brand list + prompts → “Start tracking” button (calls FastAPI, which enqueues a Celery task).
    - Result page(s):
      - Simple tables and plots for visibility metrics over time.
      - Shows brand and product sentiment metrics
      - “Last run” inspector with raw answers and extracted mentions.

### V2 (later)

Do **not** implement now; just keep code architecture ready for:

- Adding **remote models**:
  - Kimi2 (Kimi K2) via API.
  - DeepSeek via API.
- Option to enable **web search** for some engines:
  - Either via model-native tools (e.g. Kimi `$web_search`) or our own RAG+search layer.
  - Introduce **scheduling frequency** (daily / weekly) per “engine profile”.
- User choice of **which model(s)** to track:
  - Local Qwen vs remote Kimi/DeepSeek.
  - If remote usage is paid:
    - User supplies API key / account credentials via UI → stored securely (env / config, not committed).
- Cron-like scheduling (Celery beat or external cron) to run engines with websearch at specified frequency.

---

## Tech stack / constraints

- **Runtime**: Python 3.x, optimized for **MacBook Pro M1**.
- **Package management**: `poetry`.
- **Backend**:
  - REST: **FastAPI**.
  - Background tasks: **Celery + Redis**.
  - API contract: maintain **OpenAPI** via FastAPI and keep a `swagger.yaml` for external use.
- **Frontend**:
  - **Streamlit** for a minimal UI (forms + charts).
- **DB**:
  - Start with **SQLite** for local dev.
  - Use a thin abstraction (SQLAlchemy) so we can switch to Postgres later (for AWS/GCP).
- **Local LLMs**:
  - Use **Ollama** to run:
    - Qwen (for V1 main engine + translation + sentiment).
    - Possibly other small models for NLP tasks later.
- **Remote LLMs (V2+)**:
  - Kimi2 and DeepSeek accessed via official APIs only.
  - All secrets via environment variables / config files; **never commit keys**.
- **Deployment goal** (later):
  - Keep FastAPI + Celery + DB design **stateless** enough so they can be deployed to AWS / GCP with minimal changes.

---

## Key behaviours & logic

### Input handling (Streamlit)

- User provides:
  - `vertical` (string).
  - `brands` (list; allow manual input for now).
  - `prompts` (list; English or Chinese).
- On **submit**:
  - Call FastAPI to create a “tracking configuration” (vertical + brand + prompt triplet).
  - Enqueue a Celery job to:
    - Prepare translated prompts.
    - Run the model(s).
    - Store metrics.

### Language handling

- Prompts:
  - If **Chinese**: keep as-is; also store a best-effort EN translation.
  - If **English**: translate to **Chinese** (for querying), and store both.
- Answers:
  - Model should answer in **Chinese** (set via system prompt).
  - Always translate answers to **English** for UI/debugging and store both versions.
- Use Qwen (local via Ollama) as the **primary translation engine** for both directions in V1.

### Metrics (initial design, can change later)

- `Answer Share of Voice Coverage (ASoV_coverage)`
  - Definition: Fraction of prompts in the prompt set where the brand/product is mentioned at least once (#prompts_with_brand / #all_prompts).
- `Answer Share of Voice – Relative (ASoV_relative)`
  - Definition: Share of all brand mentions across the prompt set (brand_mentions / sum_all_brands_mentions).
- `Prominence Score`
  - Definition: Average position-weighted score across answers where the brand appears, e.g. mean of w(rank) with w(1)=1, w(2)=0.7, w(3)=0.4, ….
- `Top-Spot Share`
  - Definition: Fraction of prompts where the brand/product is ranked first in the answer (#prompts_where_rank1 / #all_prompts).
- `Sentiment Index`
  - Definition: Average sentiment score over all mentions, mapping Positive=+1, Neutral=0, Negative=−1 and taking the mean.
- `Positive Share`
  - Definition: Fraction of brand mentions classified as positive (#positive_mentions / #all_mentions).
- `Opportunity Rate`
  - Definition: Fraction of prompts where at least one competitor is mentioned but this brand is not (#prompts_with_competitor_without_brand / #all_prompts).
- `Dragon Visibility Score (DVS)`
  - Definition: Composite 0–100 score combining normalized ASoV_coverage, Prominence, and Positive Share with chosen weights, e.g. DVS = 100 * (α·cov_norm + β·prom_norm + γ·pos_share) / (α+β+γ).

We can refine/add metrics later; design DB tables to support this.

### Storage model (suggested)

At minimum:

- `models`:
  - id, name, type (`local`, `remote`), web_search_enabled (bool).
- `verticals`:
  - id, name, description.
- `brands`:
  - id, vertical_id, display_name, aliases (JSON).
- `products`
  - id, brand_id, display_name, aliases (JSON).
- `runs`:
  - id, model_id, vertical_id, created_at, status, error_message (if any).
- `prompts`:
  - id, vertical_id, zh_text, en_text, source_language.
- `answers`:
  - id, run_id, prompt_id, zh_answer, en_answer, raw_metadata (JSON).
- `products_mentions`:
  - id, answer_id, brand_id, product_id, mentioned (bool), rank (int/null),
    sentiment (enum), zh_snippet, en_snippet.
- `metrics` (materialized/aggregated table or view):
  - date, model_id, vertical_id, brand_id, run_id, asov_coverage, asov_relative, prominence_score, top_spot_share, sentiment_index, positive_share, opportunity_rate, dvs_score.
---

## Implementation principles for the agent

- Follow TDD! Always write unit and integration tests first and them implement the feature. Run all tests after a new implementation and reiterate if any test fails.
- Strictly follow PEP 8 conventions
- Never use relative imports
- Prefer **small, composable modules** over a big monolith.
- Write small functions with maximum 10 lines of code!
- Never any # comment. Docs string only for API function!
- Where possible, provide **type hints** and basic tests (pytest) for core logic (parsing, extraction).
- Keep local-mode as the default:
  - The project should be usable on an M1 laptop with only **Ollama, Redis, SQLite** and `poetry install`.
- All secrets (API keys) must be read from env variables or a local `.env` file (ignored by git).
- Avoid vendor lock-in and keep code open for extension: wrap LLM calls in simple adapter classes (`QwenLocalClient`, `DeepSeekClient`, `KimiClient`).
- For Celery tasks, keep them:
  - Idempotent where possible.
  - Logged (start/end, prompt counts, errors).

---

## Non-goals (for now)

- No user authentication / multi-tenant accounts.
- No advanced web UI; Streamlit is enough.
- No complex scheduling UI; if needed, scheduling can be configured in code / env and triggered via Celery beat or external cron.
- No scraping of closed LLM UIs (we only use official APIs and local models).

---

If you need to make architectural choices not specified here, prefer:

- Simpler over more complex.
- Standard, well-documented patterns over cleverness.
- Ease of local dev and later AWS/GCP deployment.

