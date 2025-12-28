.PHONY: help setup check-deps install-ollama install-poetry install-deps pull-qwen download-embeddings test test-unit test-integration test-smoke run start-redis start-api start-celery stop clean clear example example-all-mini example-all-mini-qwen example-all-mini-deepseek example-all-mini-kimi wikidata wikidata-status wikidata-clear wikidata-industry wikidata-search

# Default target
.DEFAULT_GOAL := help

# Variables
OLLAMA_MODEL := qwen2.5:7b
PYTHON_VERSION := 3.11
REDIS_PORT := 6379
API_PORT := 8000
STREAMLIT_PORT := 8501
CELERY_LOG := celery.log
API_LOG := api.log
STREAMLIT_LOG := streamlit.log

# Detect Docker Compose command (docker compose vs docker-compose)
DOCKER_COMPOSE := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; elif command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; fi)

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)DragonLens - Available Make Targets$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

check-deps: ## Check if all dependencies are installed
	@echo "$(YELLOW)Checking dependencies...$(NC)"
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)Error: Docker is not installed. Please install Docker first.$(NC)"; exit 1; }
	@echo "$(GREEN)✓ Docker found$(NC)"
	@if ! (docker compose version >/dev/null 2>&1 || docker-compose --version >/dev/null 2>&1); then \
		echo "$(RED)Error: Docker Compose is not installed.$(NC)"; \
		echo "$(YELLOW)Install it with:$(NC)"; \
		echo "  brew install docker-compose"; \
		echo "  OR"; \
		echo "  pip install docker-compose"; \
		exit 1; \
	fi
	@echo "$(GREEN)✓ Docker Compose found$(NC)"
	@command -v poetry >/dev/null 2>&1 || { echo "$(RED)Error: Poetry is not installed. Run 'make install-poetry' first.$(NC)"; exit 1; }
	@echo "$(GREEN)✓ Poetry found$(NC)"
	@command -v ollama >/dev/null 2>&1 || { echo "$(RED)Error: Ollama is not installed. Run 'make install-ollama' first.$(NC)"; exit 1; }
	@echo "$(GREEN)✓ Ollama found$(NC)"
	@echo "$(GREEN)All dependencies are installed!$(NC)"

install-poetry: ## Install Poetry if not already installed
	@command -v poetry >/dev/null 2>&1 && { echo "$(GREEN)✓ Poetry is already installed$(NC)"; exit 0; } || true
	@echo "$(YELLOW)Installing Poetry...$(NC)"
	@curl -sSL https://install.python-poetry.org | python3 -
	@echo "$(GREEN)✓ Poetry installed successfully$(NC)"
	@echo "$(YELLOW)Please add Poetry to your PATH if not already done:$(NC)"
	@echo "  export PATH=\"\$$HOME/.local/bin:\$$PATH\""

install-ollama: ## Install Ollama if not already installed (macOS only)
	@command -v ollama >/dev/null 2>&1 && { echo "$(GREEN)✓ Ollama is already installed$(NC)"; exit 0; } || true
	@echo "$(YELLOW)Installing Ollama...$(NC)"
	@if [ "$$(uname)" = "Darwin" ]; then \
		if command -v brew >/dev/null 2>&1; then \
			brew install ollama; \
			echo "$(GREEN)✓ Ollama installed via Homebrew$(NC)"; \
		else \
			echo "$(RED)Error: Homebrew not found. Please install from https://ollama.ai$(NC)"; \
			exit 1; \
		fi \
	else \
		echo "$(RED)Error: Automatic Ollama installation only supported on macOS$(NC)"; \
		echo "Please install from: https://ollama.ai"; \
		exit 1; \
	fi

install-deps: check-deps ## Install Python dependencies with Poetry
	@echo "$(YELLOW)Installing Python dependencies...$(NC)"
	@poetry install
	@$(MAKE) download-embeddings
	@echo "$(GREEN)✓ Python dependencies installed$(NC)"

download-embeddings:
	@poetry run python -m scripts.prefetch_embedding_model

