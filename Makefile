.PHONY: help setup check-deps install-ollama install-poetry install-deps pull-qwen download-embeddings test test-unit test-integration test-smoke run start-redis start-api start-celery stop clean example

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
	@poetry run celery -A workers.celery_app worker --loglevel=info > $(CELERY_LOG) 2>&1 & echo $$! > .celery.pid
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

example: ## Run an example SUV tracking job with VW brand
	@echo "$(YELLOW)Running example SUV tracking job...$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 1: Cleaning up existing 'SUV Cars' jobs and vertical...$(NC)"
	@DELETE_JOBS_RESPONSE=$$(curl -s -X DELETE "http://localhost:$(API_PORT)/api/v1/tracking/jobs?vertical_name=SUV%20Cars"); \
	DELETED_COUNT=$$(echo "$$DELETE_JOBS_RESPONSE" | jq -r '.deleted_count // 0' 2>/dev/null || echo "0"); \
	if [ "$$DELETED_COUNT" -gt 0 ]; then \
		echo "$(GREEN)✓ Deleted $$DELETED_COUNT existing job(s)$(NC)"; \
		VERTICAL_IDS=$$(echo "$$DELETE_JOBS_RESPONSE" | jq -r '.vertical_ids[]?' 2>/dev/null); \
		for VID in $$VERTICAL_IDS; do \
			DELETE_V_RESPONSE=$$(curl -s -X DELETE http://localhost:$(API_PORT)/api/v1/verticals/$$VID); \
			if echo "$$DELETE_V_RESPONSE" | jq -e '.deleted' > /dev/null 2>&1; then \
				echo "$(GREEN)✓ Deleted vertical (ID: $$VID)$(NC)"; \
			else \
				echo "$(YELLOW)  Could not delete vertical $$VID (may have other data)$(NC)"; \
			fi; \
		done; \
	else \
		echo "$(GREEN)✓ No existing jobs found$(NC)"; \
	fi
	@echo ""
	@echo "$(YELLOW)Step 2: Creating new tracking job for 'SUV Cars' with VW brand...$(NC)"
	@RESPONSE=$$(curl -s -w "\n%{http_code}" -X POST http://localhost:$(API_PORT)/api/v1/tracking/jobs \
		-H "Content-Type: application/json" \
		-d @examples/suv_example.json); \
	HTTP_CODE=$$(echo "$$RESPONSE" | tail -n1); \
	BODY=$$(echo "$$RESPONSE" | sed '$$d'); \
	if [ "$$HTTP_CODE" = "201" ]; then \
		echo "$$BODY" | jq .; \
		echo ""; \
		echo "$(GREEN)✓ Example tracking job created!$(NC)"; \
	else \
		echo "$(RED)✗ Failed to create tracking job (HTTP $$HTTP_CODE)$(NC)"; \
		echo "$$BODY"; \
		exit 1; \
	fi
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  View runs:    curl http://localhost:$(API_PORT)/api/v1/tracking/runs | jq"
	@echo "  Check status: curl http://localhost:$(API_PORT)/api/v1/tracking/runs/1 | jq"
	@echo "  View in UI:   http://localhost:$(STREAMLIT_PORT)"
	@echo ""

dev: ## Start services in development mode (with auto-reload)
	@echo "$(YELLOW)Starting development environment...$(NC)"
	@$(MAKE) start-redis
	@$(MAKE) start-ollama
	@echo ""
	@echo "$(GREEN)Starting FastAPI with auto-reload...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	@echo ""
	@poetry run uvicorn api.app:app --reload --host 0.0.0.0 --port $(API_PORT)
