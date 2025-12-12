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

- **Docker** (for Redis)
- **macOS** (for automatic Ollama installation via Homebrew)
- Python 3.11+ will be managed by Poetry

### One-Command Setup

```bash
# Install everything (Poetry, Ollama, Qwen model, dependencies)
make setup
```

This will:
- Install Poetry if not present
- Install Ollama if not present (macOS only)
- Install Python dependencies
- Pull Qwen 2.5:7b model
- Set up the environment

### Configuration

```bash
# Copy environment template and configure (optional)
cp .env.example .env
# Edit .env if you need to use remote LLMs (DeepSeek, Kimi)
```

### Running All Services

```bash
# Start Redis, Ollama, FastAPI, and Celery in background
make run
```

This will start:
- **Redis**: Docker container on port 6379
- **Ollama**: Local LLM service
- **FastAPI**: REST API on http://localhost:8000
- **Celery**: Background task worker

Access the application:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Stopping Services

```bash
# Stop all services
make stop
```

### Development Mode (with auto-reload)

```bash
# Start services with FastAPI auto-reload
make dev
```

This starts Redis and Ollama, then runs FastAPI with auto-reload enabled. Keep this running and start Celery in another terminal if needed.

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

### Testing

```bash
# Run all tests (unit + integration + smoke)
make test

# Run specific test suites
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-smoke         # Smoke tests only

# Run tests with coverage report
make test-coverage
```

### Code Quality

```bash
# Format code
poetry run black src/ tests/

# Lint
poetry run ruff check src/

# Type check
poetry run mypy src/
```

### Service Management

```bash
# Check status of all services
make status

# View logs
make logs

# Clean up temporary files and logs
make clean
```

## Available Make Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make setup` | Complete setup - install all dependencies and models |
| `make check-deps` | Check if all dependencies are installed |
| `make install-poetry` | Install Poetry if not already installed |
| `make install-ollama` | Install Ollama if not already installed (macOS only) |
| `make install-deps` | Install Python dependencies with Poetry |
| `make pull-qwen` | Pull Qwen model for Ollama |
| `make run` | Start all services (Redis, Ollama, API, Celery) |
| `make dev` | Start services in development mode (with auto-reload) |
| `make stop` | Stop all services |
| `make start-redis` | Start Redis using Docker Compose |
| `make stop-redis` | Stop Redis |
| `make start-ollama` | Start Ollama service |
| `make start-api` | Start FastAPI server |
| `make start-celery` | Start Celery worker |
| `make test` | Run all tests (unit + integration + smoke) |
| `make test-unit` | Run unit tests only |
| `make test-integration` | Run integration tests only |
| `make test-smoke` | Run smoke tests only |
| `make test-coverage` | Run tests with coverage report |
| `make status` | Show status of all services |
| `make logs` | Tail all logs |
| `make clean` | Clean up temporary files and logs |

## Architecture

- **Backend**: FastAPI for REST API
- **Task Queue**: Celery + Redis (via Docker Compose) for async processing
- **Database**: SQLAlchemy (SQLite default, Postgres ready)
- **Frontend**: Streamlit for UI
- **LLMs**: Ollama (local Qwen) + Remote APIs (DeepSeek, Kimi)
- **Orchestration**: Make for build automation, Docker Compose for Redis

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
