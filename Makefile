.PHONY: help setup check-deps install-ollama install-poetry install-deps pull-qwen test test-unit test-integration test-smoke run start-redis start-api start-celery stop clean

# Default target
.DEFAULT_GOAL := help

# Variables
OLLAMA_MODEL := qwen2.5:7b
PYTHON_VERSION := 3.11
REDIS_PORT := 6379
API_PORT := 8000
CELERY_LOG := celery.log
API_LOG := api.log

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
	@echo "$(GREEN)✓ Python dependencies installed$(NC)"

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
	@docker-compose up -d redis
	@echo "$(GREEN)✓ Redis started$(NC)"

stop-redis: ## Stop Redis
	@echo "$(YELLOW)Stopping Redis...$(NC)"
	@docker-compose down
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

run: check-deps ## Start all services (Redis, Ollama, API, Celery)
	@echo "$(GREEN)Starting DragonLens services...$(NC)"
	@echo ""
	@$(MAKE) start-redis
	@$(MAKE) start-ollama
	@$(MAKE) start-api
	@$(MAKE) start-celery
	@echo ""
	@echo "$(GREEN)✓ All services started!$(NC)"
	@echo ""
	@echo "$(YELLOW)Services running:$(NC)"
	@echo "  FastAPI:  http://localhost:$(API_PORT)"
	@echo "  API Docs: http://localhost:$(API_PORT)/docs"
	@echo "  Redis:    localhost:$(REDIS_PORT)"
	@echo ""
	@echo "$(YELLOW)Logs:$(NC)"
	@echo "  API:    tail -f $(API_LOG)"
	@echo "  Celery: tail -f $(CELERY_LOG)"
	@echo ""
	@echo "$(YELLOW)To stop:$(NC) make stop"
	@echo ""

stop: ## Stop all services
	@echo "$(YELLOW)Stopping all services...$(NC)"
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
	@rm -f $(API_LOG) $(CELERY_LOG)
	@rm -f .api.pid .celery.pid
	@rm -rf .pytest_cache
	@rm -rf htmlcov
	@rm -rf .coverage
	@rm -rf **/__pycache__
	@rm -f dragonlens.db
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

status: ## Show status of all services
	@echo "$(YELLOW)Service Status:$(NC)"
	@echo ""
	@echo -n "Redis:    "
	@if docker-compose ps | grep -q "redis.*Up"; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "Ollama:   "
	@if pgrep -x "ollama" > /dev/null; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "FastAPI:  "
	@if [ -f .api.pid ] && kill -0 $$(cat .api.pid) 2>/dev/null; then \
		echo "$(GREEN)Running$(NC) (http://localhost:$(API_PORT))"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi
	@echo -n "Celery:   "
	@if [ -f .celery.pid ] && kill -0 $$(cat .celery.pid) 2>/dev/null; then \
		echo "$(GREEN)Running$(NC)"; \
	else \
		echo "$(RED)Stopped$(NC)"; \
	fi

logs: ## Tail all logs
	@echo "$(YELLOW)Tailing logs (Ctrl+C to stop)...$(NC)"
	@tail -f $(API_LOG) $(CELERY_LOG)

dev: ## Start services in development mode (with auto-reload)
	@echo "$(YELLOW)Starting development environment...$(NC)"
	@$(MAKE) start-redis
	@$(MAKE) start-ollama
	@echo ""
	@echo "$(GREEN)Starting FastAPI with auto-reload...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	@echo ""
	@poetry run uvicorn api.app:app --reload --host 0.0.0.0 --port $(API_PORT)