pull-qwen: ## Pull Qwen model for Ollama (if not already pulled)
	@echo "$(YELLOW)Checking if Qwen model is already pulled...$(NC)"
	@if ollama list | grep -q "$(OLLAMA_MODEL)"; then \
		echo "$(GREEN)✓ Qwen model $(OLLAMA_MODEL) is already available$(NC)"; \
	else \
		echo "$(YELLOW)Pulling Qwen model $(OLLAMA_MODEL)...$(NC)"; \
		ollama pull $(OLLAMA_MODEL); \
		echo "$(GREEN)✓ Qwen model pulled successfully$(NC)"; \
	fi

setup: ## Complete setup - Install all dependencies and models
	@echo "$(GREEN)Starting DragonLens setup...$(NC)"
	@echo ""
	@$(MAKE) install-poetry
	@$(MAKE) install-ollama
	@$(MAKE) install-deps
	@$(MAKE) pull-qwen
	@echo ""
	@echo "$(GREEN)✓ Setup complete!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Copy .env.example to .env and configure if needed"
	@echo "  2. Run 'make run' to start all services"
	@echo ""

# =============================================================================
# Wikidata Cache Management
# =============================================================================

wikidata: ## Load all predefined industries from Wikidata (runs once, cached locally)
	@echo "$(YELLOW)Loading Wikidata cache for all predefined industries...$(NC)"
	@echo "$(YELLOW)This may take several minutes due to rate limiting.$(NC)"
	@echo ""
	@poetry run python scripts/load_wikidata.py all
	@echo ""
	@echo "$(GREEN)✓ Wikidata cache loaded!$(NC)"
	@echo "$(YELLOW)Run 'make wikidata-status' to see cache statistics$(NC)"

wikidata-status: ## Show Wikidata cache status
	@poetry run python scripts/load_wikidata.py status

wikidata-clear: ## Clear Wikidata cache (separate from main database)
	@echo "$(YELLOW)Clearing Wikidata cache...$(NC)"
	@poetry run python scripts/load_wikidata.py clear --force
	@echo "$(GREEN)✓ Wikidata cache cleared$(NC)"

wikidata-industry: ## Load a specific predefined industry (usage: make wikidata-industry INDUSTRY=automotive)
	@if [ -z "$(INDUSTRY)" ]; then \
		echo "$(RED)Error: INDUSTRY not specified$(NC)"; \
		echo "$(YELLOW)Usage: make wikidata-industry INDUSTRY=<name>$(NC)"; \
		echo "$(YELLOW)Available industries: automotive, consumer_electronics, cosmetics, home_appliances, sportswear, food_beverage, luxury_goods$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Loading Wikidata cache for $(INDUSTRY)...$(NC)"
	@poetry run python scripts/load_wikidata.py predefined $(INDUSTRY)
	@echo "$(GREEN)✓ $(INDUSTRY) loaded!$(NC)"

wikidata-search: ## Search Wikidata for industries (usage: make wikidata-search QUERY=luxury)
	@if [ -z "$(QUERY)" ]; then \
		echo "$(RED)Error: QUERY not specified$(NC)"; \
		echo "$(YELLOW)Usage: make wikidata-search QUERY=<search_term>$(NC)"; \
		exit 1; \
	fi
	@poetry run python scripts/load_wikidata.py search "$(QUERY)"

# =============================================================================
# Services
# =============================================================================

start-redis: ## Start Redis using Docker Compose
	@echo "$(YELLOW)Starting Redis...$(NC)"
	@if [ ! -f docker-compose.yml ]; then \
		echo "$(RED)Error: docker-compose.yml not found$(NC)"; \
		exit 1; \
	fi
	@$(DOCKER_COMPOSE) up -d redis
	@echo "$(GREEN)✓ Redis started$(NC)"

stop-redis: ## Stop Redis
	@echo "$(YELLOW)Stopping Redis...$(NC)"
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Redis stopped$(NC)"

start-ollama: ## Start Ollama service (macOS with Homebrew)
	@echo "$(YELLOW)Starting Ollama service...$(NC)"
	@if pgrep -x "ollama" > /dev/null; then \
		echo "$(GREEN)✓ Ollama is already running$(NC)"; \
	else \
		if [ "$$(uname)" = "Darwin" ]; then \
			if command -v brew >/dev/null 2>&1; then \
				brew services start ollama || ollama serve > /dev/null 2>&1 & \
				sleep 2; \
				echo "$(GREEN)✓ Ollama service started$(NC)"; \
			else \
				ollama serve > /dev/null 2>&1 & \
				sleep 2; \
				echo "$(GREEN)✓ Ollama service started$(NC)"; \
			fi \
		else \
			ollama serve > /dev/null 2>&1 & \
			sleep 2; \
			echo "$(GREEN)✓ Ollama service started$(NC)"; \
		fi \
	fi

