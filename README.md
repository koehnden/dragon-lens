# DragonLens 🐉

**Track how Chinese LLMs talk about your brand**

DragonLens is a brand visibility tracking system for Chinese LLMs. It helps you understand how AI models like Qwen, DeepSeek, and Kimi mention and rank your brand compared to competitors.

## Features

- 🤖 **Multi-LLM Support**: Track across Qwen (local), DeepSeek, and Kimi (V2)
- 📊 **Visibility Metrics**: Mention rates, rankings, sentiment analysis
- 🌐 **Bilingual**: Works with English and Chinese prompts
- 🎨 **Easy UI**: Streamlit-based interface for setup and visualization
- 🔄 **Background Processing**: Celery-powered async task execution
- 💾 **Persistent Storage**: SQLite (or PostgreSQL) for all data

## Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- [Ollama](https://ollama.ai/) (for local Qwen models)
- Redis (for Celery task queue)

### Installation

```bash
# 1. Install dependencies
poetry install

# 2. Configure environment
cp .env.example .env
# Edit .env if you need to use remote LLMs (DeepSeek, Kimi)

# 3. Install and start Ollama
brew install ollama
ollama pull qwen2.5:7b

# 4. Start Redis
brew services start redis
# Or: docker run -d -p 6379:6379 redis:alpine
```

### Running

Open 3 terminal windows:

```bash
# Terminal 1: FastAPI Backend
poetry run python -m src

# Terminal 2: Celery Worker
poetry run celery -A src.workers.celery_app worker --loglevel=info

# Terminal 3: Streamlit UI
poetry run streamlit run src/ui/app.py
```

Then open your browser to:
- **UI**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs

## Usage

1. **Setup**: Go to "Setup & Start" page
   - Enter your vertical (e.g., "SUV Cars")
   - Add brands with Chinese/English aliases
   - Add prompts to ask LLMs
   - Select model (Qwen, DeepSeek, Kimi)
   - Click "Start Tracking"

2. **View Results**: Go to "View Results" page
   - Select vertical and model
   - View mention rates, rankings, sentiment
   - Analyze brand visibility metrics

3. **Track History**: Go to "Runs History" page
   - See all tracking runs
   - Monitor job status
   - View run details

## Project Structure

```
src/
├── api/          # FastAPI REST API
├── models/       # Database models (SQLAlchemy)
├── services/     # LLM clients (Ollama, DeepSeek, Kimi)
├── workers/      # Celery background tasks
├── ui/           # Streamlit interface
└── config.py     # Configuration management

tests/
├── unit/         # Unit tests
└── integration/  # Integration tests
```

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src/ tests/

# Lint
poetry run ruff check src/

# Type check
poetry run mypy src/
```

## Architecture

- **Backend**: FastAPI for REST API
- **Task Queue**: Celery + Redis for async processing
- **Database**: SQLAlchemy (SQLite default, Postgres ready)
- **Frontend**: Streamlit for UI
- **LLMs**: Ollama (local Qwen) + Remote APIs (DeepSeek, Kimi)

## Roadmap

### V1 (Current)
- ✅ Local Qwen via Ollama
- ✅ Basic tracking pipeline
- ✅ Streamlit UI
- ✅ SQLite storage
- ⏳ Brand mention extraction
- ⏳ Sentiment analysis
- ⏳ Ranking detection

### V2 (Future)
- ⬜ DeepSeek integration
- ⬜ Kimi integration with web search
- ⬜ Scheduled tracking jobs
- ⬜ Advanced metrics (DVS, ASoV)
- ⬜ PostgreSQL support
- ⬜ Multi-tenant support

## License

MIT

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and architecture details.