start-api: check-deps ## Start FastAPI server
	@echo "$(YELLOW)Starting FastAPI server...$(NC)"
	@poetry run uvicorn api.app:app --host 0.0.0.0 --port $(API_PORT) > $(API_LOG) 2>&1 & echo $$! > .api.pid
	@sleep 2
	@if [ -f .api.pid ] && kill -0 $$(cat .api.pid) 2>/dev/null; then \
		echo "$(GREEN)✓ FastAPI server started on http://localhost:$(API_PORT)$(NC)"; \
		echo "  Logs: tail -f $(API_LOG)"; \
	else \
		echo "$(RED)✗ Failed to start FastAPI server$(NC)"; \
		cat $(API_LOG); \
		exit 1; \
	fi

start-celery: check-deps start-redis ## Start Celery worker
	@echo "$(YELLOW)Starting Celery worker...$(NC)"
	@poetry run celery -A workers.celery_app worker --loglevel=info --pool=solo > $(CELERY_LOG) 2>&1 & echo $$! > .celery.pid
	@sleep 2
	@if [ -f .celery.pid ] && kill -0 $$(cat .celery.pid) 2>/dev/null; then \
		echo "$(GREEN)✓ Celery worker started$(NC)"; \
		echo "  Logs: tail -f $(CELERY_LOG)"; \
	else \
		echo "$(RED)✗ Failed to start Celery worker$(NC)"; \
		cat $(CELERY_LOG); \
		exit 1; \
	fi

start-streamlit: check-deps ## Start Streamlit UI
	@echo "$(YELLOW)Starting Streamlit UI...$(NC)"
	@echo "$(YELLOW)Checking port $(STREAMLIT_PORT)...$(NC)"
	@if lsof -ti:$(STREAMLIT_PORT) > /dev/null 2>&1; then \
		echo "$(YELLOW)Port $(STREAMLIT_PORT) is in use, killing existing process...$(NC)"; \
		kill -9 $$(lsof -ti:$(STREAMLIT_PORT)) 2>/dev/null || true; \
		sleep 1; \
	fi
	@poetry run streamlit run src/ui/app.py --server.port $(STREAMLIT_PORT) --server.headless true > $(STREAMLIT_LOG) 2>&1 & echo $$! > .streamlit.pid
	@sleep 3
	@if [ -f .streamlit.pid ] && kill -0 $$(cat .streamlit.pid) 2>/dev/null; then \
		echo "$(GREEN)✓ Streamlit UI started on http://localhost:$(STREAMLIT_PORT)$(NC)"; \
		echo "  Logs: tail -f $(STREAMLIT_LOG)"; \
	else \
		echo "$(RED)✗ Failed to start Streamlit UI$(NC)"; \
		cat $(STREAMLIT_LOG); \
		exit 1; \
	fi

run: check-deps ## Start all services (Redis, Ollama, API, Celery, Streamlit)
	@echo "$(GREEN)Starting DragonLens services...$(NC)"
	@echo ""
	@$(MAKE) start-redis
	@$(MAKE) start-ollama
	@$(MAKE) start-api
	@$(MAKE) start-celery
	@$(MAKE) start-streamlit
	@echo ""
	@echo "$(GREEN)✓ All services started!$(NC)"
	@echo ""
	@echo "$(YELLOW)Services running:$(NC)"
	@echo "  Streamlit UI: http://localhost:$(STREAMLIT_PORT) $(GREEN)← Open this in your browser!$(NC)"
	@echo "  FastAPI:      http://localhost:$(API_PORT)"
	@echo "  API Docs:     http://localhost:$(API_PORT)/docs"
	@echo "  Redis:        localhost:$(REDIS_PORT)"
	@echo ""
	@echo "$(YELLOW)View logs:$(NC)"
	@echo "  Live monitor:  make watch           $(GREEN)# Watch status + recent logs$(NC)"
	@echo "  All logs:      make logs            $(GREEN)# Tail all service logs$(NC)"
	@echo "  Streamlit:     make logs-streamlit  $(GREEN)# Tail Streamlit logs$(NC)"
	@echo "  API only:      make logs-api        $(GREEN)# Tail FastAPI logs$(NC)"
	@echo "  Celery only:   make logs-celery     $(GREEN)# Tail Celery logs$(NC)"
	@echo "  Redis only:    make logs-redis      $(GREEN)# Tail Redis logs$(NC)"
	@echo ""
	@echo "$(YELLOW)Other commands:$(NC)"
	@echo "  Check status: make status       $(GREEN)# Check service status$(NC)"
	@echo "  Stop all:     make stop         $(GREEN)# Stop all services$(NC)"
	@echo ""

stop: ## Stop all services
	@echo "$(YELLOW)Stopping all services...$(NC)"
	@if [ -f .streamlit.pid ]; then \
		kill $$(cat .streamlit.pid) 2>/dev/null || true; \
		rm .streamlit.pid; \
		echo "$(GREEN)✓ Streamlit stopped$(NC)"; \
	fi
	@if [ -f .api.pid ]; then \
		kill $$(cat .api.pid) 2>/dev/null || true; \
		rm .api.pid; \
		echo "$(GREEN)✓ FastAPI stopped$(NC)"; \
	fi
	@if [ -f .celery.pid ]; then \
		kill $$(cat .celery.pid) 2>/dev/null || true; \
		rm .celery.pid; \
		echo "$(GREEN)✓ Celery stopped$(NC)"; \
	fi
	@$(MAKE) stop-redis
	@echo "$(GREEN)✓ All services stopped$(NC)"

test: check-deps ## Run all tests (unit + integration + smoke)
	@echo "$(YELLOW)Running all tests...$(NC)"
	@poetry run pytest tests/ -v
	@echo "$(GREEN)✓ All tests passed!$(NC)"

test-unit: check-deps ## Run unit tests only
	@echo "$(YELLOW)Running unit tests...$(NC)"
	@poetry run pytest tests/unit/ -v

test-integration: check-deps ## Run integration tests only
	@echo "$(YELLOW)Running integration tests...$(NC)"
	@poetry run pytest tests/integration/ -v

test-smoke: check-deps ## Run smoke tests only
	@echo "$(YELLOW)Running smoke tests...$(NC)"
	@poetry run pytest tests/smoke/ -v -s

test-coverage: check-deps ## Run tests with coverage report
	@echo "$(YELLOW)Running tests with coverage...$(NC)"
	@poetry run pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated$(NC)"
	@echo "  HTML report: open htmlcov/index.html"

clean: ## Clean up temporary files and logs
	@echo "$(YELLOW)Cleaning up...$(NC)"
	@rm -f $(API_LOG) $(CELERY_LOG) $(STREAMLIT_LOG)
	@rm -f .api.pid .celery.pid .streamlit.pid
	@rm -rf .pytest_cache
	@rm -rf htmlcov
	@rm -rf .coverage
	@rm -rf **/__pycache__
	@rm -f dragonlens.db
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clear: ## Full reset: kill all workers, flush Redis, clear database data (keep prompt results), clear caches
	@echo "$(YELLOW)Performing full system reset...$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 1: Killing ALL Celery processes...$(NC)"
	@pkill -9 -f "celery" 2>/dev/null || true
	@pkill -9 -f "workers.celery_app" 2>/dev/null || true
	@pkill -9 -f "billiard" 2>/dev/null || true
	@pkill -9 -f "ForkPoolWorker" 2>/dev/null || true
	@rm -f .celery.pid
	@sleep 1
	@REMAINING=$$(pgrep -f "celery|billiard" 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$REMAINING" -gt 0 ]; then \
		echo "$(YELLOW)  Killing $$REMAINING remaining worker(s)...$(NC)"; \
		pkill -9 -f "celery|billiard" 2>/dev/null || true; \
		sleep 1; \
	fi
	@echo "$(GREEN)✓ Celery processes killed$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 2: Killing API and Streamlit...$(NC)"
	@if [ -f .api.pid ]; then kill -9 $$(cat .api.pid) 2>/dev/null || true; rm -f .api.pid; fi
	@if [ -f .streamlit.pid ]; then kill -9 $$(cat .streamlit.pid) 2>/dev/null || true; rm -f .streamlit.pid; fi
	@echo "$(GREEN)✓ API and Streamlit stopped$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 3: Flushing Redis (clearing all queued tasks)...$(NC)"
	@docker exec $$(docker ps -q -f name=redis) redis-cli FLUSHALL 2>/dev/null || redis-cli FLUSHALL 2>/dev/null || echo "$(YELLOW)  Redis not running or not accessible$(NC)"
	@echo "$(GREEN)✓ Redis flushed$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 4: Clearing database data (keeping prompt results)...$(NC)"
	@echo "$(YELLOW)  By default, keeping prompt results (LLM answers) to avoid re-running expensive LLM calls$(NC)"
	@echo "$(YELLOW)  Use 'make clear-all' to delete everything including prompt results$(NC)"
	@poetry run python scripts/clear_data.py
	@echo "$(GREEN)✓ Database data cleared (prompt results preserved)$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 5: Clearing Python caches...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -f $(API_LOG) $(CELERY_LOG) $(STREAMLIT_LOG)
	@echo "$(GREEN)✓ Caches cleared$(NC)"
	@echo ""
	@echo "$(GREEN)✓ Full reset complete!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Run 'make run' to start all services fresh"
	@echo "  2. Run 'make example' to create a test job"
	@echo ""

clear-all: ## Clear ALL data including prompt results (LLM answers)
	@echo "$(YELLOW)Performing complete data reset (including prompt results)...$(NC)"
	@echo ""
	@echo "$(RED)WARNING: This will delete ALL data including LLM answers which are expensive to regenerate!$(NC)"
	@echo ""
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" != "yes" ]; then \
		echo "$(YELLOW)Operation cancelled.$(NC)"; \
		exit 0; \
	fi
	@echo ""
	@echo "$(YELLOW)Step 1: Killing ALL Celery processes...$(NC)"
	@pkill -9 -f "celery" 2>/dev/null || true
	@pkill -9 -f "workers.celery_app" 2>/dev/null || true
	@pkill -9 -f "billiard" 2>/dev/null || true
	@pkill -9 -f "ForkPoolWorker" 2>/dev/null || true
	@rm -f .celery.pid
	@sleep 1
	@REMAINING=$$(pgrep -f "celery|billiard" 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$REMAINING" -gt 0 ]; then \
		echo "$(YELLOW)  Killing $$REMAINING remaining worker(s)...$(NC)"; \
		pkill -9 -f "celery|billiard" 2>/dev/null || true; \
		sleep 1; \
	fi
	@echo "$(GREEN)✓ Celery processes killed$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 2: Killing API and Streamlit...$(NC)"
	@if [ -f .api.pid ]; then kill -9 $$(cat .api.pid) 2>/dev/null || true; rm -f .api.pid; fi
	@if [ -f .streamlit.pid ]; then kill -9 $$(cat .streamlit.pid) 2>/dev/null || true; rm -f .streamlit.pid; fi
	@echo "$(GREEN)✓ API and Streamlit stopped$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 3: Flushing Redis (clearing all queued tasks)...$(NC)"
	@docker exec $$(docker ps -q -f name=redis) redis-cli FLUSHALL 2>/dev/null || redis-cli FLUSHALL 2>/dev/null || echo "$(YELLOW)  Redis not running or not accessible$(NC)"
	@echo "$(GREEN)✓ Redis flushed$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 4: Clearing ALL database data including prompt results...$(NC)"
	@poetry run python scripts/clear_data.py --clear-prompts-results --yes
	@echo "$(GREEN)✓ Database data cleared (including prompt results)$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 5: Clearing Python caches...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -f $(API_LOG) $(CELERY_LOG) $(STREAMLIT_LOG)
	@echo "$(GREEN)✓ Caches cleared$(NC)"
	@echo ""
	@echo "$(GREEN)✓ Complete reset finished!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Run 'make run' to start all services fresh"
	@echo "  2. Run 'make example' to create a test job"
	@echo ""

status: ## Show status of all services
	@echo "$(YELLOW)Service Status:$(NC)"
	@echo ""
	@echo -n "Redis:     "
	@if $(DOCKER_COMPOSE) ps 2>/dev/null | grep -q "redis.*Up"; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "Ollama:    "
	@if pgrep -x "ollama" > /dev/null; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "FastAPI:   "
	@if [ -f .api.pid ] && kill -0 $$(cat .api.pid) 2>/dev/null; then \
		echo "$(GREEN)Running$(NC) (http://localhost:$(API_PORT))"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "Celery:    "
	@if [ -f .celery.pid ] && kill -0 $$(cat .celery.pid) 2>/dev/null; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "Streamlit: "
	@if [ -f .streamlit.pid ] && kill -0 $$(cat .streamlit.pid) 2>/dev/null; then \
		echo "$(GREEN)Running$(NC) (http://localhost:$(STREAMLIT_PORT))"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi

logs: ## Tail all logs (Streamlit, API, Celery, Redis)
	@echo "$(YELLOW)Tailing all logs (Ctrl+C to stop)...$(NC)"
	@echo "$(GREEN)Streamlit logs:$(NC) $(STREAMLIT_LOG)"
	@echo "$(GREEN)API logs:$(NC) $(API_LOG)"
	@echo "$(GREEN)Celery logs:$(NC) $(CELERY_LOG)"
	@echo "$(GREEN)Redis logs:$(NC) docker compose logs redis"
	@echo ""
	@($(DOCKER_COMPOSE) logs -f redis 2>/dev/null & tail -f $(STREAMLIT_LOG) $(API_LOG) $(CELERY_LOG) 2>/dev/null) || tail -f $(STREAMLIT_LOG) $(API_LOG) $(CELERY_LOG) 2>/dev/null

logs-streamlit: ## Tail Streamlit logs only
	@echo "$(YELLOW)Tailing Streamlit logs (Ctrl+C to stop)...$(NC)"
	@tail -f $(STREAMLIT_LOG)

logs-api: ## Tail FastAPI logs only
	@echo "$(YELLOW)Tailing FastAPI logs (Ctrl+C to stop)...$(NC)"
	@tail -f $(API_LOG)

logs-celery: ## Tail Celery logs only
	@echo "$(YELLOW)Tailing Celery logs (Ctrl+C to stop)...$(NC)"
	@tail -f $(CELERY_LOG)

logs-redis: ## Tail Redis logs only
	@echo "$(YELLOW)Tailing Redis logs (Ctrl+C to stop)...$(NC)"
	@$(DOCKER_COMPOSE) logs -f redis

watch: ## Watch service status and recent logs (refreshes every 2s)
	@echo "$(YELLOW)Watching DragonLens services (Ctrl+C to stop)...$(NC)"
	@echo ""
	@while true; do \
		clear; \
		echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"; \
		echo "$(GREEN)         DragonLens - Live Service Monitor$(NC)"; \
		echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"; \
		echo ""; \
		$(MAKE) --no-print-directory status; \
		echo ""; \
		echo "$(YELLOW)Recent Streamlit logs (last 3 lines):$(NC)"; \
		tail -n 3 $(STREAMLIT_LOG) 2>/dev/null || echo "  $(RED)No Streamlit logs yet$(NC)"; \
		echo ""; \
		echo "$(YELLOW)Recent API logs (last 3 lines):$(NC)"; \
		tail -n 3 $(API_LOG) 2>/dev/null || echo "  $(RED)No API logs yet$(NC)"; \
		echo ""; \
		echo "$(YELLOW)Recent Celery logs (last 3 lines):$(NC)"; \
		tail -n 3 $(CELERY_LOG) 2>/dev/null || echo "  $(RED)No Celery logs yet$(NC)"; \
		echo ""; \
		echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"; \
		echo "$(YELLOW)View logs: make logs-streamlit | make logs-api | make logs-celery$(NC)"; \
		echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"; \
		sleep 2; \
	done

example: ## Run an example SUV tracking job with VW brand (reuses prompt results by default)
	@echo "$(YELLOW)Running example SUV tracking job...$(NC)"
	@echo ""
	@echo "$(YELLOW)By default, reuses existing prompt results to avoid expensive LLM calls$(NC)"
	@echo "$(YELLOW)Use 'make example-fresh' to run from scratch$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=qwen

example-fresh: ## Run example from scratch (delete existing data, don't reuse prompt results)
	@echo "$(YELLOW)Running example SUV tracking job from scratch...$(NC)"
	@echo ""
	@echo "$(RED)WARNING: This will delete existing 'SUV Cars' data and make new LLM calls$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --no-reuse-prompt-results --provider=qwen

example-deepseek-chat: ## Run example with DeepSeek Chat model
	@echo "$(YELLOW)Running example with DeepSeek Chat model...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-chat

example-deepseek-reasoner: ## Run example with DeepSeek Reasoner model
	@echo "$(YELLOW)Running example with DeepSeek Reasoner model...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-reasoner

example-kimi-8k: ## Run example with Kimi 8K model
	@echo "$(YELLOW)Running example with Kimi 8K model...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-8k

example-kimi-32k: ## Run example with Kimi 32K model
	@echo "$(YELLOW)Running example with Kimi 32K model...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-32k

example-kimi-128k: ## Run example with Kimi 128K model
	@echo "$(YELLOW)Running example with Kimi 128K model...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-128k

example-all: ## Run example with all models (qwen, deepseek-chat, deepseek-reasoner, kimi-8k, kimi-32k, kimi-128k)
	@echo "$(YELLOW)Running example with all models...$(NC)"
	@echo ""
	@echo "$(YELLOW)1. Running with Qwen...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=qwen
	@echo ""
	@echo "$(YELLOW)2. Running with DeepSeek Chat...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-chat
	@echo ""
	@echo "$(YELLOW)3. Running with DeepSeek Reasoner...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-reasoner
	@echo ""
	@echo "$(YELLOW)4. Running with Kimi 8K...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-8k
	@echo ""
	@echo "$(YELLOW)5. Running with Kimi 32K...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-32k
	@echo ""
	@echo "$(YELLOW)6. Running with Kimi 128K...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-128k
	@echo ""
	@echo "$(GREEN)✓ All 6 models completed!$(NC)"
	@echo ""
	@echo "$(YELLOW)View results:$(NC)"
	@echo "  curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"
	@echo "  http://localhost:$(STREAMLIT_PORT)"

example-all-mini: ## Smoke test: Run mini example (1 prompt) with 3 models (qwen, deepseek-chat, kimi-8k)
	@echo "$(YELLOW)Running mini example smoke test (1 prompt, 3 models)...$(NC)"
	@echo ""
	@echo "$(YELLOW)This is a quick smoke test to verify the pipeline works correctly.$(NC)"
	@echo "$(YELLOW)Each model should process exactly 1 prompt.$(NC)"
	@echo ""
	@echo "$(YELLOW)1/3 Running with Qwen...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=qwen --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(YELLOW)2/3 Running with DeepSeek Chat...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-chat --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(YELLOW)3/3 Running with Kimi 8K...$(NC)"
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-8k --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(GREEN)✓ Mini smoke test completed (3 models, 1 prompt each)!$(NC)"
	@echo ""
	@echo "$(YELLOW)Verify results:$(NC)"
	@echo "  curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"
	@echo ""
	@echo "$(YELLOW)Expected: Each run should have processed exactly 1 prompt$(NC)"

example-all-mini-qwen: ## Smoke test: Run mini example with Qwen only
	@echo "$(YELLOW)Running mini example with Qwen (1 prompt)...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=qwen --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(GREEN)✓ Qwen mini test completed!$(NC)"
	@echo ""
	@echo "$(YELLOW)Verify results:$(NC)"
	@echo "  curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"

example-all-mini-deepseek: ## Smoke test: Run mini example with DeepSeek Chat only
	@echo "$(YELLOW)Running mini example with DeepSeek Chat (1 prompt)...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=deepseek-chat --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(GREEN)✓ DeepSeek Chat mini test completed!$(NC)"
	@echo ""
	@echo "$(YELLOW)Verify results:$(NC)"
	@echo "  curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"

example-all-mini-kimi: ## Smoke test: Run mini example with Kimi 8K only
	@echo "$(YELLOW)Running mini example with Kimi 8K (1 prompt)...$(NC)"
	@echo ""
	@poetry run python scripts/run_example_with_reuse.py --provider=kimi-8k --example-file=examples/suv_example_mini.json
	@echo ""
	@echo "$(GREEN)✓ Kimi 8K mini test completed!$(NC)"
	@echo ""
	@echo "$(YELLOW)Verify results:$(NC)"
	@echo "  curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"

dev: ## Start services in development mode (with auto-reload)
	@echo "$(YELLOW)Starting development environment...$(NC)"
	@$(MAKE) start-redis
	@$(MAKE) start-ollama
	@echo ""
	@echo "$(GREEN)Starting FastAPI with auto-reload...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	@echo ""
	@poetry run uvicorn api.app:app --reload --host 0.0.0.0 --port $(API_PORT)
